"""Ports the ``provider`` kind's application layer declares for others to satisfy.

``ProviderIntrospectionPort`` is the outbound seam for "test this connection"
and "list this endpoint's models": the OpenAI-compatible client, the Anthropic
REST shape and the SSRF guard all live behind it in
``infrastructure.provider.introspector``, per the engine-confinement and
application-no-infrastructure contracts. The service that drives the port is
``application.provider.introspection.ModelIntrospectionService``.

``EngineNotifyPort`` is the outbound seam onto Coffer's own engine, declared
HERE, by the caller, rather than imported from ``application.engine``: this kind
must not acquire an import of the engine, or every consumer of the engine would
acquire one of this kind in return and four cross-kind contracts would fail.
The composition root satisfies it with the engine's own guard.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from coffer.domain.provider.modality import Modality
from coffer.domain.usage.pricing import ModelPrice


@dataclass(frozen=True)
class TestResult:
    ok: bool
    message: str
    detail: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DiscoveredModel:
    """One id an endpoint reported, with the modality INFERRED from its name.

    The guess is for pre-filling the connection editor's model table only —
    the endpoint says what it serves, never what kind each one is, and the user
    corrects a wrong guess. Once curated, the stored modality is the truth.
    """

    id: str
    modality: Modality


@dataclass(frozen=True)
class ListedModel:
    """One id an endpoint listed, with the price its API reported for it —
    OpenRouter and gateways like it answer ``/models`` with each model's
    per-token rates. ``None`` when the endpoint says nothing about price."""

    id: str
    price: ModelPrice | None = None


@dataclass(frozen=True)
class ReportedPrices:
    """What one endpoint's API last reported its models cost, and when."""

    fetched_at: datetime
    prices: Mapping[str, ModelPrice]


class ReportedPriceStore(Protocol):
    """Where the prices an endpoint's API reported are remembered between
    listings (spec provider-switching "Resolve each model's price from the
    provider, its API, or the bundled list"). Keyed by the endpoint's root, so
    two connections to one endpoint share it. Derived: losing it only means
    waiting for the next listing."""

    def get(self, root: str) -> ReportedPrices | None: ...

    def put(self, root: str, prices: Mapping[str, ModelPrice]) -> None: ...


@dataclass(frozen=True)
class ModelList:
    models: list[DiscoveredModel]
    message: str = ""
    #: Whether the endpoint answered the listing at all. ``False`` only when the
    #: call failed (unreachable, refused key); an endpoint that answered with an
    #: empty list is reachable.
    reachable: bool = True


class ProviderIntrospectionPort(Protocol):
    """Outbound provider calls (infrastructure implements this)."""

    async def list_models(
        self, *, provider: str, base_url: str | None, api_key: str | None
    ) -> Sequence[str | ListedModel]:
        """The endpoint's models — a bare id, or a :class:`ListedModel` when
        its API also reported a price."""

    async def test_chat(
        self, *, provider: str, model: str, base_url: str | None, api_key: str | None
    ) -> None:
        """Raise on failure (any exception); return None on success."""


class EngineNotifyPort(Protocol):
    """What this kind tells Coffer's internal engine when a connection the
    engine runs on moves (spec internal-engine "Drop the engine model when its connection moves",
    "Drop the speech-to-text model when its connection moves").

    Two connections, two methods: the one Coffer thinks with and the one it
    transcribes speech with. They are told apart rather than folded together
    because a move of one must not forget the other's model.
    """

    async def drop_model_unless_curated(
        self, curated_ids: Collection[str], *, actor: str
    ) -> None: ...

    async def drop_transcribe_model_unless_curated(
        self, curated_ids: Collection[str], *, actor: str
    ) -> None: ...
