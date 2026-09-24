"""Tests the report data-assembly logic (heat map bucketing, roadmap
grouping, context building, domain-prefix stripping, datetime formatting)
without invoking a browser -- see pdf_report.py's module docstring for why
that split exists.
"""

from __future__ import annotations

from output.pdf_report import (
    build_heat_map,
    build_report_context,
    format_report_datetime,
    group_remediation_roadmap,
)

# Domain strings carry the framework's absolute index (e.g. "5. Privileged
# Access" -- this run has no "1." or "6." domain), exactly as check modules
# really store them -- fixtures must include the prefixes to exercise the
# stripping/renumbering logic, not just the already-clean case.
_KPI_TILES = [
    {"value": 426, "label": "Users holding SAP_ALL", "cls": "crit", "check_id": "PRV-001"},
    {"value": 1, "label": "Standard users unlocked", "cls": "crit", "check_id": "USR-007"},
    {"value": 213, "label": "Dormant unlocked users", "cls": "warn", "check_id": "USR-004"},
]

_CHECKS = [
    {"check_id": "PRV-001", "domain": "5. Privileged Access", "question": "Who has SAP_ALL?", "scope": "client-specific", "record_count": 426, "error_count": 0, "key_finding": "426 users hold SAP_ALL."},
    {"check_id": "USR-007", "domain": "3. User Administration", "question": "Standard users secured?", "scope": "client-specific", "record_count": 3, "error_count": 0, "key_finding": "DDIC unlocked."},
    {"check_id": "USR-004", "domain": "3. User Administration", "question": "Dormant users reviewed?", "scope": "client-specific", "record_count": 440, "error_count": 0, "key_finding": "213 dormant unlocked."},
    {"check_id": "LAN-001", "domain": "2. SAP Landscape", "question": "Components and versions?", "scope": "system-wide", "record_count": 100, "error_count": 0, "key_finding": "100 components found."},
]

_RUN_SUMMARY = {
    "run_name": "S21_20260810_205146",
    "meta": {"system_id": "S21", "run_at": "2026-08-10T20:51:50"},
    "kpi_tiles": _KPI_TILES,
    "checks": _CHECKS,
}

_AI_INSIGHTS = {
    "executive_summary": "Overall posture is moderate, with a few critical gaps.",
    "generated_at": "2026-09-24T00:31:31",
    "provider": "groq",
    "remediation": [
        {"check_id": "PRV-001", "label": "Users holding SAP_ALL", "recommendation": "Revoke SAP_ALL.", "steps": ["a", "b"]},
        {"check_id": "USR-007", "label": "Standard users unlocked", "recommendation": "Lock DDIC.", "steps": ["a"]},
        {"check_id": "USR-004", "label": "Dormant unlocked users", "recommendation": "Lock dormant accounts.", "steps": ["a"]},
    ],
}


def test_heat_map_strips_domain_prefixes():
    heat_map = build_heat_map(_CHECKS, _KPI_TILES)
    domains = {row["domain"] for row in heat_map}
    assert domains == {"SAP Landscape", "User Administration", "Privileged Access"}


def test_heat_map_buckets_by_domain_and_severity():
    heat_map = build_heat_map(_CHECKS, _KPI_TILES)
    by_domain = {row["domain"]: row for row in heat_map}
    assert by_domain["Privileged Access"] == {"domain": "Privileged Access", "critical": 1, "warning": 0, "clean": 0}
    assert by_domain["User Administration"] == {"domain": "User Administration", "critical": 1, "warning": 1, "clean": 0}
    assert by_domain["SAP Landscape"] == {"domain": "SAP Landscape", "critical": 0, "warning": 0, "clean": 1}


def test_heat_map_rows_follow_domain_order_not_source_prefix():
    heat_map = build_heat_map(_CHECKS, _KPI_TILES)
    domains_in_order = [row["domain"] for row in heat_map]
    # Source prefixes are 2/3/5 -- confirms ordering comes from _DOMAIN_ORDER,
    # not the (stripped-away) embedded numbers.
    assert domains_in_order == ["SAP Landscape", "User Administration", "Privileged Access"]


