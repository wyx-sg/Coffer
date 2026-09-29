"""The channel's reserved commands: /new /stop /model /dir /status /resume
/thread /kb /help (spec channels "Answer the conversation commands from any
paired chat", and the requirements each command cites in its own module).

The roster itself — which words are reserved, their help text and menus — is
domain data (``domain.channel.commands``); this is where each word is
dispatched. Every command is a function of a :class:`CommandContext` and the
typed text, living in its own module (``new_conversation``, ``model_switch``,
``dir_switch``, ``resume_switch``, ``status_card``, ``parallel_threads``,
``document_save``); a card's ``cmd:<name>`` button runs through :meth:`run`
exactly like the typed word. `/stop` lives here because the platform's own stop
control shares its one path.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.channel import (
    dir_switch,
    document_save,
    model_switch,
    new_conversation,
    parallel_threads,
    resume_switch,
    status_card,
)
from coffer.application.channel.card_delivery import dispatch_card_tap
from coffer.application.channel.command_context import CommandContext, SafeSend
from coffer.application.channel.ports import AgentCatalogPort, ChannelBinding, ModelSuggestionPort
from coffer.application.channel.save_ports import CollectionCatalogPort, IngestPort
from coffer.application.channel.store_ports import ChannelPeer, ChannelThreadConversationRepoPort
from coffer.domain.channel.commands import command_name
from coffer.domain.chat.errors import ConversationNotFound

__all__ = ["ChannelCommands", "SafeSend"]

_Handler = Callable[[CommandContext, str], Awaitable[None]]

#: Every reserved word's handler, keyed by roster name. ``stop`` is the
#: processor-facing :meth:`ChannelCommands.interrupt` and is dispatched apart.
_HANDLERS: dict[str, _Handler] = {
    "new": new_conversation.cmd_new,
    "model": model_switch.cmd_model,
    "dir": dir_switch.cmd_dir,
    "status": status_card.cmd_status,
    "resume": resume_switch.cmd_resume,
    "thread": parallel_threads.cmd_thread,
    "kb": document_save.cmd_kb,
    "help": status_card.cmd_help,
}


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
        running_in_chat: Callable[[str, str], list[str]] = lambda *_: [],
    ) -> None:
        #: ``(channel, chat, thread) → the conversation rendering a turn there``,
        #: read without creating a session; `/status` asks it per thread.
        self.running_in = running_in
        #: ``(channel, chat) → every conversation rendering a turn in that chat``
        #: — a SeaTalk group's main chat stops and reports them all.
        self.running_in_chat = running_in_chat
        self._threads = threads
        self._conversations = conversations
        self._turns = turns
        self._agents = agents
        self._model_suggestions = model_suggestions
        self._collections = collections
        self._ingest = ingest
        #: Whether the knowledge feature is on right now; `/kb` and `/help` read it.
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
        group_main: bool = False,
    ) -> None:
        """Dispatch one reserved command. ``thread_id`` is where the answer goes;
        ``conversation_thread_id`` is which conversation it is about (see "Key
        conversation identity by channel, chat and thread") — ``""``, the
        group's defaults, when ``group_main`` (spec channels "Set a group's
        defaults from its main chat")."""
        ctx = CommandContext(
            commands=self,
            binding=binding,
            peer=peer,
            send=send,
            session=session,
            chat_kind=chat_kind,
            thread_id=thread_id,
            conversation_thread_id=conversation_thread_id,
            group_main=group_main,
        )
        await self.run(ctx, text)

    async def run(self, ctx: CommandContext, text: str) -> None:
        """Run the command ``text`` names in ``ctx`` — typed, or tapped as a
        ``cmd:`` button (spec channels "Offer choices and actions as
        owner-gated cards": a command button runs the command it names)."""
        name = command_name(text)
        if name == "stop":
            await self._stop(ctx)
        elif name is not None:
            await _HANDLERS[name](ctx, text)

    async def send_help(self, binding: ChannelBinding, peer: ChannelPeer, send: SafeSend) -> None:
        """The help card, sent once after a chat pairs (spec channels "Offer the
        commands as a help card")."""
        ctx = CommandContext(
            commands=self,
            binding=binding,
            peer=peer,
            send=send,
            session=None,
            chat_kind="direct",
            thread_id="",
            conversation_thread_id="",
        )
        await status_card.cmd_help(ctx, "/help")

    async def _stop(self, ctx: CommandContext) -> None:
        if ctx.group_main:
            await self._stop_group(ctx)
            return
        await self.interrupt(
            ctx.binding,
            ctx.peer,
            ctx.session,
            ctx.send,
            chat_kind=ctx.chat_kind,
            thread_id=ctx.thread_id,
            conversation_thread_id=ctx.conversation_thread_id,
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
        running = session.running_conversation_id if session is not None else None
        target = running or bound
        if target is not None:
            self._turns.interrupt_turn(target)
        answer = "⏹ Stopping…" if target is not None else "Nothing is running."
        await send(binding, peer.chat_id, answer, chat_kind=chat_kind, thread_id=thread_id)

    async def running_titles(self, binding: ChannelBinding, peer: ChannelPeer) -> list[str]:
        """The titles of the conversations running a turn anywhere in this chat."""
        return [
            await self._title(conversation_id)
            for conversation_id in self.running_in_chat(binding.resource.name, peer.chat_id)
        ]

    async def _title(self, conversation_id: str) -> str:
        try:
            conversation = await self._conversations.get_conversation(conversation_id)
        except ConversationNotFound:
            return "Untitled conversation"
        return str(conversation.title or "").strip() or "Untitled conversation"

    async def _stop_group(self, ctx: CommandContext) -> None:
        """`/stop` in a SeaTalk group's main chat: every turn in the group."""
        running = self.running_in_chat(ctx.binding.resource.name, ctx.chat_id)
        if not running:
            await ctx.say("Nothing is running in this group.")
            return
        titles = [await self._title(conversation_id) for conversation_id in running]
        for conversation_id in running:
            self._turns.interrupt_turn(conversation_id)
        noun = "turn" if len(running) == 1 else "turns"
        await ctx.say(f"⏹ Stopping {len(running)} {noun}:\n" + "\n".join(f"• {t}" for t in titles))

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
        """Route a card tap (``data`` = the tapped ``ChoiceButton.value``) to the
        same function the typed command calls (the processor owner-gated it).
        ``chat_kind``/``thread_id`` route the confirmation back into a group tap's
        own group/thread, not a DM (see "Route group selection-card taps back to
        the group"). ``card_message_id`` is the card that was tapped: the message
        a page turn, a refresh or the model card's effort step rewrites."""
        ctx = CommandContext(
            commands=self,
            binding=binding,
            peer=peer,
            send=send,
            session=session,
            chat_kind=chat_kind,
            thread_id=thread_id,
            conversation_thread_id=conversation_thread_id,
            card_message_id=card_message_id,
        )
        await dispatch_card_tap(ctx, data)
