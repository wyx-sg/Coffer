"""The shared inbound pipeline: every channel's messages flow through here.

owner gate → pairing claim → commands → queueing → conversation mapping →
turn driving (rendering lives in ``turn_render``) → approval bridging.

The chat platform is reached only through its public seams (conversation
service + turn orchestrator), exactly like the web UI: agents cannot tell a
channel turn from a UI turn, and a new agent provider is reachable from every
channel with no code here changing.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from coffer.application.audit_service import AuditService
from coffer.application.channel.conversation_spec import resolve_conversation_spec
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.ports import (
    AgentCatalogPort,
    ChannelAdapter,
    ChannelPeer,
    ChannelPeerRepoPort,
    ModelCatalogPort,
)
from coffer.application.channel.turn_render import PendingApproval, TurnRenderer
from coffer.application.chat.ports import ApprovalDecision
from coffer.domain.audit import AuditEventType
from coffer.domain.channel.envelopes import (
    ApprovalClick,
    InboundMessage,
    parse_approval_value,
)
from coffer.domain.chat.errors import (
    AgentConfigRejected,
    ApprovalNotFound,
    ConversationNotFound,
    TurnInProgress,
)
from coffer.domain.errors import CofferError
from coffer.domain.resource import ResourceRef

_logger = logging.getLogger(__name__)

_QUEUE_MAX = 10

_HELP_TEXT = (
    "Coffer channel commands:\n"
    "/new — start a fresh conversation\n"
    "/agent [key] — show or switch the agent (opens a fresh conversation)\n"
    "/cwd [name] — show or switch the workspace (opens a fresh conversation)\n"
    "/model [name] — show or switch the model (next turn)\n"
    "/stop — interrupt the running turn\n"
    "/status — active conversation, agent, workspace, and turn state\n"
    "/help — this list"
)


class ConversationPort(Protocol):
    """The slice of the chat platform's conversation service we use."""

    async def create_conversation(
        self, *, agent_key: str, agent_config: dict[str, Any] | None, actor: str
    ) -> Any: ...

    async def get_conversation(self, conversation_id: str) -> Any: ...

    async def set_conversation_model(
        self, conversation_id: str, *, model_id: str | None
    ) -> Any: ...

    async def get_agent_config(self, conversation_id: str) -> dict[str, Any]: ...

    async def set_agent_config(self, conversation_id: str, config: dict[str, Any]) -> None: ...


class TurnPort(Protocol):
    """The slice of the turn orchestrator we use."""

    async def start_turn(self, conversation_id: str, user_text: str) -> asyncio.Queue[Any]: ...

    def interrupt_turn(self, conversation_id: str) -> None: ...

    def submit_approval(
        self, conversation_id: str, request_id: str, decision: ApprovalDecision
    ) -> None: ...


@dataclass(frozen=True)
class ChannelBinding:
    """A live channel the runtime has started: resource identity + adapter."""

    name: str
    resource_id: int
    channel_type: str
    default_agent: str
    default_agent_config: dict[str, Any] | None
    adapter: ChannelAdapter
    workspaces: dict[str, str] = field(default_factory=dict)  # name -> absolute path
    default_workspace: str | None = None


@dataclass
class _Session:
    queue: deque[str] = field(default_factory=lambda: deque(maxlen=_QUEUE_MAX))
    drain_task: asyncio.Task[None] | None = None
    pending_approvals: dict[str, PendingApproval] = field(default_factory=dict)
    # The conversation whose turn is draining right now (None between turns).
    # Tracked separately from the peer's active conversation: ``/new`` rebinds
    # the peer while a turn keeps draining on the old conversation, so ``/stop``
    # and unbind must target the turn that is actually running.
    running_conversation_id: str | None = None


