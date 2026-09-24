from __future__ import annotations

import pytest

from ai.errors import AIProviderError
from ai.providers import get_provider
from ai.providers.claude_provider import ClaudeProvider
from ai.providers.fake_provider import FakeProvider
from ai.providers.gemini_provider import GeminiProvider
from ai.providers.groq_provider import GroqProvider


def test_get_provider_defaults_to_claude(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    provider = get_provider()
    assert isinstance(provider, ClaudeProvider)
    assert provider.name == "claude"


def test_get_provider_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    provider = get_provider("gemini")
    assert isinstance(provider, GeminiProvider)
    assert provider.name == "gemini"


def test_gemini_provider_requires_a_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(AIProviderError, match="not configured"):
        GeminiProvider()


def test_get_provider_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    provider = get_provider("groq")
    assert isinstance(provider, GroqProvider)
    assert provider.name == "groq"


def test_groq_provider_requires_a_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(AIProviderError, match="not configured"):
        GroqProvider()


def test_get_provider_unknown_name_raises():
    with pytest.raises(AIProviderError, match="Unknown AI provider"):
        get_provider("mistral")


def test_fake_provider_records_calls():
    fake = FakeProvider(text_response="hello", json_response={"ok": True})
    text = fake.generate_text("context here", "say hi")
    data = fake.generate_json("context here", "give json", {"type": "object"})
    assert text == "hello"
    assert data == {"ok": True}
    assert [c["method"] for c in fake.calls] == ["generate_text", "generate_json"]
    assert fake.calls[0]["context"] == "context here"
