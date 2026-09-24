"""Auto-detects a system's Gateway/ICM HTTP(S) base URL by reading its own
icm/server_port_* profile parameters via RFC (same TH_GET_PARAMETER call
checks/sys_001_profile_parameters.py already uses), rather than assuming the
default 8000/44300 + instance-number port convention.

This only finds the port ICM is actually listening on for the connected
application server instance -- it can't discover a web dispatcher, reverse
proxy, or load balancer sitting in front of it, so the caller should still
leave the field editable after a successful detection.
"""

from __future__ import annotations

from connectors import RFCConnectionError, RFCConnector

_MAX_PORT_SLOTS = 10  # icm/server_port_0.. -- systems rarely define more than a handful


class GatewayDetectionError(RuntimeError):
    pass


def _parse_port_param(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in value.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            parsed[k.strip().upper()] = v.strip()
    return parsed


def detect_gateway_url(
    ashost: str, sysnr: str, client: str, user: str, passwd: str, lang: str = "EN"
) -> dict:
    connector = RFCConnector(ashost=ashost, sysnr=sysnr, client=client, user=user, passwd=passwd, lang=lang)
    try:
        connector.connect()
    except RFCConnectionError as exc:
        raise GatewayDetectionError(f"Connection failed: {exc}") from exc

    try:
        found = []
        for i in range(_MAX_PORT_SLOTS):
            param = f"icm/server_port_{i}"
            try:
                result = connector.call_fm("TH_GET_PARAMETER", PARAMETER_NAME=param)
            except Exception:  # noqa: BLE001 -- no more slots configured past this point
                break
            raw = str(result.get("PARAMETER_VALUE", "")).strip()
            if not raw:
                continue
            parsed = _parse_port_param(raw)
            if parsed.get("PROT") in ("HTTP", "HTTPS") and parsed.get("PORT"):
                found.append({"parameter": param, "protocol": parsed["PROT"], "port": parsed["PORT"], "raw": raw})
    finally:
        connector.close()

    if not found:
        raise GatewayDetectionError(
            "No icm/server_port_* HTTP(S) service found on this application server. "
            "The Gateway may be exposed only through a separate web dispatcher -- enter the URL manually."
        )

    https_entries = [f for f in found if f["protocol"] == "HTTPS"]
    chosen = https_entries[0] if https_entries else found[0]
    scheme = "https" if chosen["protocol"] == "HTTPS" else "http"
    base_url = f"{scheme}://{ashost}:{chosen['port']}"

    return {
        "base_url": base_url,
        "detected_from": chosen["parameter"],
        "all_ports": found,
    }
