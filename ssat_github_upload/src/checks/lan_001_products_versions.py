from __future__ import annotations

from checks.base import CheckResult, CheckSpec, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="LAN-001",
    domain="SAP Landscape",
    question="List all SAP components and versions.",
    data_source="FM SUPA_GET_INSTALLED_SW_COMPS (installed software component versions, same source as "
    "System -> Status -> Installed Software Component Versions)",
    collection_method="Direct RFC call -- discovered live via TFDIR search, chosen over a plain "
    "RFC_READ_TABLE on CVERS because CVERS alone carries no human-readable description field",
    scope="system-wide",  # same install list regardless of client
)


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    result = connector.call_fm("SUPA_GET_INSTALLED_SW_COMPS")
    rows = result.get("TT_COMPTAB", [])
    findings = [
        {
            "component": r.get("COMPONENT", "").strip(),
            "release": r.get("RELEASE", "").strip(),
            "extended_release": r.get("EXTRELEASE", "").strip(),
            "component_type": r.get("COMP_TYPE", "").strip(),
            "description": r.get("DESC_TEXT", "").strip(),
        }
        for r in rows
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
        summary={"component_count": len(findings)},
    )
