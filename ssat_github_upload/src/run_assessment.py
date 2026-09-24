"""CLI entrypoint: connect to one SAP system and run the requested extraction checks.

Example:
    python run_assessment.py --config config/connection.json --checks all
    python run_assessment.py --config config/connection.json --checks USR-004,PRV-001

Extraction only (per project decision): each check returns raw structured
data pulled from SAP, not a risk/maturity score. Results are written as
per-check JSON, a combined all_results.json, and a consultant-facing Excel
workbook, matching the answers captured for this build (RFC_READ_TABLE for
table-driven checks, JSON + Excel output).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks  # noqa: E402  (registers all check modules on import)
from checks.base import CheckResult, all_check_ids, get_check, get_spec, now_iso  # noqa: E402
from connectors import RFCConnectionError, RFCConnector  # noqa: E402
from output import write_excel, write_json  # noqa: E402


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as fh:
        config = json.load(fh)

    if not config.get("passwd"):
        config["passwd"] = os.environ.get("SAP_RFC_PASSWD", "")

    odata_cfg = config.get("odata")
    if odata_cfg and not odata_cfg.get("passwd"):
        odata_cfg["passwd"] = os.environ.get("SAP_ODATA_PASSWD", config["passwd"])

    return config


def build_connector(config: dict) -> RFCConnector:
    return RFCConnector(
        ashost=config["ashost"],
        sysnr=config["sysnr"],
        client=config["client"],
        user=config["user"],
        passwd=config["passwd"],
        lang=config.get("lang", "EN"),
        system_id=config.get("system_id"),
    )


def run_checks(connector, config: dict, check_ids: list[str], on_progress=None) -> list[CheckResult]:
    """on_progress, if given, is called as on_progress(check_id, status, result) with
    status "running" (result=None) before each check and "done" (result=CheckResult) after --
    used by the web UI to show live per-check progress. Purely additive: the CLI doesn't pass it."""
    results = []
    for check_id in check_ids:
        spec = get_spec(check_id)
        print(f"[{check_id}] {spec.question} ...", flush=True)
        if on_progress:
            on_progress(check_id, "running", None)
        # Tags every RFC call this check makes with its check_id in connector.trace (see
        # RFCConnector._record_trace), so a consultant can see exactly what was executed against
        # the backend and what it returned -- not just this check's own summary sentence.
        if hasattr(connector, "current_check_id"):
            connector.current_check_id = check_id
        try:
            result = get_check(check_id)(connector, config)
        except Exception as exc:  # noqa: BLE001 - one failing check must not abort the run
            traceback.print_exc()
            result = CheckResult(
                check_id=spec.check_id,
                domain=spec.domain,
                question=spec.question,
                data_source=spec.data_source,
                collection_method=spec.collection_method,
                system_id=getattr(connector, "system_id", ""),
                collected_at=now_iso(),
                errors=[f"Check failed: {exc}"],
            )
        print(f"  -> {len(result.findings)} records, {len(result.errors)} error(s)")
        if on_progress:
            on_progress(check_id, "done", result)
        results.append(result)
    if hasattr(connector, "current_check_id"):
        connector.current_check_id = None
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SAP security assessment extraction checks.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "config" / "connection.json",
        help="Path to connection.json (see config/connection.json.example)",
    )
    parser.add_argument(
        "--checks",
        default="all",
        help="Comma-separated check IDs (e.g. USR-004,PRV-001) or 'all'",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "output",
        help="Directory to write results into",
    )
    parser.add_argument(
        "--format",
        choices=["json", "excel", "both"],
        default="both",
    )
    args = parser.parse_args()

    if not args.config.exists():
        print(f"Config file not found: {args.config}\nCopy config/connection.json.example to get started.")
        return 1

    config = load_config(args.config)
    check_ids = all_check_ids() if args.checks == "all" else [c.strip() for c in args.checks.split(",")]

    unknown = sorted(set(check_ids) - set(all_check_ids()))
    if unknown:
        print(f"Unknown check ID(s): {', '.join(unknown)}\nAvailable: {', '.join(all_check_ids())}")
        return 1

    connector = build_connector(config)
    try:
        connector.connect()
    except RFCConnectionError as exc:
        print(f"Connection failed: {exc}")
        return 1

    try:
        results = run_checks(connector, config, check_ids)
    finally:
        connector.close()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.output_dir / f"{connector.system_id or 'assessment'}_{timestamp}"

    if args.format in ("json", "both"):
        write_json(results, run_dir)
        print(f"JSON results written to {run_dir}")

    if args.format in ("excel", "both"):
        excel_path = run_dir / f"SAP_Security_Assessment_{connector.system_id or 'results'}_{timestamp}.xlsx"
        write_excel(results, excel_path)
        print(f"Excel workbook written to {excel_path}")

    trace = getattr(connector, "trace", None)
    if trace is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "rfc_trace.json").write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
