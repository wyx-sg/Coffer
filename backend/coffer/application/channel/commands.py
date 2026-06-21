"""Slash-command handling for channels: /help /new /agent /model /stop /status.

The router owns the structural switch (/agent → a fresh conversation, sticky on
the peer) and the parametric switch (/model → next turn, same conversation).
Conversation creation is delegated to ``conversation_ops`` so the inbound
turn-driver and this router agree on how a channel conversation is born.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, Protocol

from coffer.application.channel.conversation_ops import (
    ensure_conversation,
    explain_conversation_error,
    open_conversation,
)
from coffer.application.channel.ports import (
    AgentCatalogPort,
    ChannelBinding,
    ChannelPeer,
    ChannelPeerRepoPort,
    ModelSuggestionPort,
)
from coffer.domain.channel.envelopes import ChoiceButton
from coffer.domain.errors import CofferError

HELP_TEXT = (
    "Coffer channel commands:\n"
    "/new — start a fresh conversation\n"
    "/agent [key] — show or switch the agent (opens a fresh conversation)\n"
    "/model [name] — show or switch the model (next turn)\n"
    "/stop — interrupt the running turn\n"
    "/status — active conversation, agent, and turn state\n"
    "/help — this list"
)

# Telegram caps inline-button callback_data at 64 bytes; skip any option whose
# encoded value would exceed it (SeaTalk is more generous, so this is the floor).
_CALLBACK_MAX_BYTES = 64


def _callback_fits(value: str) -> bool:
    return len(value.encode("utf-8")) <= _CALLBACK_MAX_BYTES


class SafeSend(Protocol):
    """Owner-gated send supplied by the processor: ``(binding, chat_id, text)``
    plus optional selection-card ``buttons`` (rendered only where the transport
    ``supports_buttons``; ignored otherwise)."""

    async def __call__(
        self,
        binding: ChannelBinding,
        chat_id: str,
        text: str,
        *,
        buttons: Sequence[ChoiceButton] | None = None,
    ) -> None: ...


class ChannelCommands:
    """Owner-gated slash commands, operating on the processor's shared ports."""

    def __init__(
        self,
        *,
        peers: ChannelPeerRepoPort,
        conversations: Any,
        turns: Any,
        agents: AgentCatalogPort,
        model_suggestions: ModelSuggestionPort,
    ) -> None:
        self._peers = peers
        self._conversations = conversations
        self._turns = turns
        self._agents = agents
        self._model_suggestions = model_suggestions

    async def handle(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        text: str,
        session: Any,
        send: SafeSend,
    ) -> None:
        command = text.split()[0].lower()
        if command in ("/help", "/start"):
            await send(binding, peer.chat_id, HELP_TEXT)
        elif command == "/new":
            await self._open_and_report(binding, peer, send, "🆕 Started a fresh conversation.")
        elif command == "/agent":
            await self._cmd_agent(binding, peer, text, send)
        elif command == "/model":
            await self._cmd_model(binding, peer, text, send)
        elif command == "/stop":
            # The turn that is actually draining wins over the peer's bound
            # conversation: after ``/new`` rebinds the peer, a turn can still be
            # running on the previous conversation. Stopping the bound (idle)
            # conversation would claim "Stopping…" while the real turn runs on.
            target = session.running_conversation_id or peer.active_conversation_id
            if target is not None:
                self._turns.interrupt_turn(target)
                await send(binding, peer.chat_id, "⏹ Stopping…")
            else:
                await send(binding, peer.chat_id, "Nothing is running.")
        elif command == "/status":
            running = session.drain_task is not None and not session.drain_task.done()
            conv = peer.active_conversation_id or "none yet"
            agent = peer.preferred_agent or binding.default_agent
            await send(
                binding,
                peer.chat_id,
                f"Conversation: {conv}\nAgent: {agent}\n"
                f"Turn running: {'yes' if running else 'no'}\nQueued: {len(session.queue)}",
            )
        else:
            await send(binding, peer.chat_id, f"Unknown command {command}. /help")

    # -- structural switches (open a fresh conversation, sticky on the peer) ------

    async def _cmd_agent(
        self, binding: ChannelBinding, peer: ChannelPeer, text: str, send: SafeSend
    ) -> None:
        parts = text.split()
        keys = self._agents.agent_keys()
        if len(parts) < 2:
            current = peer.preferred_agent or binding.default_agent
            if binding.adapter.capabilities.supports_buttons:
                buttons = [
                    ChoiceButton(
                        label=name + (" ✓" if key == current else ""),
                        value=f"agent:{key}",
                    )
                    for key, name in self._agents.agent_choices()
                    if _callback_fits(f"agent:{key}")
                ]
                if buttons:
                    await send(
                        binding,
                        peer.chat_id,
                        f"Current agent: {current}\nTap to switch:",
                        buttons=buttons,
                    )
                    return
            await send(binding, peer.chat_id, f"Agent: {current}\nAvailable: {', '.join(keys)}")
            return
        key = parts[1]
        if key not in keys:
            await send(
                binding, peer.chat_id, f"Unknown agent '{key}'. Available: {', '.join(keys)}"
            )
            return
        await self.apply_agent(binding, peer, key, send)

    async def apply_agent(
        self, binding: ChannelBinding, peer: ChannelPeer, key: str, send: SafeSend
    ) -> None:
        """The structural switch to ``key`` (assumes ``key`` already validated):
        stick it on the peer and open a fresh conversation. Shared by the text
        ``/agent <key>`` path and a card tap."""
        await self._peers.set_preferences(binding.resource_id, preferred_agent=key)
        await self._open_and_report(
            binding, replace(peer, preferred_agent=key), send, f"🔀 Switched to agent '{key}'."
        )

    # -- parametric switch (/model: same conversation, next turn) -----------------

    async def _cmd_model(
        self, binding: ChannelBinding, peer: ChannelPeer, text: str, send: SafeSend
    ) -> None:
        try:
            conversation_id = await ensure_conversation(
                self._conversations, self._peers, binding, peer
            )
        except CofferError as e:
            await send(binding, peer.chat_id, explain_conversation_error(e))
            return
        parts = text.split()
        if len(parts) < 2:
            # Show the current model. Coffer-managed CLI agents own their own
            # model namespace (ADR-024 retired the builtin model-registry agent),
            # so we just report what will be passed through to the agent's CLI.
            cfg = await self._conversations.get_agent_config(conversation_id)
            current = cfg.model or "(CLI default)"
            if binding.adapter.capabilities.supports_buttons:
                agent_key = peer.preferred_agent or binding.default_agent
                picks = await self._model_suggestions.suggest(agent_key)
                buttons = [
                    ChoiceButton(
                        label=m + (" ✓" if m == cfg.model else ""),
                        value=f"model:{m}",
                    )
                    for m in picks
                    if _callback_fits(f"model:{m}")
                ]
                if buttons:
                    await send(
                        binding,
                        peer.chat_id,
                        f"Current model: {current}\nTap a quick-pick (or send /model <name>):",
                        buttons=buttons,
                    )
                    return
            await send(
                binding, peer.chat_id, f"Model: {current}\n(passed through to the agent's CLI)"
            )
            return
        await self.apply_model(binding, peer, parts[1], send)

    async def apply_model(
        self, binding: ChannelBinding, peer: ChannelPeer, name: str, send: SafeSend
    ) -> None:
        """The parametric switch: set the next-turn model on the peer's
        conversation. Raw passthrough — we do not own the CLI's model namespace,
        so a bad name surfaces as the CLI's own error next turn. Shared by the
        text ``/model <name>`` path and a card tap."""
        try:
            conversation_id = await ensure_conversation(
                self._conversations, self._peers, binding, peer
            )
        except CofferError as e:
            await send(binding, peer.chat_id, explain_conversation_error(e))
            return
        cfg = await self._conversations.get_agent_config(conversation_id)
        await self._conversations.set_agent_config(conversation_id, replace(cfg, model=name))
        await send(binding, peer.chat_id, f"🧠 Model set to '{name}' for the next turn.")

    # -- card tap → the same switch (owner gate enforced by the processor) ---------

    async def dispatch_callback(
        self, binding: ChannelBinding, peer: ChannelPeer, data: str, send: SafeSend
    ) -> None:
        """Route a selection-card tap (``data`` = the tapped ``ChoiceButton.value``)
        to the same switch the text command performs. The processor has already
        owner-gated the tap."""
        kind, _, value = data.partition(":")
        if kind == "agent":
            if value not in self._agents.agent_keys():
                await send(binding, peer.chat_id, f"Unknown agent '{value}'.")
                return
            await self.apply_agent(binding, peer, value, send)
        elif kind == "model" and value:
            await self.apply_model(binding, peer, value, send)

    async def _open_and_report(
        self, binding: ChannelBinding, peer: ChannelPeer, send: SafeSend, success: str
    ) -> None:
        try:
            await open_conversation(self._conversations, self._peers, binding, peer)
        except CofferError as e:
            await send(binding, peer.chat_id, explain_conversation_error(e))
            return
        await send(binding, peer.chat_id, success)
