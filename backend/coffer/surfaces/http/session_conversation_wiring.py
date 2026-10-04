"""Bridge from an agent's native sessions to the turn platform's conversations.

The agent kind lists, renames and deletes an agent's own sessions; a session a
channel conversation points at is also that conversation (spec agent-registry
"List an agent's native sessions through the agent", "Rename and delete a native
session through the agent"). The agent kind declares what it needs as a port and
this composition root satisfies it with the chat kind's service and orchestrator,
so neither kind imports the other.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from coffer.application.agent.native_session_service import NativeSessionService
from coffer.application.agent.service import AgentService
from coffer.application.chat.questions import needs_you
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.chat.turn_state import is_running
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.native_sessions import (
    NativeSessionNotFound,
    SessionChannel,
    SessionConversation,
    SessionPlace,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.chat.errors import ConversationNotFound
from coffer.surfaces.http.chat.conversation_views import channel_binding, conversation_extras
from coffer.surfaces.http.chat.dependencies import get_channel_places


class ChatSessionConversations:
    """``SessionConversations`` over the chat service and the turn orchestrator."""

    def __init__(
        self, *, chat: ChatService, orchestrator: TurnOrchestrator, resources: ResourceService
    ) -> None:
        self._chat = chat
        self._orchestrator = orchestrator
        self._resources = resources

    async def linked(self, session_ids: Sequence[str]) -> Mapping[str, SessionConversation]:
        by_session = await self._chat.conversations_of_sessions(session_ids)
        if not by_session:
            return {}
        convs = list(by_session.values())
        extras = await conversation_extras(convs, self._resources, get_channel_places())
        out: dict[str, SessionConversation] = {}
        for session_id, conv in by_session.items():
            binding = channel_binding(conv, extras)
            channel = (
                SessionChannel(
                    channel_uid=binding.channel_uid,
                    channel=binding.channel,
                    chat_id=binding.chat_id,
                    platform=binding.platform,
                    place=(
                        SessionPlace(
                            chat_kind=binding.place.chat_kind,
                            thread=binding.place.thread,
                            parallel_mark=binding.place.parallel_mark,
                            chat_name=binding.place.chat_name,
                        )
                        if binding.place is not None
                        else None
                    ),
                )
                if binding is not None
                else None
            )
            out[session_id] = SessionConversation(
                conversation_id=conv.id,
                running=is_running(conv.id),
                needs_you=needs_you(conv.id),
                channel=channel,
            )
        return out

    async def retitle(self, session_id: str, title: str) -> None:
        for conv in (await self._chat.conversations_of_sessions([session_id])).values():
            try:
                await self._chat.rename_conversation(conv.id, new_title=title)
            except ConversationNotFound:
                continue

    async def forget(self, session_id: str) -> None:
        for conv in (await self._chat.conversations_of_sessions([session_id])).values():
            try:
                await self._chat.delete_conversation(
                    conv.id, cancel_turn_fn=self._orchestrator.cancel_turn
                )
            except ConversationNotFound:
                continue


class AgentConversationSessions:
    """``ConversationSessionsPort`` over the agent kind's sessions service.

    The conversation names its agent by type key; the registered agent of that
    type owns the sessions. The index row stays the chat kind's to change.
    """

    def __init__(self, *, agents: AgentService, sessions: NativeSessionService) -> None:
        self._agents = agents
        self._sessions = sessions

    async def _agent_uid(self, agent_key: str) -> str | None:
        try:
            agent_type = AgentType(agent_key)
        except ValueError:
            return None
        agent = await self._agents.find_by_type(agent_type)
        return agent.uid if agent is not None else None

    async def rename(self, agent_key: str, session_id: str, title: str) -> None:
        uid = await self._agent_uid(agent_key)
        if uid is None:
            return
        try:
            await self._sessions.rename(uid, session_id, title, sync_index=False)
        except NativeSessionNotFound:
            return  # the agent no longer has it (its own clean-up): index only

    async def delete(self, agent_key: str, session_id: str) -> None:
        uid = await self._agent_uid(agent_key)
        if uid is None:
            return
        try:
            await self._sessions.delete(uid, session_id, sync_index=False)
        except NativeSessionNotFound:
            return


def wire_session_conversations(
    sessions: NativeSessionService,
    *,
    chat: ChatService,
    orchestrator: TurnOrchestrator,
    resources: ResourceService,
    agents: AgentService,
) -> None:
    """Join the sessions service and the turn platform, both ways (after ``wire_chat``)."""
    sessions.link_conversations(
        ChatSessionConversations(chat=chat, orchestrator=orchestrator, resources=resources)
    )
    chat.link_sessions(AgentConversationSessions(agents=agents, sessions=sessions))


__all__ = ["AgentConversationSessions", "ChatSessionConversations", "wire_session_conversations"]
