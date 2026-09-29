"""A fake IM transport: the one ``ChannelAdapter`` every channel test drives.

``FakeChannelAdapter`` implements ``coffer.application.channel.ports.ChannelAdapter``
structurally and records every outbound call, so a test asserts on what the
shared channel core *sent* (texts, cards, edits, typing, reactions, media)
without a network. Inbound traffic is simulated by calling the callbacks the
core handed to :meth:`FakeChannelAdapter.start` (``adapter.callbacks``) —
``tap`` does it for a card button. Every capability flag is a constructor
argument, so one fake stands in for a Telegram-shaped transport (edits, live
text) or a SeaTalk-shaped one (streams, mentions, groups, threads).

It lives here rather than in ``integration/channel/conftest.py`` so tiers other
than the channel core's (the daemon, the HTTP routes) can wire a channel without
reaching into another directory's conftest; that conftest re-exports it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from coffer.application.channel.ports import AdapterCallbacks
from coffer.domain.channel.envelopes import (
    ChannelCapabilities,
    ChoiceButton,
    InboundAttachment,
    InboundCallback,
    ReactionSet,
    SentMessage,
)
from coffer.domain.channel.rich_content import ForwardedItem

#: The progress marks a reacting fake declares unless a test names others —
#: Telegram's, so a reacting fake reads like the transport it stands in for.
TELEGRAM_LIKE_REACTIONS = ReactionSet(
    received="👀", working="👨‍💻", done="👌", failed="😢", stopped="🤷"
)


class FakeChannelAdapter:
    """Recording ``ChannelAdapter`` — the only fake the channel core needs."""

    def __init__(
        self,
        *,
        supports_edit: bool = True,
        supports_live_text: bool | None = None,
        live_text_persists: bool = False,
        supports_typing: bool = True,
        max_message_chars: int = 4096,
        supports_buttons: bool = False,
        supports_card_update: bool = False,
        supports_media: bool = True,
        supports_groups: bool = False,
        supports_history_fetch: bool = False,
        supports_reactions: bool = False,
        set_reaction_fails: bool = False,
        mention_template: str = "",
        mention_email_template: str = "",
        direct_threads_are_replies: bool = False,
        reactions: ReactionSet | None = None,
        **capabilities: Any,
    ) -> None:
        self._caps = ChannelCapabilities(
            supports_edit=supports_edit,
            # A transport that can edit has a live surface by definition; one
            # that cannot may still stream (SeaTalk) — a test says so explicitly.
            supports_live_text=supports_edit if supports_live_text is None else supports_live_text,
            live_text_persists=live_text_persists,
            supports_typing=supports_typing,
            max_message_chars=max_message_chars,
            supports_buttons=supports_buttons,
            supports_card_update=supports_card_update,
            supports_media=supports_media,
            supports_groups=supports_groups,
            supports_history_fetch=supports_history_fetch,
            supports_reactions=supports_reactions,
            # How this transport spells an @mention, if it can at all ("Mention
            # the asker in a group answer").
            # Shaped like SeaTalk's tag in the tests that set it; "" is the
            # Telegram-shaped default, where a reply carries no mention.
            mention_template=mention_template,
            # …and its second, address-keyed spelling where it has one (SeaTalk),
            # used only when the primary id is missing.
            mention_email_template=mention_email_template,
            # Typing is two endpoints, not one (SeaTalk: single_chat_typing /
            # group_chat_typing): a fake may hold the DM one alone, exactly like
            # a transport that never gained the group call.
            # SeaTalk-shaped when True: a DM reply-in-thread is a casual reply
            # (see "Key conversation identity by channel, chat and thread").
            direct_threads_are_replies=direct_threads_are_replies,
            reactions=(
                reactions
                if reactions is not None
                else (TELEGRAM_LIKE_REACTIONS if supports_reactions else ReactionSet())
            ),
            # Any further capability a test names (renders_tables, …).
            **capabilities,
        )
        # When True, ``set_reaction`` raises — proves the best-effort suppression
        # at the call sites (a failed ack must never break the turn) (see
        # "Acknowledge receipt and completion by capability").
        self._set_reaction_fails = set_reaction_fails
        self.started = False
        self.stopped = False
        self.callbacks: AdapterCallbacks | None = None
        self.sent: list[tuple[str, str]] = []  # (chat_id, text)
        # (chat_id, text, thread_id, chat_kind) for every send_text call — the
        # full routing detail, kept separate so every existing ``.sent``/
        # ``.texts()`` assertion above stays a plain 2-tuple.
        self.sent_routed: list[tuple[str, str, str, str]] = []
        # "Attach a group reply to the message it answers": the reply target of
        # each send_text, positionally aligned with
        # ``sent`` ("" when the send answered nothing in particular).
        self.sent_reply_targets: list[str] = []
        #: The EphemeralTarget of each send_text, positionally aligned with
        #: ``sent`` (None when the answer was said out loud).
        self.sent_ephemeral: list[Any] = []
        # Telegram's chat action: what each send_typing claimed to be doing.
        self.typing_actions: list[str] = []
        # (chat_id, text, buttons) for sends that carried a selection card.
        self.cards: list[tuple[str, str, list[ChoiceButton]]] = []
        # The card title each of those sends carried, positionally aligned with
        # ``cards`` so existing 3-tuple assertions stay untouched.
        self.card_titles: list[str] = []
        # (chat_id, message_id, text, buttons, title) for every update_card.
        self.card_updates: list[tuple[str, str, str, list[ChoiceButton], str]] = []
        self.edits: list[tuple[str, str, str]] = []  # (chat_id, message_id, text)
        self.deleted: list[tuple[str, str]] = []  # (chat_id, message_id)
        self.typing: list[str] = []  # chat_ids
        # (chat_id, chat_kind, thread_id) for every send_typing call — the full
        # routing detail, kept separate so existing ``.typing`` assertions stay
        # a plain list of chat ids (mirrors ``sent_routed``).
        self.typing_routed: list[tuple[str, str, str]] = []
        # (chat_id, message_id, emoji) for every set_reaction call (see
        # "Acknowledge receipt and completion by capability").
        self.reactions: list[tuple[str, str, str]] = []
        # (chat_id, path, caption, as_photo) for each uploaded file.
        self.media: list[tuple[str, str, str | None, bool]] = []
        # (chat_id, path, caption, as_photo, thread_id, chat_kind) — the full
        # routing detail for each upload, kept separate so every existing
        # ``.media`` assertion stays a plain 4-tuple (mirrors ``sent_routed``).
        self.media_routed: list[tuple[str, str, str | None, bool, str, str]] = []
        # Scriptable ``fetch_thread`` result (Task 7b) — a test sets this to a
        # list of ``ForwardedItem`` for its scenario; unset yields ``[]``.
        self.thread_items: list[ForwardedItem] = []
        # Scriptable thread-history attachments ("Download the media a thread's
        # messages carry") — the images/files the
        # thread's own messages carry, already downloaded; unset yields ``()``.
        self.thread_attachments: tuple[InboundAttachment, ...] = ()
        # (chat_id, thread_id) for every ``fetch_thread`` call the core made,
        # so a test can assert the fetch happened (or, on a non-fetching
        # transport, that it never did).
        self.fetch_thread_calls: list[tuple[str, str]] = []
        # The ``chat_kind`` each of those fetches carried, positionally aligned
        # with ``fetch_thread_calls`` — a DM thread reads a different endpoint
        # from a group one, so the kind the core passed is worth asserting.
        self.fetch_thread_kinds: list[str] = []
        # Scriptable ``fetch_quoted`` result ("Ground a turn in the message it
        # quotes") and the ids the core asked it to resolve.
        self.quoted_items: list[ForwardedItem] = []
        self.quoted_attachments: tuple[InboundAttachment, ...] = ()
        self.fetch_quoted_calls: list[str] = []
        # "Grow a reply in place on one live surface": every live-text handle the
        # core opened this session, and the
        # switch that makes the transport refuse to open one.
        self.live_handles: list[FakeLiveText] = []
        self.live_text_unavailable = False
        # When True the live surface IS the reply (SeaTalk's stream): closing it
        # finishes the message in place and leaves the caller nothing to send.
        self.live_text_finalizes = False
        # (chat_id, mark, body, thread_id) for every ``open_thread`` the core
        # asked for ("Open parallel conversations beside a direct chat"), and the
        # scripted refusal a transport with no threads available raises.
        self.opened_threads: list[tuple[str, str, str, str]] = []
        self.open_thread_fails_with: Exception | None = None
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
        title: str = "",
        thread_id: str = "",
        chat_kind: str = "direct",
        reply_to_message_id: str = "",
        ephemeral: Any = None,
    ) -> SentMessage:
        # "Keep non-answer chatter private in a group": which sends were
        # addressed to one member of the group only.
        self.sent_ephemeral.append(ephemeral)
        self.sent.append((chat_id, markdown))
        self.sent_routed.append((chat_id, markdown, thread_id, chat_kind))
        # "Attach a group reply to the message it answers": what each send
        # pointed back at, so a test can assert a group
        # reply is attached to the message it answers.
        self.sent_reply_targets.append(reply_to_message_id)
        if buttons:
            self.cards.append((chat_id, markdown, list(buttons)))
            self.card_titles.append(title)
        return SentMessage(message_id=self._new_id())

    async def open_thread(self, chat_id: str, mark: str, body: str) -> str:
        if self.open_thread_fails_with is not None:
            raise self.open_thread_fails_with
        thread_id = f"t{len(self.opened_threads) + 1}"
        self.opened_threads.append((chat_id, mark, body, thread_id))
        return thread_id

    async def update_card(
        self,
        chat_id: str,
        message_id: str,
        markdown: str,
        buttons: Sequence[ChoiceButton],
        *,
        title: str = "",
        chat_kind: str = "direct",
    ) -> None:
        self.card_updates.append((chat_id, message_id, markdown, list(buttons), title))

    async def open_live_text(
        self, chat_id: str, *, thread_id: str = "", chat_kind: str = "direct"
    ) -> FakeLiveText | None:
        if not self._caps.supports_live_text or self.live_text_unavailable:
            return None
        handle = FakeLiveText(self, chat_id, thread_id=thread_id, chat_kind=chat_kind)
        self.live_handles.append(handle)
        return handle

    async def edit_text(self, chat_id: str, message_id: str, text: str) -> None:
        self.edits.append((chat_id, message_id, text))

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        self.deleted.append((chat_id, message_id))

    async def send_typing(
        self,
        chat_id: str,
        *,
        thread_id: str = "",
        chat_kind: str = "direct",
        action: str = "typing",
    ) -> None:
        self.typing_actions.append(action)
        self.typing.append(chat_id)
        self.typing_routed.append((chat_id, chat_kind, thread_id))

    async def set_reaction(self, chat_id: str, message_id: str, emoji: str) -> None:
        self.reactions.append((chat_id, message_id, emoji))
        if self._set_reaction_fails:
            raise RuntimeError("set_reaction failed (scripted)")

    async def send_media(
        self,
        chat_id: str,
        path: str,
        *,
        caption: str | None = None,
        as_photo: bool = True,
        thread_id: str = "",
        chat_kind: str = "direct",
    ) -> SentMessage:
        self.media.append((chat_id, path, caption, as_photo))
        self.media_routed.append((chat_id, path, caption, as_photo, thread_id, chat_kind))
        return SentMessage(message_id=self._new_id())

    async def fetch_thread(
        self, chat_id: str, thread_id: str, *, limit: int = 50, chat_kind: str = "group"
    ) -> tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]:
        self.fetch_thread_calls.append((chat_id, thread_id))
        self.fetch_thread_kinds.append(chat_kind)
        return list(self.thread_items), self.thread_attachments

    async def fetch_quoted(
        self, message_id: str
    ) -> tuple[list[ForwardedItem], tuple[InboundAttachment, ...]]:
        self.fetch_quoted_calls.append(message_id)
        return list(self.quoted_items), self.quoted_attachments

    async def tap(
        self, value: str, *, channel: str, chat_id: str = "owner", sender_id: str = ""
    ) -> None:
        """Simulate a selection-card button tap arriving from the platform."""
        assert self.callbacks is not None and self.callbacks.on_callback is not None
        await self.callbacks.on_callback(
            InboundCallback(channel=channel, chat_id=chat_id, sender_id=sender_id, data=value)
        )


class FakeLiveText:
    """The fake's live surface ("Grow a reply in place on one live surface"),
    shaped like Telegram's: the first
    update sends a message, later ones edit it, and closing deletes it and hands
    the whole final text back for the ordinary send path."""

    def __init__(
        self,
        adapter: FakeChannelAdapter,
        chat_id: str,
        *,
        thread_id: str = "",
        chat_kind: str = "direct",
    ) -> None:
        self._adapter = adapter
        self._chat_id = chat_id
        self._thread_id = thread_id
        self._chat_kind = chat_kind
        self.message_id = ""
        self.closed = False
        self.final = ""
        self.snapshots: list[str] = []

    async def update(self, text: str) -> None:
        self.snapshots.append(text)
        if not self.message_id:
            sent = await self._adapter.send_text(
                self._chat_id, text, thread_id=self._thread_id, chat_kind=self._chat_kind
            )
            self.message_id = sent.message_id
            return
        if self._adapter.live_text_finalizes:
            return  # a stream re-renders its own message — no new chat traffic
        await self._adapter.edit_text(self._chat_id, self.message_id, text)

    async def close(self, text: str) -> str:
        self.closed = True
        self.final = text
        if self._adapter.live_text_finalizes:
            # A stream cannot be deleted: it finishes carrying the final text.
            return ""
        if self.message_id:
            await self._adapter.delete_message(self._chat_id, self.message_id)
        return text
