"""BuiltinRuntime construction + credential resolution (spec 008).

These exercise the parts that need no live model: the 503 (LlmNotConfigured)
path and provider/key resolution. Streaming + tool/confirmation behaviour over a
real LangChain model is covered by the (deferred) e2e tier; the port contract is
covered at the application layer with a fake runtime.
"""

from __future__ import annotations

import pytest

from coffer.domain.errors import LlmNotConfigured
from coffer.infrastructure.chat.builtin_runtime import BuiltinRuntime


class _FakeKeyring:
    def __init__(self, value: str | None = None) -> None:
        self._value = value

    def get(self, ref: str) -> str | None:
        return self._value


def _build(config, keyring):
    return BuiltinRuntime(config=config, gateway_url=None, gateway_token=None, keyring=keyring)


def test_cloud_provider_without_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LlmNotConfigured):
        _build({"model": "anthropic:claude-sonnet-4-6"}, _FakeKeyring(None))


def test_cloud_provider_with_credential_ok(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = _build(
        {"model": "anthropic:claude-sonnet-4-6", "credential_ref": "builtin/coffer/anthropic"},
        _FakeKeyring("sk-ant-xxx"),
    )
    assert rt is not None


def test_cloud_provider_with_env_key_ok(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-xxx")
    rt = _build({"model": "openai:gpt-4o"}, _FakeKeyring(None))
    assert rt is not None


def test_local_provider_needs_no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    rt = _build({"model": "ollama:llama3"}, _FakeKeyring(None))
    assert rt is not None
