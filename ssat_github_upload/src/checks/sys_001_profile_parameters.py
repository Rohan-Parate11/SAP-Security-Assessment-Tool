from __future__ import annotations

import json
from pathlib import Path

from checks.base import CheckResult, CheckSpec, RiskTile, now_iso, register
from connectors.base import SAPConnector

CHECK = CheckSpec(
    check_id="SYS-001",
    domain="System Hardening",
    question="Profile parameters aligned with SAP recommendations?",
    data_source="FM TH_GET_PARAMETER, one call per parameter in the baseline library",
    collection_method="Direct RFC calls against a configurable baseline parameter list",
    # Marked system-wide since profile parameters aren't client data (no MANDT), but this is an
    # approximation worth knowing: TH_GET_PARAMETER only reports the value on whichever application
    # server instance handled this RFC call. On a multi-instance landscape, another instance could
    # have an override. Most login/* security parameters are normally set once in the DEFAULT
    # profile and inherited everywhere, but that's a convention, not something this check verifies.
    scope="system-wide",
    risk_tiles=[
        RiskTile("Params off baseline", "warn", lambda s: s.get("non_compliant_count") or None),
    ],
)

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "baseline_profile_parameters.json"

_COMPARISONS = {
    "eq": lambda actual, expected: actual.strip().upper() == expected.strip().upper(),
    "gte": lambda actual, expected: _safe_int(actual) is not None and _safe_int(actual) >= int(expected),
    "lte": lambda actual, expected: _safe_int(actual) is not None and _safe_int(actual) <= int(expected),
}


def _safe_int(value: str) -> int | None:
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


def _load_baseline(config: dict) -> list[dict[str, str]]:
    path = Path(config.get("sys_001", {}).get("baseline_file") or _DEFAULT_CONFIG_PATH)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@register(CHECK)
def collect(connector: SAPConnector, config: dict) -> CheckResult:
    baseline = _load_baseline(config)

    findings = []
    for entry in baseline:
        param = entry["parameter"]
        try:
            result = connector.call_fm("TH_GET_PARAMETER", PARAMETER_NAME=param)
            actual = str(result.get("PARAMETER_VALUE", "")).strip()
            compare = _COMPARISONS.get(entry["comparison"])
            compliant = compare(actual, entry["recommended"]) if compare and actual else None
            findings.append(
                {
                    "parameter": param,
                    "description": entry.get("description", ""),
                    "current_value": actual,
                    "recommended_value": entry["recommended"],
                    "comparison": entry["comparison"],
                    "compliant": compliant,
                }
            )
        except Exception as exc:  # noqa: BLE001
            findings.append(
                {
                    "parameter": param,
                    "description": entry.get("description", ""),
                    "current_value": None,
                    "recommended_value": entry["recommended"],
                    "comparison": entry["comparison"],
                    "compliant": None,
                    "error": str(exc),
                }
            )

    non_compliant = sum(1 for f in findings if f["compliant"] is False)
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
        summary={"parameters_checked": len(findings), "non_compliant_count": non_compliant},
    )
