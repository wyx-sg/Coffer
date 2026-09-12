"""Unit tests for :class:`EmbeddingConfigService`.

The service holds the two things the domain cannot: the lookup of the NAMED
connection (a port) and the rules for refusing a connection that cannot embed.
Both are exercised here against fakes — no repo, no vault, no HTTP.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.embedding_config_service import (
    DEFAULT_DIMENSIONS,
    EmbeddingConfigService,
)
from coffer.domain.audit import AuditEntry
from coffer.domain.embedding_config import EmbeddingEndpoint, GlobalEmbeddingConfig
from coffer.domain.errors import ConfigValidationError

pytestmark = pytest.mark.asyncio


class FakeAuditRepo:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def insert(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    async def repoint(self, kind: str, old_name: str, new_name: str) -> int:
        return 0

    async def query(self, **_: object) -> list[AuditEntry]:
        return list(self.entries)


class FakeRepo:
    """The singleton row, in memory."""

    def __init__(self, cfg: GlobalEmbeddingConfig | None = None) -> None:
        self.cfg = cfg

    async def get(self) -> GlobalEmbeddingConfig | None:
        return self.cfg

    async def set(
        self,
        *,
        enabled: bool,
        connection: str | None,
        model: str | None,
        dimensions: int,
        default_chunk_size: int,
        default_chunk_overlap: int,
    ) -> GlobalEmbeddingConfig:
        self.cfg = GlobalEmbeddingConfig(
            enabled=enabled,
            connection=connection,
            model=model,
            dimensions=dimensions,
            default_chunk_size=default_chunk_size,
            default_chunk_overlap=default_chunk_overlap,
            updated_at=datetime(2026, 9, 12, tzinfo=UTC),
        )
        return self.cfg


class FakeConnections:
    """``EmbeddingConnectionPort`` over a dict of named endpoints."""

    def __init__(self, **endpoints: EmbeddingEndpoint) -> None:
        self.endpoints = dict(endpoints)
        self.asked: list[str] = []

    async def endpoint(self, name: str) -> EmbeddingEndpoint | None:
        self.asked.append(name)
        return self.endpoints.get(name)


def _endpoint(
    protocol: str = "openai",
    *,
    base_url: str = "https://api.openai.com/v1",
    credential_ref: str | None = "provider/acme/key",
    offered_models: tuple[str, ...] | None = ("text-embedding-3-large",),
) -> EmbeddingEndpoint:
    return EmbeddingEndpoint(
        protocol=protocol,
        base_url=base_url,
        credential_ref=credential_ref,
        offered_models=offered_models,
    )


def _stored(
    *,
    enabled: bool = True,
    connection: str | None = "acme",
    model: str | None = "text-embedding-3-large",
    dimensions: int = 3072,
) -> GlobalEmbeddingConfig:
    return GlobalEmbeddingConfig(
        enabled=enabled,
        connection=connection,
        model=model,
        dimensions=dimensions,
        default_chunk_size=512,
        default_chunk_overlap=64,
        updated_at=datetime(2026, 9, 12, tzinfo=UTC),
    )


def _service(repo: FakeRepo, connections: FakeConnections) -> EmbeddingConfigService:
    return EmbeddingConfigService(
        repo=repo, audit=AuditService(FakeAuditRepo()), connections=connections
    )


# --- get() -------------------------------------------------------------------


async def test_get_returns_a_disabled_default_when_never_configured() -> None:
    cfg = await _service(FakeRepo(), FakeConnections()).get()
    assert cfg.enabled is False
    assert cfg.connection is None and cfg.model is None
    assert cfg.dimensions == DEFAULT_DIMENSIONS


# --- resolve(): every way vector degrades to keyword --------------------------


async def test_resolve_is_none_when_the_switch_is_off() -> None:
    svc = _service(FakeRepo(_stored(enabled=False)), FakeConnections(acme=_endpoint()))
    assert await svc.resolve() is None


async def test_resolve_is_none_when_no_connection_is_named() -> None:
    svc = _service(FakeRepo(_stored(connection=None)), FakeConnections(acme=_endpoint()))
    assert await svc.resolve() is None


async def test_resolve_is_none_when_the_named_connection_is_gone() -> None:
    """The connection was deleted after the config was saved: retrieval degrades
    to keyword rather than erroring at read time."""
    connections = FakeConnections()
    svc = _service(FakeRepo(_stored()), connections)
    assert await svc.resolve() is None
    assert connections.asked == ["acme"]


async def test_resolve_is_none_when_the_connections_wire_serves_no_embeddings() -> None:
    svc = _service(
        FakeRepo(_stored()),
        FakeConnections(acme=_endpoint("anthropic", offered_models=None)),
    )
    assert await svc.resolve() is None


@pytest.mark.parametrize(
    ("protocol", "expected"),
    [("openai", "openai"), ("unknown", "openai"), ("ollama", "ollama")],
)
async def test_resolve_maps_the_wire_onto_an_embedding_client(protocol: str, expected: str) -> None:
    """openai and every unclassified gateway speak the OpenAI-compatible
    embeddings call; ollama has its own keyless local endpoint."""
    credential_ref = None if protocol == "ollama" else "provider/acme/key"
    endpoint = _endpoint(protocol, base_url="http://gw/v1", credential_ref=credential_ref)
    svc = _service(FakeRepo(_stored(dimensions=1024)), FakeConnections(acme=endpoint))

    resolved = await svc.resolve()

    assert resolved is not None
    assert resolved.provider == expected
    assert resolved.model == "text-embedding-3-large"
    # The endpoint's, not the config's: there is one place to correct a URL and
    # one place to rotate a key.
    assert resolved.base_url == "http://gw/v1"
    assert resolved.credential_ref == credential_ref
    assert resolved.dimensions == 1024


# --- update(): what is accepted -----------------------------------------------


async def test_update_persists_and_audits() -> None:
    repo = FakeRepo()
    audit_repo = FakeAuditRepo()
    svc = EmbeddingConfigService(
        repo=repo,
        audit=AuditService(audit_repo),
        connections=FakeConnections(acme=_endpoint()),
    )

    saved = await svc.update(
        enabled=True,
        connection="  acme  ",
        model="  text-embedding-3-large  ",
        dimensions=3072,
        default_chunk_size=512,
        default_chunk_overlap=64,
        actor="ui",
    )

    assert saved.connection == "acme"  # trimmed before validation and storage
    assert saved.model == "text-embedding-3-large"
    assert repo.cfg is saved
    (entry,) = audit_repo.entries
    assert entry.event_type == "embedding_config_updated"
    assert entry.actor == "ui"
    assert entry.details["connection"] == "acme"
    # The audited details restate no endpoint or key — those live on the
    # connection now.
    assert set(entry.details) == {
        "enabled",
        "connection",
        "model",
        "dimensions",
        "default_chunk_size",
        "default_chunk_overlap",
    }


async def test_update_takes_the_model_at_its_word_when_the_connection_curates_nothing() -> None:
    """``offered_models is None`` is the "no restriction" answer: Coffer knows
    where the calls go, not what that endpoint serves."""
    repo = FakeRepo()
    svc = _service(repo, FakeConnections(acme=_endpoint(offered_models=None)))

    saved = await svc.update(
        enabled=True,
        connection="acme",
        model="some-vendor-embedding-v9",
        dimensions=768,
        default_chunk_size=512,
        default_chunk_overlap=64,
        actor="ui",
    )

    assert saved.model == "some-vendor-embedding-v9"


async def test_update_may_disable_without_naming_anything() -> None:
    repo = FakeRepo(_stored())
    svc = _service(repo, FakeConnections())

    saved = await svc.update(
        enabled=False,
        connection=None,
        model=None,
        dimensions=768,
        default_chunk_size=512,
        default_chunk_overlap=64,
        actor="ui",
    )

    assert saved.enabled is False and saved.connection is None
    assert saved.is_active() is False


# --- update(): every rejection, by its message --------------------------------


async def _reject(
    svc: EmbeddingConfigService,
    *,
    enabled: bool = True,
    connection: str | None = "acme",
    model: str | None = "text-embedding-3-large",
    dimensions: int = 768,
    default_chunk_size: int = 512,
    default_chunk_overlap: int = 64,
) -> str:
    with pytest.raises(ConfigValidationError) as excinfo:
        await svc.update(
            enabled=enabled,
            connection=connection,
            model=model,
            dimensions=dimensions,
            default_chunk_size=default_chunk_size,
            default_chunk_overlap=default_chunk_overlap,
            actor="ui",
        )
    return str(excinfo.value)


async def test_enabling_without_a_connection_and_model_is_refused() -> None:
    svc = _service(FakeRepo(), FakeConnections())
    message = await _reject(svc, connection=None, model=None)
    assert message == "connection and model are required to enable embedding"
    # Blank strings are the same answer as omitting them.
    assert await _reject(svc, connection="   ", model="text-embedding-3-large") == message


async def test_an_unknown_connection_is_refused_by_name() -> None:
    svc = _service(FakeRepo(), FakeConnections())
    assert "no connection named 'acme'" in await _reject(svc)


async def test_a_wire_that_serves_no_embeddings_is_refused() -> None:
    svc = _service(FakeRepo(), FakeConnections(acme=_endpoint("anthropic")))
    message = await _reject(svc)
    assert "speaks anthropic" in message
    assert "serves no embedding API" in message


async def test_a_connection_curating_no_embedding_model_is_refused() -> None:
    """It curates a set and no entry in it is ``embedding``-modality — a
    different answer from curating nothing at all."""
    svc = _service(FakeRepo(), FakeConnections(acme=_endpoint(offered_models=())))
    message = await _reject(svc)
    assert "offers no embedding model" in message
    assert "modality 'embedding'" in message


async def test_a_model_the_connection_does_not_offer_is_refused() -> None:
    svc = _service(
        FakeRepo(),
        FakeConnections(acme=_endpoint(offered_models=("text-embedding-3-large", "bge-m3"))),
    )
    message = await _reject(svc, model="nope")
    assert "does not offer embedding model 'nope'" in message
    # The message says what it DOES offer, so the UI can show it verbatim.
    assert "text-embedding-3-large, bge-m3" in message


async def test_a_rejected_update_stores_nothing() -> None:
    repo = FakeRepo(_stored())
    svc = _service(repo, FakeConnections())
    before = repo.cfg
    await _reject(svc)
    assert repo.cfg is before


@pytest.mark.parametrize("dimensions", [0, 8193])
async def test_out_of_range_dimensions_are_refused(dimensions: int) -> None:
    svc = _service(FakeRepo(), FakeConnections(acme=_endpoint()))
    assert "dimensions must be in 1..8192" in await _reject(svc, dimensions=dimensions)


@pytest.mark.parametrize("chunk_size", [63, 2049])
async def test_out_of_range_chunk_size_is_refused(chunk_size: int) -> None:
    svc = _service(FakeRepo(), FakeConnections(acme=_endpoint()))
    assert "chunk size must be in 64..2048" in await _reject(svc, default_chunk_size=chunk_size)


async def test_an_overlap_past_half_the_chunk_is_refused() -> None:
    svc = _service(FakeRepo(), FakeConnections(acme=_endpoint()))
    message = await _reject(svc, default_chunk_size=512, default_chunk_overlap=257)
    assert "chunk overlap must be in 0..chunk_size/2" in message


# --- endpoint_for(): the test route answers the same way saving would ---------


async def test_endpoint_for_returns_the_connections_endpoint() -> None:
    endpoint = _endpoint()
    svc = _service(FakeRepo(), FakeConnections(acme=endpoint))
    assert await svc.endpoint_for("acme", "text-embedding-3-large") is endpoint


async def test_endpoint_for_refuses_exactly_what_update_refuses() -> None:
    svc = _service(FakeRepo(), FakeConnections())
    with pytest.raises(ConfigValidationError, match="no connection named 'ghost'"):
        await svc.endpoint_for("ghost", "text-embedding-3-large")
