"""Tests RFC connectivity for a system profile before it's saved, using the
same RFC_SYSTEM_INFO call RFCConnector already makes internally to resolve a
system's SID -- surfaced here as its own step so a typo in host/sysnr/user is
caught immediately instead of during the first real assessment run.
"""

from __future__ import annotations

from connectors import RFCConnectionError, RFCConnector


class ConnectionTestError(RuntimeError):
    pass


def test_connection(
    ashost: str, sysnr: str, client: str, user: str, passwd: str, lang: str = "EN"
) -> dict:
    connector = RFCConnector(ashost=ashost, sysnr=sysnr, client=client, user=user, passwd=passwd, lang=lang)
    try:
        connector.connect()
    except RFCConnectionError as exc:
        raise ConnectionTestError(f"Connection failed: {exc}") from exc

    try:
        info = connector.call_fm("RFC_SYSTEM_INFO").get("RFCSI_EXPORT", {})
    finally:
        connector.close()

    return {
        "system_id": info.get("RFCSYSID", ""),
        "host": info.get("RFCHOST", ""),
        "db_system": info.get("RFCDBSYS", ""),
        "kernel_release": info.get("RFCKERNRL", ""),
        "sap_release": info.get("RFCSAPRL", ""),
    }
