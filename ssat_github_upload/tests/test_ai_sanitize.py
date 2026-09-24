"""Highest-priority test in this feature: proves the redaction boundary holds
against the two checks confirmed to embed raw username lists, using fixtures
shaped exactly like their real summary dicts.
"""

from __future__ import annotations

from ai.sanitize import build_ai_safe_context

_RUN_SUMMARY = {
    "meta": {
        "system_key": "abc123",
        "system_id": "S23",
        "client": "100",
        "run_at": "2026-09-23T10:00:00",
        "excel_filename": "SAP_Security_Assessment_S23.xlsx",
    },
    "kpi_tiles": [{"value": 426, "label": "Users holding SAP_ALL", "cls": "crit", "check_id": "PRV-001"}],
    "rfc_trace": [{"call": "RFC_READ_TABLE(USR02)", "ok": True}],
    "checks": [
        {
            "check_id": "PRV-001",
            "domain": "Privileged Access",
            "question": "Who has SAP_ALL?",
            "scope": "client-specific",
            "record_count": 426,
            "error_count": 0,
            "collected_at": "2026-09-23T09:55:00",
            "errors": [],
            "key_finding": "426 unique user(s) hold SAP_ALL: 379 active/unlocked, 47 locked.",
            "summary": {
                "user_count": 426,
                "users": ["JDOE", "MSMITH", "ASINGH"],
                "active_unlocked_count": 379,
                "locked_count": 47,
                "removal_candidate_count": 240,
                "removal_candidates": ["JDOE", "ASINGH"],
                "note": "removal_candidates are users holding SAP_ALL who are unlocked but dormant.",
            },
        },
        {
            "check_id": "USR-007",
            "domain": "User Administration",
            "question": "Standard users secured (SAP*, DDIC, EARLYWATCH)?",
            "scope": "client-specific",
            "record_count": 3,
            "error_count": 0,
            "collected_at": "2026-09-23T09:56:00",
            "errors": [],
            "key_finding": "Standard account(s) currently unlocked: DDIC.",
            "summary": {
                "standard_users_checked": ["SAP*", "DDIC", "EARLYWATCH"],
                "unlocked_standard_users": ["DDIC"],
            },
        },
    ],
}


def _all_string_values(obj) -> list[str]:
    """Flatten every string leaf value out of a nested dict/list structure."""
    out: list[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(_all_string_values(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_all_string_values(v))
    elif isinstance(obj, str):
        out.append(obj)
    return out


def test_no_username_list_survives():
    safe = build_ai_safe_context(_RUN_SUMMARY)
    leaked = [v for v in _all_string_values(safe) if v in {"JDOE", "MSMITH", "ASINGH", "DDIC"}]
    assert leaked == []


def test_scalar_summary_values_are_kept():
    safe = build_ai_safe_context(_RUN_SUMMARY)
    prv001 = next(c for c in safe["checks"] if c["check_id"] == "PRV-001")
    assert prv001["summary"]["user_count"] == 426
    assert prv001["summary"]["active_unlocked_count"] == 379
    assert prv001["summary"]["removal_candidate_count"] == 240
    assert "users" not in prv001["summary"]
    assert "removal_candidates" not in prv001["summary"]


def test_key_finding_and_kpi_tiles_pass_through():
    safe = build_ai_safe_context(_RUN_SUMMARY)
    prv001 = next(c for c in safe["checks"] if c["check_id"] == "PRV-001")
    assert "426 unique user(s)" in prv001["key_finding"]
    assert safe["kpi_tiles"] == _RUN_SUMMARY["kpi_tiles"]


def test_meta_is_trimmed_to_system_id_and_run_at():
    safe = build_ai_safe_context(_RUN_SUMMARY)
    assert safe["system_id"] == "S23"
    assert safe["run_at"] == "2026-09-23T10:00:00"
    assert "system_key" not in safe
    assert "excel_filename" not in safe


def test_rfc_trace_and_raw_errors_are_dropped():
    safe = build_ai_safe_context(_RUN_SUMMARY)
    assert "rfc_trace" not in safe
    for check in safe["checks"]:
        assert "errors" not in check
        assert "collected_at" not in check
