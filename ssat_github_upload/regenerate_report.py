"""Rebuild the Excel workbook from an already-collected all_results.json --
useful after changing report formatting without re-connecting to SAP.

Usage:
    python.exe regenerate_report.py output\\S23_20260807_004802
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from checks.base import CheckResult  # noqa: E402
from output import write_excel  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path, help="Folder containing all_results.json")
    args = parser.parse_args()

    all_results_path = args.run_dir / "all_results.json"
    if not all_results_path.exists():
        print(f"Not found: {all_results_path}")
        return 1

    with open(all_results_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    results = [CheckResult.from_dict(r) for r in raw]

    sid = results[0].system_id if results else "results"
    excel_path = args.run_dir / f"SAP_Security_Assessment_{sid}_readable.xlsx"
    write_excel(results, excel_path)
    print(f"Wrote {excel_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
