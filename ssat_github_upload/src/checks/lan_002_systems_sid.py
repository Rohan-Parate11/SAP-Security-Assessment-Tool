from __future__ import annotations

from checks.base import CheckResult, CheckSpec, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="LAN-002",
    domain="SAP Landscape",
    question="List all SAP systems and SID.",
    data_source="FM RFC_SYSTEM_INFO (this system's identity) + table T000 (clients)",
    collection_method="Direct RFC call + RFC_READ_TABLE on T000",
    scope="system-wide",  # T000 lists every client on the system, not just the connected one
)

# NOTE: RFC_SYSTEM_INFO only describes the system this connector is pointed
# at. A true multi-system landscape inventory is the list of connector
# configs the tool itself is run against (see config/connection.json) -- one
# assessment run per SID. This check records that one system's identity and
# its defined clients so it can be reconciled against the consultant's
# landscape inventory.
#
# System identity is a single descriptive fact about the run, not a "record"
# to review like a client is -- it lives in `summary`, not `findings`, so
# record_count and client_count always agree (they used to diverge by
# exactly one, which read as a bug in the UI).


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    findings = []
    errors = []
    system_identity = {}

    try:
        info = connector.call_fm("RFC_SYSTEM_INFO")
        sysinfo = info.get("RFCSI_EXPORT", {})
        system_identity = {
            "sid": sysinfo.get("RFCSYSID", "").strip(),
            "host": sysinfo.get("RFCHOST", "").strip(),
            "db_system": sysinfo.get("RFCDBSYS", "").strip(),
            "db_host": sysinfo.get("RFCDBHOST", "").strip(),
            "sap_release": sysinfo.get("RFCSAPRL", "").strip(),
            "kernel_release": sysinfo.get("RFCKERNRL", "").strip(),
            "os": sysinfo.get("RFCOPSYS", "").strip(),
            "ip_address": sysinfo.get("RFCIPADDR", "").strip(),
        }
    except Exception as exc:  # noqa: BLE001 - surfaced in errors, not raised
        errors.append(f"RFC_SYSTEM_INFO failed: {exc}")

    try:
        clients = connector.read_table("T000", fields=["MANDT", "MTEXT", "ORT01", "CCCATEGORY", "LOGSYS"])
        for c in clients:
            findings.append(
                {
                    "client": c.get("MANDT", "").strip(),
                    "description": c.get("MTEXT", "").strip(),
                    "city": c.get("ORT01", "").strip(),
                    "category": c.get("CCCATEGORY", "").strip(),
                    "logical_system": c.get("LOGSYS", "").strip(),
                }
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"T000 read failed: {exc}")

    connected_client = str(config.get("client", "")).strip()
    connected = next((f for f in findings if f["client"] == connected_client), None)
    category_labels = {"P": "Production", "T": "Test", "C": "Customizing", "D": "Demo", "S": "SAP reference"}
    connected_category = connected["category"] if connected else ""

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
            "system_identity": system_identity,
            "client_count": len(findings),
            "connected_client": connected_client,
            "connected_client_description": connected["description"] if connected else "",
            "connected_client_category": connected_category,
            "connected_client_category_label": category_labels.get(connected_category, connected_category),
            "connected_client_is_production": connected_category == "P",
        },
        errors=errors,
    )
