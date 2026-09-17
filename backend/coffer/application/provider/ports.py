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

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Protocol

from coffer.domain.provider.modality import Modality

#: WIRE PROTOCOLS Coffer treats as machine-local; their base URL is loopback, so
#: the SSRF guard (which blocks loopback) is intentionally skipped for them. The
#: members are ``domain.provider.config.Protocol`` values, because that is what
#: the port's ``provider`` argument carries — a detected wire, not a vendor id.
LOCAL_PROTOCOLS = frozenset({"ollama"})


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
class ModelList:
    models: list[DiscoveredModel]
    message: str = ""


class ProviderIntrospectionPort(Protocol):
    """Outbound provider calls (infrastructure implements this)."""

    async def list_models(
        self, *, provider: str, base_url: str | None, api_key: str | None
    ) -> list[str]: ...

    async def test_chat(
        self, *, provider: str, model: str, base_url: str | None, api_key: str | None
    ) -> None:
        """Raise on failure (any exception); return None on success."""

    async def detect_protocol(self, *, base_url: str | None, api_key: str | None) -> str:
        """Classify the endpoint's wire as 'anthropic'/'openai'/'ollama'/'unknown'.

        Conservative: only assert anthropic/openai when a probe clearly succeeds;
        ambiguity returns 'unknown' so the agent page falls back to user choice.
        """


class EngineNotifyPort(Protocol):
    """What this kind tells Coffer's internal engine when a connection the
    engine runs on moves (spec internal-engine FR-005/FR-026).

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
