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

from coffer.application.channel.card_delivery import deliver_card, dispatch_card_tap
from coffer.application.channel.conversation_ops import (
    ensure_conversation,
    explain_conversation_error,
    open_conversation,
)
from coffer.application.channel.conversation_spec import narrow_to_allowed, refuse_model
from coffer.application.channel.ports import (
    AgentCatalogPort,
    ChannelBinding,
    ChannelPeer,
    ChannelThreadConversationRepoPort,
    ModelSuggestionPort,
)
from coffer.application.channel.selection_cards import agent_card, model_card
from coffer.domain.channel.commands import help_text
from coffer.domain.channel.envelopes import ChoiceButton, EphemeralTarget
from coffer.domain.errors import CofferError

#: FR-065: rendered from the one roster the platform's command menu also reads,
#: so the help text can never offer a command the menu omits.
HELP_TEXT = help_text()


class SafeSend(Protocol):
    """Owner-gated send supplied by the processor: ``(binding, chat_id, text)``
    plus optional selection-card ``buttons`` (rendered only where the transport
    ``supports_buttons``; ignored otherwise), the card ``title`` that heads
    them, and the routing pair ``chat_kind``/``thread_id`` (default to a DM
    reply when omitted)."""

    async def __call__(
        self,
        binding: ChannelBinding,
        chat_id: str,
        text: str,
        *,
        buttons: Sequence[ChoiceButton] | None = None,
        title: str = "",
        chat_kind: str = "direct",
        thread_id: str = "",
        reply_to_message_id: str = "",
        ephemeral: EphemeralTarget | None = None,
    ) -> None: ...


