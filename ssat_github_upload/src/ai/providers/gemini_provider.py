"""Google Gemini implementation of LLMProvider -- the free-tier alternative
to ClaudeProvider, selected via AI_PROVIDER=gemini. Proves the abstraction
holds for a second real vendor, not just the FakeProvider test double.

Reads credentials the SDK's own way (GEMINI_API_KEY or GOOGLE_API_KEY env var
-- see genai.Client()'s zero-arg constructor); never hardcode a key here.
Unlike ClaudeProvider, this doesn't do prompt caching -- Gemini's context
caching API works differently and isn't available on the free tier, so this
provider simply doesn't use it, per LLMProvider's contract (caching is a
provider-internal optimization, not part of the interface).
"""

from __future__ import annotations

import json
import os
from typing import Any

import jsonschema
from google import genai
from google.genai import errors, types

from ai.errors import AIProviderError
from ai.providers.base import LLMProvider

DEFAULT_MODEL = "gemini-flash-latest"


class GeminiProvider(LLMProvider):
    def __init__(self, model: str | None = None) -> None:
        # Fail fast with a clear message rather than relying on whatever
        # exception the SDK happens to raise deep inside a request call for
        # missing credentials (that undocumented shape bit ClaudeProvider
        # during testing -- a bare TypeError, not an APIError subclass).
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise AIProviderError(
                "Gemini API is not configured: set the GEMINI_API_KEY (or GOOGLE_API_KEY) "
                "environment variable and restart the server."
            )
        self._model = model or os.environ.get("AI_MODEL", DEFAULT_MODEL)
        self._client = genai.Client()

    @property
    def name(self) -> str:
        return "gemini"

    def generate_text(self, context: str, instruction: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=instruction,
                config=types.GenerateContentConfig(system_instruction=context),
            )
        except errors.APIError as exc:
            raise AIProviderError(f"Gemini request failed ({exc.code}): {exc.message}") from exc
        if not response.text:
            raise AIProviderError("Gemini returned no text content.")
        return response.text

    def generate_json(self, context: str, instruction: str, json_schema: dict[str, Any]) -> Any:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=instruction,
                config=types.GenerateContentConfig(
                    system_instruction=context,
                    response_mime_type="application/json",
                    response_json_schema=json_schema,
                ),
            )
        except errors.APIError as exc:
            raise AIProviderError(f"Gemini request failed ({exc.code}): {exc.message}") from exc
        if not response.text:
            raise AIProviderError("Gemini returned no text content.")
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise AIProviderError(f"Gemini returned invalid JSON: {exc}") from exc
        try:
            jsonschema.validate(instance=data, schema=json_schema)
        except jsonschema.ValidationError as exc:
            raise AIProviderError(f"Gemini's JSON did not match the expected shape: {exc.message}") from exc
        return data