def test_heat_map_does_not_double_count_a_check_with_two_kpi_tiles():
    # Reproduces the real bug: ROL-005 contributed two kpi_tiles ("SAP
    # standard roles directly assigned" and "Unused custom roles"), both
    # crit. A naive sum over kpi_tiles counted it twice; the heat map (and
    # the totals derived from it) must count the check once.
    checks = [
        {"check_id": "ROL-005", "domain": "4. Roles & Authorizations", "question": "Roles?", "scope": "client-specific", "record_count": 10, "error_count": 0, "key_finding": "x"},
    ]
    tiles = [
        {"value": 909, "label": "SAP standard roles directly assigned", "cls": "crit", "check_id": "ROL-005"},
        {"value": 496, "label": "Unused custom roles", "cls": "crit", "check_id": "ROL-005"},
    ]
    heat_map = build_heat_map(checks, tiles)
    assert heat_map == [{"domain": "Roles & Authorizations", "critical": 1, "warning": 0, "clean": 0}]


def test_roadmap_groups_critical_as_immediate():
    roadmap = group_remediation_roadmap(_AI_INSIGHTS["remediation"], _KPI_TILES)
    immediate_ids = {r["check_id"] for r in roadmap["immediate"]}
    near_term_ids = {r["check_id"] for r in roadmap["near_term"]}
    assert immediate_ids == {"PRV-001", "USR-007"}
    assert near_term_ids == {"USR-004"}


def test_format_report_datetime():
    formatted = format_report_datetime("2026-08-10T20:51:50")
    # "10-Aug-2026 20:51:50 <timezone name>" -- date-month-year, month spelled
    # out, space (not "T") between date and time, timezone present. (The
    # timezone name itself may legitimately contain the letter "T" -- e.g.
    # "India Standard Time" -- so check the date/time split precisely rather
    # than searching the whole string for "T".)
    date_part, time_part, tz_part = formatted.split(" ", 2)
    assert date_part == "10-Aug-2026"
    assert time_part == "20:51:50"
    assert tz_part  # some non-empty timezone label follows


def test_format_report_datetime_handles_empty_string():
    assert format_report_datetime("") == ""


def test_build_report_context_assembles_everything():
    ctx = build_report_context(_RUN_SUMMARY, _AI_INSIGHTS)
    assert ctx["system_id"] == "S21"
    assert ctx["run_at"].startswith("10-Aug-2026 20:51:50")
    assert ctx["ai_provider"] == "groq"
    assert ctx["executive_summary"] == _AI_INSIGHTS["executive_summary"]
    assert ctx["domains"] == ["SAP Landscape", "User Administration", "Privileged Access"]
    assert ctx["totals"] == {"checks": 4, "critical": 2, "warning": 1, "clean": 1}
    assert len(ctx["roadmap"]["immediate"]) == 2
    assert len(ctx["roadmap"]["near_term"]) == 1


def test_build_report_context_strips_check_id_from_client_facing_data():
    # check_id (PRV-001 etc.) is an internal identifier from building the
    # tool's checklist and code -- must not appear anywhere in the data handed
    # to the client-facing template.
    ctx = build_report_context(_RUN_SUMMARY, _AI_INSIGHTS)
    for tile in ctx["kpi_tiles"]:
        assert "check_id" not in tile
    for tier in ctx["roadmap"].values():
        for item in tier:
            assert "check_id" not in item
    for domain_checks in ctx["checks_by_domain"].values():
        for check in domain_checks:
            assert "check_id" not in check


def test_build_report_context_handles_missing_ai_insights_gracefully():
    ctx = build_report_context(_RUN_SUMMARY, {})
    assert ctx["executive_summary"] == ""
    assert ctx["roadmap"] == {"immediate": [], "near_term": []}
