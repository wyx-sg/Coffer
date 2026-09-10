"""Remote transcription (spec channels FR-022).

The gate matters more than the happy path: audio must NEVER leave the machine
unless the user designated an internal connection that can take it. Every test
here that returns ``None`` is asserting exactly that.
"""

from __future__ import annotations

import pytest

from coffer.domain.provider.config import Protocol, ProviderConfig, ResolvedConnection
from coffer.infrastructure.llm.transcription import (
    RemoteTranscriber,
    remote_transcriber,
    remote_transcriber_factory,
)


def _conn(protocol: Protocol = Protocol.OPENAI, ref: str | None = "provider/x/key"):
    return ResolvedConnection(
        config=ProviderConfig(
            protocol=protocol, base_url="https://api.example/v1", credential_ref=ref
        ),
        model="gpt-4o-mini",
    )


def _resolver(value: str = "sk-secret"):
    def _r(ref: str) -> str:
        return value

    return _r


def test_no_connection_means_no_upload() -> None:
    """The default state of a fresh install: nothing configured, nothing sent."""
    assert remote_transcriber(None, _resolver()) is None


def test_anthropic_has_no_transcription_endpoint() -> None:
    assert remote_transcriber(_conn(Protocol.ANTHROPIC), _resolver()) is None


def test_ollama_is_not_used_for_transcription() -> None:
    assert remote_transcriber(_conn(Protocol.OLLAMA, ref=None), _resolver()) is None


def test_unknown_protocol_is_tried() -> None:
    """A gateway the probe could not classify is usually OpenAI-shaped."""
    assert isinstance(remote_transcriber(_conn(Protocol.UNKNOWN), _resolver()), RemoteTranscriber)


def test_an_unresolvable_credential_sends_nothing() -> None:
    """A revoked or missing key must not become an unauthenticated upload."""

    def _boom(ref: str) -> str:
        raise KeyError(ref)

    assert remote_transcriber(_conn(), _boom) is None


def test_openai_with_a_key_builds_a_transcriber() -> None:
    assert isinstance(remote_transcriber(_conn(), _resolver()), RemoteTranscriber)


def test_model_is_overridable_without_a_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COFFER_TRANSCRIBE_MODEL", "gateway-stt-v2")
    t = remote_transcriber(_conn(), _resolver())
    assert t is not None
    assert t._model == "gateway-stt-v2"


@pytest.mark.asyncio
async def test_factory_resolves_per_call() -> None:
    """The connection is read when a turn needs it, so designating one takes
    effect without a daemon restart."""
    connections: list[ResolvedConnection | None] = [None, _conn()]

    async def _resolve():
        return connections.pop(0)

    factory = remote_transcriber_factory(_resolve, _resolver())
    assert await factory() is None
    assert isinstance(await factory(), RemoteTranscriber)


@pytest.mark.asyncio
async def test_factory_swallows_a_resolve_failure() -> None:
    """A provider-service error must degrade to "hand over the file", never
    break the turn."""

    async def _boom():
        raise RuntimeError("db down")

    assert await remote_transcriber_factory(_boom, _resolver())() is None


@pytest.mark.asyncio
async def test_unreadable_audio_returns_empty_not_an_exception(tmp_path) -> None:
    t = remote_transcriber(_conn(), _resolver())
    assert t is not None
    assert await t.transcribe(str(tmp_path / "does-not-exist.ogg")) == ""
