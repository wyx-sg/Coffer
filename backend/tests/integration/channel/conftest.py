"""Shared fixtures for the channel-core integration tests (spec 009).

``FakeChannelAdapter`` implements ``ChannelAdapter`` structurally and is the
SC-003 proof: a new channel needs a transport adapter and nothing else —
pairing, queueing, conversation mapping, turn driving, and the approval
bridge are all exercised here through the real shared core.

Everything except the transport is real: real SQLite (resources, audit,
channel_peers, conversations, messages), the real ``ChatService`` +
``TurnOrchestrator`` driven by scripted agent providers — the same pattern
the spec-008 chat integration tests use.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from coffer.application.audit_service import AuditService
from coffer.application.channel.inbound import ChannelBinding, InboundProcessor
from coffer.application.channel.kind import make_channel_kind
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.ports import AdapterCallbacks, ChannelPeer
from coffer.application.channel.runtime import ChannelRuntime
from coffer.application.channel.service import ChannelService
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import (
    TurnOrchestrator,
    clear_active_turns,
)
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEntry
from coffer.domain.channel.envelopes import (
    ChannelCapabilities,
    InboundMessage,
    SentMessage,
)
from coffer.domain.chat.events import TextDelta, TurnDone, TurnStarted
from coffer.domain.resource import Resource, ResourceRef
from coffer.infrastructure.channel.persistence import ChannelPeerRepo
from coffer.infrastructure.chat.persistence import ConversationRepo, MessageRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from tests.unit.chat.conftest import FakeAgentAdapter

# ---------------------------------------------------------------------------
# Deterministic waiting
# ---------------------------------------------------------------------------


async def wait_until(
    predicate: Any,
    *,
    timeout: float = 5.0,
    interval: float = 0.01,
    message: str = "condition not met within timeout",
) -> None:
    """Poll ``predicate`` (sync or async) until truthy, bounded by ``timeout``."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        result = predicate()
        if inspect.isawaitable(result):
            result = await result
        if result:
            return
        if asyncio.get_running_loop().time() >= deadline:
            pytest.fail(message)
        await asyncio.sleep(interval)


def inbound(
    channel: str, chat_id: str, text: str, *, sender_display: str = "Owner"
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        chat_id=chat_id,
        sender_display=sender_display,
        text=text,
        platform_message_id="pm-1",
        timestamp=datetime.now(tz=UTC),
    )


# ---------------------------------------------------------------------------
# Fakes at the non-local boundaries (IM platform, credential store, child process)
# ---------------------------------------------------------------------------


