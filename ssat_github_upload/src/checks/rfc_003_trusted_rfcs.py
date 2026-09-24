from __future__ import annotations

from checks.base import CheckResult, CheckSpec, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="RFC-003",
    domain="RFC & Interfaces",
    question="Trusted RFCs documented?",
    data_source="Tables RFCSYSACL (systems trusting this one) and RFCTRUST (systems this one trusts)",
    collection_method="RFC_READ_TABLE, curated field lists (confirmed against a live system via "
    "DDIF_FIELDINFO_GET; both tables have wide RFCOPTION*-style fields that overflow "
    "RFC_READ_TABLE's row-width limit if all fields are requested)",
    scope="system-wide",  # neither table carries MANDT -- same trust config regardless of client
)

_SYSACL_FIELDS = ["RFCSYSID", "RFCTRUSTSY", "RFCDEST", "RFCSECACTV", "RFCTSTACTV", "RFCCREUSER", "RFCCREDATE"]
_TRUST_FIELDS = ["RFCTRUSTID", "RFCTRUSTSY", "RFCDEST", "RFCTSTACTV", "RFCCREUSER", "RFCCREDATE"]


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    findings = []
    errors = []

    try:
        for row in connector.read_table("RFCSYSACL", fields=_SYSACL_FIELDS):
            findings.append({"direction": "trusting_this_system", **{k: v.strip() for k, v in row.items()}})
    except Exception as exc:  # noqa: BLE001
        errors.append(f"RFCSYSACL read failed: {exc}")

    try:
        for row in connector.read_table("RFCTRUST", fields=_TRUST_FIELDS):
            findings.append({"direction": "trusted_by_this_system", **{k: v.strip() for k, v in row.items()}})
    except Exception as exc:  # noqa: BLE001
        errors.append(f"RFCTRUST read failed: {exc}")

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
        summary={"trust_relationship_count": len(findings)},
        errors=errors,
    )
