from __future__ import annotations

import datetime as _dt

from checks.base import CheckResult, CheckSpec, RiskTile, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="USR-004",
    domain="User Administration",
    question="Are dormant users reviewed?",
    data_source="Table USR02 (user master, last logon date)",
    collection_method="RFC_READ_TABLE on USR02",
    risk_tiles=[
        RiskTile("Dormant unlocked users", "warn", lambda s: s.get("dormant_unlocked_count") or None),
    ],
)

_DEFAULT_DORMANT_DAYS = 90


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    dormant_days = int(config.get("usr_004", {}).get("dormant_days", _DEFAULT_DORMANT_DAYS))
    today = _dt.date.today()

    rows = connector.read_table(
        "USR02",
        fields=["BNAME", "USTYP", "TRDAT", "UFLAG", "GLTGB"],
        where="USTYP <> 'S'",  # exclude system/service users from the dormancy question
    )

    findings = []
    for r in rows:
        bname = r.get("BNAME", "").strip()
        trdat = r.get("TRDAT", "").strip()
        uflag = r.get("UFLAG", "").strip()
        last_logon = None
        days_since_logon = None
        if trdat and trdat != "00000000":
            last_logon = f"{trdat[0:4]}-{trdat[4:6]}-{trdat[6:8]}"
            days_since_logon = (today - _dt.date(int(trdat[0:4]), int(trdat[4:6]), int(trdat[6:8]))).days

        is_dormant = days_since_logon is None or days_since_logon > dormant_days
        is_locked = uflag not in ("", "0")

        findings.append(
            {
                "user": bname,
                "user_type": r.get("USTYP", "").strip(),
                "last_logon_date": last_logon,
                "days_since_last_logon": days_since_logon,
                "never_logged_on": last_logon is None,
                "locked": is_locked,
                "dormant": is_dormant and not is_locked,
            }
        )

    dormant_count = sum(1 for f in findings if f["dormant"])
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
            "total_users": len(findings),
            "dormant_threshold_days": dormant_days,
            "dormant_unlocked_count": dormant_count,
        },
    )
