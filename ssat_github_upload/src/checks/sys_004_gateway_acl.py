from __future__ import annotations

from checks.base import CheckResult, CheckSpec, RiskTile, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="SYS-004",
    domain="System Hardening",
    question="Gateway security configured?",
    data_source="FM GWY_READ_SECURITY (live RFC gateway secinfo ACL)",
    collection_method="Direct RFC call, discovered live via TFDIR search since this isn't a documented "
    "table -- GWMON_GET_SEC_INFO/GWMON_GET_REG_INFO looked like better matches but are blocked by an "
    "internal GWMON_FORBIDDEN gate that even SAP_ALL doesn't bypass; GWY_READ_SECURITY (function group "
    "SGWY) works and returns the live secinfo ACL",
    scope="system-wide",  # gateway ACL is an instance-level security setting, not client data
    risk_tiles=[
        RiskTile("Gateway secinfo ACL", "crit", lambda s: "Open" if s.get("no_explicit_secinfo_configured") else None),
    ],
)

# Known limitation: this reads the SECINFO ACL (controls which users/hosts may start external
# programs via the gateway) via GWY_READ_SECURITY. REGINFO (controls which programs may register)
# is a separate, closely-related ACL this check does not yet cover -- the corresponding read FM
# wasn't identified in the time available. Treat this as SECINFO-only for now.
#
# When NO secinfo file is configured, the gateway falls back to a well-documented default of three
# wildcard rules (SEC_USER=*, HOST=local/internal in both directions) -- this is SAP's own
# permissive default, not a customer-configured restriction, and is exactly the condition behind
# the well-known "10KBLAZE"-class RFC gateway exploits. Seeing only these three rows back is itself
# the finding: no explicit secinfo ACL is configured.
def _is_default_fallback_row(row: dict[str, str]) -> bool:
    return (
        row.get("sec_user") == "*"
        and row.get("host") in ("local", "internal")
        and row.get("userhost") in ("local", "internal")
    )


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    findings = []
    errors = []

    try:
        result = connector.call_fm("GWY_READ_SECURITY", DISCONNECT="", GWHOST="", GWSERV="")
        rows = result.get("EXSEC", [])
        for r in rows:
            clean = {k.lower(): v.strip() for k, v in r.items()}
            findings.append(
                {
                    "allowed_user": clean.get("sec_user"),
                    "calling_host": clean.get("userhost"),
                    "target_host": clean.get("host"),
                    "program_id": clean.get("tp"),
                    "snc_name": clean.get("sncname") or None,
                    "is_default_fallback_rule": _is_default_fallback_row(clean),
                }
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"GWY_READ_SECURITY failed: {exc}")

    only_defaults = bool(findings) and all(f["is_default_fallback_rule"] for f in findings)
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
            "secinfo_rule_count": len(findings),
            "no_explicit_secinfo_configured": only_defaults,
            "note": "This covers SECINFO only (who may start external programs); REGINFO (which "
            "programs may register) is not yet covered -- see module docstring. "
            + (
                "All rules returned are SAP's default wildcard fallback -- no explicit secinfo ACL "
                "is configured on this gateway. This is the condition behind well-known RFC gateway "
                "exploits (e.g. the '10KBLAZE' class) and is worth remediating on any "
                "internet-reachable or otherwise sensitive gateway."
                if only_defaults
                else "Explicit secinfo rules are configured (not just the default fallback)."
            ),
        },
        errors=errors,
    )
