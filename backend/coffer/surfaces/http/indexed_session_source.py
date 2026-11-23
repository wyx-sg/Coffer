"""The conversations Coffer ran on an agent, as its session list: what the
sessions tab shows for OpenCode, DeepSeek Harness or Cursor when the agent's own
store cannot be read (spec agent-registry "List the sessions an agent keeps in
its own store"; ``FallbackSessionSource``).

Every conversation a channel or scheduled task ran on the agent is listed with
the session id the agent named. Renaming and deleting here change nothing of
the agent's; the service retitles or forgets Coffer's row.

The index lives in the chat kind, which is wired after the agent kind, so the
source is bound to the chat service once that exists.
"""

from __future__ import annotations

import pathlib
from typing import Any

from coffer.application.agent.native_session_service import SourcePage
from coffer.application.chat.conversation_repo import Narrowing
from coffer.application.chat.service import ChatService
from coffer.domain.agent.native_sessions import NativeSession, scrub_secrets
from coffer.domain.pagination import CursorInvalid


class IndexedSessionSource:
    """``NativeSessionSource`` over the conversation index, for one agent type."""

    def __init__(self, agent_key: str) -> None:
        self._agent_key = agent_key
        self._chat: ChatService | None = None

    def bind(self, chat: ChatService) -> None:
        self._chat = chat

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage:
        if self._chat is None:
            return SourcePage(items=[], next_position=None, total=0)
        cursor: str | None = None
        if position is not None:
            if len(position) != 1 or not isinstance(position[0], str):
                raise CursorInvalid("its position does not fit this list")
            cursor = position[0]
        page = await self._chat.page_conversations(
            limit=limit, cursor=cursor, q=q, narrow=Narrowing.of(agents=[self._agent_key])
        )
        items = [
            NativeSession(
                session_id=c.agent_config.session_id,
                title=scrub_secrets(c.title),
                cwd=c.agent_config.cwd,
                created_at=c.created_at,
                last_activity_at=c.updated_at,
            )
            for c in page.items
            if c.agent_config.session_id
        ]
        return SourcePage(
            items=items,
            next_position=[page.next_cursor] if page.next_cursor else None,
            total=None,
        )

    async def rename(self, config_dir: pathlib.Path, session_id: str, title: str) -> None:
        # The agent's own title is not Coffer's to change; the conversation's
        # row takes the new title (NativeSessionService retitles it).
        return

    async def delete(self, config_dir: pathlib.Path, session_id: str) -> None:
        # Only Coffer's row goes (NativeSessionService forgets it); the agent
        # keeps its own copy.
        return


__all__ = ["IndexedSessionSource"]
