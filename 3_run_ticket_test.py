#!/usr/bin/env python3
"""
Run Java tests for a PR ticket
----------------------------------------
Base  ➜  Merge  ➜  (merge + neg-patch)  ➜  (merge + neg-patch + code-patch)

Only tests that are *green* on both base & merge influence the verdict on
negative / code patches (skip-list logic).
The skip list for each ticket is stored persistently in `pr_states.csv`
(column `skipped_tests`).

Every Maven run is logged to  mvn-logs/<TICKET>_<stage>_<timestamp>.log

By default this script runs the full flow (base → merge → patches).
Pass `--ai` to skip the base+merge steps and re‑use the skip list already
recorded in `pr_states.csv`.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, os, re, shutil, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path

csv.field_size_limit(sys.maxsize)

# ──────────────────────── CLI ─────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("ticket", help="PR ticket ID")
parser.add_argument("patch", nargs="?", help="Optional code-patch diff")
parser.add_argument("--ai", action="store_true",
                    help="Skip base+merge, only run neg+code using skip list from pr_states.csv")
parser.add_argument("--project-root", type=Path,
                    help="Root directory of the benchmark project (defaults to this script's folder)")
parser.add_argument("--java-major", type=int, metavar="N",
                    help="Force Java major version (e.g., 8, 17) instead of auto‑detect")
args = parser.parse_args()

TICKET        = args.ticket
PATCH_STR = args.patch
AI_MODE   = args.ai

# ───────────────────── PATHS / CONSTS ─────────────────────────
ROOT       = Path(args.project_root or Path(__file__).parent).expanduser().resolve()
REPO       = (ROOT / "project_repo").resolve()
PATCH_NEG  = ROOT / "patches_neg"  / f"{TICKET}_non_test.diff"
PR_STATE   = ROOT / "pr_states.csv"
LOG_DIR    = ROOT / "mvn-logs";     LOG_DIR.mkdir(exist_ok=True)
JVM_DIR    = ROOT / "jvm"

# ────────── Java detection ───────────────────────────────────
TAG_RGX = [
    re.compile(r"<maven\.compiler\.release>(\d+)"),
    re.compile(r"<maven\.compiler\.source>(\d+)"),
    re.compile(r"<java\.version>(\d+)")
]
def highest_java() -> str:
    vers = 11
    for pom in [REPO/"pom.xml", *REPO.rglob("*/pom.xml")]:
        try:
            txt = pom.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for r in TAG_RGX:
            for m in r.finditer(txt):
                vers = max(vers, int(m.group(1)))
    return str(vers)

def jdk_home(major: str) -> Path:
    for p in JVM_DIR.glob(f"*{major}*"):
        javac = p/"bin"/"javac"
        if not javac.exists():
            javac = next((c for c in p.rglob("bin/javac") if c.name=="javac"), javac)
        if javac.exists():
            return javac.parent.parent.resolve()
    raise FileNotFoundError(f"JDK {major} not found under {JVM_DIR}")

JAVA_MAJOR = str(args.java_major or highest_java())
JAVA_HOME  = jdk_home(JAVA_MAJOR)
print(f"ℹ️  Java {JAVA_MAJOR}  →  {JAVA_HOME}")

CODE_PATCH = ROOT / PATCH_STR

def read_commits(key: str) -> tuple[str, str]:
    with PR_STATE.open() as fh:
        for r in csv.DictReader(fh):
            if r["ticket"] == key:
                return r["before_commit"], r["merge_commit"]
    sys.exit(f"❌ ticket {key} not found in {PR_STATE}")

def git(*args):
    subprocess.run(["git", *args], cwd=REPO,
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def checkout(ref: str):
    git("reset", "--hard")
    git("clean", "-fd")
    git("checkout", ref)

def mvn_pom() -> str:
    for p in (REPO/"java"/"pom.xml", REPO/"pom.xml"):
        if p.is_file():
            return str(p)
    raise FileNotFoundError("pom.xml not found")

def clean_targets():
    for t in REPO.rglob("target"):
        shutil.rmtree(t, ignore_errors=True)

def surefire_stats() -> dict[str,int]:
    s = dict(run=0, failures=0, errors=0, skipped=0)
    for xml in REPO.rglob("target/surefire-reports/*.xml"):
        try:
            r = ET.parse(xml).getroot()
            for k,a in (("run","tests"),("failures","failures"),
                        ("errors","errors"),("skipped","skipped")):
                s[k] += int(r.attrib.get(a,0))
        except ET.ParseError:
            pass
    return s

def red_tests() -> set[tuple[str,str]]:
    bad = set()
    for xml in REPO.rglob("target/surefire-reports/*.xml"):
        try:
            root = ET.parse(xml).getroot()
            for tc in root.findall(".//testcase"):
                if tc.find("failure") is not None or tc.find("error") is not None:
                    c = tc.attrib["classname"].split('.')[-1]
                    m = tc.attrib["name"].split('{')[0].split('[')[0]
                    bad.add((c, m))
        except ET.ParseError:
            pass
    return bad

# ────────── skip‑list persistence ────────────────────────────
def write_skip(b: set[tuple[str, str]]):
    """
    Persist the union of red tests as a comma‑separated list in the
    `skipped_tests` column of pr_states.csv (one row per ticket).
    The column is created automatically if missing.
    """
    # read entire CSV
    rows: list[dict[str, str]] = []
    with PR_STATE.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        for r in reader:
            rows.append(r)

    # ensure the column exists
    if "skipped_tests" not in fieldnames:
        fieldnames.append("skipped_tests")

    # update the row for this ticket
    for r in rows:
        if r["ticket"] == TICKET:
            r["skipped_tests"] = ",".join(f"{c}#{m}" for c, m in sorted(b))
            break
    else:
        sys.exit(f"❌ ticket {TICKET} not found in {PR_STATE}")

    # write back
    with PR_STATE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def load_skip() -> set[tuple[str, str]]:
    """
    Return the skip list for *TICKET* from pr_states.csv.
    If the ticket is present but the field is empty or just a comment,
    we simply return an empty set instead of exiting with an error.
    """
    with PR_STATE.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["ticket"] != TICKET:
                continue

            # Allow both comma‑ and newline‑separated entries
            raw_field = (r.get("skipped_tests", "") or "")
            fragments = raw_field.replace("\n", ",").split(",")

            out: set[tuple[str, str]] = set()
            for frag in fragments:
                frag = frag.strip()
                # ignore empty fragments, comments, malformed bits
                if not frag or frag.startswith("#") or "#" not in frag:
                    continue
                c, m = frag.split("#", 1)
                out.add((c, m))
            return out          # may be an empty set

    sys.exit(f"❌ ticket {TICKET} not found in {PR_STATE}")

def dtest() -> str | None:
    """
    Build the -Dtest exclusion filter based on the skip list already
    recorded in pr_states.csv. Returns None if no skip list yet.
    """
    # Build the Maven -Dtest filter from the CSV skip list
    with PR_STATE.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["ticket"] != TICKET:
                continue

            raw_field = (r.get("skipped_tests", "") or "")
            fragments = [f.strip() for f in raw_field.replace("\n", ",").split(",") if f.strip()]

            # keep only well‑formed “Class#method” fragments that aren’t comments
            pats = [frag for frag in fragments if "#" in frag and not frag.startswith("#")]
            if not pats:
                return None
            return "-Dtest=" + ",".join(["*"] + [f"!{p}" for p in sorted(pats)])

    return None


# ────────── Maven runner ──────────────────────────────────────
def run(stage: str) -> tuple[int, dict[str, int]]:
    clean_targets()

    # 1) full install (compile + package) without running tests
    install_log = LOG_DIR / f"{TICKET}_{stage}_install_{dt.datetime.now():%Y%m%d_%H%M%S}.log"
    install_cmd = [
        "mvn", "-B", "clean", "install",
        "-DskipTests=true",
        "-Dcheckstyle.skip=true",
        "-f", mvn_pom(),
    ]
    env = os.environ.copy()
    env["JAVA_HOME"] = str(JAVA_HOME)
    env["PATH"]      = f"{JAVA_HOME/'bin'}{os.pathsep}{env['PATH']}"

    print(f"▶️ {stage} install: JAVA_HOME={JAVA_HOME} PATH={JAVA_HOME/'bin'}:$PATH " + " ".join(install_cmd))
    res_i = subprocess.run(install_cmd, cwd=REPO, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    install_log.write_text(res_i.stdout)
    if res_i.returncode != 0:
        print(f"[{stage} install] failed → {install_log.name}")
        # abort early if install fails
        return res_i.returncode, dict(run=0, failures=0, errors=0, skipped=0)
    print(f"[{stage} install] succeeded → {install_log.name}")

    # 2) now run tests (using any skip‐file filter)
    test_log = LOG_DIR / f"{TICKET}_{stage}_test_{dt.datetime.now():%Y%m%d_%H%M%S}.log"
    test_cmd = [
        "mvn", "-B", "test",
        "-DfailIfNoTests=false",
        "-Dcheckstyle.skip=true",
        "-f", mvn_pom(),
    ]
    if (flt := dtest()):
        test_cmd.append(flt)

    print(f"▶️ {stage} test: JAVA_HOME={JAVA_HOME} PATH={JAVA_HOME/'bin'}:$PATH " + " ".join(test_cmd))
    res_t = subprocess.run(test_cmd, cwd=REPO, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    test_log.write_text(res_t.stdout)

    stats = surefire_stats()
    print(f"[{stage}] run:{stats['run']} fail:{stats['failures']} err:{stats['errors']} skip:{stats['skipped']} → {test_log.name}")
    return res_t.returncode, stats

def apply_patch(p: Path) -> bool:
    return subprocess.run(["git","apply","--ignore-whitespace", str(p)], cwd=REPO).returncode == 0

# ────────── Flow ───────────────────────────────────────────────
BASE, MERGE = read_commits(TICKET)

if not AI_MODE:
    checkout(BASE)
    base_rc, base_st = run("base")
    skip = red_tests()

    checkout(MERGE)
    merge_rc, merge_st = run("merge")
    skip |= red_tests()
    write_skip(skip)
else:
    skip = load_skip()
    print(f"ℹ️  Loaded {len(skip)} tests to skip for {TICKET}")

# patches always run on merge
checkout(MERGE)
neg_ok = apply_patch(PATCH_NEG)
neg_rc, neg_st = run("neg_patch")

code_ok = False
if neg_ok and CODE_PATCH and CODE_PATCH.exists():
    apply_patch(CODE_PATCH)
    code_ok = True
code_rc, code_st = run("code_patch")

# ────────── summary ───────────────────────────────────────────
print("\nSummary")
# base & merge
if AI_MODE:
    print(f"{'base':<5}: SKIP  run=0 fail=0 err=0 skip=0")
    print(f"{'merge':<5}: SKIP  run=0 fail=0 err=0 skip=0")
else:
    print(f"{'base':<5}: {'PASS' if base_rc==0 else 'FAIL'}  run={base_st['run']} fail={base_st['failures']} err={base_st['errors']} skip={base_st['skipped']}")
    print(f"{'merge':<5}: {'PASS' if merge_rc==0 else 'FAIL'}  run={merge_st['run']} fail={merge_st['failures']} err={merge_st['errors']} skip={merge_st['skipped']}")
# neg & code
print(f"{'neg':<5}: {'PASS' if neg_rc==0 else 'FAIL'}  run={neg_st['run']} fail={neg_st['failures']} err={neg_st['errors']} skip={neg_st['skipped']}")
print(f"{'code':<5}: {'PASS' if code_rc==0 else 'FAIL'}  run={code_st['run']} fail={code_st['failures']} err={code_st['errors']} skip={code_st['skipped']}")
print("patch applied → neg:", neg_ok, "code:", code_ok)

sys.exit(0)
