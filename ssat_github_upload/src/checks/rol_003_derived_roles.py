from __future__ import annotations

from checks._auth_lookup import LARGE_TABLE_BATCH_SIZE
from checks.base import CheckResult, CheckSpec, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="ROL-003",
    domain="Roles & Authorizations",
    question="Derived roles implemented?",
    data_source="Table AGR_DEFINE (role definitions; PARENT_AGR marks derived roles)",
    collection_method="RFC_READ_TABLE on AGR_DEFINE",
)


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    rows = connector.read_table("AGR_DEFINE", fields=["AGR_NAME", "PARENT_AGR"], batch_size=LARGE_TABLE_BATCH_SIZE)

    findings = []
    for r in rows:
        parent = r.get("PARENT_AGR", "").strip()
        findings.append(
            {
                "role": r.get("AGR_NAME", "").strip(),
                "is_derived": bool(parent),
                "parent_role": parent or None,
            }
        )

    derived_count = sum(1 for f in findings if f["is_derived"])
    return CheckResult(
        check_id=CHECK.check_id,
        domain=CHECK.domain,
        question=CHECK.question,
        data_source=CHECK.data_source,
        collection_method=CHECK.collection_method,
        system_id=connector.system_id,
        collected_at=now_iso(),
        findings=findings,
        summary={
            "total_roles": len(findings),
            "derived_role_count": derived_count,
            "master_role_count": len(findings) - derived_count,
        },
    )
