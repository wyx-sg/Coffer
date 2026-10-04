"""The non-REST gates of the four experimental features, one unit each.

Spec experimental-features: a switched-off feature closes every surface, not
only its routes. The REST, kind, CLI and tool gates are exercised through the
real daemon in ``tests/integration/surfaces/http/test_phase_feature_gates.py``;
this file holds what has no route to ask — the passes, the adapters, the proxy
and the projection — each started through the real wiring with fakes behind it.
"""

from __future__ import annotations

import asyncio
import pathlib
from types import SimpleNamespace
from typing import Any

import pytest

from coffer.application.channel.attention import ChannelAttentionSource
from coffer.application.provider.projection_reconcile import (
    _WARRANTED,
    ProviderProjectionTarget,
)
from coffer.application.sync.attention import SyncAttentionSource
from coffer.application.usage.ingest import UsageIngestService
from coffer.domain.features import (
    EXPERIMENTAL_FEATURES,
    KNOWLEDGE,
    MEMORY,
    MODELS,
    SYNC,
    feature_keys,
)
from coffer.domain.model_proxy.state import ProxyState
from coffer.domain.reconcile import Difference, Disposition, Op, Trigger
from coffer.surfaces.http import memory_turn_wiring

# --- channels --------------------------------------------------------------


def test_the_channel_attention_source_belongs_to_no_feature() -> None:
    """Channels are always on, so their attention source is always asked."""
    assert ChannelAttentionSource.feature is None


# --- models ----------------------------------------------------------------


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="models off withdraws the provider projection from agents",
)
async def test_the_projection_wants_nothing_and_withdraws_what_it_wrote_while_models_is_off() -> (
    None
):
    state = {"on": False}
    target = ProviderProjectionTarget(
        providers=None,  # type: ignore[arg-type]
        agents=None,  # type: ignore[arg-type]
        projector=None,  # type: ignore[arg-type]
        store=None,  # type: ignore[arg-type]
        clear_choice=None,  # type: ignore[arg-type]
        is_enabled=lambda: state["on"],
    )
    # Nothing is scanned: with models off no agent is wanted on a connection.
    assert list(await target.desired()) == []

    leftover = Difference("provider_projection", "agent-1", Op.REMOVE, None, None)
    [decision] = target.decide([leftover], Trigger.SWITCH)
    assert decision.disposition is Disposition.REPAIR
    assert decision.reason_code == "feature_off"

    # With models on, a leftover is only reported unless a person asked.
    state["on"] = True
    [decision] = target.decide([leftover], Trigger.BOOT)
    assert decision.disposition is Disposition.REPORT


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="switching models on projects the connection again",
)
def test_the_models_switch_warrants_projecting_without_clearing_the_choice() -> None:
    """Without the warrant, switching models back on would read as a contradicted
    choice and clear every agent's record."""
    assert Trigger.SWITCH in _WARRANTED


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="models off serves no agent through the model proxy",
)
async def test_the_proxy_is_pushed_an_empty_state_while_models_is_off(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coffer.application.reconcile.reconciler import Reconciler
    from coffer.surfaces.http.model_proxy_wiring import wire_model_proxy
    from coffer.surfaces.http.proxy_dependencies import get_proxy_facade, set_proxy_facade

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_MODEL_PROXY", "off")
    state = {"on": False}
    reconciler = Reconciler(audit=SimpleNamespace())  # type: ignore[arg-type]
    wiring = wire_model_proxy(
        SimpleNamespace(_agents=SimpleNamespace(list=_no_rows)),  # type: ignore[arg-type]
        SimpleNamespace(),
        reconciler,
        coffer_dir=tmp_path,
        enabled=lambda: state["on"],
    )
    try:
        facade = get_proxy_facade()
        assert await facade.state() == ProxyState()
    finally:
        await wiring.stop()
        set_proxy_facade(None)  # type: ignore[arg-type]


async def _no_rows() -> list[Any]:
    return []


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="models off skips usage ingest and the price-list refresh",
)
async def test_the_usage_ingest_loop_skips_its_pass_while_models_is_off() -> None:
    passes: list[int] = []
    state = {"on": False}

    class _Ingest(UsageIngestService):
        async def ingest_once(self) -> Any:
            passes.append(1)
            return None

    svc = _Ingest(
        repo=None,  # type: ignore[arg-type]
        spool=None,  # type: ignore[arg-type]
        prices=None,  # type: ignore[arg-type]
        is_enabled=lambda: state["on"],
    )
    task = asyncio.create_task(svc.run(0.01))
    await asyncio.sleep(0.05)
    assert passes == []

    state["on"] = True
    await asyncio.sleep(0.05)
    svc.stop()
    await task
    assert passes


