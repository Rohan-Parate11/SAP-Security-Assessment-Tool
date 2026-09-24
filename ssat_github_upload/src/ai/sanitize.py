"""Builds the only view of a run's results that may ever cross into an LLM
call. Extends output/narrative.py's extraction-only philosophy ("no risk or
maturity judgement is added") one step further: no row-level data either.

This is a structural rule, not a per-check allowlist. Several checks'
`summary` dicts embed a literal list of usernames (e.g. prv_001_sap_all.py's
`summary["users"]` / `summary["removal_candidates"]`, usr_007_standard_users.py's
`summary["unlocked_standard_users"]`) -- real customer identifiers that must
never leave the machine. Rather than hand-maintaining an allowlist per
check_id (which a new check could silently violate), every `summary` value
that isn't a plain scalar (str/int/float/bool) is dropped, for every check,
unconditionally. `key_finding` (already-aggregated narrative prose) and
`kpi_tiles` (already scalar-valued) pass through unchanged.
"""

from __future__ import annotations

from typing import Any

_KEPT_CHECK_KEYS = (
    "check_id",
    "domain",
    "question",
    "scope",
    "record_count",
    "error_count",
    "key_finding",
)


def _sanitize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in summary.items() if isinstance(v, (str, int, float, bool)) or v is None}


def build_ai_safe_context(run_summary: dict[str, Any]) -> dict[str, Any]:
    meta = run_summary.get("meta") or {}
    checks = []
    for check in run_summary.get("checks") or []:
        sanitized = {key: check.get(key) for key in _KEPT_CHECK_KEYS}
        sanitized["summary"] = _sanitize_summary(check.get("summary") or {})
        checks.append(sanitized)

    return {
        "system_id": meta.get("system_id"),
        "run_at": meta.get("run_at"),
        "kpi_tiles": run_summary.get("kpi_tiles") or [],
        "checks": checks,
    }
