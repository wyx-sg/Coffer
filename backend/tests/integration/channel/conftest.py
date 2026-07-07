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
from collections.abc import Sequence
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
    ChoiceButton,
    InboundCallback,
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
    channel: str,
    chat_id: str,
    text: str,
    *,
    sender_display: str = "Owner",
    sender_id: str = "",
    thread_id: str = "",
    chat_kind: str = "direct",
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        chat_id=chat_id,
        sender_display=sender_display,
        text=text,
        platform_message_id="pm-1",
        timestamp=datetime.now(tz=UTC),
        sender_id=sender_id,
        thread_id=thread_id,
        chat_kind=chat_kind,
    )


def tap_event(channel: str, chat_id: str, data: str, *, sender_id: str = "") -> InboundCallback:
    """A selection-card button tap, for driving ``processor.on_callback``."""
    return InboundCallback(channel=channel, chat_id=chat_id, sender_id=sender_id, data=data)


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


class FakeChannelAdapter:
    """Recording ``ChannelAdapter`` — the only fake the channel core needs."""

    def __init__(
        self,
        *,
        supports_edit: bool = True,
        supports_typing: bool = True,
        max_message_chars: int = 4096,
        supports_buttons: bool = False,
        supports_media: bool = True,
    ) -> None:
        self._caps = ChannelCapabilities(
            supports_edit=supports_edit,
            supports_typing=supports_typing,
            max_message_chars=max_message_chars,
            supports_buttons=supports_buttons,
            supports_media=supports_media,
        )
        self.started = False
        self.stopped = False
        self.callbacks: AdapterCallbacks | None = None
        self.sent: list[tuple[str, str]] = []  # (chat_id, text)
        # (chat_id, text, thread_id, chat_kind) for every send_text call — the
        # full routing detail, kept separate so every existing ``.sent``/
        # ``.texts()`` assertion above stays a plain 2-tuple.
        self.sent_routed: list[tuple[str, str, str, str]] = []
        # (chat_id, text, buttons) for sends that carried a selection card.
        self.cards: list[tuple[str, str, list[ChoiceButton]]] = []
        self.edits: list[tuple[str, str, str]] = []  # (chat_id, message_id, text)
        self.deleted: list[tuple[str, str]] = []  # (chat_id, message_id)
        self.typing: list[str] = []  # chat_ids
        # (chat_id, path, caption, as_photo) for each uploaded file.
        self.media: list[tuple[str, str, str | None, bool]] = []
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

    async def send_text(
        self,
        chat_id: str,
        markdown: str,
        *,
        buttons: Sequence[ChoiceButton] | None = None,
        thread_id: str = "",
        chat_kind: str = "direct",
    ) -> SentMessage:
        self.sent.append((chat_id, markdown))
        self.sent_routed.append((chat_id, markdown, thread_id, chat_kind))
        if buttons:
            self.cards.append((chat_id, markdown, list(buttons)))
        return SentMessage(message_id=self._new_id())

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        self.edits.append((chat_id, message_id, text))

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        self.deleted.append((chat_id, message_id))

    async def send_typing(self, chat_id: str) -> None:
        self.typing.append(chat_id)

    async def send_media(
        self,
        chat_id: str,
        path: str,
        *,
        caption: str | None = None,
        as_photo: bool = True,
    ) -> SentMessage:
        self.media.append((chat_id, path, caption, as_photo))
        return SentMessage(message_id=self._new_id())

    async def tap(
        self, value: str, *, channel: str, chat_id: str = "owner", sender_id: str = ""
    ) -> None:
        """Simulate a selection-card button tap arriving from the platform."""
        assert self.callbacks is not None and self.callbacks.on_callback is not None
        await self.callbacks.on_callback(
            InboundCallback(channel=channel, chat_id=chat_id, sender_id=sender_id, data=value)
        )


class FakeModelSuggestions:
    """In-memory ModelSuggestionPort: per-agent model quick-picks for cards."""

    def __init__(self) -> None:
        self._by_agent: dict[str, list[str]] = {}

    def add(self, agent_key: str, models: list[str]) -> None:
        self._by_agent[agent_key] = models

    async def suggest(self, agent_key: str) -> list[str]:
        return list(self._by_agent.get(agent_key, []))


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

    def __init__(self, adapter: Any, agent_key: str = "builtin") -> None:
        self.adapter = adapter
        self.agent_key = agent_key
        self.last_agent_config: dict[str, Any] | None = None

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        self.last_agent_config = agent_config
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
    registry: AgentProviderRegistry
    model_suggestions: FakeModelSuggestions
    chat: ChatService
    orchestrator: TurnOrchestrator
    processor: InboundProcessor
    runtime: ChannelRuntime
    service: ChannelService
    listener: StubListenerController
    created_adapters: list[FakeChannelAdapter] = field(default_factory=list)

    def add_agent(self, agent_key: str, reply: str = "from-other") -> ScriptedAgentProvider:
        """Register a second scripted agent so routing tests have a target."""
        provider = ScriptedAgentProvider(default_reply_adapter(reply), agent_key=agent_key)
        self.registry.register(provider, display_name=agent_key.title())
        return provider

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

    async def pair(
        self, resource: Resource, chat_id: str = "owner", *, sender_id: str | None = None
    ) -> ChannelPeer:
        peer = ChannelPeer(
            resource_id=resource.id,
            chat_id=chat_id,
            display_name="Owner",
            paired_at=datetime.now(tz=UTC),
            active_conversation_id=None,
            sender_id=sender_id,
        )
        await self.peers.upsert(peer)
        return peer

    def bind(
        self,
        resource: Resource,
        adapter: FakeChannelAdapter | None = None,
        *,
        default_agent: str = "builtin",
        default_agent_config: dict[str, Any] | None = None,
    ) -> FakeChannelAdapter:
        adapter = adapter or FakeChannelAdapter()
        self.processor.bind(
            ChannelBinding(
                name=resource.name,
                resource_id=resource.id,
                channel_type=str(resource.config.get("channel_type", "telegram")),
                default_agent=default_agent,
                default_agent_config=default_agent_config,
                adapter=adapter,
            )
        )
        return adapter

    async def paired_channel(
        self, name: str = "tg", chat_id: str = "owner", *, sender_id: str | None = None
    ) -> tuple[Resource, FakeChannelAdapter]:
        resource = await self.register_channel(name)
        adapter = self.bind(resource)
        await self.pair(resource, chat_id, sender_id=sender_id)
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
    model_suggestions = FakeModelSuggestions()
    processor = InboundProcessor(
        peers=peers,
        pairing=pairing,
        conversations=chat,
        turns=orchestrator,
        audit=audit,
        agents=registry,
        model_suggestions=model_suggestions,
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
        registry=registry,
        model_suggestions=model_suggestions,
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
