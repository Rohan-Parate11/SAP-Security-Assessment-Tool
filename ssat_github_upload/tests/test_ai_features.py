"""Proves the three feature modules only ever hand the provider sanitized
context -- never the raw run_summary (which may contain username lists) --
using FakeProvider so no network call is made.
"""

from __future__ import annotations

from ai.exec_summary import generate_executive_summary
from ai.providers.fake_provider import FakeProvider
from ai.qa import answer_question
from ai.remediation import generate_remediation

_RUN_SUMMARY = {
    "meta": {"system_id": "S23", "run_at": "2026-09-23T10:00:00"},
    "kpi_tiles": [{"value": 426, "label": "Users holding SAP_ALL", "cls": "crit", "check_id": "PRV-001"}],
    "checks": [
        {
            "check_id": "PRV-001",
            "domain": "Privileged Access",
            "question": "Who has SAP_ALL?",
            "scope": "client-specific",
            "record_count": 426,
            "error_count": 0,
            "key_finding": "426 unique user(s) hold SAP_ALL.",
            "summary": {"user_count": 426, "users": ["JDOE", "MSMITH"]},
        }
    ],
}


def test_exec_summary_never_sees_raw_usernames():
    fake = FakeProvider(text_response="A narrative summary.")
    result = generate_executive_summary(_RUN_SUMMARY, provider=fake)
    assert result == "A narrative summary."
    call = fake.calls[0]
    assert "JDOE" not in call["context"]
    assert "JDOE" not in call["instruction"]
    assert "426" in call["context"]  # the aggregate count is still there


def test_remediation_calls_generate_json_with_schema():
    fake = FakeProvider(json_response={"items": [{"check_id": "PRV-001", "label": "x", "recommendation": "y", "steps": ["z"]}]})
    result = generate_remediation(_RUN_SUMMARY, provider=fake)
    assert result == [{"check_id": "PRV-001", "label": "x", "recommendation": "y", "steps": ["z"]}]
    assert "JDOE" not in fake.calls[0]["context"]
    assert fake.calls[0]["json_schema"]["required"] == ["items"]


def test_remediation_skips_call_when_no_flagged_findings():
    fake = FakeProvider()
    empty_run = {**_RUN_SUMMARY, "kpi_tiles": []}
    result = generate_remediation(empty_run, provider=fake)
    assert result == []
    assert fake.calls == []


def test_qa_folds_history_into_instruction():
    fake = FakeProvider(text_response="An answer.")
    history = [{"question": "How many checks ran?", "answer": "20."}]
    result = answer_question(_RUN_SUMMARY, "What about SAP_ALL?", history=history, provider=fake)
    assert result == "An answer."
    instruction = fake.calls[0]["instruction"]
    assert "How many checks ran?" in instruction
    assert "What about SAP_ALL?" in instruction
    assert "JDOE" not in fake.calls[0]["context"]
