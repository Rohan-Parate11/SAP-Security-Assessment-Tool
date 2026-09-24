"""Provider interface that the AI feature modules (exec_summary, remediation,
qa) are written against -- mirrors connectors/base.py's SAPConnector: a check
must not depend on the transport mechanism; an AI feature must not depend on
which LLM vendor answers it.

Deliberately the lowest common denominator across providers -- plain text in,
plain text or schema-validated JSON out -- rather than any one vendor's native
primitives (e.g. Claude's output_config.format / messages.parse()). A provider
implementation is free to use its own vendor-specific features (prompt
caching, tool use, etc.) internally, as long as it honors this contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract base for all LLM provider implementations (Claude, and future
    providers such as Gemini or OpenAI)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this provider, e.g. "claude"."""

    @abstractmethod
    def generate_text(self, context: str, instruction: str) -> str:
        """Return a plain-text response.

        Args:
            context: the large, reused part of the prompt (e.g. a run's
                sanitized results) -- kept separate from `instruction` so a
                provider that supports prompt caching can cache it across
                repeated calls for the same run.
            instruction: the small, per-call task description (varies every
                call -- what to write, or the question being asked).
        """

    @abstractmethod
    def generate_json(self, context: str, instruction: str, json_schema: dict[str, Any]) -> Any:
        """Return a response validated against `json_schema` (a JSON Schema
        dict). Must raise `ai.errors.AIProviderError` if the model's output
        cannot be parsed as JSON or does not validate against the schema.
        """
