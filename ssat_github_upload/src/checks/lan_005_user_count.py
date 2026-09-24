from __future__ import annotations

from checks.base import CheckResult, CheckSpec, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="LAN-005",
    domain="SAP Landscape",
    question="Number of users per system?",
    data_source="Table USR02 (user master)",
    collection_method="RFC_READ_TABLE on USR02, no filter -- every user account in this client",
)

# SAP user type codes (USR02-USTYP).
_USER_TYPE_LABELS = {
    "A": "dialog",
    "B": "system",
    "C": "communication",
    "L": "reference",
    "S": "service",
}


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    rows = connector.read_table("USR02", fields=["BNAME", "USTYP", "UFLAG"])

    findings = []
    by_type: dict[str, int] = {}
    for r in rows:
        ustyp = r.get("USTYP", "").strip()
        uflag = r.get("UFLAG", "").strip()
        label = _USER_TYPE_LABELS.get(ustyp, ustyp or "unknown")
        by_type[label] = by_type.get(label, 0) + 1
        findings.append(
            {
                "user": r.get("BNAME", "").strip(),
                "user_type": ustyp,
                "user_type_label": label,
                "locked": uflag not in ("", "0"),
            }
        )

    dialog_users = [f for f in findings if f["user_type"] == "A"]
    dialog_unlocked_count = sum(1 for f in dialog_users if not f["locked"])

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
            "total_user_count": len(findings),
            "by_user_type": by_type,
            "dialog_user_count": len(dialog_users),
            "dialog_unlocked_count": dialog_unlocked_count,
            "note": "dialog_user_count is the closest sizing figure to actual named/human users -- "
            "system, communication and service accounts are technical, not people.",
        },
    )
