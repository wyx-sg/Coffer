"""Shared fixtures for the channel-core integration tests (spec channels).

``FakeChannelAdapter`` implements ``ChannelAdapter`` structurally and is the
proof of the channels spec's N + M promise (its Purpose): a new channel needs
a transport adapter and nothing else —
pairing, queueing, conversation mapping, turn driving, and the approval
bridge are all exercised here through the real shared core.

Everything except the transport is real: real SQLite (resources, audit,
channel_peers, conversations, messages), the real ``ChatService`` +
``TurnOrchestrator`` driven by scripted agent providers — the same pattern
the chat integration tests use.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from coffer.application.audit_service import AuditService
from coffer.application.channel.inbound import ChannelBinding, InboundProcessor
from coffer.application.channel.kind import make_channel_kind
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.runtime import ChannelRuntime
from coffer.application.channel.service import ChannelService
from coffer.application.channel.store_ports import ChannelPeer
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import (
    TurnOrchestrator,
    clear_active_turns,
)
from coffer.application.resource_service import ResourceService
from coffer.application.runtime.supervisor import tasks
from coffer.application.secret.resolver import SecretResolver
from coffer.domain.audit import AuditEntry
from coffer.domain.channel.envelopes import (
    InboundAttachment,
    InboundCallback,
    InboundLifecycle,
    InboundMessage,
)
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.events import TextDelta, TurnDone, TurnStarted
from coffer.domain.resource import Kind, Resource
from coffer.domain.scope import Scope
from coffer.infrastructure.channel.persistence import (
    ChannelPeerRepo,
    ChannelReplyRepo,
    ChannelThreadConversationRepo,
    ChannelThreadCursorRepo,
)
from coffer.infrastructure.chat.persistence import ConversationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.surfaces.http.channel_wiring import ChatQuestions
from tests.support.channel import FakeChannelAdapter as FakeChannelAdapter
from tests.support.channel import FakeLiveText as FakeLiveText
from tests.support.vault_stores import make_resource_repo
from tests.support.waiting import wait_until  # noqa: F401  (re-exported to the channel tests)
from tests.unit.chat.conftest import FakeAgentAdapter

#: The agent key this fixture's own scripted provider is registered under, and
#: therefore the agent every channel here is bound to unless a test says
#: otherwise.
DEFAULT_AGENT_KEY = "builtin"


def channel_row(name: str, config: dict[str, Any], *, id: int = 1) -> Resource:
    """A channel row, for the supervision reconcilers driven directly.

    They are handed the resource now rather than an ``(id, config)`` tuple: the
    runtime needs the row's uid and name as well, and a tuple carrying a subset
    of a row is a place for the subset to fall behind it.
    """
    now = datetime.now(tz=UTC)
    return Resource(
        uid=f"uid-of-{name}",
        kind="channel",
        name=name,
        description=None,
        config=config,
        enabled=True,
        created_at=now,
        updated_at=now,
    )


class _StubAgentConfig(BaseModel):
    """Enough of the agent kind's config for a reference to resolve.

    The real ``AgentConfig`` pins ``type`` to the ``AgentType`` enum, which this
    fixture's own scripted provider ("builtin") is deliberately not a member of.
    What the channel kind reads off an agent row is its uid and its ``type``,
    and it reads the latter as a raw string precisely because it may not import
    the agent kind (the cross-kind import contract) — so policing which products
    exist belongs to the agent kind's own tests, not to these.
    """

    type: str


# ---------------------------------------------------------------------------
# Deterministic waiting
# ---------------------------------------------------------------------------


#: ``{channel name: uid}`` for every channel ``register_channel`` has made. A
#: channel is addressed on the wire by its uid now, but a test reads better with
#: the name it registered the channel under, so the helpers below translate.
_UIDS: dict[str, str] = {}


def uid_of(name: str) -> str:
    """The uid of the channel a test registered as ``name`` (unknown: as given)."""
    return _UIDS.get(name, name)


def inbound(
    channel: str,
    chat_id: str,
    text: str,
    *,
    sender_display: str = "Owner",
    sender_id: str | None = None,
    thread_id: str = "",
    chat_kind: str = "direct",
    chat_title: str = "",
    addressed: bool = True,
    mentions_others: bool = False,
    platform_message_id: str = "pm-1",
    ephemeral_id: str = "",
    sender_mention_id: str = "",
    attachments: Sequence[InboundAttachment] = (),
    quoted_message_id: str = "",
    group_main: bool = False,
) -> InboundMessage:
    return InboundMessage(
        channel=uid_of(channel),
        chat_id=chat_id,
        sender_display=sender_display,
        text=text,
        platform_message_id=platform_message_id,
        ephemeral_id=ephemeral_id,
        timestamp=datetime.now(tz=UTC),
        # A direct chat's id IS its person's id on both platforms, so a DM
        # message that names no sender is the chat's own person; a group message
        # that names none stays anonymous (the group gate refuses it).
        sender_id=(chat_id if chat_kind == "direct" else "") if sender_id is None else sender_id,
        sender_mention_id=sender_mention_id,
        thread_id=thread_id,
        chat_kind=chat_kind,
        chat_title=chat_title,
        addressed=addressed,
        mentions_others=mentions_others,
        attachments=tuple(attachments),
        quoted_message_id=quoted_message_id,
        group_main=group_main,
    )


ORIGIN_HEADER = "[Message origin]"


def turn_body(text: str) -> str:
    """The user's own text from a turn prompt, with the origin block ("Open every
    turn with its message origin") stripped.

    Every turn now opens with a provenance block; tests about queueing,
    ordering, threading and history assert on what the user actually typed, not
    on that header (``test_message_origin.py`` owns the header itself).
    """
    if not text.startswith(ORIGIN_HEADER):
        return text
    return text.split("\n\n", 1)[1]


def tap_event(
    channel: str,
    chat_id: str,
    data: str,
    *,
    sender_id: str | None = None,
    chat_kind: str = "direct",
    thread_id: str = "",
    platform_message_id: str = "",
) -> InboundCallback:
    """A selection-card button tap, for driving ``processor.on_callback``.

    ``platform_message_id`` is the card that was tapped; supply it to exercise
    the in-place card refresh.
    """
    return InboundCallback(
        channel=uid_of(channel),
        chat_id=chat_id,
        # As for ``inbound``: a direct chat's id is its person's id.
        sender_id=(chat_id if chat_kind == "direct" else "") if sender_id is None else sender_id,
        data=data,
        platform_message_id=platform_message_id,
        chat_kind=chat_kind,
        thread_id=thread_id,
    )


def lifecycle_event(
    channel: str, chat_id: str, kind: str, *, actor_display: str = ""
) -> InboundLifecycle:
    """A non-message platform event about the bot's standing in a chat, for
    driving ``processor.on_lifecycle``."""
    return InboundLifecycle(
        channel=uid_of(channel), chat_id=chat_id, kind=kind, actor_display=actor_display
    )


# ---------------------------------------------------------------------------
# Fakes at the non-local boundaries (IM platform, secret store, child process)
# ---------------------------------------------------------------------------


class FakeKeyring:
    """In-memory secret store satisfying the ResourceService keyring port."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def set(self, ref: str, value: str) -> None:
        self._values[ref] = value

    def get(self, ref: str) -> str | None:
        return self._values.get(ref)


