from __future__ import annotations

import json
from pathlib import Path

from checks.base import CheckResult, CheckSpec, RiskTile, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="FIO-006",
    domain="Fiori & Web",
    question="Required ICF services only active?",
    data_source="Table ICFSERVLOC (per-node activation status)",
    collection_method="RFC_READ_TABLE on ICFSERVLOC; cross-referenced against a curated denylist of "
    "services SAP's own Security Baseline Template flags for deactivation, and (if configured) "
    "the client's required-services allowlist",
    scope="system-wide",  # ICFSERVLOC has no MANDT -- ICF/HTTP services serve the whole system
    risk_tiles=[
        RiskTile("ICF services on hardening denylist", "crit", lambda s: s.get("denylist_hit_count") or None),
    ],
)

# ICFSERVICE (the service tree) is intentionally not read here: it has
# RFCOPTION*-style wide fields that overflow RFC_READ_TABLE's row-width limit
# (confirmed on a live system), and it isn't needed to answer this question --
# ICFSERVLOC's ICF_NAME + activation flag is sufficient.

_DEFAULT_DENYLIST_PATH = Path(__file__).resolve().parent.parent / "config" / "icf_denylist.json"


def _load_denylist(config: dict) -> dict[str, dict]:
    path = Path(config.get("fio_006", {}).get("denylist_file") or _DEFAULT_DENYLIST_PATH)
    with open(path, encoding="utf-8") as fh:
        entries = json.load(fh)
    # Matched on ICFSERVLOC's leaf node name -- that table stores only the node's own segment,
    # not its full hierarchical path (which would need walking ICFSERVICE's parent-GUID tree,
    # a table we can't read cheaply here -- see note above). This is a real limitation: a leaf
    # name like "echo" or "info" could in principle collide with an unrelated custom node
    # elsewhere in the tree. Treat a hit as "worth confirming in SICF", not a certainty.
    return {e["leaf_name"].lower(): e for e in entries}


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    errors = []
    activation_rows: list[dict[str, str]] = []

    try:
        activation_rows = connector.read_table("ICFSERVLOC", fields=["ICF_NAME", "ICFPARGUID", "ICFACTIVE", "ICFSRVGRP"])
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ICFSERVLOC read failed: {exc}")

    allowlist = set(config.get("fio_006", {}).get("required_services", []))
    try:
        denylist = _load_denylist(config)
    except Exception as exc:  # noqa: BLE001
        denylist = {}
        errors.append(f"Denylist load failed: {exc}")

    findings = []
    for row in activation_rows:
        clean = {k: v.strip() for k, v in row.items()}
        service_name = clean.get("ICF_NAME", "")
        deny_entry = denylist.get(service_name.lower())
        findings.append(
            {
                **clean,
                "outside_allowlist": bool(allowlist) and service_name not in allowlist,
                "denylist_match": deny_entry["service_path"] if deny_entry else None,
                "denylist_reason": deny_entry["reason"] if deny_entry else None,
            }
        )

    denylist_hits = [f for f in findings if f["denylist_match"]]
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
            "activation_records": len(findings),
            "allowlist_configured": bool(allowlist),
            "denylist_hit_count": len(denylist_hits),
            "denylist_hits": sorted({f["ICF_NAME"] for f in denylist_hits}),
            "note": "denylist_hits are active services SAP's own Security Baseline Template flags "
            "for deactivation unless explicitly needed for a business scenario -- the actionable "
            "figure here, versus the raw activation_records count which is just inventory. Matched "
            "on leaf node name (see code comment); confirm each hit's full path in SICF before acting.",
        },
        errors=errors,
    )
