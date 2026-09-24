from __future__ import annotations

from checks.base import CheckResult, CheckSpec, RiskTile, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="RFC-002",
    domain="RFC & Interfaces",
    question="Stored passwords reviewed?",
    data_source="Table RFCDES (RFC destination definitions) -- RFCDEST/RFCTYPE only",
    collection_method="RFC_READ_TABLE on RFCDES",
    scope="system-wide",  # RFCDES has no MANDT field -- same destinations regardless of client
    risk_tiles=[
        RiskTile("RFC destinations to review", "warn", lambda s: s.get("flagged_for_manual_review") or None),
    ],
)

# Confirmed against a live system via DDIF_FIELDINFO_GET: RFCDES does NOT have
# plain RFCSYSID/RFCHOST/RFCUSER columns. Destination target/logon detail is
# packed into a series of 250-char RFCOPTION* blob fields, and neither
# RFCDES2RFCDISPLAY nor RFC_GET_DESTINATIONS/RSRFC_DESTINATION_ATTRIBUTES was
# remote-enabled on the test system to decode them. So this check can only
# safely read RFCDEST + RFCTYPE via RFC_READ_TABLE; every ABAP connection
# (type '3', the type that carries a logon) is flagged for manual review in
# SM59 rather than guessing at the encoded credential data.


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    rows = connector.read_table("RFCDES", fields=["RFCDEST", "RFCTYPE"])

    findings = []
    for r in rows:
        rfctype = r.get("RFCTYPE", "").strip()
        findings.append(
            {
                "destination": r.get("RFCDEST", "").strip(),
                "type": rfctype,
                "needs_manual_review": rfctype == "3",
            }
        )

    flagged = sum(1 for f in findings if f["needs_manual_review"])
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
            "destination_count": len(findings),
            "flagged_for_manual_review": flagged,
            "note": "RFCDES stores logon/credential detail in opaque RFCOPTION* fields that "
            "RFC_READ_TABLE can't decode and no decoder FM was RFC-enabled on the test system. "
            "Type '3' (ABAP connection) destinations are flagged here for manual confirmation "
            "in SM59 of whether a password is stored vs. current-user/trusted-system logon.",
        },
    )