class FakeKeyring:
    """In-memory credential store satisfying the ResourceService keyring port."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def set(self, ref: str, value: str) -> None:
        self._values[ref] = value

    def get(self, ref: str) -> str | None:
        return self._values.get(ref)


@dataclass(frozen=True)
class ApprovalPromptRecord:
    chat_id: str
    text: str
    allow_value: str
    deny_value: str
    message_id: str


class FakeChannelAdapter:
    """Recording ``ChannelAdapter`` — the only fake the channel core needs."""

    def __init__(
        self,
        *,
        supports_edit: bool = True,
        supports_buttons: bool = True,
        supports_typing: bool = True,
        max_message_chars: int = 4096,
    ) -> None:
        self._caps = ChannelCapabilities(
            supports_edit=supports_edit,
            supports_buttons=supports_buttons,
            supports_typing=supports_typing,
            max_message_chars=max_message_chars,
        )
        self.started = False
        self.stopped = False
        self.callbacks: AdapterCallbacks | None = None
        self.sent: list[tuple[str, str]] = []  # (chat_id, text)
        self.edits: list[tuple[str, str, str]] = []  # (chat_id, message_id, text)
        self.deleted: list[tuple[str, str]] = []  # (chat_id, message_id)
        self.typing: list[str] = []  # chat_ids
        self.approval_prompts: list[ApprovalPromptRecord] = []
        self.resolved: list[tuple[str, str, str]] = []  # (chat_id, message_id, outcome)
        self._next_id = 0

    @property
    def capabilities(self) -> ChannelCapabilities:
        return self._caps

    def texts(self) -> list[str]:
        return [text for _chat_id, text in self.sent]

    def _new_id(self) -> str:
        self._next_id += 1
        return f"m{self._next_id}"

    async def start(self, callbacks: AdapterCallbacks) -> None:
        self.started = True
        self.stopped = False
        self.callbacks = callbacks

    async def stop(self) -> None:
        self.started = False
        self.stopped = True

    async def send_text(self, chat_id: str, markdown: str) -> SentMessage:
        self.sent.append((chat_id, markdown))
        return SentMessage(message_id=self._new_id())

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        self.edits.append((chat_id, message_id, text))

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        self.deleted.append((chat_id, message_id))

    async def send_typing(self, chat_id: str) -> None:
        self.typing.append(chat_id)

    async def send_approval_prompt(
        self, chat_id: str, text: str, *, allow_value: str, deny_value: str
    ) -> SentMessage:
        message_id = self._new_id()
        self.approval_prompts.append(
            ApprovalPromptRecord(
                chat_id=chat_id,
                text=text,
                allow_value=allow_value,
                deny_value=deny_value,
                message_id=message_id,
            )
        )
        return SentMessage(message_id=message_id)

    async def resolve_approval_prompt(
        self, chat_id: str, message_id: str, outcome_text: str
    ) -> None:
        self.resolved.append((chat_id, message_id, outcome_text))


class StubListenerController:
    """Recording ``ListenerControllerPort`` (no real child process)."""

    def __init__(self) -> None:
        self._running = False
        self.ensure_running_calls: list[dict[str, str]] = []
        self.ensure_stopped_calls = 0

    @property
    def port(self) -> int:
        return 8466

    def running(self) -> bool:
        return self._running

    async def ensure_running(self, signing_secrets: dict[str, str]) -> None:
        self._running = True
        self.ensure_running_calls.append(dict(signing_secrets))

    async def ensure_stopped(self) -> None:
        self._running = False
        self.ensure_stopped_calls += 1


class ScriptedAgentProvider:
    """``AgentProvider`` whose adapter a test swaps in before sending."""

    agent_key = "builtin"

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        return None

    async def build_adapter(self, conversation_id: str) -> Any:
        return self.adapter

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        return None

    async def availability(self) -> bool:
        return True


def default_reply_adapter(text: str = "Hello world") -> FakeAgentAdapter:
    """A one-shot scripted agent that replies with ``text``."""
    return FakeAgentAdapter(
        [
            TurnStarted(),
            TextDelta(text=text),
            TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn"),
        ]
    )


# ---------------------------------------------------------------------------
# The wired environment
# ---------------------------------------------------------------------------


@dataclass
class ChannelEnv:
    """Real channel core + real chat platform over one SQLite file."""

    engine: AsyncEngine
    audit: AuditService
    keyring: FakeKeyring
    resources: ResourceService
    peers: ChannelPeerRepo
    pairing: PairingManager
    provider: ScriptedAgentProvider
    chat: ChatService
    orchestrator: TurnOrchestrator
    processor: InboundProcessor
    runtime: ChannelRuntime
    service: ChannelService
    listener: StubListenerController
    created_adapters: list[FakeChannelAdapter] = field(default_factory=list)

    async def register_channel(
        self,
        name: str = "tg",
        *,
        ref: str = "channel/tg/bot-token",
        config: dict[str, Any] | None = None,
    ) -> Resource:
        self.keyring.set(ref, f"secret-for-{ref}")
        cfg = config or {"channel_type": "telegram", "bot_token_ref": ref}
        return await self.resources.register(kind="channel", name=name, config=cfg, actor="test")

    async def pair(self, resource: Resource, chat_id: str = "owner") -> ChannelPeer:
        peer = ChannelPeer(
            resource_id=resource.id,
            chat_id=chat_id,
            display_name="Owner",
            paired_at=datetime.now(tz=UTC),
            active_conversation_id=None,
        )
        await self.peers.upsert(peer)
        return peer

    def bind(
        self, resource: Resource, adapter: FakeChannelAdapter | None = None
    ) -> FakeChannelAdapter:
        adapter = adapter or FakeChannelAdapter()
        self.processor.bind(
            ChannelBinding(
                name=resource.name,
                resource_id=resource.id,
                channel_type=str(resource.config.get("channel_type", "telegram")),
                default_agent="builtin",
                default_agent_config=None,
                adapter=adapter,
            )
        )
        return adapter

    async def paired_channel(
        self, name: str = "tg", chat_id: str = "owner"
    ) -> tuple[Resource, FakeChannelAdapter]:
        resource = await self.register_channel(name)
        adapter = self.bind(resource)
        await self.pair(resource, chat_id)
        return resource, adapter

    async def audit_entries(self, event_type: str, name: str | None = None) -> list[AuditEntry]:
        return await self.audit.query(kind="channel", name=name, event_type=event_type)


async def _build_env(tmp_path: Any) -> ChannelEnv:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'coffer.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    audit = AuditService(SqlAlchemyAuditRepo(sm))
    keyring = FakeKeyring()
    kinds: dict[str, Any] = {}
    resources = ResourceService(
        kinds=kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit, credentials=keyring
    )
    peers = ChannelPeerRepo(sm)
    pairing = PairingManager()

    provider = ScriptedAgentProvider(default_reply_adapter())
    registry = AgentProviderRegistry()
    registry.register(provider, display_name="Coffer Assistant")
    chat = ChatService(
        conversations=ConversationRepo(sm),
        messages=MessageRepo(sm),
        registry=registry,
        audit=audit,
    )
    orchestrator = TurnOrchestrator(chat_service=chat, registry=registry, audit=audit)
    processor = InboundProcessor(
        peers=peers, pairing=pairing, conversations=chat, turns=orchestrator, audit=audit
    )

    created_adapters: list[FakeChannelAdapter] = []

    async def adapter_factory(name: str, config: dict[str, object]) -> FakeChannelAdapter:
        adapter = FakeChannelAdapter()
        created_adapters.append(adapter)
        return adapter

    resolver = CredentialResolver(keyring)

    async def materialize(refs: dict[str, str]) -> dict[str, str]:
        # The real resolver, so failures raise CredentialMissing exactly as
        # production wiring does.
        return resolver.materialize(refs)

    listener = StubListenerController()
    runtime = ChannelRuntime(
        resources=resources,
        adapter_factory=adapter_factory,
        processor=processor,
        pairing=pairing,
        listener=listener,
        materialize=materialize,
        interval_seconds=0.05,
    )

    async def on_delete(ref: ResourceRef) -> None:
        await runtime.evict(ref.name)

    kinds["channel"] = make_channel_kind(on_delete=on_delete)

    service = ChannelService(
        resources=resources, peers=peers, pairing=pairing, runtime=runtime, audit=audit
    )
    return ChannelEnv(
        engine=engine,
        audit=audit,
        keyring=keyring,
        resources=resources,
        peers=peers,
        pairing=pairing,
        provider=provider,
        chat=chat,
        orchestrator=orchestrator,
        processor=processor,
        runtime=runtime,
        service=service,
        listener=listener,
        created_adapters=created_adapters,
    )


@pytest.fixture(autouse=True)
def _reset_turns() -> Any:
    clear_active_turns()
    yield
    clear_active_turns()


@pytest_asyncio.fixture
async def env(tmp_path: Any) -> Any:
    e = await _build_env(tmp_path)
    try:
        yield e
    finally:
        # Cancel any still-running turn and drain tasks deterministically
        # before closing the database they write to.
        leftovers = [
            t
            for t in asyncio.all_tasks()
            if t is not asyncio.current_task()
            and t.get_name().startswith(("turn:", "channel-drain:"))
        ]
        for task in leftovers:
            task.cancel()
        if leftovers:
            await asyncio.gather(*leftovers, return_exceptions=True)
        e.processor.shutdown()
        await e.engine.dispose()
