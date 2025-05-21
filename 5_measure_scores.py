#!/usr/bin/env python3
"""
rate_pass_scores.py <folder_path>

For each *.csv in <folder_path>, compute the PASS-and-APPLIED rate and
print the results *sorted from highest to lowest*, with the percentages
aligned in a tidy column:

    filename <spaces>  87.2%
"""

import sys
from pathlib import Path
import pandas as pd

CODE_STATUS  = "code_status"
CODE_APPLIED = "code_applied"
NEG_APPLIED = "neg_applied"


def pass_and_applied_rate(csv_path: Path) -> float | None:
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        print(f"Skipping {csv_path.name}: could not read ({exc})", file=sys.stderr)
        return None

    missing = [c for c in (CODE_STATUS, CODE_APPLIED, NEG_APPLIED) if c not in df.columns]
    if missing:
        print(f"Skipping {csv_path.name}: missing column(s) {', '.join(missing)}", file=sys.stderr)
        return None

    total = len(df)
    if total == 0:
        print(f"Skipping {csv_path.name}: empty file", file=sys.stderr)
        return None

    status_pass      = df[CODE_STATUS].astype(str).str.upper() == "PASS"
    applied_true     = df[CODE_APPLIED].astype(str).str.strip().str.upper() == "TRUE"
    neg_applied_true = df[NEG_APPLIED].astype(str).str.strip().str.upper() == "TRUE"
    passes           = (status_pass & applied_true & neg_applied_true).sum()

    # Hard-coded totals for the “special-case” files
    stem = csv_path.stem
    s = stem.upper()
    classic_totals = {
        'CF': 10,
        'DMB': 3,
        'EAK': 20,
    }
    tdd_totals = {
        'CF': 53,
        'DMB': 43,
        'EAK': 51,
    }
    totals = classic_totals if 'CLASSIC' in s else tdd_totals
    for key, val in totals.items():
        if key in s:
            total = val
            break

    return passes / total


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python rate_pass_scores.py <folder_with_csv>", file=sys.stderr)
        sys.exit(1)

    folder = Path(sys.argv[1]).expanduser().resolve()
    if not folder.is_dir():
        print(f"{folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    results: list[tuple[str, float]] = []

    for csv_path in folder.glob("test_results*.csv"):
        score = pass_and_applied_rate(csv_path)
        if score is not None:
            results.append((csv_path.name, score))

    # Sort by score (DESC), then filename (ASC) for stability
    results.sort(key=lambda x: (-x[1], x[0]))

    # Compute padding so all percentages start in the same column
    max_name_len = max(len(name) for name, _ in results) if results else 0

    for filename, score in results:
        # 6 chars wide gives room for “100.0%”
        print(f"{filename[len('test_results-'):]:<{max_name_len}}  {score:>6.1%}")


if __name__ == "__main__":
    main()
