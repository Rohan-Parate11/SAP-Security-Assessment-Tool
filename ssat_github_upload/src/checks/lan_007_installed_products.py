from __future__ import annotations

from checks.base import CheckResult, CheckSpec, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="LAN-007",
    domain="SAP Landscape",
    question="List all installed SAP product versions.",
    data_source="FM SUPA_GET_INSTALLED_SW_PRODUCTS (installed product versions, same source as "
    "System -> Status -> Installed Product Versions -- e.g. S/4HANA Foundation, SAP Fiori for S/4HANA)",
    collection_method="Direct RFC call -- discovered live via TFDIR search since product-version "
    "tracking (as opposed to the individual component list in LAN-001) isn't exposed via a documented "
    "transparent table",
    scope="system-wide",  # same product install list regardless of client
)


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    result = connector.call_fm("SUPA_GET_INSTALLED_SW_PRODUCTS")
    rows = result.get("ET_SWPRODUCTS", [])
    findings = [
        {
            "product_id": r.get("ID", "").strip(),
            "name": r.get("NAME", "").strip(),
            "version": r.get("VERSION", "").strip(),
            "vendor": r.get("VENDOR", "").strip(),
            "description": r.get("DESCRIPT", "").strip(),
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
        summary={"product_count": len(findings)},
    )
