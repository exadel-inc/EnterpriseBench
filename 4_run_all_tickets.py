#!/usr/bin/env python3
"""
Run 3_run_ticket_test.py for every ticket found in *pr_states.csv*,
store one CSV per ticket and finally merge everything into *test_results.csv*.

Supports two modes:
  1) Default: process tickets from pr_states.csv (optionally bounded by --start/--end)
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

# ───────────────────────── settings ──────────────────────────
CSV_FILE     = "pr_states.csv"
DEFAULT_PATCHES_DIR  = Path("patches_pos")
SCRIPT       = "3_run_ticket_test.py"
RESULTS_DIR  = Path("results_csv")
LOGS_DIR     = RESULTS_DIR / "logs"
MERGED_CSV   = "test_results.csv"

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

# ─────────── run single ticket ───────────────────────────────
def run_ticket(ticket: str, patches_dir: Path, ai: bool) -> dict | None:
    patch_file = patches_dir / f"{ticket}_non_test.diff"
    if not patch_file.exists():
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
        if f.name == MERGED_CSV:
            continue
        for row in csv.DictReader(f.open()):
            rows.append(row)
            fields.update(row.keys())
    if rows:
        with open(MERGED_CSV, "w", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=sorted(fields))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\n📦  Merged results → {MERGED_CSV}")
    else:
        print("⚠️  No individual CSVs found – nothing merged.")

# ─────────────────────────── CLI entry-point ─────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--ai", action="store_true",
                      help="only retry tickets from filter-CSV where neg=FAIL & code=PASS")
    mode.add_argument("--start", type=int, help="process tickets ≥ this number")
    ap.add_argument("--end", type=int, help="process tickets ≤ this number")
    ap.add_argument("--filter-csv", type=Path,
                    help="(ai) CSV to read previous results from")
    ap.add_argument("--ai-patches-dir", type=Path,
                    help="(ai) directory of non_test.diff files (required with --ai)")
    args = ap.parse_args()

    # validate ai arguments
    if args.ai:
        if args.start is not None or args.end is not None:
            sys.exit("❌  --start/--end cannot be used with --ai")
        if not args.ai_patches_dir:
            sys.exit("❌  --ai-patches-dir is required when using --ai")
        if not args.filter_csv:
            sys.exit("❌  --filter-csv is required when using --ai")
        patches_dir = args.ai_patches_dir
    else:
        patches_dir = DEFAULT_PATCHES_DIR

    tickets: list[str] = []
    if args.ai:
        # read the filter-CSV and pick only neg==FAIL & code==PASS
        with open(args.filter_csv) as fh:
            for row in csv.DictReader(fh):
                if row.get("neg_status") == "FAIL" and row.get("code_status") == "PASS":
                    tickets.append(row["ticket"])
    else:
        # normal: read pr_states.csv within optional numeric bounds
        with open(CSV_FILE) as fh:
            for row in csv.DictReader(fh):
                t = row.get("ticket","").strip()
                if not t:
                    continue
                n = ticket_num(t)
                if args.start is not None and n < args.start:
                    continue
                if args.end   is not None and n > args.end:
                    continue
                tickets.append(t)

    for ticket in tickets:
        try:
            run_ticket(ticket, patches_dir, args.ai)
        except Exception as exc:
            print(f"⚠️  {ticket}: {exc}")

    merge_results()

if __name__ == "__main__":
    main()
