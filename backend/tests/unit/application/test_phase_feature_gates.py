"""The non-REST gates of the two experimental features, one unit each.

Spec experimental-features: a switched-off feature closes every surface, not
only its routes. The REST, kind, CLI and tool gates are exercised through the
real daemon in ``tests/integration/surfaces/http/test_phase_feature_gates.py``;
this file holds what has no route to ask — the channel turns and the attention
sources — each started through the real wiring with fakes behind it.
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.channel.attention import ChannelAttentionSource
from coffer.application.sync.attention import SyncAttentionSource
from coffer.domain.features import (
    EXPERIMENTAL_FEATURES,
    KNOWLEDGE,
    MEMORY,
    feature_keys,
)
from coffer.surfaces.http import memory_turn_wiring

# --- channels --------------------------------------------------------------


def test_the_channel_attention_source_belongs_to_no_feature() -> None:
    """Channels are always on, so their attention source is always asked."""
    assert ChannelAttentionSource.feature is None


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


def test_the_sync_attention_source_belongs_to_no_feature() -> None:
    """Vault sync graduated, so its attention source is always asked."""
    assert SyncAttentionSource.feature is None


# --- the registry ----------------------------------------------------------


def test_every_registered_feature_owns_a_surface() -> None:
    """A feature with neither a route prefix nor a kind would close nothing."""
    for feature in EXPERIMENTAL_FEATURES:
        assert feature.route_prefixes, feature.key
    assert feature_keys() == (KNOWLEDGE, MEMORY)
