"""Unit tests for ModelIntrospectionService (fake port, no network)."""

from __future__ import annotations

import pytest

from coffer.application.providers.ports import ModelIntrospectionService, ProviderIntrospectionPort


class _FakePort:
    def __init__(self, models=None, fail=None, dim=None):  # type: ignore[no-untyped-def]
        self.models = models or []
        self.fail = fail
        self.dim = dim
        self.seen_key: str | None = "UNSET"

    async def list_models(self, *, provider, base_url, api_key):  # type: ignore[no-untyped-def]
        self.seen_key = api_key
        if self.fail:
            raise self.fail
        return self.models

    async def test_chat(self, *, provider, model, base_url, api_key):  # type: ignore[no-untyped-def]
        self.seen_key = api_key
        if self.fail:
            raise self.fail

    async def test_embedding(self, *, provider, model, base_url, api_key):  # type: ignore[no-untyped-def]
        self.seen_key = api_key
        if self.fail:
            raise self.fail
        return self.dim


def _svc(port: ProviderIntrospectionPort, secrets=None):  # type: ignore[no-untyped-def]
    secrets = secrets or {"ref-x": "sk-secret"}
    return ModelIntrospectionService(port, lambda ref: secrets[ref])


async def test_list_models_resolves_credential_ref() -> None:
    port = _FakePort(models=["gpt-4o", "gpt-4o-mini"])
    result = await _svc(port).list_models(provider="openai", base_url=None, credential_ref="ref-x")
    assert result.models == ["gpt-4o", "gpt-4o-mini"]
    assert port.seen_key == "sk-secret"  # ref resolved server-side


async def test_list_models_no_ref_passes_no_key() -> None:
    port = _FakePort(models=["llama3"])
    await _svc(port).list_models(provider="ollama", base_url=None, credential_ref=None)
    assert port.seen_key is None


async def test_list_models_degrades_on_error() -> None:
    port = _FakePort(fail=RuntimeError("boom"))
    result = await _svc(port).list_models(provider="openai", base_url=None, credential_ref="ref-x")
    assert result.models == []
    assert "boom" in result.message  # never raises — picker falls back to manual


async def test_list_models_empty_message() -> None:
    port = _FakePort(models=[])
    result = await _svc(port).list_models(provider="openai", base_url=None, credential_ref="ref-x")
    assert result.models == []
    assert "manually" in result.message


async def test_test_connection_ok_and_fail() -> None:
    ok = await _svc(_FakePort()).test_connection(
        provider="openai", model="gpt-4o", base_url=None, credential_ref="ref-x"
    )
    assert ok.ok is True
    bad = await _svc(_FakePort(fail=RuntimeError("401 unauthorized"))).test_connection(
        provider="openai", model="gpt-4o", base_url=None, credential_ref="ref-x"
    )
    assert bad.ok is False
    assert "401" in bad.message


async def test_test_embedding_reports_dimension() -> None:
    res = await _svc(_FakePort(dim=1536)).test_embedding(
        provider="openai", model="text-embedding-3-small", base_url=None, credential_ref="ref-x"
    )
    assert res.ok is True
    assert res.detail["dimensions"] == 1536


@pytest.mark.acceptance(spec="008-agent-chat", scenario="test a model connection")
async def test_acceptance_test_connection() -> None:
    res = await _svc(_FakePort()).test_connection(
        provider="openai", model="gpt-4o", base_url=None, credential_ref="ref-x"
    )
    assert res.ok is True
