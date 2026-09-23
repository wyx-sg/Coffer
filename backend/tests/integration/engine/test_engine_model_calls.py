"""The calls Coffer's own model makes (spec internal-engine).

Real LangChain clients are constructed (no network is reached) so the claims
are about what the engine really hands a provider SDK: which client, which
model, which endpoint, and which bound on one call.
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.knowledge.ingest import IngestService
from coffer.domain.provider.config import Protocol, ProviderConfig, ResolvedConnection
from coffer.infrastructure.llm import agentic_reorg
from coffer.infrastructure.llm.agentic_reorg import LangchainAgenticReorg
from coffer.infrastructure.llm.langchain_models import build_chat_model
from coffer.infrastructure.llm.transcription import remote_transcriber_factory


def _pair(protocol: Protocol, *, base_url: str, model: str) -> ResolvedConnection:
    return ResolvedConnection(
        config=ProviderConfig(protocol=protocol, base_url=base_url, credential_ref="provider/ref"),
        model=model,
    )


def _key(ref: str) -> str:
    assert ref == "provider/ref"
    return "sk-test"


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="build the engine's chat model from the resolved pair",
)
def test_the_chat_model_is_the_resolved_pairs_protocol_model_and_endpoint() -> None:
    anthropic = build_chat_model(
        _pair(Protocol.ANTHROPIC, base_url="https://relay.example/anthropic", model="thinker-a"),
        _key,
    )
    assert anthropic.__class__.__name__ == "ChatAnthropic"
    assert anthropic.model == "thinker-a"
    assert anthropic.anthropic_api_url == "https://relay.example/anthropic"

    openai = build_chat_model(
        _pair(Protocol.OPENAI, base_url="https://gateway.example/v1", model="thinker-b"),
        _key,
    )
    assert openai.__class__.__name__ == "ChatOpenAI"
    assert openai.model_name == "thinker-b"
    assert openai.openai_api_base == "https://gateway.example/v1"


class _Bound:
    """The settings row's call bound, as the passes' reader sees it."""

    def __init__(self, seconds: int | None) -> None:
        self.seconds = seconds

    async def read(self) -> int | None:
        return self.seconds


class _Selector:
    def __init__(self, pair: ResolvedConnection) -> None:
        self._pair = pair

    async def get_default(self) -> ResolvedConnection:
        return self._pair


class _Completion:
    def __init__(self) -> None:
        self.timeouts: list[float | None] = []

    async def complete(
        self,
        *,
        system: str,
        user: str,
        model: Any,
        credential_resolver: Any,
        timeout: float | None = None,
    ) -> str:
        self.timeouts.append(timeout)
        return "a description"


@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="every internal model call reads the current bound",
)
async def test_every_internal_call_runs_under_the_bound_read_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound = _Bound(45)
    pair = _pair(Protocol.OPENAI, base_url="https://gateway.example/v1", model="thinker")

    # Knowledge ingestion's description step.
    completion = _Completion()
    ingest = IngestService(
        knowledge=None,  # type: ignore[arg-type]  # _describe never reaches it
        registry=None,  # type: ignore[arg-type]
        models=_Selector(pair),
        completion=completion,
        credential_resolver=_key,
        read_timeout=bound.read,
    )
    assert await ingest._describe("# T\n\nbody", title="T") == "a description"

    # Speech-to-text, built per turn.
    build_transcriber = remote_transcriber_factory(
        lambda: _async(pair), _key, read_timeout=bound.read
    )
    transcriber = await build_transcriber()
    assert transcriber is not None
    assert transcriber._timeout == 45.0

    # Curation's agentic loop: the bound is on the CLIENT each turn runs through.
    clients: list[Any] = []

    async def capture(*, lc_model: Any, **_: Any) -> dict[str, Any]:
        clients.append(lc_model)
        return {"messages": []}

    monkeypatch.setattr(agentic_reorg, "run_agentic_reorg", capture)
    from coffer.application.engine_timeout import resolve_timeout

    await LangchainAgenticReorg().run(
        model=pair,
        tools=[],
        system_prompt="s",
        user_prompt="u",
        credential_resolver=_key,
        recursion_limit=3,
        timeout=await resolve_timeout(bound.read),
    )
    assert clients[-1].request_timeout == 45.0

    # The operator raises the bound; nothing is rebuilt or rewired.
    bound.seconds = 240
    await ingest._describe("# T\n\nbody", title="T")
    assert completion.timeouts == [45.0, 240.0]
    transcriber = await build_transcriber()
    assert transcriber is not None
    assert transcriber._timeout == 240.0
    await LangchainAgenticReorg().run(
        model=pair,
        tools=[],
        system_prompt="s",
        user_prompt="u",
        credential_resolver=_key,
        recursion_limit=3,
        timeout=await resolve_timeout(bound.read),
    )
    assert clients[-1].request_timeout == 240.0


async def _async(value: ResolvedConnection) -> ResolvedConnection:
    return value
