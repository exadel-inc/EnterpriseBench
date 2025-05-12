#!/usr/bin/env python3
"""
Run Java tests for a PR ticket
----------------------------------------
Base  ➜  Merge  ➜  (merge + neg-patch)  ➜  (merge + neg-patch + code-patch)

Only tests that are *green* on both base & merge influence the verdict on
negative / code patches (skip-file logic).

Every Maven run is logged to  mvn-logs/<TICKET>_<stage>_<timestamp>.log

By default this script runs the full flow (base+merge then patches).  
Pass --ai to skip the base+merge steps and re-use the skip-list
previously generated in skipped_tests/<TICKET>_skip-tests.txt.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, os, re, shutil, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path

# ──────────────────────── CLI ─────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("ticket", help="PR ticket ID")
parser.add_argument("patch", nargs="?", help="Optional code-patch diff")
parser.add_argument("--ai", action="store_true",
                    help="Skip base+merge, only run neg+code using saved skip-file")
args = parser.parse_args()

TICKET        = args.ticket
OPT_PATCH_STR = args.patch
AI_MODE   = args.ai

# ───────────────────── PATHS / CONSTS ─────────────────────────
ROOT       = Path(__file__).parent.resolve()
REPO       = ROOT / "edmb-backend"
PATCH_NEG  = ROOT / "patches_neg"  / f"{TICKET}_non_test.diff"
PATCH_POS  = ROOT / "patches_pos"
PR_STATE   = ROOT / "pr_states.csv"
LOG_DIR    = ROOT / "mvn-logs";     LOG_DIR.mkdir(exist_ok=True)
JVM_DIR    = ROOT / "jvm"
SKIP_DIR   = ROOT / "skipped_tests"; SKIP_DIR.mkdir(exist_ok=True)

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
    for p in JVM_DIR.glob(f"jdk-{major}*"):
        javac = p/"bin"/"javac"
        if not javac.exists():
            javac = next((c for c in p.rglob("bin/javac") if c.name=="javac"), javac)
        if javac.exists():
            return javac.parent.parent.resolve()
    raise FileNotFoundError(f"JDK {major} not found under {JVM_DIR}")

JAVA_MAJOR = highest_java()
JAVA_HOME  = jdk_home(JAVA_MAJOR)
print(f"ℹ️  Java {JAVA_MAJOR}  →  {JAVA_HOME}")

# ────────── helper functions ──────────────────────────────────
def resolve_patch(p: str|None) -> Path|None:
    if not p: return None
    q = Path(p)
    if q.is_absolute() and q.exists(): return q
    q = PATCH_POS / q.name
    return q if q.exists() else None
CODE_PATCH = resolve_patch(OPT_PATCH_STR)

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

def write_skip(b: set[tuple[str,str]]):
    lines = ["# auto-generated – union of red tests on base & merge"]
    lines += [f"{c}#{m}" for c,m in sorted(b)]
    (SKIP_DIR / f"{TICKET}_skip-tests.txt").write_text("\n".join(lines), encoding="utf-8")

def load_skip() -> set[tuple[str,str]]:
    path = SKIP_DIR / f"{TICKET}_skip-tests.txt"
    if not path.exists():
        sys.exit(f"❌  Skip file not found: {path}")
    out = set()
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"): continue
        c,m = ln.split("#",1)
        out.add((c,m))
    return out

def dtest() -> str|None:
    path = SKIP_DIR / f"{TICKET}_skip-tests.txt"
    if not path.exists(): return None
    pats = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]
    if not pats: return None
    return "-Dtest=" + ",".join(["*"] + [f"!{p}" for p in pats])

# ────────── Maven runner ──────────────────────────────────────
def run(stage: str) -> tuple[int, dict[str,int]]:
    clean_targets()
    cmd = [
        "mvn", "-q", "-B", "clean", "test",
        "-f", mvn_pom(),
        "-DfailIfNoTests=false",
        "-Dcheckstyle.skip=true"
    ]
    if (flt := dtest()):
        cmd.append(flt)
    env = os.environ.copy()
    env["JAVA_HOME"] = str(JAVA_HOME)
    env["PATH"]      = f"{JAVA_HOME/'bin'}{os.pathsep}{env['PATH']}"
    ts  = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log = LOG_DIR / f"{TICKET}_{stage}_{ts}.log"
    print(f"▶️ {stage}: JAVA_HOME={JAVA_HOME} PATH={JAVA_HOME/'bin'}:$PATH " + " ".join(cmd))
    res = subprocess.run(cmd, cwd=REPO, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    log.write_text(res.stdout)
    stats = surefire_stats()
    print(f"[{stage}] run:{stats['run']} fail:{stats['failures']} err:{stats['errors']} skip:{stats['skipped']} → {log.name}")
    return res.returncode, stats

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