# --- memory ----------------------------------------------------------------


@pytest.mark.acceptance(
    spec="experimental-features",
    scenario="memory off leaves channel turns without memory",
)
async def test_a_channel_turn_appends_and_retrieves_no_memory_while_memory_is_off() -> None:
    class _Turns:
        async def index_for_turn(self, **_: Any) -> str:
            raise AssertionError("memory must not be read while memory is off")

        async def for_turn(self, **_: Any) -> str:
            raise AssertionError("memory must not be read while memory is off")

    turns: Any = _Turns()
    compose = memory_turn_wiring.memory_context_composer(turns, lambda _key: False)
    retrieve = memory_turn_wiring.memory_turn_retriever(turns, lambda _key: False)
    assert await compose("claude_code", "/w", "c1") is None
    assert await retrieve("claude_code", "/w", "what is x", "c1") is None


async def test_a_channel_turn_reads_memory_only_while_the_memory_feature_is_on() -> None:
    """The gate asks for ``memory`` itself, not for ``knowledge``."""
    asked: list[str] = []

    class _Turns:
        async def index_for_turn(self, **_: Any) -> str:
            return "index"

    def is_enabled(key: str) -> bool:
        asked.append(key)
        return key == MEMORY

    compose = memory_turn_wiring.memory_context_composer(_Turns(), is_enabled)  # type: ignore[arg-type]
    assert await compose("claude_code", "/w", "c1") == "index"
    assert asked == [MEMORY]
    assert KNOWLEDGE not in asked


def test_the_channel_gates_follow_their_own_feature_and_no_other() -> None:
    """Knowledge off leaves the memory index on, and memory off turns it off:
    each gate asks for its own key only."""
    from coffer.application.features import FeatureService

    class _Settings:
        def __init__(self, stored: dict[str, bool]) -> None:
            self.stored = stored

        def read(self) -> dict[str, bool]:
            return dict(self.stored)

        def write(self, key: str, enabled: bool) -> None:
            self.stored[key] = enabled

        def clear(self, key: str) -> None:
            self.stored.pop(key, None)

    memory_off = FeatureService(settings=_Settings({KNOWLEDGE: True, MEMORY: False}))
    knowledge_off = FeatureService(settings=_Settings({KNOWLEDGE: False, MEMORY: True}))

    class _Turns:
        async def index_for_turn(self, **_: Any) -> str:
            return "index"

    async def composed(features: FeatureService) -> str | None:
        compose = memory_turn_wiring.memory_context_composer(_Turns(), features.is_enabled)  # type: ignore[arg-type]
        return await compose("claude_code", "/w", "c1")

    import asyncio as _asyncio

    assert _asyncio.run(composed(memory_off)) is None
    assert _asyncio.run(composed(knowledge_off)) == "index"


# --- sync ------------------------------------------------------------------


def test_the_sync_attention_source_belongs_to_sync() -> None:
    assert SyncAttentionSource.feature == SYNC


# --- the registry ----------------------------------------------------------


def test_every_registered_feature_owns_a_surface() -> None:
    """A feature with neither a route prefix nor a kind would close nothing."""
    for feature in EXPERIMENTAL_FEATURES:
        assert feature.route_prefixes, feature.key
    assert feature_keys() == (KNOWLEDGE, MEMORY, SYNC, MODELS)
