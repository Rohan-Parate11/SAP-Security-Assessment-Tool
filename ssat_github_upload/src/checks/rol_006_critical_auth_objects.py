from __future__ import annotations

import json
from pathlib import Path

from checks._auth_lookup import active_users_for_roles, roles_with_auth_object
from checks.base import CheckResult, CheckSpec, RiskTile, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="ROL-006",
    domain="Roles & Authorizations",
    question="Critical authorization objects reviewed?",
    data_source="Table AGR_1251 (role authorization values) for a configurable list of critical objects",
    collection_method="RFC_READ_TABLE on AGR_1251 and AGR_USERS",
    risk_tiles=[
        RiskTile(
            "Critical auth objects assigned to users",
            "warn",
            lambda s: s.get("critical_objects_in_use_count") or None,
        ),
    ],
)

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "critical_auth_objects.json"


def _load_critical_objects(config: dict) -> list[dict[str, str]]:
    path = Path(config.get("rol_006", {}).get("critical_objects_file") or _DEFAULT_CONFIG_PATH)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    critical_objects = _load_critical_objects(config)

    findings = []
    for entry in critical_objects:
        obj = entry["object"]
        roles = roles_with_auth_object(connector, obj)
        assignments = active_users_for_roles(connector, roles)
        users = sorted({a.get("UNAME", "").strip() for a in assignments if a.get("UNAME")})
        findings.append(
            {
                "auth_object": obj,
                "description": entry.get("description", ""),
                "role_count": len(roles),
                "roles": roles,
                "user_count": len(users),
                "users": users,
            }
        )

    in_use = [f["auth_object"] for f in findings if f["user_count"] > 0]

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
            "objects_reviewed": len(findings),
            "critical_objects_in_use_count": len(in_use),
            "critical_objects_in_use": in_use,
        },
    )
