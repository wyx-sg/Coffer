"""Vault Console: channel-driven conversations are observable + approvable (ADR-021).

Observable: a conversation a channel opened carries ``origin="channel"`` plus the
IM peer's identity, and the console's conversation-list mapper surfaces it.
Approvable: the web approval card resolves the *same* approval relay
(``ApprovalChannel``) the IM button drives — a decision delivered through it
releases a turn waiting on that request id.
"""

from __future__ import annotations

import asyncio
import pathlib
from datetime import UTC, datetime

import pytest

from coffer.application.chat.approvals import ApprovalChannel
from coffer.application.chat.ports import ApprovalDecision
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
    scenario="a channel-driven conversation is observable and approvable from the console",
)
@pytest.mark.asyncio
async def test_channel_conversation_observable_and_approvable(tmp_path: pathlib.Path) -> None:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    repo = ConversationRepo(session_maker(engine))
    now = datetime.now(tz=UTC)

    # A conversation an IM peer drives (what application/channel/inbound persists).
    await repo.create(
        Conversation(
            id="c-channel",
            agent_key="claude_code",
            title="standup thread",
            model_id=None,
            created_at=now,
            updated_at=now,
            origin="channel",
            channel_name="team-standup",
            peer_chat_id="peer-42",
            peer_display_name="Alice",
        )
    )
    # A plain Vault Console draft (defaults: web origin, no peer).
    await repo.create(
        Conversation(
            id="c-web",
            agent_key="builtin",
            title="draft",
            model_id=None,
            created_at=now,
            updated_at=now,
        )
    )

    by_id = {c.id: _conv_out(c) for c in await repo.list()}
    try:
        # --- Observable: origin + peer identity surface in the console list ---
        channel_out = by_id["c-channel"]
        assert channel_out.origin == "channel"
        assert channel_out.peer is not None
        assert channel_out.peer.chat_id == "peer-42"
        assert channel_out.peer.display_name == "Alice"
        assert channel_out.peer.channel == "team-standup"

        web_out = by_id["c-web"]
        assert web_out.origin == "web"
        assert web_out.peer is None
    finally:
        await engine.dispose()

    # --- Approvable: the console resolves the SAME relay the IM button drives ---
    relay = ApprovalChannel()
    request_id = "tool-call-1"
    relay.register(request_id)
    waiting = asyncio.create_task(relay.wait(request_id))
    await asyncio.sleep(0)  # let the turn reach wait()

    # POST .../approvals (web card) and the IM approval button both call resolve().
    relay.resolve(request_id, ApprovalDecision(behavior="allow"))
    decision = await waiting
    assert decision.behavior == "allow"