class ChannelCommands:
    """Owner-gated slash commands, operating on the processor's shared ports."""

    def __init__(
        self,
        *,
        threads: ChannelThreadConversationRepoPort,
        conversations: Any,
        turns: Any,
        agents: AgentCatalogPort,
        model_suggestions: ModelSuggestionPort,
    ) -> None:
        self._threads = threads
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
        *,
        chat_kind: str = "direct",
        thread_id: str = "",
    ) -> None:
        command = text.split()[0].lower()
        if command in ("/help", "/start"):
            await send(binding, peer.chat_id, HELP_TEXT, chat_kind=chat_kind, thread_id=thread_id)
        elif command == "/new":
            await self._open_and_report(
                binding,
                peer,
                send,
                "🆕 Started a fresh conversation.",
                chat_kind=chat_kind,
                thread_id=thread_id,
            )
        elif command == "/agent":
            await self._cmd_agent(
                binding, peer, text, send, chat_kind=chat_kind, thread_id=thread_id
            )
        elif command == "/model":
            await self._cmd_model(
                binding, peer, text, send, chat_kind=chat_kind, thread_id=thread_id
            )
        elif command == "/stop":
            await self.interrupt(
                binding, peer, session, send, chat_kind=chat_kind, thread_id=thread_id
            )
        elif command == "/status":
            running = session.drain_task is not None and not session.drain_task.done()
            row = await self._threads.get(binding.resource_id, peer.chat_id, thread_id)
            conv = (row.active_conversation_id if row is not None else None) or "none yet"
            agent = (row.preferred_agent if row is not None else None) or binding.default_agent
            await send(
                binding,
                peer.chat_id,
                f"Conversation: {conv}\nAgent: {agent}\n"
                f"Turn running: {'yes' if running else 'no'}\nQueued: {len(session.queue)}",
                chat_kind=chat_kind,
                thread_id=thread_id,
            )
        else:
            await send(
                binding,
                peer.chat_id,
                f"Unknown command {command}. /help",
                chat_kind=chat_kind,
                thread_id=thread_id,
            )

    async def interrupt(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        session: Any,
        send: SafeSend,
        *,
        chat_kind: str = "direct",
        thread_id: str = "",
    ) -> None:
        """Stop the turn running for this ``(chat, thread)``.

        Shared by the typed ``/stop`` and the platform's own stop control
        (FR-063) so both take exactly one path: same cancellation, same queue
        pause (FR-051), same thing said back to the user.

        The turn that is actually draining wins over the thread's bound
        conversation: after ``/new`` rebinds the thread, a turn can still be
        running on the previous conversation, and stopping the bound (idle) one
        would claim "Stopping…" while the real turn ran on.
        """
        row = await self._threads.get(binding.resource_id, peer.chat_id, thread_id)
        bound = row.active_conversation_id if row is not None else None
        target = session.running_conversation_id or bound
        if target is not None:
            self._turns.interrupt_turn(target)
            await send(
                binding, peer.chat_id, "⏹ Stopping…", chat_kind=chat_kind, thread_id=thread_id
            )
        else:
            await send(
                binding,
                peer.chat_id,
                "Nothing is running.",
                chat_kind=chat_kind,
                thread_id=thread_id,
            )

    # -- structural switches (open a fresh conversation, sticky on the peer) ------

    async def _cmd_agent(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        text: str,
        send: SafeSend,
        *,
        chat_kind: str = "direct",
        thread_id: str = "",
    ) -> None:
        parts = text.split()
        keys = self._agents.agent_keys()
        if len(parts) < 2:
            row = await self._threads.get(binding.resource_id, peer.chat_id, thread_id)
            current = (row.preferred_agent if row is not None else None) or binding.default_agent
            if binding.adapter.capabilities.supports_buttons:
                # A card the platform refuses must not end the command in
                # silence — fall through to the plain-text answer below.
                card = agent_card(current=current, choices=self._agents.agent_choices())
                if await deliver_card(
                    binding, peer, card, chat_kind=chat_kind, thread_id=thread_id
                ):
                    return
            await send(
                binding,
                peer.chat_id,
                f"Agent: {current}\nAvailable: {', '.join(keys)}",
                chat_kind=chat_kind,
                thread_id=thread_id,
            )
            return
        key = parts[1]
        if key not in keys:
            await send(
                binding,
                peer.chat_id,
                f"Unknown agent '{key}'. Available: {', '.join(keys)}",
                chat_kind=chat_kind,
                thread_id=thread_id,
            )
            return
        await self.apply_agent(binding, peer, key, send, chat_kind=chat_kind, thread_id=thread_id)

    async def apply_agent(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        key: str,
        send: SafeSend,
        *,
        chat_kind: str = "direct",
        thread_id: str = "",
    ) -> None:
        """The structural switch to ``key`` (assumes ``key`` already validated):
        stick it on THIS thread and open a fresh conversation for it (FR-032/040
        — a different thread of the same group can run a different agent). Shared
        by the text ``/agent <key>`` path and a card tap."""
        await self._threads.set_preferred_agent(binding.resource_id, peer.chat_id, thread_id, key)
        await self._open_and_report(
            binding,
            peer,
            send,
            f"🔀 Switched to agent '{key}'.",
            chat_kind=chat_kind,
            thread_id=thread_id,
        )

    # -- parametric switch (/model: same conversation, next turn) -----------------

    async def _cmd_model(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        text: str,
        send: SafeSend,
        *,
        chat_kind: str = "direct",
        thread_id: str = "",
    ) -> None:
        try:
            conversation_id = await ensure_conversation(
                self._conversations, self._threads, binding, peer, thread_id
            )
        except CofferError as e:
            await send(
                binding,
                peer.chat_id,
                explain_conversation_error(e),
                chat_kind=chat_kind,
                thread_id=thread_id,
            )
            return
        parts = text.split()
        if len(parts) < 2:
            # Show the current model. Coffer-managed CLI agents own their own
            # model namespace (the builtin model-registry agent is retired),
            # so we just report what will be passed through to the agent's CLI.
            cfg = await self._conversations.get_agent_config(conversation_id)
            current = cfg.model or "(CLI default)"
            if binding.adapter.capabilities.supports_buttons:
                row = await self._threads.get(binding.resource_id, peer.chat_id, thread_id)
                key = (row.preferred_agent if row is not None else None) or binding.default_agent
                offers = await self._model_suggestions.suggest(key)
                picks = narrow_to_allowed(offers, binding.models)
                card = model_card(current=cfg.model, picks=picks)
                # Same fallback as /agent: a refused card degrades to text.
                if await deliver_card(
                    binding, peer, card, chat_kind=chat_kind, thread_id=thread_id
                ):
                    return
            await send(
                binding,
                peer.chat_id,
                f"Model: {current}\n(passed through to the agent's CLI)",
                chat_kind=chat_kind,
                thread_id=thread_id,
            )
            return
        await self.apply_model(
            binding, peer, parts[1], send, chat_kind=chat_kind, thread_id=thread_id
        )

    async def apply_model(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        name: str,
        send: SafeSend,
        *,
        chat_kind: str = "direct",
        thread_id: str = "",
    ) -> None:
        """The parametric switch: set the next-turn model on the peer's
        conversation. Shared by the text ``/model <name>`` path and a card tap.

        Passthrough within the channel's allowed range (FR-071): a name inside
        it — or ANY name when the channel curates none — reaches the CLI
        verbatim, whose namespace we do not own, so a bad one surfaces as its
        own error next turn. One outside a curated range is refused here naming
        what is allowed, since the card never offered it."""
        refusal = refuse_model(name, binding.models)
        if refusal is not None:
            await send(binding, peer.chat_id, refusal, chat_kind=chat_kind, thread_id=thread_id)
            return
        try:
            conversation_id = await ensure_conversation(
                self._conversations, self._threads, binding, peer, thread_id
            )
        except CofferError as e:
            await send(
                binding,
                peer.chat_id,
                explain_conversation_error(e),
                chat_kind=chat_kind,
                thread_id=thread_id,
            )
            return
        cfg = await self._conversations.get_agent_config(conversation_id)
        await self._conversations.set_agent_config(conversation_id, replace(cfg, model=name))
        await send(
            binding,
            peer.chat_id,
            f"🧠 Model set to '{name}' for the next turn.",
            chat_kind=chat_kind,
            thread_id=thread_id,
        )

    # -- card tap → the same switch (owner gate enforced by the processor) ---------

    async def dispatch_callback(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        data: str,
        send: SafeSend,
        *,
        chat_kind: str = "direct",
        thread_id: str = "",
        card_message_id: str = "",
    ) -> None:
        """Route a selection-card tap (``data`` = the tapped ``ChoiceButton.value``)
        to the same switch the text command performs (the processor owner-gated it).
        ``chat_kind``/``thread_id`` route the confirmation back into a group tap's
        own group/thread, not a DM (FR-034).

        ``card_message_id`` is the card that was tapped: the message a Prev/Next
        turn rewrites, and the one rewritten after a switch lands so it shows
        the new choice — otherwise it sits in the chat still offering the option
        the user just took, which is the one thing a selection card must never
        do. The routing itself lives in ``card_delivery`` beside the rendering
        it drives."""
        await dispatch_card_tap(
            self,
            binding,
            peer,
            data,
            send,
            chat_kind=chat_kind,
            thread_id=thread_id,
            card_message_id=card_message_id,
        )

    async def _open_and_report(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        send: SafeSend,
        success: str,
        *,
        chat_kind: str = "direct",
        thread_id: str = "",
    ) -> None:
        try:
            await open_conversation(self._conversations, self._threads, binding, peer, thread_id)
        except CofferError as e:
            await send(
                binding,
                peer.chat_id,
                explain_conversation_error(e),
                chat_kind=chat_kind,
                thread_id=thread_id,
            )
            return
        await send(binding, peer.chat_id, success, chat_kind=chat_kind, thread_id=thread_id)
