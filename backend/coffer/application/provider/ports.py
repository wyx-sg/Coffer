"""Ports the ``provider`` kind's application layer defines for infrastructure.

``ProviderIntrospectionPort`` is the outbound seam for "test this connection"
and "list this endpoint's models": the OpenAI-compatible client, the Anthropic
REST shape and the SSRF guard all live behind it in
``infrastructure.provider.introspector``, per the engine-confinement and
application-no-infrastructure contracts. The service that drives the port is
``application.provider.introspection.ModelIntrospectionService``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from coffer.domain.provider.modality import Modality

#: Providers Coffer treats as machine-local; their base URL is loopback, so the
#: SSRF guard (which blocks loopback) is intentionally skipped for them.
LOCAL_PROVIDERS = frozenset({"ollama", "lmstudio", "local"})


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
