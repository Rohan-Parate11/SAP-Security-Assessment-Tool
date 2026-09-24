"""Groq implementation of LLMProvider -- a third, free-tier option (fast,
open-weight models) alongside ClaudeProvider and GeminiProvider.

Reads credentials the SDK's own way (GROQ_API_KEY env var); never hardcode a
key here. Groq's chat completions API is OpenAI-compatible: no vendor-native
schema-constrained output mode is assumed here (unlike Claude's
output_config.format or Gemini's response_json_schema) -- generate_json just
asks for JSON mode and leans on this module's own jsonschema.validate() call
to catch anything that doesn't match, per LLMProvider's contract that a
provider without a feature simply doesn't use it.
"""

from __future__ import annotations

import json
import os
from typing import Any

import groq
import jsonschema

from ai.errors import AIProviderError
from ai.providers.base import LLMProvider

DEFAULT_MODEL = "openai/gpt-oss-20b"

# Groq applies its own (fairly low) default output-token cap when max_completion_tokens is
# omitted. gpt-oss-20b is a reasoning model -- it spends part of its budget on internal
# reasoning tokens before ever emitting the final answer -- so a run with many flagged
# findings (one remediation item per kpi_tile, ai/remediation.py) can hit that default cap
# before finishing the JSON, producing a "max completion tokens reached before generating a
# valid document" 400. Generous, explicit budgets avoid that; generate_text's output (a short
# narrative) needs far less than generate_json's (structured items, one per finding).
_MAX_TOKENS_TEXT = 4096
_MAX_TOKENS_JSON = 16384


class GroqProvider(LLMProvider):
    def __init__(self, model: str | None = None) -> None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise AIProviderError(
                "Groq API is not configured: set the GROQ_API_KEY environment variable and restart the server."
            )
        self._model = model or os.environ.get("AI_MODEL", DEFAULT_MODEL)
        self._client = groq.Groq(api_key=api_key)

    @property
    def name(self) -> str:
        return "groq"

    def _complete(self, context: str, instruction: str, *, response_format: dict | None = None, max_tokens: int):
        try:
            return self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": context},
                    {"role": "user", "content": instruction},
                ],
                response_format=response_format,
                max_completion_tokens=max_tokens,
            )
        except groq.APIStatusError as exc:
            raise AIProviderError(f"Groq request failed ({exc.status_code}): {exc.message}") from exc
        except groq.APIConnectionError as exc:
            raise AIProviderError(f"Groq request failed: {exc}") from exc

    def generate_text(self, context: str, instruction: str) -> str:
        response = self._complete(context, instruction, max_tokens=_MAX_TOKENS_TEXT)
        text = response.choices[0].message.content
        if not text:
            raise AIProviderError("Groq returned no text content.")
        return text

    def generate_json(self, context: str, instruction: str, json_schema: dict[str, Any]) -> Any:
        # Groq/OpenAI-style JSON mode requires the word "json" to appear in
        # the prompt and, unlike Claude's output_config.format or Gemini's
        # response_json_schema, never receives the schema structurally -- the
        # model only ever sees whatever we put in the prompt text. Without the
        # actual schema spelled out, a model will happily return valid JSON
        # under a differently-named key (observed: {"remediations": [...]}
        # instead of the required {"items": [...]}) -- correct content, wrong
        # shape. Spelling the schema out fixed that, but then surfaced a
        # second failure mode: the model echoed JSON-Schema meta-keywords
        # (observed: a literal "additionalProperties" key in its data) as if
        # they were data fields, having no native notion that a schema
        # *describes* a shape rather than being an example of one -- the
        # explicit "these are structural rules, not fields" instruction below
        # fixes that. This is all Groq-specific plumbing, kept out of the
        # shared, provider-agnostic instruction text in ai/remediation.py.
        json_instruction = (
            f"{instruction}\n\nRespond with a single valid JSON object only, no other text. It must "
            f"validate against this JSON Schema:\n{json.dumps(json_schema)}\n\nThe schema's own keywords "
            f'("type", "properties", "required", "additionalProperties", etc.) describe the shape your '
            f"response must have -- they are structural rules, never literal keys to include in your "
            f"response. Your response is data that satisfies the schema, not the schema itself."
        )
        response = self._complete(
            context, json_instruction, response_format={"type": "json_object"}, max_tokens=_MAX_TOKENS_JSON
        )
        text = response.choices[0].message.content
        if not text:
            raise AIProviderError("Groq returned no text content.")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIProviderError(f"Groq returned invalid JSON: {exc}") from exc
        try:
            jsonschema.validate(instance=data, schema=json_schema)
        except jsonschema.ValidationError as exc:
            raise AIProviderError(f"Groq's JSON did not match the expected shape: {exc.message}") from exc
        return data