class FakeModelSuggestions:
    """In-memory ModelSuggestionPort: per-agent model quick-picks."""

    def __init__(self) -> None:
        self._by_agent: dict[str, list[str]] = {}
        self._labels: dict[str, str] = {}

    def add(
        self, agent_key: str, models: list[str], *, labels: dict[str, str] | None = None
    ) -> None:
        self._by_agent[agent_key] = models
        self._labels.update(labels or {})

    async def suggest(self, agent_key: str) -> list[str]:
        return list(self._by_agent.get(agent_key, []))

    async def model_labels(self, agent_key: str) -> dict[str, str]:
        # Unlabelled unless a test names them, so a button shows its bare id.
        return {m: self._labels.get(m, m) for m in self._by_agent.get(agent_key, [])}


class StubWebSocketController:
    """Recording ``WebSocketControllerPort`` (no SDK, no socket, no thread).

    The real connector's threading is pinned in ``test_seatalk_ws.py`` against
    the fake SDK; what the runtime needs from it here is only the converge
    contract — who is wanted, with which materialized secrets.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self.started: dict[str, tuple[str, str]] = {}
        self.stopped: list[str] = []
        self.disposed = 0
        self._fail = fail
        self._states: dict[str, tuple[str, str | None]] = {}

    def running(self, name: str) -> bool:
        return name in self.started

    def active(self) -> set[str]:
        return set(self.started)

    def state(self, name: str) -> tuple[str, str | None] | None:
        return self._states.get(name)

    def set_state(self, name: str, state: str, error: str | None = None) -> None:
        self._states[name] = (state, error)

    async def ensure_running(self, name: str, app_id: str, app_secret: str) -> None:
        if self._fail:
            raise RuntimeError("the SeaTalk SDK is missing")
        self.started[name] = (app_id, app_secret)
        self._states.setdefault(name, ("connecting", None))

    async def ensure_stopped(self, name: str) -> None:
        self.stopped.append(name)
        self.started.pop(name, None)
        self._states.pop(name, None)

    async def dispose(self) -> None:
        self.disposed += 1
        for name in list(self.started):
            await self.ensure_stopped(name)


class _RecordingAdapter:
    """Wraps the scripted adapter of one turn and notes what it was asked."""

    def __init__(self, inner: Any, provider: ScriptedAgentProvider, conversation_id: str) -> None:
        self._inner = inner
        self._provider = provider
        self._conversation_id = conversation_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def run_turn(self, prompt: str, attachments: Any = ()) -> Any:
        self._provider.turns.append((self._conversation_id, prompt))
        return await self._inner.run_turn(prompt, attachments)


class ScriptedAgentProvider:
    """``AgentProvider`` whose adapter a test swaps in before sending.

    Coffer keeps no message text, so what a turn was asked is read back from
    ``turns``: one ``(conversation_id, prompt)`` per ``run_turn``, in order."""

    def __init__(self, adapter: Any, agent_key: str = "builtin", store: Any = None) -> None:
        self.adapter = adapter
        self.agent_key = agent_key
        self.last_agent_config: dict[str, Any] | None = None
        #: The conversation store, when set: the config a conversation opens
        #: with is persisted there, exactly as the real providers do.
        self.store = store
        self.turns: list[tuple[str, str]] = []

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        self.last_agent_config = agent_config
        if self.store is not None:
            await self.store.set_agent_config(conversation_id, AgentConfig.from_json(agent_config))

    async def build_adapter(self, conversation_id: str) -> Any:
        return _RecordingAdapter(self.adapter, self, conversation_id)

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
    threads: ChannelThreadConversationRepo
    cursors: ChannelThreadCursorRepo
    pairing: PairingManager
    provider: ScriptedAgentProvider
    registry: AgentProviderRegistry
    model_suggestions: FakeModelSuggestions
    chat: ChatService
    orchestrator: TurnOrchestrator
    processor: InboundProcessor
    runtime: ChannelRuntime
    service: ChannelService
    websockets: StubWebSocketController
    #: The same factory ``runtime`` was built with, kept so a test can stand up
    #: a SECOND runtime over these identical parts — which is what the machine
    #: binding needs: the point of the binding is that two daemons look at one
    #: resource table and only one of them starts anything.
    adapter_factory: Any
    created_adapters: list[FakeChannelAdapter] = field(default_factory=list)

    async def conversations(self) -> list[Conversation]:
        """Every conversation the channels opened, newest activity first."""
        return (await self.chat.page_conversations(limit=500)).items

    def user_texts(self, conversation_id: str) -> list[str]:
        """The prompts the conversation's turns were run with, in order, each
        without its message-origin block (what the person wrote, plus any thread
        or quote context the channel folded in)."""
        return [turn_body(p) for cid, p in self.provider.turns if cid == conversation_id]

    def raw_prompts(self, conversation_id: str) -> list[str]:
        """The prompts exactly as the adapter received them (origin block included)."""
        return [p for cid, p in self.provider.turns if cid == conversation_id]

    async def send(self, msg: InboundMessage) -> None:
        """Deliver ``msg`` and wait until its burst has been released into the
        conversation (spec channels "Take a burst of messages as one turn"), for a
        test that inspects the queue right after sending."""
        await self.processor.on_message(msg)
        await self.processor._burst.settled()

    def runtime_for(self, machine_id: str) -> ChannelRuntime:
        """A runtime that believes it is running on ``machine_id``.

        The fixture's own ``runtime`` is deliberately ungated — it has no
        machine, so it starts every enabled channel, which is what every test
        that is not about the binding wants. A test that IS about the binding
        asks for one of these instead, and can ask twice to have two machines
        reconciling the same table.
        """

        async def local_machine_id() -> str:
            return machine_id

        return ChannelRuntime(
            resources=self.resources,
            adapter_factory=self.adapter_factory,
            processor=self.processor,
            pairing=self.pairing,
            interval_seconds=0.05,
            machine_id=local_machine_id,
        )

    def service_for(self, runtime: ChannelRuntime) -> ChannelService:
        """A ``ChannelService`` reading a particular runtime's answers."""
        return ChannelService(
            resources=self.resources,
            peers=self.peers,
            threads=self.threads,
            pairing=self.pairing,
            runtime=runtime,
            audit=self.audit,
        )

    def add_agent(self, agent_key: str, reply: str = "from-other") -> ScriptedAgentProvider:
        """Register a second scripted agent so routing tests have a target."""
        provider = ScriptedAgentProvider(
            default_reply_adapter(reply), agent_key=agent_key, store=self.provider.store
        )
        self.registry.register(provider, display_name=agent_key.title())
        return provider

    async def register_agent_resource(self, name: str, agent_key: str) -> Resource:
        """An agent RESOURCE — what a scope and a ``default_agent`` both name.

        The turn platform's registry (``add_agent``) is keyed by agent key; the
        resource table is keyed by the row's uid, and the agent key is one
        field on it. A test about scope or routing needs the row, because the
        row is what a reference resolves to.
        """
        return await self.resources.register(
            kind="agent", name=name, config={"type": agent_key}, actor="test"
        )

    async def agent_uid(self, agent_key: str, name: str | None = None) -> str:
        """The uid of the agent row for ``agent_key``, registering it if needed.

        The helper a scope and a ``default_agent`` are both written with: both
        hold agent uids (ADR identity-is-the-uid-inside-the-file), and a uid
        only exists once there is a row to mint it for.
        """
        name = name or agent_key.replace("_", "-")
        existing = await self.resources.find_by_name("agent", name)
        if existing is not None:
            return existing.uid
        return (await self.register_agent_resource(name, agent_key)).uid

    async def bound(self, config: dict[str, Any]) -> dict[str, Any]:
        """``config`` with this fixture's own agent bound into it.

        For the tests that build a channel config by hand rather than through
        ``register_channel``. A channel that names no agent drives nothing and
        the runtime declines to start it, so a config that will be reconciled
        has to say which agent it is for.
        """
        return {**config, "default_agent": await self.agent_uid(DEFAULT_AGENT_KEY)}

    async def register_channel(
        self,
        name: str = "tg",
        *,
        ref: str = "channel/tg/bot-token",
        config: dict[str, Any] | None = None,
    ) -> Resource:
        """A channel, bound by default to this fixture's own scripted agent.

        The binding is explicit now because it has to be: ``default_agent``
        holds the uid of an agent ROW, so a channel registered without one is
        bound to nobody and the runtime declines to start it. It used to be a
        constant in the schema, which is exactly the fiction this change
        removes — there was never an agent behind it.
        """
        self.keyring.set(ref, f"secret-for-{ref}")
        cfg = (
            dict(config)
            if config is not None
            else {"channel_type": "telegram", "bot_token_ref": ref}
        )
        cfg.setdefault("default_agent", await self.agent_uid(DEFAULT_AGENT_KEY))
        resource = await self.resources.register(
            kind="channel", name=name, config=cfg, actor="test"
        )
        _UIDS[name] = resource.uid
        return resource

    async def pair(
        self, resource: Resource, chat_id: str = "owner", *, sender_id: str | None = None
    ) -> ChannelPeer:
        peer = ChannelPeer(
            resource_uid=resource.uid,
            chat_id=chat_id,
            display_name="Owner",
            paired_at=datetime.now(tz=UTC),
            # Every pairing carries its sender; a DM's is the chat's own id.
            sender_id=chat_id if sender_id is None else sender_id,
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
        require_mention: bool = True,
        ignore_other_mentions: bool = False,
        agent_scope: Scope | None = None,
        directories: Sequence[str] = (),
        new_conversation_after_idle_hours: float = 24.0,
    ) -> FakeChannelAdapter:
        adapter = adapter or FakeChannelAdapter()
        _UIDS[resource.name] = resource.uid
        if hasattr(adapter, "_name"):
            # A real adapter built by the infrastructure fixtures was named
            # "tg"/"st"; in the daemon the factory names it by the channel's uid,
            # which is what its inbound messages carry.
            adapter._name = resource.uid
        self.processor.bind(
            ChannelBinding(
                resource=resource,
                channel_type=str(resource.config.get("channel_type", "telegram")),
                default_agent=default_agent,
                default_agent_config=default_agent_config,
                adapter=adapter,
                require_mention=require_mention,
                ignore_other_mentions=ignore_other_mentions,
                agent_scope=agent_scope,
                directories=tuple(directories),
                new_conversation_after_idle_hours=new_conversation_after_idle_hours,
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

    async def active_conversation(
        self, resource: Resource, chat_id: str = "owner", thread_id: str = ""
    ) -> str | None:
        """The conversation a turn drives for this ``(chat, thread)`` — the
        per-thread binding ("Key conversation identity by channel, chat and
        thread"), which replaced ``peer.active_conversation_id``
        as the source of truth."""
        row = await self.threads.get(resource.uid, chat_id, thread_id)
        return row.active_conversation_id if row is not None else None

    async def thread_preferred_agent(
        self, resource: Resource, chat_id: str = "owner", thread_id: str = ""
    ) -> str | None:
        row = await self.threads.get(resource.uid, chat_id, thread_id)
        return row.preferred_agent if row is not None else None

    async def audit_entries(
        self, event_type: str, resource: Resource | None = None
    ) -> list[AuditEntry]:
        """One channel's trail, or every channel's. Filtered by the resource
        rather than by a name: the audit service takes the row, so a rename
        leaves the history addressable by the thing it is about."""
        return await self.audit.query(kind="channel", resource=resource, event_type=event_type)


async def _build_env(tmp_path: Any) -> ChannelEnv:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'runs.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    audit = AuditService(SqlAlchemyAuditRepo(sm))
    keyring = FakeKeyring()
    kinds: dict[str, Any] = {}
    resource_repo = make_resource_repo()
    resources = ResourceService(kinds=kinds, repo=resource_repo, audit=audit, secrets=keyring)
    # As channel_wiring builds them: the pairings document is named after its
    # channel and goes with the channel's rename and delete.
    peers = ChannelPeerRepo(name_of=resource_repo.name_of)
    resource_repo.add_follower(peers.documents.follow)
    threads = ChannelThreadConversationRepo(sm)
    cursors = ChannelThreadCursorRepo(sm)
    pairing = PairingManager()

    conversation_repo = ConversationRepo(sm)
    provider = ScriptedAgentProvider(default_reply_adapter(), store=conversation_repo)
    registry = AgentProviderRegistry()
    registry.register(provider, display_name="Coffer Assistant")
    chat = ChatService(
        conversations=conversation_repo,
        registry=registry,
    )
    orchestrator = TurnOrchestrator(chat_service=chat, registry=registry)
    model_suggestions = FakeModelSuggestions()
    processor = InboundProcessor(
        peers=peers,
        threads=threads,
        pairing=pairing,
        conversations=chat,
        turns=orchestrator,
        audit=audit,
        agents=registry,
        model_suggestions=model_suggestions,
        replies=ChannelReplyRepo(sm),
        cursors=cursors,
        questions=ChatQuestions(),
    )

    created_adapters: list[FakeChannelAdapter] = []

    async def adapter_factory(name: str, config: dict[str, object]) -> FakeChannelAdapter:
        adapter = FakeChannelAdapter()
        created_adapters.append(adapter)
        return adapter

    resolver = SecretResolver(keyring)

    async def materialize(refs: dict[str, str], destination: Any = None) -> dict[str, str]:
        # The real resolver, so failures raise SecretMissing exactly as
        # production wiring does.
        return resolver.materialize(refs, destination)

    websockets = StubWebSocketController()
    runtime = ChannelRuntime(
        resources=resources,
        adapter_factory=adapter_factory,
        processor=processor,
        pairing=pairing,
        websockets=websockets,
        materialize=materialize,
        interval_seconds=0.05,
    )

    async def on_delete(resource: Resource) -> None:
        await runtime.evict(resource)

    async def agent_names() -> dict[str, str]:
        """Every registered agent's uid mapped to its name, wired exactly as
        production wires it. It decides nothing — a scope and a channel's
        ``default_agent`` are both agent uids — it only lets a refusal name the
        agent the way the owner does."""
        return {r.uid: r.name for r in await resources.list(kind="agent")}

    kinds["channel"] = make_channel_kind(on_delete=on_delete, agent_names=agent_names)
    # Enough of the agent kind for a scope to have something to name. The real
    # one carries on-disk lifecycle these tests have no use for; what they need
    # is that `kind=agent` rows exist and validate their config the same way.
    kinds["agent"] = Kind(name="agent", display_name="Agent", config_schema=_StubAgentConfig)

    service = ChannelService(
        resources=resources,
        peers=peers,
        threads=threads,
        pairing=pairing,
        runtime=runtime,
        audit=audit,
    )
    return ChannelEnv(
        adapter_factory=adapter_factory,
        engine=engine,
        audit=audit,
        keyring=keyring,
        resources=resources,
        peers=peers,
        threads=threads,
        cursors=cursors,
        pairing=pairing,
        provider=provider,
        registry=registry,
        model_suggestions=model_suggestions,
        chat=chat,
        orchestrator=orchestrator,
        processor=processor,
        runtime=runtime,
        service=service,
        websockets=websockets,
        created_adapters=created_adapters,
    )


async def _drain_background_tasks(timeout: float = 5.0) -> None:
    """Cancel and await every task except the caller, until none is left.

    Cancelling a task that awaits a shielded write leaves the write itself
    running, so a second pass picks up what the first one unmasked.
    """
    await tasks().shutdown(timeout=timeout)
    for _ in range(5):
        leftovers = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if not leftovers:
            return
        for task in leftovers:
            task.cancel()
        await asyncio.wait(leftovers, timeout=timeout)


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
        # Cancel every still-running task the test left behind (turns, burst
        # windows, trailing partial flushes, reply-ledger writes, tickers) and
        # wait for them BEFORE closing the database they write to. A task that
        # outlives the engine holds a pooled aiosqlite connection, and the
        # dispose then blocks on it (a >300s CI hang in teardown).
        await _drain_background_tasks()
        e.processor.shutdown()
        await e.engine.dispose()
