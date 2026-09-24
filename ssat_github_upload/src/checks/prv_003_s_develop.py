from __future__ import annotations

from checks._auth_lookup import user_status, users_with_auth_object
from checks.base import CheckResult, CheckSpec, RiskTile, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="PRV-003",
    domain="Privileged Access",
    question="Who has S_DEVELOP?",
    data_source="Table AGR_1251 (role authorization values) joined with AGR_USERS (role-to-user), "
    "USR02 (lock status/last logon)",
    collection_method="RFC_READ_TABLE joins in Python",
    risk_tiles=[
        RiskTile("Users holding S_DEVELOP", "warn", lambda s: s.get("user_count") or None),
    ],
)


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    dormant_days = int(config.get("usr_004", {}).get("dormant_days", 90))

    findings = users_with_auth_object(connector, "S_DEVELOP")
    users = sorted({f["user"] for f in findings if f["user"]})
    status = user_status(connector, set(users), dormant_days)

    for f in findings:
        f.update(status.get(f["user"], {"locked": None, "last_logon_date": None,
                                          "days_since_last_logon": None, "dormant": None}))

    active_unlocked = [u for u in users if status.get(u, {}).get("locked") is False]
    locked = [u for u in users if status.get(u, {}).get("locked") is True]
    dormant_candidates = [u for u in users if status.get(u, {}).get("dormant")]

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
            "user_count": len(users),
            "users": users,
            "active_unlocked_count": len(active_unlocked),
            "locked_count": len(locked),
            "removal_candidate_count": len(dormant_candidates),
            "removal_candidates": dormant_candidates,
            "note": "removal_candidates are users holding S_DEVELOP who are unlocked but haven't "
            f"logged on in over {dormant_days} days -- the most defensible first group to review "
            "for removing development access from.",
        },
    )
