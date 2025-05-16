#!/usr/bin/env python3
"""
Run 3_run_ticket_test.py for every ticket found in *pr_states.csv*,
store one CSV per ticket and finally merge everything into *test_results.csv*.

Supports two modes:
  1) Default: process tickets from pr_states.csv
     and run each through 3_run_ticket_test.py.
  2) --ai: **requires** --ai-patches-dir, reads a previous results CSV
     (via --filter-csv), picks only those with neg_status FAIL and code_status PASS,
     then invokes 3_run_ticket_test.py --ai using the new patches dir.
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

csv.field_size_limit(sys.maxsize)

# ──────────────────────── CLI ─────────────────────────────────
parser = argparse.ArgumentParser()
mode = parser.add_mutually_exclusive_group()
parser.add_argument("--project-root", type=Path,
                    help="Root directory of the benchmark project (defaults to this script's folder)")
parser.add_argument("--java-major", type=int, metavar="N",
                    help="Pass through to ticket tests to force Java version (e.g., 8, 17)")
mode.add_argument("--ai", action="store_true",
                  help="run tests on tickets that use AI-generated patches")
parser.add_argument("--ai-patches-dir", type=Path,
                    help="(ai) directory of non_test.diff files (required with --ai)")
args = parser.parse_args()

PROJECT_ROOT = Path(args.project_root or Path(__file__).parent).expanduser().resolve()

# ───────────────────────── settings ──────────────────────────
CSV_FILE            = PROJECT_ROOT / "pr_states.csv"
DEFAULT_PATCHES_DIR = PROJECT_ROOT / "patches_pos"
SCRIPT              = "3_run_ticket_test.py"
RESULTS_DIR         = PROJECT_ROOT / "results"
LOGS_DIR            = RESULTS_DIR / "logs"
MERGED_CSV          = PROJECT_ROOT / "test_results.csv"

RESULTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ───────────────── regex patterns ────────────────────────────
RUN_LINE_RGX    = re.compile(
    r"\[(base|merge|neg_patch|code_patch)]\s+run:(\d+)"
    r"\s+fail:(\d+)\s+err:(\d+)\s+skip:(\d+)"
)
SUMMARY_RGX     = re.compile(r"^(base|merge|neg|code)\s*:\s*(PASS|FAIL)", re.M)
PATCH_LINE_RGX  = re.compile(r"patch applied →\s+neg:\s+(True|False)\s+code:\s+(True|False)")

# ──────────────── helper parsers ─────────────────────────────
def parse_run_lines(text: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for m in RUN_LINE_RGX.finditer(text):
        stage, run, fail, err, skip = m.groups()
        out[stage] = dict(tests=run, failures=fail, errors=err, skipped=skip)
    return out

def parse_summary(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in SUMMARY_RGX.finditer(text)}

def parse_patch_flags(text: str) -> tuple[str, str]:
    m = PATCH_LINE_RGX.search(text)
    if m:
        return m.group(1), m.group(2)
    return "", ""

def ticket_num(key: str) -> int:
    m = re.search(r"(\d+)", key)
    return int(m.group(1)) if m else -1

def find_patch_file(ticket: str, directory: Path) -> Path | None:
    """
    Locate a patch file for *ticket* inside *directory*.

    Search order:
      1. Any filename that contains the **full ticket key** (e.g. ``EAK-76``).
      2. Fallback: filenames that contain just the **numeric part** of the ticket
         (e.g. ``76``).
         This lets a patch like ``acme-inc__compreface_76.patch`` match ticket
         ``EAK-76`` while avoiding collisions with ``EAK-176``.

    Accepted extensions are ``.diff`` or ``.patch`` (case‑insensitive).
    If multiple matches exist, the first one in *sorted order* is chosen.
    Returns ``None`` when nothing matches.
    """
    patterns: list[str] = [f"*{ticket}*.diff", f"*{ticket}*.patch"]

    # Extract numeric part (first run of digits) and add fallback patterns
    m = re.search(r"(\d+)", ticket)
    if m:
        num = m.group(1)
        patterns += [f"*{num}*.diff", f"*{num}*.patch"]

    matches: list[Path] = []
    seen: set[Path] = set()
    for pat in patterns:
        for p in sorted(directory.glob(pat)):
            # Skip macOS resource‑fork files (AppleDouble)
            if p.name.startswith("._"):
                continue
            if p not in seen:
                matches.append(p)
                seen.add(p)

    if not matches:
        return None
    if len(matches) > 1:
        print(f"⚠️  {ticket}: multiple patches found, using {matches[0].name}")
    return matches[0]

# ─────────── run single ticket ───────────────────────────────
def run_ticket(ticket: str, patches_dir: Path, ai: bool) -> dict | None:
    patch_file = patches_dir / f"{ticket}_non_test.diff"
    if ai:
        patch_file = find_patch_file(ticket, patches_dir)

    if patch_file is None:
        print(f"❌  {ticket}: patch not found in {patches_dir}")
        return None

    if not ai:
        test_patch = patches_dir / f"{ticket}_test.diff"
        if not test_patch.exists() or test_patch.stat().st_size == 0:
            print(f"↷  {ticket}: test patch missing/empty – skipping")
            return None

    cmd = ["python3", SCRIPT]
    if ai:
        cmd.append("--ai")
    if args.java_major:
        cmd += ["--java-major", str(args.java_major)]
    cmd += ["--project-root", str(PROJECT_ROOT)]
    cmd += [ticket, str(patch_file)]

    print(f"▶️  {ticket} ({'ai' if ai else 'full'})")
    res = subprocess.run(cmd, capture_output=True, text=True)
    output = f"{res.stdout}\n{res.stderr}"
    (LOGS_DIR / f"{ticket}.txt").write_text(output, encoding="utf-8")

    run_stats    = parse_run_lines(output)
    summary      = parse_summary(output)
    neg_flag, code_flag = parse_patch_flags(output)

    def g(stage: str, field: str) -> str:
        return run_stats.get(stage, {}).get(field, "")

    row = {
        "ticket": ticket,
        # base
        "base_tests":   g("base",   "tests"),
        "base_fail":    g("base",   "failures"),
        "base_err":     g("base",   "errors"),
        "base_skip":    g("base",   "skipped"),
        "base_status":  summary.get("base", ""),
        # merge
        "merge_tests":  g("merge",  "tests"),
        "merge_fail":   g("merge",  "failures"),
        "merge_err":    g("merge",  "errors"),
        "merge_skip":   g("merge",  "skipped"),
        "merge_status": summary.get("merge", ""),
        # neg patch
        "neg_tests":    g("neg_patch",  "tests"),
        "neg_fail":     g("neg_patch",  "failures"),
        "neg_err":      g("neg_patch",  "errors"),
        "neg_skip":     g("neg_patch",  "skipped"),
        "neg_status":   summary.get("neg", ""),
        # code patch
        "code_tests":   g("code_patch", "tests"),
        "code_fail":    g("code_patch", "failures"),
        "code_err":     g("code_patch", "errors"),
        "code_skip":    g("code_patch", "skipped"),
        "code_status":  summary.get("code", ""),
        # patch flags
        "neg_applied":  neg_flag,
        "code_applied": code_flag,
    }

    with (RESULTS_DIR / f"{ticket}.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=row.keys())
        writer.writeheader()
        writer.writerow(row)

    print("   ✓ saved")
    return row

# ─────────── merge everything ────────────────────────────────
def merge_results() -> None:
    rows: list[dict] = []
    fields: set[str] = set()
    for f in RESULTS_DIR.glob("*.csv"):
        if f.name == MERGED_CSV.name:
            continue
        for row in csv.DictReader(f.open()):
            rows.append(row)
            fields.update(row.keys())
    if rows:
        def row_key(row: dict) -> int:
            # Use ticket_num for sorting, fallback to -1
            return ticket_num(row.get("ticket", ""))

        rows.sort(key=row_key, reverse=True)       # descending order
        with open(MERGED_CSV, "w", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=sorted(fields))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n📦  Merged results → {MERGED_CSV}")
    else:
        print("⚠️  No individual CSVs found – nothing merged.")

# ─────────────────────────── CLI entry-point ─────────────────────────────
def main() -> None:
    # validate ai arguments
    if args.ai:
        if not args.ai_patches_dir:
            sys.exit("❌  --ai-patches-dir is required when using --ai")
        patches_dir = Path(args.ai_patches_dir)
        # If the user passed a *relative* path, resolve it under PROJECT_ROOT
        if not patches_dir.is_absolute():
            patches_dir = PROJECT_ROOT / patches_dir
    else:
        patches_dir = DEFAULT_PATCHES_DIR

    # ────────── collect tickets ────────────────────────────────
    tickets: list[str] = []
    source_csv = CSV_FILE
    with open(source_csv) as fh:
        for row in csv.DictReader(fh):
            t = row.get("ticket", "").strip()
            if t:
                tickets.append(t)

    for ticket in tickets:
        try:
            run_ticket(ticket, patches_dir, args.ai)
        except Exception as exc:
            print(f"⚠️  {ticket}: {exc}")

    merge_results()

if __name__ == "__main__":
    main()
