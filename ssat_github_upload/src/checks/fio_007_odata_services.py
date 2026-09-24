from __future__ import annotations

import requests

from checks.base import CheckResult, CheckSpec, RiskTile, now_iso, register
from connectors.base import SAPConnector
from connectors.odata_connector import ODataConnector

CHECK = CheckSpec(
    check_id="FIO-007",
    domain="Fiori & Web",
    question="OData services reviewed?",
    data_source="SAP Gateway service catalogs, OData V2 (/IWFND/CATALOGSERVICE;v=2/ServiceCollection) "
    "and V4 (iwfnd/catalog ServiceGroups) -- V2 and V4 services are registered in separate catalogs, "
    "so checking only one would miss any V4-only services",
    collection_method="HTTPS GET against the Gateway host (separate from the RFC connector; "
    "see config['odata'])",
    risk_tiles=[
        RiskTile("Custom OData services", "warn", lambda s: s.get("custom_service_count") or None),
    ],
)

# The Gateway service catalog isn't exposed through a stable transparent
# table, so this check goes over HTTPS to the documented CATALOGSERVICE OData
# endpoint instead of RFC_READ_TABLE, using its own connector (config['odata']).


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    odata_cfg = config.get("odata")
    if not odata_cfg:
        return CheckResult(
            check_id=CHECK.check_id,
            domain=CHECK.domain,
            question=CHECK.question,
            data_source=CHECK.data_source,
            collection_method=CHECK.collection_method,
            scope=CHECK.scope,
            system_id=connector.system_id,
            collected_at=now_iso(),
            errors=["No config['odata'] section configured (base_url/client/user/passwd) - skipped."],
        )

    client = ODataConnector(
        base_url=odata_cfg["base_url"],
        client=odata_cfg["client"],
        user=odata_cfg["user"],
        passwd=odata_cfg["passwd"],
        verify_ssl=odata_cfg.get("verify_ssl", True),
    )

    findings = []
    errors = []
    try:
        services = client.get_service_catalog()
        for svc in services:
            findings.append(
                {
                    "odata_version": "v2",
                    "technical_service_name": svc.get("TechnicalServiceName"),
                    "version": svc.get("TechnicalServiceVersion"),
                    "description": svc.get("Description"),
                    "author": svc.get("Author"),
                    "service_url": svc.get("ServiceUrl"),
                    "is_sap_service": svc.get("IsSapService"),
                }
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Gateway V2 catalog request failed: {exc}")

    v4_status = "active"
    v4_note = None
    try:
        services_v4 = client.get_service_catalog_v4()
        for svc in services_v4:
            findings.append(
                {
                    "odata_version": "v4",
                    "technical_service_name": svc.get("Id") or svc.get("TechnicalName") or svc.get("Name"),
                    "version": svc.get("DefaultSystemVersion") or svc.get("Version"),
                    "description": svc.get("Description") or svc.get("Title"),
                    "author": svc.get("Author"),
                    "service_url": svc.get("Url") or svc.get("ServiceUrl"),
                    "is_sap_service": svc.get("IsSapService"),
                }
            )
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            # Expected on systems that never activated the V4 catalog service -- not a
            # failure of the check, so it doesn't count as an error against this run.
            v4_status = "not_activated"
            v4_note = "OData V4 catalog service is not activated on this system -- no V4 services to report. The V2 catalog was scanned successfully."
        else:
            v4_status = "error"
            errors.append(f"Gateway V4 catalog request failed: {exc}")
    except Exception as exc:  # noqa: BLE001
        v4_status = "error"
        errors.append(f"Gateway V4 catalog request failed: {exc}")

    def _is_sap(v: object) -> bool:
        return v is True or str(v).strip().lower() == "true"

    sap_count = sum(1 for f in findings if _is_sap(f.get("is_sap_service")))
    custom_count = len(findings) - sap_count

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
            "service_count": len(findings),
            "v2_service_count": sum(1 for f in findings if f.get("odata_version") == "v2"),
            "v4_service_count": sum(1 for f in findings if f.get("odata_version") == "v4"),
            "v4_status": v4_status,
            "v4_note": v4_note,
            "sap_delivered_service_count": sap_count,
            "custom_service_count": custom_count,
            "note": "custom_service_count is the actionable figure -- SAP-delivered services have "
            "already been through SAP's own hardening; custom/Z-services generally haven't and are "
            "where a reviewer should look first.",
        },
        errors=errors,
    )
