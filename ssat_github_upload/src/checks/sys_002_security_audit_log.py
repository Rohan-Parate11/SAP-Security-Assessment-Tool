from __future__ import annotations

from checks.base import CheckResult, CheckSpec, RiskTile, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="SYS-002",
    domain="System Hardening",
    question="Security Audit Log enabled?",
    data_source="FM TH_GET_PARAMETER (rsau/enable, rsau/selection_slots, rsau/max_diskspace/local)",
    collection_method="Direct RFC calls, one per parameter -- same pattern as SYS-001",
    scope="system-wide",
    risk_tiles=[
        RiskTile("Security Audit Log", "crit", lambda s: "Disabled" if s.get("audit_log_enabled") is False else None),
    ],
)


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    def _param(name: str) -> str:
        return str(connector.call_fm("TH_GET_PARAMETER", PARAMETER_NAME=name).get("PARAMETER_VALUE", "")).strip()

    enable_raw = _param("rsau/enable")
    slots_raw = _param("rsau/selection_slots")
    diskspace_raw = _param("rsau/max_diskspace/local")

    enabled = enable_raw == "1"

    findings = [
        {"parameter": "rsau/enable", "value": enable_raw, "meaning": "1 = audit log active, 0 = disabled"},
        {"parameter": "rsau/selection_slots", "value": slots_raw, "meaning": "number of configurable audit filter slots"},
        {"parameter": "rsau/max_diskspace/local", "value": diskspace_raw, "meaning": "max local audit file size in bytes"},
    ]

    return CheckResult(
        check_id=CHECK.check_id,
        domain=CHECK.domain,
        question=CHECK.question,
        data_source=CHECK.data_source,
        collection_method=CHECK.collection_method,
        scope=CHECK.scope,
        system_id=connector.system_id,
        collected_at=now_iso(),
        findings=findings,
        summary={
            "audit_log_enabled": enabled,
            "selection_slots": slots_raw,
            "max_diskspace_local_bytes": diskspace_raw,
            "note": "Confirms only whether the audit log's master switch is on and its capacity "
            "settings -- it doesn't verify WHAT is actually being audited, since the specific filter "
            "rules (which events/users/clients) are configured dynamically via SM19/RSAU_CONFIG, not "
            "as static profile parameters this check can read the same way.",
        },
    )
