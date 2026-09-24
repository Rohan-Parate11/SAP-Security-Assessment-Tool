"""Standalone connectivity proof-of-concept -- run this BEFORE trusting any
of the 14 assessment checks against a real system.

Steps (matches the POC plan): connect with a read-only RFC user, call a
trivial RFC-enabled FM (STFC_CONNECTION), call RFC_SYSTEM_INFO, then attempt
one RFC_READ_TABLE read to confirm that's actually permitted for this user.

Usage:
    . .\\activate_env.ps1
    python.exe poc_connection_test.py --config config/connection.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from connectors import RFCConnectionError, RFCConnector  # noqa: E402


def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        config = json.load(fh)
    if not config.get("passwd"):
        config["passwd"] = os.environ.get("SAP_RFC_PASSWD", "")
    return config


def step(title: str):
    print(f"\n=== {title} ===")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("src/config/connection.json"))
    parser.add_argument("--test-table", default="T000", help="Small table to try RFC_READ_TABLE against")
    args = parser.parse_args()

    if not args.config.exists():
        print(f"Config not found: {args.config}. Copy src/config/connection.json.example and fill it in.")
        return 1

    config = load_config(args.config)
    if not config["passwd"]:
        print("No password in config and SAP_RFC_PASSWD env var not set.")
        return 1

    connector = RFCConnector(
        ashost=config["ashost"],
        sysnr=config["sysnr"],
        client=config["client"],
        user=config["user"],
        passwd=config["passwd"],
        lang=config.get("lang", "EN"),
        system_id=config.get("system_id"),
    )

    step("1. Connect")
    try:
        connector.connect()
        print(f"Connected. SID = {connector.system_id}")
    except RFCConnectionError as exc:
        print(f"FAILED: {exc}")
        return 1

    try:
        step("2. STFC_CONNECTION (echo test)")
        try:
            result = connector.call_fm("STFC_CONNECTION", REQUTEXT="ping from SAP Security Assessment Tool")
            print("RESPTEXT:", result.get("RESPTEXT"))
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED: {exc}")

        step("3. RFC_SYSTEM_INFO")
        try:
            info = connector.call_fm("RFC_SYSTEM_INFO")
            sysinfo = info.get("RFCSI_EXPORT", {})
            for key in ("RFCSYSID", "RFCHOST", "RFCSAPRL", "RFCDBSYS", "RFCKERNRL"):
                print(f"  {key}: {sysinfo.get(key, '').strip()}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED: {exc}")

        step(f"4. RFC_READ_TABLE on {args.test_table} (max 5 rows)")
        try:
            rows = connector.read_table(args.test_table, max_rows=5)
            print(f"Read {len(rows)} row(s). Sample: {rows[0] if rows else '(table empty)'}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED: {exc}")
            print("If this is an authorization error, the SSAT_RFC user is missing S_TABU_DIS/S_TABU_NAM/S_RFC.")
    finally:
        connector.close()

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
