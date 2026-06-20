"""Chat: a channel-driven conversation is observable from the console (ADR-031).

A conversation the owner also drives from an IM channel carries a channel binding
(``channel_name`` + ``peer_chat_id``); the conversation-list mapper surfaces it so
the desktop can badge and observe it. A desktop-only conversation has no binding.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest

from coffer.domain.chat.conversation import Conversation
from coffer.infrastructure.chat.persistence import ConversationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.surfaces.http.chat.conversation_routes import _conv_out


@pytest.mark.acceptance(
    spec="008-agent-chat",
    scenario="a channel-driven conversation is observable from the console",
)
@pytest.mark.asyncio
async def test_channel_conversation_observable(tmp_path: pathlib.Path) -> None:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repo = ConversationRepo(session_maker(engine))
    now = datetime.now(tz=UTC)

    # A conversation the owner drives from a channel (what channel inbound persists).
    await repo.create(
        Conversation(
            id="c-channel",
            agent_key="claude_code",
            title="standup thread",
            model_id=None,
            created_at=now,
            updated_at=now,
            channel_name="team-standup",
            peer_chat_id="peer-42",
        )
    )
    # A plain desktop draft (no channel binding).
    await repo.create(
        Conversation(
            id="c-web",
            agent_key="claude_code",
            title="draft",
            model_id=None,
            created_at=now,
            updated_at=now,
        )
    )

    by_id = {c.id: _conv_out(c) for c in await repo.list()}
    try:
        # --- Observable: the channel binding surfaces in the conversation list ---
        channel_out = by_id["c-channel"]
        assert channel_out.channel_binding is not None
        assert channel_out.channel_binding.channel == "team-standup"
        assert channel_out.channel_binding.chat_id == "peer-42"

        # A desktop-only conversation has no channel binding.
        web_out = by_id["c-web"]
        assert web_out.channel_binding is None
    finally:
        await engine.dispose()
