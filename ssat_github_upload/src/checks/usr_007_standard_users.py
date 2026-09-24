from __future__ import annotations

from checks.base import CheckResult, CheckSpec, RiskTile, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="USR-007",
    domain="User Administration",
    question="Standard users secured (SAP*, DDIC, EARLYWATCH)?",
    data_source="Table USR02 (user master) for the standard SAP accounts",
    collection_method="RFC_READ_TABLE on USR02",
    risk_tiles=[
        RiskTile(
            "Standard users unlocked (SAP*/DDIC/EARLYWATCH)",
            "crit",
            lambda s: len(s.get("unlocked_standard_users") or []) or None,
        ),
    ],
)

_STANDARD_USERS = ["SAP*", "DDIC", "EARLYWATCH"]


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    where = " OR ".join(f"BNAME = '{u}'" for u in _STANDARD_USERS)
    rows = connector.read_table(
        "USR02",
        fields=["BNAME", "USTYP", "UFLAG", "TRDAT", "GLTGB"],
        where=where,
    )

    found_users = {r.get("BNAME", "").strip() for r in rows}
    findings = []
    for r in rows:
        uflag = r.get("UFLAG", "").strip()
        findings.append(
            {
                "user": r.get("BNAME", "").strip(),
                "user_type": r.get("USTYP", "").strip(),
                "locked": uflag not in ("", "0"),
                "last_logon_date": r.get("TRDAT", "").strip() or None,
                "valid_to": r.get("GLTGB", "").strip() or None,
                "exists_in_this_client": True,
            }
        )

    for missing in set(_STANDARD_USERS) - found_users:
        findings.append(
            {
                "user": missing,
                "user_type": None,
                "locked": None,
                "last_logon_date": None,
                "valid_to": None,
                "exists_in_this_client": False,
            }
        )

    unlocked = [f["user"] for f in findings if f["exists_in_this_client"] and not f["locked"]]
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
            "standard_users_checked": _STANDARD_USERS,
            "unlocked_standard_users": unlocked,
        },
    )
