from __future__ import annotations

import datetime as _dt

from checks._auth_lookup import LARGE_TABLE_BATCH_SIZE
from checks.base import CheckResult, CheckSpec, RiskTile, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="ROL-005",
    domain="Roles & Authorizations",
    question="Unused roles identified?",
    data_source="Table AGR_DEFINE (all roles) vs. AGR_USERS (active role-to-user assignments)",
    collection_method="RFC_READ_TABLE on AGR_DEFINE and AGR_USERS",
    risk_tiles=[
        RiskTile("Unused custom roles", "warn", lambda s: s.get("unused_custom_role_count") or None),
        RiskTile(
            "SAP standard roles directly assigned",
            "warn",
            lambda s: s.get("sap_delivered_roles_in_use_count") or None,
        ),
    ],
)

# SAP's own naming convention: every SAP-delivered role starts with "SAP_". Anything else is a
# customer/custom role.
#
# Two distinct findings come out of the same data, not one:
#   - unused CUSTOM roles: a real cleanup candidate. SAP ships thousands of roles most customers
#     never assign, so an unused SAP-delivered role is normal and excluded from that count.
#   - SAP-delivered roles that ARE actively assigned: per SAP's own guidance, standard/delivered
#     roles must never be modified and should not be assigned to users directly -- the standard
#     practice is to copy the role into the customer namespace (Y_/Z_) and assign the copy, so
#     SAP upgrades/support packs don't touch (or get blocked by changes to) the original. Every
#     SAP-delivered role with active users is worth flagging for that reason, regardless of "unused".
_SAP_DELIVERED_PREFIX = "SAP_"


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    today = _dt.date.today().strftime("%Y%m%d")

    all_roles = {
        r.get("AGR_NAME", "").strip()
        for r in connector.read_table("AGR_DEFINE", fields=["AGR_NAME"], batch_size=LARGE_TABLE_BATCH_SIZE)
    }

    assignment_rows = connector.read_table(
        "AGR_USERS",
        fields=["AGR_NAME", "UNAME", "FROM_DAT", "TO_DAT"],
        where=f"FROM_DAT <= '{today}' AND TO_DAT >= '{today}'",
        batch_size=LARGE_TABLE_BATCH_SIZE,
    )
    active_users_by_role: dict[str, set[str]] = {}
    for row in assignment_rows:
        role = row.get("AGR_NAME", "").strip()
        uname = row.get("UNAME", "").strip()
        active_users_by_role.setdefault(role, set()).add(uname)

    findings = []
    for role in sorted(all_roles):
        users = active_users_by_role.get(role, set())
        is_sap = role.startswith(_SAP_DELIVERED_PREFIX)
        findings.append(
            {
                "role": role,
                "active_user_count": len(users),
                "active_users": sorted(users) if is_sap and users else None,  # only kept for the
                # SAP-delivered-in-use finding below; omitted otherwise to avoid bloating output
                # with per-user lists across thousands of custom roles that aren't the point here.
                "unused": len(users) == 0,
                "is_sap_delivered": is_sap,
            }
        )

    custom_unused = [f for f in findings if f["unused"] and not f["is_sap_delivered"]]
    sap_unused = [f for f in findings if f["unused"] and f["is_sap_delivered"]]
    sap_in_use = [f for f in findings if f["is_sap_delivered"] and not f["unused"]]

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
            "total_roles": len(findings),
            "unused_role_count": len(custom_unused) + len(sap_unused),
            "unused_custom_role_count": len(custom_unused),
            "unused_sap_delivered_role_count": len(sap_unused),
            "sap_delivered_roles_in_use_count": len(sap_in_use),
            "sap_delivered_roles_in_use": [
                {"role": f["role"], "active_user_count": f["active_user_count"], "users": f["active_users"]}
                for f in sap_in_use
            ],
            "note": "Two separate findings: (1) unused_custom_role_count -- customer/custom roles "
            "with no active assignment, a cleanup candidate; SAP-delivered unused roles are normal "
            "and excluded. (2) sap_delivered_roles_in_use -- SAP-delivered roles ('SAP_' prefix) "
            "that ARE actively assigned to users. Per SAP's own guidance, standard roles must never "
            "be modified and should not be assigned directly -- copy each into the customer "
            "namespace (Y_/Z_) and assign the copy instead, then remove the SAP-delivered "
            "assignment from the affected users.",
        },
    )
