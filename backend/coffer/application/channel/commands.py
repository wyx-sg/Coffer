"""Slash-command handling for channels: /help /new /agent /model /effort /stop
/status /save /thread /threads.

The router owns the structural switch (/agent → a fresh conversation, sticky on the
peer) and the parametric switch (/model → next turn, same conversation). Conversation
creation is delegated to ``conversation_ops`` so the inbound turn-driver and this router
agree on how a channel conversation is born. ``/save`` (spec channels "Save a sent
document into a collection"), ``/model``, ``/effort`` and ``/status``/``/thread``/
``/threads`` each live in a sibling module (``document_save``/``model_switch``/
``effort_switch``/``parallel_threads``) for this file's size budget — ``handle``
below still dispatches every command from one place.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from coffer.application.channel import (
    document_save,
    effort_switch,
    model_switch,
    parallel_threads,
)
from coffer.application.channel.agent_routing import (
    effective_agent,
    routable_choices,
    routable_keys,
)
from coffer.application.channel.card_delivery import deliver_card, dispatch_card_tap
from coffer.application.channel.conversation_ops import (
    explain_conversation_error,
    open_conversation,
)
from coffer.application.channel.ports import AgentCatalogPort, ChannelBinding, ModelSuggestionPort
from coffer.application.channel.save_ports import CollectionCatalogPort, IngestPort
from coffer.application.channel.selection_cards import agent_card
from coffer.application.channel.store_ports import ChannelPeer, ChannelThreadConversationRepoPort
from coffer.domain.channel.commands import help_text
from coffer.domain.channel.envelopes import ChoiceButton, EphemeralTarget
from coffer.domain.errors import CofferError

#: Rendered from the one roster the platform's command menu also reads (see "Register
#: the bot's command menu and profile from one roster"),
#: so the help text can never offer a command the menu omits.
HELP_TEXT = help_text()

#: What `/agent` says when the channel's scope leaves it no agent to offer.
#: Reachable only in the narrow window where a scope edit has landed but the
#: runtime has not yet stopped the (now dormant) channel — it must still name
#: the cause rather than answering with an empty list.
NO_AGENT_IN_SCOPE = (
    "This channel is scoped to no agent, so it can drive nothing. "
    "Widen its scope in Coffer to use it."
)


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
        collections: CollectionCatalogPort,
        ingest: IngestPort,
        knowledge_enabled: Callable[[], bool] = lambda: True,
        running_in: Callable[[str, str, str], str | None] = lambda *_: None,
    ) -> None:
        #: ``(channel, chat, thread) → the conversation rendering a turn there``,
        #: read without creating a session; `/threads` asks it per thread.
        self.running_in = running_in
        self._threads = threads
        self._conversations = conversations
        self._turns = turns
        self._agents = agents
        self._model_suggestions = model_suggestions
        self._collections = collections
        self._ingest = ingest
        #: Whether the knowledge feature is on right now; `/save` reads it.
        self._knowledge_enabled = knowledge_enabled

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
        conversation_thread_id: str,
    ) -> None:
        """Dispatch one command. ``thread_id`` is where the answer goes;
        ``conversation_thread_id`` is which conversation it is about (see "Key
        conversation identity by channel, chat and thread")."""
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
                conversation_thread_id=conversation_thread_id,
            )
        elif command == "/agent":
            await self._cmd_agent(
                binding,
                peer,
                text,
                send,
                chat_kind=chat_kind,
                thread_id=thread_id,
                conversation_thread_id=conversation_thread_id,
            )
        elif command == "/model":
            await model_switch.cmd_model(
                self,
                binding,
                peer,
                text,
                send,
                chat_kind=chat_kind,
                thread_id=thread_id,
                conversation_thread_id=conversation_thread_id,
            )
        elif command == "/effort":
            # Dispatched straight into its module (like ``/save``) rather than
            # through a method here: this file's size budget, and nothing in
            # between would do anything but forward.
            await effort_switch.cmd_effort(
                self,
                binding,
                peer,
                text,
                send,
                chat_kind=chat_kind,
                thread_id=thread_id,
                conversation_thread_id=conversation_thread_id,
            )
        elif command == "/stop":
            await self.interrupt(
                binding,
                peer,
                session,
                send,
                chat_kind=chat_kind,
                thread_id=thread_id,
                conversation_thread_id=conversation_thread_id,
            )
        elif command == "/save":
            await document_save.cmd_save(
                self, binding, peer, text, session, send, chat_kind=chat_kind, thread_id=thread_id
            )
        elif command in ("/status", "/thread", "/threads"):
            # `/status` names a parallel thread's mark, so it lives beside
            # `/thread` and `/threads` (see "Open parallel conversations in a
            # direct chat").
            await parallel_threads.dispatch(
                self,
                command,
                binding,
                peer,
                text,
                session,
                send,
                chat_kind=chat_kind,
                thread_id=thread_id,
                conversation_thread_id=conversation_thread_id,
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
        conversation_thread_id: str,
    ) -> None:
        """Stop the turn running for this ``(chat, thread)``.

        Shared by the typed ``/stop`` and the platform's own stop control (see "Stop the
        turn from the platform's own stop control") so both take exactly one path: same
        cancellation, same queue pause (spec chat "Pause the pending queue on
        interrupt"), same thing said back to the user.

        The turn that is actually draining wins over the thread's bound
        conversation: after ``/new`` rebinds the thread, a turn can still be
        running on the previous conversation, and stopping the bound (idle) one
        would claim "Stopping…" while the real turn ran on.
        """
        row = await self._threads.get(binding.resource.id, peer.chat_id, conversation_thread_id)
        bound = row.active_conversation_id if row is not None else None
        target = session.running_conversation_id or bound
        if target is not None:
            self._turns.interrupt_turn(target)
        answer = "⏹ Stopping…" if target is not None else "Nothing is running."
        await send(binding, peer.chat_id, answer, chat_kind=chat_kind, thread_id=thread_id)

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
        conversation_thread_id: str,
    ) -> None:
        parts = text.split()
        # Narrowed to the agents THIS channel may drive (ADR per-agent-resource-scope). The
        # listing, the card and the validation below all read the same
        # narrowed set, so a card can never offer a key the check rejects.
        keys = routable_keys(binding, self._agents)
        if len(parts) < 2:
            row = await self._threads.get(binding.resource.id, peer.chat_id, conversation_thread_id)
            current = effective_agent(binding, row.preferred_agent if row is not None else None)
            if keys and binding.adapter.capabilities.supports_buttons:
                # A card the platform refuses must not end the command in
                # silence — fall through to the plain-text answer below.
                card = agent_card(current=current, choices=routable_choices(binding, self._agents))
                if await deliver_card(
                    binding, peer, card, chat_kind=chat_kind, thread_id=thread_id
                ):
                    return
            await send(
                binding,
                peer.chat_id,
                f"Agent: {current}\nAvailable: {', '.join(keys)}" if keys else NO_AGENT_IN_SCOPE,
                chat_kind=chat_kind,
                thread_id=thread_id,
            )
            return
        agent = parts[1]
        if agent not in keys:
            await send(
                binding,
                peer.chat_id,
                f"Unknown agent '{agent}'. Available: {', '.join(keys)}"
                if keys
                else NO_AGENT_IN_SCOPE,
                chat_kind=chat_kind,
                thread_id=thread_id,
            )
            return
        await self.apply_agent(
            binding,
            peer,
            agent,
            send,
            chat_kind=chat_kind,
            thread_id=thread_id,
            conversation_thread_id=conversation_thread_id,
        )

    async def apply_agent(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        agent: str,
        send: SafeSend,
        *,
        chat_kind: str = "direct",
        thread_id: str = "",
        conversation_thread_id: str,
    ) -> None:
        """The structural switch to ``agent`` (assumes ``agent`` already validated): stick
        it on THIS thread and open a fresh conversation for it (see "Key conversation
        identity by channel, chat and thread" and "Drive every managed agent from one
        bot" — a different thread of the same group can run a different agent). Shared
        by the text ``/agent <key>`` path and a card tap."""
        await self._threads.set_preferred_agent(
            binding.resource.id, peer.chat_id, conversation_thread_id, agent
        )
        await self._open_and_report(
            binding,
            peer,
            send,
            f"🔀 Switched to agent '{agent}'.",
            chat_kind=chat_kind,
            thread_id=thread_id,
            conversation_thread_id=conversation_thread_id,
        )

    # `/model` (the parametric switch: same conversation, next turn) lives in
    # ``model_switch`` for this file's size budget, exactly like /save; a card tap
    # calls it directly.

    async def dispatch_callback(
        self,
        binding: ChannelBinding,
        peer: ChannelPeer,
        data: str,
        send: SafeSend,
        *,
        session: Any,
        chat_kind: str = "direct",
        thread_id: str = "",
        conversation_thread_id: str,
        card_message_id: str = "",
    ) -> None:
        """Route a selection-card tap (``data`` = the tapped ``ChoiceButton.value``)
        to the same switch the text command performs (the processor owner-gated it).
        ``chat_kind``/``thread_id`` route the confirmation back into a group tap's
        own group/thread, not a DM (see "Route group selection-card taps back to the group").

        ``card_message_id`` is the card that was tapped: the message a Prev/Next turn
        rewrites, and the one rewritten after a switch lands so it shows the new choice
        — otherwise it sits in the chat still offering the option the user just took,
        which is the one thing a selection card must never do. The routing itself lives
        in ``card_delivery`` beside the rendering it drives. ``session`` is read only by
        a ``collection:`` tap (spec channels "Save a sent document into a collection"),
        for the pending document held there."""
        await dispatch_card_tap(
            self,
            binding,
            peer,
            data,
            send,
            chat_kind=chat_kind,
            thread_id=thread_id,
            conversation_thread_id=conversation_thread_id,
            card_message_id=card_message_id,
            session=session,
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
        conversation_thread_id: str,
    ) -> None:
        try:
            await open_conversation(
                self._conversations, self._threads, binding, peer, conversation_thread_id
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
        await send(binding, peer.chat_id, success, chat_kind=chat_kind, thread_id=thread_id)
