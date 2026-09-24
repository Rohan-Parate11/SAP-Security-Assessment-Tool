"""Deterministic, no-network LLMProvider used by tests to prove the interface
holds -- that exec_summary/remediation/qa only ever depend on the LLMProvider
contract, never on anything Claude-specific.
"""

from __future__ import annotations

from typing import Any


class FakeProvider:
    """Records every call it receives and returns a fixed or callable response."""

    def __init__(self, text_response: str = "fake response", json_response: Any = None) -> None:
        self.text_response = text_response
        self.json_response = json_response if json_response is not None else {}
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "fake"

    def generate_text(self, context: str, instruction: str) -> str:
        self.calls.append({"method": "generate_text", "context": context, "instruction": instruction})
        return self.text_response

    def generate_json(self, context: str, instruction: str, json_schema: dict[str, Any]) -> Any:
        self.calls.append(
            {"method": "generate_json", "context": context, "instruction": instruction, "json_schema": json_schema}
        )
        return self.json_response
