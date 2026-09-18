"""Chat: a channel-driven conversation is observable from the console.

ADR chat-single-owner-live-mirror.

A conversation the owner also drives from an IM channel carries a channel binding
(``channel_uid`` + ``peer_chat_id``); the conversation-list mapper surfaces it so
the desktop can badge and observe it. A desktop-only conversation has no binding.

The row stores the channel's uid, not its name (ADR
resource-identity-is-an-immutable-uid) — a binding has to keep naming the same
channel after a rename. The name the console badge shows is resolved from that
uid by the mapper.
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

#: The channel resource this thread is bridged to, by uid.
_STANDUP_UID = "7f2b6e0c9a1d4f8e5b3c2a6d0e9f1b47"
#: What the mapper is given to resolve that uid with. In the daemon it is built
#: once per request from the channel registry (``_channel_names``); here it is
#: written out, because what this test is about is the mapper's own join and not
#: the read that feeds it.
_CHANNEL_NAMES = {_STANDUP_UID: "team-standup"}


@pytest.mark.acceptance(
    spec="chat",
    scenario="observe a turn started from another surface",
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
            created_at=now,
            updated_at=now,
            channel_uid=_STANDUP_UID,
            peer_chat_id="peer-42",
        )
    )
    # A plain desktop draft (no channel binding).
    await repo.create(
        Conversation(
            id="c-web",
            agent_key="claude_code",
            title="draft",
            created_at=now,
            updated_at=now,
        )
    )

    by_id = {c.id: _conv_out(c, _CHANNEL_NAMES) for c in await repo.list()}
    try:
        # --- Observable: the channel binding surfaces in the conversation list ---
        channel_out = by_id["c-channel"]
        assert channel_out.channel_binding is not None
        # The binding points at the channel's IDENTITY — that is what keeps it
        # naming the same channel after a rename, and it is what the desktop
        # follows the badge with...
        assert channel_out.channel_binding.channel_uid == _STANDUP_UID
        # ...while the name beside it is resolved from that uid, for the person
        # reading the badge. Same assertion as before the identity change: the
        # console can say WHICH channel this thread belongs to.
        assert channel_out.channel_binding.channel == "team-standup"
        assert channel_out.channel_binding.chat_id == "peer-42"

        # A desktop-only conversation has no channel binding.
        web_out = by_id["c-web"]
        assert web_out.channel_binding is None
    finally:
        await engine.dispose()
