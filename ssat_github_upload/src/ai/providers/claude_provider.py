"""Claude (Anthropic) implementation of LLMProvider.

Reads credentials the SDK's own way (ANTHROPIC_API_KEY env var by default --
see anthropic.Anthropic()'s zero-arg constructor); never hardcode a key here.
Model is configurable via the AI_MODEL env var so a cheaper/pricier Claude
model can be swapped in without a code change, defaulting to Opus 5.
"""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic
import jsonschema

from ai.errors import AIProviderError
from ai.providers.base import LLMProvider

DEFAULT_MODEL = "claude-opus-5"
# Anthropic's minimum cacheable prefix is a few hundred to a few thousand
# tokens depending on model -- a short run's sanitized context may fall under
# it, in which case cache_control is simply a no-op (the API silently doesn't
# cache rather than erroring), so it's always safe to include.
_CONTEXT_CACHE_TTL = "1h"


class ClaudeProvider(LLMProvider):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or os.environ.get("AI_MODEL", DEFAULT_MODEL)
        self._client = anthropic.Anthropic()

    @property
    def name(self) -> str:
        return "claude"

    def _system_blocks(self, context: str) -> list[dict[str, Any]]:
        return [
            {
                "type": "text",
                "text": context,
                "cache_control": {"type": "ephemeral", "ttl": _CONTEXT_CACHE_TTL},
            }
        ]

    def generate_text(self, context: str, instruction: str) -> str:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=self._system_blocks(context),
                messages=[{"role": "user", "content": instruction}],
            )
        except anthropic.APIError as exc:
            raise AIProviderError(f"Claude request failed: {exc}") from exc
        except TypeError as exc:
            # The SDK raises a plain TypeError (not an APIError subclass) when no
            # credential source resolves at all -- see anthropic-cli.md's
            # resolution chain (ANTHROPIC_API_KEY -> ANTHROPIC_AUTH_TOKEN -> ...).
            raise AIProviderError(
                f"Claude API is not configured: {exc}. Set the ANTHROPIC_API_KEY environment variable "
                "and restart the server."
            ) from exc

        if response.stop_reason == "refusal":
            raise AIProviderError("Claude declined to answer this request.")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise AIProviderError("Claude returned no text content.")
        return text

    def generate_json(self, context: str, instruction: str, json_schema: dict[str, Any]) -> Any:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=8192,
                system=self._system_blocks(context),
                messages=[{"role": "user", "content": instruction}],
                output_config={"format": {"type": "json_schema", "schema": json_schema}},
            )
        except anthropic.APIError as exc:
            raise AIProviderError(f"Claude request failed: {exc}") from exc
        except TypeError as exc:
            raise AIProviderError(
                f"Claude API is not configured: {exc}. Set the ANTHROPIC_API_KEY environment variable "
                "and restart the server."
            ) from exc

        if response.stop_reason == "refusal":
            raise AIProviderError("Claude declined to answer this request.")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise AIProviderError("Claude returned no text content.")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIProviderError(f"Claude returned invalid JSON: {exc}") from exc
        try:
            jsonschema.validate(instance=data, schema=json_schema)
        except jsonschema.ValidationError as exc:
            raise AIProviderError(f"Claude's JSON did not match the expected shape: {exc.message}") from exc
        return data
