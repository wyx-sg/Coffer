"""The channel's default model belongs to its default agent only
(spec channels "Keep a chat's agent, model and directory across its conversations")."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from coffer.application.channel.command_text import settings_in_effect
from coffer.application.channel.store_ports import ChannelThreadConversation


def _row(**fields: str | None) -> ChannelThreadConversation:
    return ChannelThreadConversation(
        resource_uid=1,
        chat_id="c",
        thread_id="",
        active_conversation_id=None,
        preferred_agent=fields.pop("agent", None),
        updated_at=datetime.now(tz=UTC),
        **fields,  # type: ignore[arg-type]
    )


class _Threads:
    def __init__(self, row: ChannelThreadConversation | None) -> None:
        self._row = row

    async def get(self, *_args: object) -> ChannelThreadConversation | None:
        return self._row


def _commands(row: ChannelThreadConversation | None) -> SimpleNamespace:
    return SimpleNamespace(_threads=_Threads(row), _conversations=None)


BINDING = SimpleNamespace(
    resource=SimpleNamespace(uid=1),
    default_agent="claude",
    default_agent_config={"model": "opus", "cwd": "/w"},
    agent_scope=None,
)
PEER = SimpleNamespace(chat_id="c")


async def _settings(row: ChannelThreadConversation | None):  # type: ignore[no-untyped-def]
    return await settings_in_effect(_commands(row), BINDING, PEER, "", chat_kind="private")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_the_default_agent_shows_the_channel_default_model() -> None:
    s = await _settings(None)
    assert (s.agent, s.model, s.cwd) == ("claude", "opus", "/w")


@pytest.mark.asyncio
async def test_a_sticky_model_beats_the_channel_default_model() -> None:
    s = await _settings(_row(agent="claude", preferred_model="sonnet"))
    assert s.model == "sonnet"


@pytest.mark.acceptance(
    spec="channels", scenario="the channel's default model applies only to its default agent"
)
@pytest.mark.asyncio
async def test_a_sticky_other_agent_has_no_channel_default_model_but_keeps_the_directory() -> None:
    s = await _settings(_row(agent="codex"))
    assert (s.agent, s.model, s.cwd) == ("codex", None, "/w")
