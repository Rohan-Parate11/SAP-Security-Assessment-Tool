from __future__ import annotations

import os

from ai.errors import AIProviderError
from ai.providers.base import LLMProvider
from ai.providers.claude_provider import ClaudeProvider
from ai.providers.gemini_provider import GeminiProvider
from ai.providers.groq_provider import GroqProvider

__all__ = ["LLMProvider", "ClaudeProvider", "GeminiProvider", "GroqProvider", "get_provider"]

_PROVIDERS = {
    "claude": ClaudeProvider,
    "gemini": GeminiProvider,
    "groq": GroqProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    """Factory picking an LLMProvider implementation.

    `name` (or the AI_PROVIDER env var, default "claude") selects which
    provider to instantiate -- this is the concrete lever a business/end user
    turns to point the tool at a different LLM vendor, once a provider for
    that vendor exists.
    """
    key = (name or os.environ.get("AI_PROVIDER", "claude")).lower()
    try:
        provider_cls = _PROVIDERS[key]
    except KeyError:
        available = ", ".join(sorted(_PROVIDERS))
        raise AIProviderError(f"Unknown AI provider '{key}'. Available: {available}.") from None
    return provider_cls()
