"""ChatService — conversation lifecycle + streaming turn orchestration.

Talks to agents only through the ``AgentRuntime`` port, so it is identical for
the built-in (LangGraph) runtime and the external-agent (subprocess) runtime.
Holds one active turn per conversation to enforce single-flight (409), route
confirmation decisions, and support stop.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from coffer.application.audit_service import AuditService
from coffer.application.chat.ports import (
    AgentRuntime,
    ConversationRepo,
    MessageRepo,
    RuntimeFactory,
    TitleGenerator,
)
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.chat.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    MessageStatus,
    ToolCall,
)
from coffer.domain.chat.runtime import (
    ChatTurnRequest,
    ConfirmationRequest,
    ErrorEvent,
    RuntimeEvent,
    TextDelta,
    ToolCallStarted,
    ToolResultEvent,
    TurnMessage,
)
from coffer.domain.errors import (
    ConversationBusy,
    ConversationNotFound,
    MessageRejected,
    NotAChatTarget,
    ResourceNotFound,
    TargetAgentMissing,
)
from coffer.domain.resource import ResourceRef

_CHAT_TARGET_KINDS = frozenset({"builtin_agent", "agent"})
PLACEHOLDER_TITLE = "New chat"
MAX_MESSAGE_CHARS = 32768
_TITLE_MAX = 60


def _summarize_args(args: dict[str, Any]) -> str:
    try:
        return json.dumps(args, ensure_ascii=False)[:200]
    except (TypeError, ValueError):
        return str(args)[:200]


def _truncate_title(text: str) -> str:
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    title = first[:_TITLE_MAX].strip()
    return title or PLACEHOLDER_TITLE


@dataclass
class _ActiveTurn:
    runtime: AgentRuntime
    assistant_message_id: str
    stopped: bool = False
    tool_calls: dict[str, ToolCall] = field(default_factory=dict)


class ChatService:
    def __init__(
        self,
        *,
        conversations: ConversationRepo,
        messages: MessageRepo,
        resources: ResourceService,
        runtime_factory: RuntimeFactory,
        audit: AuditService,
        title_generator: TitleGenerator | None = None,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._conversations = conversations
        self._messages = messages
        self._resources = resources
        self._factory = runtime_factory
        self._audit = audit
        self._titler = title_generator
        self._id = id_factory or (lambda: uuid.uuid4().hex)
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._active: dict[str, _ActiveTurn] = {}

    # ---------- conversation lifecycle ----------

    def _snapshot(self, target: ResourceRef, config: dict[str, Any]) -> dict[str, Any]:
        if target.kind == "builtin_agent":
            return {"target": str(target), "model": config.get("model")}
        return {"target": str(target), "agent_type": config.get("type")}

    async def create_conversation(self, *, target_ref: str, actor: str = "api") -> Conversation:
        try:
            target = ResourceRef.parse(target_ref)
        except ValueError as e:
            raise NotAChatTarget(target_ref) from e
        if target.kind not in _CHAT_TARGET_KINDS:
            raise NotAChatTarget(target.kind)
        resource = await self._resources.get(target)  # ResourceNotFound -> 404
        now = self._clock()
        conv = Conversation(
            id=self._id(),
            target_ref=target_ref,
            title=PLACEHOLDER_TITLE,
            status=ConversationStatus.ACTIVE,
            model_snapshot=self._snapshot(target, resource.config),
            created_at=now,
            updated_at=now,
        )
        created = await self._conversations.create(conv)
        await self._audit.record(
            AuditEventType.CONVERSATION_CREATED.value,
            ref=ResourceRef("conversation", created.id),
            actor=actor,
            details={"target": target_ref},
        )
        return created

    async def list_conversations(
        self,
        *,
        status: ConversationStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        return await self._conversations.list(status=status, limit=limit, offset=offset)

    async def get_conversation(self, conversation_id: str) -> Conversation:
        conv = await self._conversations.get(conversation_id)
        if conv is None:
            raise ConversationNotFound(conversation_id)
        return conv

    async def get_messages(self, conversation_id: str) -> list[Message]:
        await self.get_conversation(conversation_id)  # 404 if absent
        return await self._messages.list_for(conversation_id)

    async def rename(self, conversation_id: str, title: str, *, actor: str = "api") -> Conversation:
        await self.get_conversation(conversation_id)
        updated = await self._conversations.set_title(conversation_id, title)
        await self._audit.record(
            AuditEventType.CONVERSATION_RENAMED.value,
            ref=ResourceRef("conversation", conversation_id),
            actor=actor,
        )
        return updated

    async def _set_status(
        self, conversation_id: str, status: ConversationStatus, event: AuditEventType, actor: str
    ) -> Conversation:
        await self.get_conversation(conversation_id)
        updated = await self._conversations.set_status(conversation_id, status)
        await self._audit.record(
            event.value, ref=ResourceRef("conversation", conversation_id), actor=actor
        )
        return updated

    async def archive(self, conversation_id: str, *, actor: str = "api") -> Conversation:
        return await self._set_status(
            conversation_id,
            ConversationStatus.ARCHIVED,
            AuditEventType.CONVERSATION_ARCHIVED,
            actor,
        )

    async def restore(self, conversation_id: str, *, actor: str = "api") -> Conversation:
        return await self._set_status(
            conversation_id, ConversationStatus.ACTIVE, AuditEventType.CONVERSATION_RESTORED, actor
        )

    async def delete(self, conversation_id: str, *, actor: str = "api") -> None:
        await self.get_conversation(conversation_id)
        await self._conversations.delete(conversation_id)
        await self._audit.record(
            AuditEventType.CONVERSATION_DELETED.value,
            ref=ResourceRef("conversation", conversation_id),
            actor=actor,
        )

    # ---------- turn control ----------

    def has_active_turn(self, conversation_id: str) -> bool:
        return conversation_id in self._active

    async def resolve_confirmation(
        self, conversation_id: str, request_id: str, approve: bool
    ) -> None:
        active = self._active.get(conversation_id)
        if active is None:
            raise ConversationNotFound(conversation_id)
        await active.runtime.resolve_confirmation(request_id, approve)

    async def stop(self, conversation_id: str) -> None:
        active = self._active.get(conversation_id)
        if active is None:
            return
        active.stopped = True
        await active.runtime.stop()

    # ---------- send a turn ----------

    async def send(
        self, conversation_id: str, text: str, *, actor: str = "api"
    ) -> AsyncIterator[RuntimeEvent]:
        if not text or not text.strip():
            raise MessageRejected("empty")
        if len(text) > MAX_MESSAGE_CHARS:
            raise MessageRejected("too_long")
        conv = await self.get_conversation(conversation_id)
        if conversation_id in self._active:
            raise ConversationBusy(conversation_id)
        target = conv.target
        try:
            resource = await self._resources.get(target)
        except ResourceNotFound as e:
            raise TargetAgentMissing(conv.target_ref) from e

        confirm_tools = (
            list(resource.config.get("confirm_tools", [])) if target.kind == "builtin_agent" else []
        )
        # Build the runtime BEFORE persisting anything — a missing provider key
        # raises LlmNotConfigured here so `send` fails with 503 and leaves no
        # half-written messages behind.
        runtime = self._factory.build(target=target, config=resource.config)

        prior = await self._messages.list_for(conversation_id)
        is_first = not any(m.role in (MessageRole.USER, MessageRole.ASSISTANT) for m in prior)
        history = [
            TurnMessage(role=m.role.value, content=m.content) for m in prior if m.content.strip()
        ]

        now = self._clock()
        await self._messages.add(
            Message(
                id=self._id(),
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=text,
                status=MessageStatus.COMPLETE,
                created_at=now,
            )
        )
        assistant = await self._messages.add(
            Message(
                id=self._id(),
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content="",
                status=MessageStatus.STREAMING,
                created_at=self._clock(),
            )
        )
        active = _ActiveTurn(runtime=runtime, assistant_message_id=assistant.id)
        self._active[conversation_id] = active
        request = ChatTurnRequest(history=history, user_message=text, confirm_tools=confirm_tools)
        return self._run_turn(conversation_id, conv, active, request, text, is_first)

    async def _run_turn(
        self,
        conversation_id: str,
        conv: Conversation,
        active: _ActiveTurn,
        request: ChatTurnRequest,
        user_text: str,
        is_first: bool,
    ) -> AsyncIterator[RuntimeEvent]:
        content_parts: list[str] = []
        confirmation_ids: set[str] = set()
        status = MessageStatus.COMPLETE
        error: dict[str, Any] | None = None
        try:
            async for ev in active.runtime.stream(request):
                if isinstance(ev, TextDelta):
                    content_parts.append(ev.text)
                elif isinstance(ev, ToolCallStarted):
                    active.tool_calls[ev.id] = ToolCall(
                        id=ev.id, tool=ev.tool, args_summary=_summarize_args(ev.args)
                    )
                elif isinstance(ev, ConfirmationRequest):
                    confirmation_ids.add(ev.id)
                    active.tool_calls.setdefault(
                        ev.id,
                        ToolCall(id=ev.id, tool=ev.tool, args_summary=_summarize_args(ev.args)),
                    )
                elif isinstance(ev, ToolResultEvent):
                    tc = active.tool_calls.get(ev.id)
                    if tc is not None:
                        tc.result_summary = ev.summary
                        if ev.id in confirmation_ids:
                            tc.confirmed = ev.ok
                elif isinstance(ev, ErrorEvent):
                    status = MessageStatus.FAILED
                    error = {"code": ev.code, "message": ev.message}
                yield ev
        finally:
            if active.stopped and status is not MessageStatus.FAILED:
                status = MessageStatus.CANCELED
            await self._finalize(
                conversation_id,
                conv,
                active,
                "".join(content_parts),
                status,
                error,
                user_text,
                is_first,
            )

    async def _finalize(
        self,
        conversation_id: str,
        conv: Conversation,
        active: _ActiveTurn,
        content: str,
        status: MessageStatus,
        error: dict[str, Any] | None,
        user_text: str,
        is_first: bool,
    ) -> None:
        self._active.pop(conversation_id, None)
        tool_calls_json = [
            {
                "id": t.id,
                "tool": t.tool,
                "args_summary": t.args_summary,
                "result_summary": t.result_summary,
                "confirmed": t.confirmed,
            }
            for t in active.tool_calls.values()
        ]
        with contextlib.suppress(Exception):
            await self._messages.update(
                active.assistant_message_id,
                content=content,
                status=status.value,
                tool_calls=tool_calls_json,
                error=error,
            )
            await self._conversations.touch(conversation_id)
        if (
            status is MessageStatus.COMPLETE
            and is_first
            and conv.title in (None, PLACEHOLDER_TITLE)
        ):
            with contextlib.suppress(Exception):
                await self._apply_title(conversation_id, user_text, content)

    async def _apply_title(self, conversation_id: str, user_text: str, assistant_text: str) -> None:
        title: str | None = None
        if self._titler is not None:
            with contextlib.suppress(Exception):
                title = await self._titler.generate(user_text, assistant_text)
        await self._conversations.set_title(conversation_id, title or _truncate_title(user_text))
