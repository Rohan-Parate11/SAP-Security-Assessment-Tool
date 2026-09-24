from __future__ import annotations

from checks._auth_lookup import user_status, users_with_profile
from checks.base import CheckResult, CheckSpec, RiskTile, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="PRV-002",
    domain="Privileged Access",
    question="Who has SAP_NEW?",
    data_source="Table AGR_PROF (role-to-profile), AGR_USERS (role-to-user), UST04 (direct profile "
    "assignment), USR02 (lock status/last logon)",
    collection_method="RFC_READ_TABLE joins in Python -- same pattern as PRV-001",
    risk_tiles=[
        RiskTile("Users holding SAP_NEW", "warn", lambda s: s.get("user_count") or None),
    ],
)


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    dormant_days = int(config.get("usr_004", {}).get("dormant_days", 90))

    findings = users_with_profile(connector, "SAP_NEW")
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
            "note": "SAP_NEW grants every authorization check introduced by a release upgrade that "
            "hasn't yet been mapped into real roles -- meant as a temporary bridge during upgrade "
            f"testing, not a permanent assignment. removal_candidates are holders unlocked but with "
            f"no logon in over {dormant_days} days -- the safest group to review first.",
        },
    )
