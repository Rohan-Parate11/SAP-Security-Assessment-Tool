from __future__ import annotations

from checks.base import CheckResult, CheckSpec, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="GRC-001",
    domain="SAP GRC",
    question="Is SAP GRC implemented?",
    data_source="FM SUPA_GET_INSTALLED_SW_COMPS (same installed-component source as LAN-001)",
    collection_method="Direct RFC call, filtered to components with a 'GRC' name prefix",
    scope="system-wide",
)

# Real SAP GRC Access Control / Process Control / Risk Management components all use a "GRC"
# name PREFIX (GRCFND_A, GRCPINW, GRCPIERP, ...) -- matched with startswith, not a substring
# search: confirmed live that "UIGRCGTS" (a Fiori UI package for Global Trade Services, an
# unrelated product) contains "GRC" as a substring but doesn't start with it.
_GRC_PREFIX = "GRC"


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    result = connector.call_fm("SUPA_GET_INSTALLED_SW_COMPS")
    rows = result.get("TT_COMPTAB", [])

    findings = [
        {
            "component": r.get("COMPONENT", "").strip(),
            "release": r.get("RELEASE", "").strip(),
            "description": r.get("DESC_TEXT", "").strip(),
        }
        for r in rows
        if r.get("COMPONENT", "").strip().upper().startswith(_GRC_PREFIX)
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
            "grc_component_count": len(findings),
            "grc_detected": len(findings) > 0,
            "note": "Only detects GRC components installed on THIS connected system (e.g. the GRC "
            "plug-in used to integrate a backend into a separate GRC Access Control system). A "
            "standalone GRC system elsewhere in the landscape that this profile doesn't connect to "
            "wouldn't be visible here -- treat a negative result as 'not detected from this system', "
            "not a confirmed absence of GRC anywhere in the landscape.",
        },
    )