class InboundProcessor:
    """Owner-gated bridge from adapter callbacks to chat-platform turns."""

    def __init__(
        self,
        *,
        peers: ChannelPeerRepoPort,
        pairing: PairingManager,
        conversations: ConversationPort,
        turns: TurnPort,
        audit: AuditService,
        agents: AgentCatalogPort,
        models: ModelCatalogPort,
    ) -> None:
        self._peers = peers
        self._pairing = pairing
        self._conversations = conversations
        self._turns = turns
        self._audit = audit
        self._agents = agents
        self._models = models
        self._bindings: dict[str, ChannelBinding] = {}
        self._sessions: dict[str, _Session] = {}

    # -- runtime registry ------------------------------------------------

    def bind(self, binding: ChannelBinding) -> None:
        self._bindings[binding.name] = binding

    def unbind(self, name: str) -> None:
        self._bindings.pop(name, None)
        session = self._sessions.pop(name, None)
        if session is None:
            return
        if session.drain_task is not None:
            session.drain_task.cancel()
        # Cancelling the drain task only stops the renderer; the orchestrator
        # turn keeps running and would deliver its reply to the web UI alone,
        # leaving the bot silent. Interrupt the live turn so its partial reply
        # is the contract — not a turn that completes undelivered.
        if session.running_conversation_id is not None:
            with contextlib.suppress(Exception):
                self._turns.interrupt_turn(session.running_conversation_id)
            session.running_conversation_id = None
        # A turn parked on an approval gate would wait forever once its
        # prompt's buttons are gone — interrupt it instead of wedging the
        # conversation until a manual /stop.
        for pending in session.pending_approvals.values():
            with contextlib.suppress(Exception):
                self._turns.interrupt_turn(pending.conversation_id)
        session.pending_approvals.clear()

    def binding(self, name: str) -> ChannelBinding | None:
        return self._bindings.get(name)

    def shutdown(self) -> None:
        for name in list(self._sessions):
            self.unbind(name)
        self._bindings.clear()

    # -- adapter callbacks -------------------------------------------------

    async def on_message(self, msg: InboundMessage) -> None:
        binding = self._bindings.get(msg.channel)
        if binding is None:
            return
        peer = await self._peers.get(binding.resource_id)
        if peer is None or peer.chat_id != msg.chat_id:
            await self._maybe_pair(binding, msg)
            return
        if peer.sender_id is not None and peer.sender_id != msg.sender_id:
            # Right chat (e.g. a paired group), wrong member — ignore silently.
            # Never fall through to pairing: an intruder must not be able to
            # re-pair the channel by sending a code into the owner's chat.
            return
        text = msg.text.strip()
        if not text:
            # Non-text content reaches the core as an empty envelope.
            await self._safe_send(
                binding, peer.chat_id, "⚠️ Only text messages are supported for now."
            )
            return
        if text.startswith("/"):
            await self._handle_command(binding, peer, text)
            return
        session = self._session(msg.channel)
        if len(session.queue) >= _QUEUE_MAX:
            await self._safe_send(binding, peer.chat_id, "⚠️ Busy — message dropped, try again.")
            return
        session.queue.append(text)
        if session.drain_task is None or session.drain_task.done():
            session.drain_task = asyncio.create_task(
                self._drain(binding), name=f"channel-drain:{binding.name}"
            )

    async def on_approval_click(self, click: ApprovalClick) -> None:
        binding = self._bindings.get(click.channel)
        if binding is None:
            return
        peer = await self._peers.get(binding.resource_id)
        if peer is None or peer.chat_id != click.chat_id:
            return  # only the owner decides
        if peer.sender_id is not None and peer.sender_id != click.sender_id:
            return  # right chat, wrong member
        parsed = parse_approval_value(click.value)
        if parsed is None:
            return
        request_id, decision_word = parsed
        session = self._session(click.channel)
        pending = session.pending_approvals.pop(request_id, None)
        if pending is None:
            return
        outcome = "✅ Approved" if decision_word == "allow" else "❌ Denied"
        decision: Literal["allow", "deny"] = "allow" if decision_word == "allow" else "deny"
        try:
            self._turns.submit_approval(
                pending.conversation_id,
                request_id,
                ApprovalDecision(behavior=decision),
            )
        except ApprovalNotFound:
            outcome = "⌛ Expired"
        await self._audit.record(
            AuditEventType.CHANNEL_APPROVAL_RESOLVED.value,
            ref=ResourceRef(kind="channel", name=binding.name),
            actor=peer.display_name or "channel",
            details={
                "channel": binding.name,
                "chat_id": peer.chat_id,
                "tool_name": pending.tool_name,
                "request_id": request_id,
                "decision": decision_word,
            },
        )
        with contextlib.suppress(Exception):
            await binding.adapter.resolve_approval_prompt(
                pending.chat_id, pending.message_id, outcome
            )

    # -- pairing -----------------------------------------------------------

    async def _maybe_pair(self, binding: ChannelBinding, msg: InboundMessage) -> None:
        # Non-text content arrives as an empty envelope; never let it burn a
        # pairing attempt (a stranger's sticker must not invalidate the code).
        if not msg.text.strip():
            return
        if not self._pairing.try_claim(binding.name, msg.text):
            _logger.debug("channel.inbound.ignored", extra={"channel": binding.name})
            return
        peer = ChannelPeer(
            resource_id=binding.resource_id,
            chat_id=msg.chat_id,
            display_name=msg.sender_display,
            paired_at=datetime.now(tz=UTC),
            active_conversation_id=None,
            sender_id=msg.sender_id or None,
        )
        await self._peers.upsert(peer)
        await self._audit.record(
            AuditEventType.CHANNEL_PAIRED.value,
            ref=ResourceRef(kind="channel", name=binding.name),
            actor="channel",
            details={"chat_id": msg.chat_id, "display_name": msg.sender_display},
        )
        await self._safe_send(
            binding,
            msg.chat_id,
            f"✅ Paired. This chat now controls Coffer channel '{binding.name}'.\n\n{_HELP_TEXT}",
        )

    # -- commands ------------------------------------------------------------

    async def _handle_command(self, binding: ChannelBinding, peer: ChannelPeer, text: str) -> None:
        command = text.split()[0].lower()
        if command in ("/help", "/start"):
            await self._safe_send(binding, peer.chat_id, _HELP_TEXT)
        elif command == "/new":
            await self._open_and_report(binding, peer, "🆕 Started a fresh conversation.")
        elif command == "/agent":
            await self._cmd_agent(binding, peer, text)
        elif command == "/cwd":
            await self._cmd_cwd(binding, peer, text)
        elif command == "/model":
            await self._cmd_model(binding, peer, text)
        elif command == "/stop":
            # The turn that is actually draining wins over the peer's bound
            # conversation: after ``/new`` rebinds the peer, a turn can still be
            # running on the previous conversation. Stopping the bound (idle)
            # conversation would claim "Stopping…" while the real turn runs on.
            session = self._session(binding.name)
            target = session.running_conversation_id or peer.active_conversation_id
            if target is not None:
                self._turns.interrupt_turn(target)
                await self._safe_send(binding, peer.chat_id, "⏹ Stopping…")
            else:
                await self._safe_send(binding, peer.chat_id, "Nothing is running.")
        elif command == "/status":
            session = self._session(binding.name)
            running = session.drain_task is not None and not session.drain_task.done()
            conv = peer.active_conversation_id or "none yet"
            agent = peer.preferred_agent or binding.default_agent
            workspace = peer.preferred_workspace or binding.default_workspace or "(none)"
            await self._safe_send(
                binding,
                peer.chat_id,
                f"Conversation: {conv}\nAgent: {agent}\nWorkspace: {workspace}\n"
                f"Turn running: {'yes' if running else 'no'}\nQueued: {len(session.queue)}",
            )
        else:
            await self._safe_send(binding, peer.chat_id, f"Unknown command {command}. /help")

    # -- structural switches (/agent, /cwd) --------------------------------------

    async def _cmd_agent(self, binding: ChannelBinding, peer: ChannelPeer, text: str) -> None:
        parts = text.split()
        keys = self._agents.agent_keys()
        if len(parts) < 2:
            current = peer.preferred_agent or binding.default_agent
            await self._safe_send(
                binding,
                peer.chat_id,
                f"Agent: {current}\nAvailable: {', '.join(keys)}",
            )
            return
        key = parts[1]
        if key not in keys:
            await self._safe_send(
                binding, peer.chat_id, f"Unknown agent '{key}'. Available: {', '.join(keys)}"
            )
            return
        await self._peers.set_preferences(
            binding.resource_id, preferred_agent=key, preferred_workspace=peer.preferred_workspace
        )
        await self._open_and_report(
            binding, replace(peer, preferred_agent=key), f"🔀 Switched to agent '{key}'."
        )

    async def _cmd_cwd(self, binding: ChannelBinding, peer: ChannelPeer, text: str) -> None:
        parts = text.split()
        available = ", ".join(sorted(binding.workspaces)) or "(none configured)"
        if len(parts) < 2:
            current = peer.preferred_workspace or binding.default_workspace or "(none)"
            await self._safe_send(
                binding, peer.chat_id, f"Workspace: {current}\nAvailable: {available}"
            )
            return
        name = parts[1]
        if name not in binding.workspaces:
            # A bare path is never honored — only operator-authorized names.
            await self._safe_send(
                binding, peer.chat_id, f"Unknown workspace '{name}'. Available: {available}"
            )
            return
        await self._peers.set_preferences(
            binding.resource_id, preferred_agent=peer.preferred_agent, preferred_workspace=name
        )
        await self._open_and_report(
            binding, replace(peer, preferred_workspace=name), f"📁 Switched to workspace '{name}'."
        )

    # -- parametric switch (/model: same conversation, next turn) ----------------

    async def _cmd_model(self, binding: ChannelBinding, peer: ChannelPeer, text: str) -> None:
        # /model targets the active conversation (created on first contact). The
        # model is re-read each turn, so the switch needs no new conversation.
        try:
            conversation_id = await self._ensure_conversation(binding, peer)
        except CofferError as e:
            await self._safe_send(
                binding, peer.chat_id, self._explain_conversation_error(binding, e)
            )
            return
        conv = await self._conversations.get_conversation(conversation_id)
        builtin = conv.agent_key == "builtin"
        parts = text.split()
        if len(parts) < 2:
            if builtin:
                current = conv.model_id or "(default)"
                available = ", ".join(n for _id, n in self._models.list_models()) or "(none)"
                await self._safe_send(
                    binding, peer.chat_id, f"Model: {current}\nAvailable: {available}"
                )
            else:
                cfg = await self._conversations.get_agent_config(conversation_id)
                current = cfg.get("model") or "(CLI default)"
                await self._safe_send(
                    binding, peer.chat_id, f"Model: {current}\n(passed through to the agent's CLI)"
                )
            return
        name = parts[1]
        if builtin:
            model_id = self._models.resolve(name)
            if model_id is None:
                available = ", ".join(n for _id, n in self._models.list_models()) or "(none)"
                await self._safe_send(
                    binding, peer.chat_id, f"Unknown model '{name}'. Available: {available}"
                )
                return
            await self._conversations.set_conversation_model(conversation_id, model_id=model_id)
        else:
            # Bridged agents: raw passthrough; we do not own the CLI's model
            # namespace, so a bad name surfaces as the CLI's own error next turn.
            cfg = await self._conversations.get_agent_config(conversation_id)
            cfg["model"] = name
            await self._conversations.set_agent_config(conversation_id, cfg)
        await self._safe_send(binding, peer.chat_id, f"🧠 Model set to '{name}' for the next turn.")

    async def _open_and_report(
        self, binding: ChannelBinding, peer: ChannelPeer, success: str
    ) -> None:
        try:
            await self._open_conversation(binding, peer)
        except CofferError as e:
            await self._safe_send(
                binding, peer.chat_id, self._explain_conversation_error(binding, e)
            )
            return
        await self._safe_send(binding, peer.chat_id, success)

    def _explain_conversation_error(self, binding: ChannelBinding, e: CofferError) -> str:
        if isinstance(e, AgentConfigRejected) and e.reason in {
            "invalid_cwd",
            "cwd_not_a_directory",
        }:
            available = ", ".join(sorted(binding.workspaces)) or "(none configured)"
            return (
                f"⚠️ That agent needs a workspace. Pick one with /cwd <name>. Available: {available}"
            )
        return f"⚠️ {e} [{e.code}]"

    # -- turn driving ----------------------------------------------------------

    async def _drain(self, binding: ChannelBinding) -> None:
        session = self._session(binding.name)
        while session.queue:
            text = session.queue.popleft()
            peer = await self._peers.get(binding.resource_id)
            if peer is None:
                break
            try:
                await self._run_turn(binding, peer, text)
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("channel.turn.failed", extra={"channel": binding.name})

    async def _ensure_conversation(self, binding: ChannelBinding, peer: ChannelPeer) -> str:
        if peer.active_conversation_id is not None:
            try:
                await self._conversations.get_conversation(peer.active_conversation_id)
            except ConversationNotFound:
                pass
            else:
                return peer.active_conversation_id
        return await self._open_conversation(binding, peer)

    async def _open_conversation(self, binding: ChannelBinding, peer: ChannelPeer) -> str:
        """Create a conversation from the peer's sticky choices + channel
        defaults (resolver) and make it the peer's active conversation."""
        spec = resolve_conversation_spec(
            default_agent=binding.default_agent,
            default_agent_config=binding.default_agent_config,
            workspaces=binding.workspaces,
            default_workspace=binding.default_workspace,
            preferred_agent=peer.preferred_agent,
            preferred_workspace=peer.preferred_workspace,
        )
        conv = await self._conversations.create_conversation(
            agent_key=spec.agent_key, agent_config=spec.agent_config, actor="channel"
        )
        await self._peers.set_active_conversation(binding.resource_id, conv.id)
        return str(conv.id)

    async def _run_turn(self, binding: ChannelBinding, peer: ChannelPeer, text: str) -> None:
        adapter = binding.adapter
        try:
            conversation_id = await self._ensure_conversation(binding, peer)
        except CofferError as e:
            # e.g. the channel's default agent is unknown/misconfigured, or a
            # bridged agent has no workspace — the owner must see it in the chat,
            # not only in the daemon log.
            await self._safe_send(
                binding, peer.chat_id, self._explain_conversation_error(binding, e)
            )
            return
        # A channel message driving a turn is first-class in the audit log:
        # who (the peer), through which channel, drives which agent.
        with contextlib.suppress(Exception):
            conv = await self._conversations.get_conversation(conversation_id)
            await self._audit.record(
                AuditEventType.CHANNEL_TURN_STARTED.value,
                ref=ResourceRef(kind="channel", name=binding.name),
                actor=peer.display_name or "channel",
                details={
                    "channel": binding.name,
                    "chat_id": peer.chat_id,
                    "display_name": peer.display_name,
                    "agent_key": conv.agent_key,
                    "conversation_id": conversation_id,
                },
            )
        if adapter.capabilities.supports_typing:
            with contextlib.suppress(Exception):
                await adapter.send_typing(peer.chat_id)
        try:
            queue = await self._turns.start_turn(conversation_id, text)
        except TurnInProgress:
            await self._safe_send(
                binding, peer.chat_id, "⚠️ A turn is already running for this conversation."
            )
            return
        except CofferError as e:
            await self._safe_send(binding, peer.chat_id, f"⚠️ {e} [{e.code}]")
            return
        session = self._session(binding.name)

        async def _send(message: str) -> None:
            await self._safe_send(binding, peer.chat_id, message)

        renderer = TurnRenderer(
            channel=binding.name,
            adapter=adapter,
            chat_id=peer.chat_id,
            conversation_id=conversation_id,
            pending_approvals=session.pending_approvals,
            send=_send,
        )
        # Track the live turn so /stop and unbind can target it even after /new
        # rebinds the peer to a fresh conversation mid-turn.
        session.running_conversation_id = conversation_id
        try:
            await renderer.consume(queue)
        finally:
            if session.running_conversation_id == conversation_id:
                session.running_conversation_id = None

    # -- helpers ---------------------------------------------------------------

    def _session(self, name: str) -> _Session:
        if name not in self._sessions:
            self._sessions[name] = _Session()
        return self._sessions[name]

    async def _safe_send(self, binding: ChannelBinding, chat_id: str, text: str) -> None:
        try:
            await binding.adapter.send_text(chat_id, text)
        except Exception:
            _logger.exception("channel.send.failed", extra={"channel": binding.name})
