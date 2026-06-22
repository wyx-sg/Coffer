"""Unit tests for ModelIntrospectionService (fake port, no network)."""

from __future__ import annotations

import pytest

from coffer.application.providers.ports import ModelIntrospectionService, ProviderIntrospectionPort


class _FakePort:
    def __init__(self, models=None, fail=None, dim=None, protocol="openai"):  # type: ignore[no-untyped-def]
        self.models = models or []
        self.fail = fail
        self.dim = dim
        self.protocol = protocol
        self.seen_key: str | None = "UNSET"

    async def detect_protocol(self, *, base_url, api_key):  # type: ignore[no-untyped-def]
        self.seen_key = api_key
        if self.fail:
            raise self.fail
        return self.protocol

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


async def test_list_models_prefers_inline_secret() -> None:
    # An unsaved (inline) secret is used verbatim — the resolver is never called.
    def _no_resolve(_ref: str) -> str:
        raise AssertionError("resolver must not run when an inline secret is given")

    port = _FakePort(models=["gpt-4o"])
    svc = ModelIntrospectionService(port, _no_resolve)
    result = await svc.list_models(
        provider="openai", base_url=None, credential_ref=None, secret_value="sk-inline"
    )
    assert result.models == ["gpt-4o"]
    assert port.seen_key == "sk-inline"


async def test_inline_secret_overrides_credential_ref() -> None:
    # When both are present the inline secret wins (resolver not consulted).
    def _no_resolve(_ref: str) -> str:
        raise AssertionError("inline secret must take precedence over credential_ref")

    port = _FakePort()
    svc = ModelIntrospectionService(port, _no_resolve)
    res = await svc.test_connection(
        provider="openai",
        model="gpt-4o",
        base_url=None,
        credential_ref="ref-x",
        secret_value="sk-inline",
    )
    assert res.ok is True
    assert port.seen_key == "sk-inline"


@pytest.mark.acceptance(spec="008-agent-chat", scenario="test a model connection")
async def test_acceptance_test_connection() -> None:
    res = await _svc(_FakePort()).test_connection(
        provider="openai", model="gpt-4o", base_url=None, credential_ref="ref-x"
    )
    assert res.ok is True


@pytest.mark.acceptance(
    spec="011-provider-switching",
    scenario="test or fetch models with an inline unsaved secret",
)
async def test_acceptance_inline_unsaved_secret() -> None:
    # The dialog can test/fetch before the connection (and its credential ref)
    # exist — the typed key is passed straight through.
    def _no_resolve(_ref: str) -> str:
        raise AssertionError("no credential ref exists yet")

    port = _FakePort(models=["claude-opus-4-6"])
    svc = ModelIntrospectionService(port, _no_resolve)
    listed = await svc.list_models(
        provider="anthropic", base_url=None, credential_ref=None, secret_value="sk-ant-inline"
    )
    tested = await svc.test_connection(
        provider="anthropic",
        model="claude-opus-4-6",
        base_url=None,
        credential_ref=None,
        secret_value="sk-ant-inline",
    )
    assert listed.models == ["claude-opus-4-6"]
    assert tested.ok is True
    assert port.seen_key == "sk-ant-inline"


async def test_detect_protocol_returns_port_classification() -> None:
    port = _FakePort(protocol="openai")
    got = await _svc(port).detect_protocol(
        base_url="https://gw/v1", credential_ref=None, secret_value="sk-x"
    )
    assert got == "openai"
    assert port.seen_key == "sk-x"  # inline secret reaches the probe


async def test_detect_protocol_degrades_to_unknown_on_error() -> None:
    port = _FakePort(fail=RuntimeError("boom"))
    got = await _svc(port).detect_protocol(base_url="https://gw/v1", credential_ref="ref-x")
    assert got == "unknown"  # never raises — agent page falls back to user choice
