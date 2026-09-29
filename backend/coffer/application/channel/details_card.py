"""A reply's details behind a card's buttons (spec channels "Offer a reply's
details behind a summary card").

A transport that cannot collapse a ``## Details`` section itself but has cards
(SeaTalk) sends the answer's head, then a small card: the outcome as its title,
how long the details are, and two buttons — **Details** posts them as a reply in
the card's thread, **As file** uploads them as a ``.md``. A card cannot carry a
long text and a button's value is short, so the details are kept as a file under
the temporary directory, keyed by a random id the buttons carry. A tap is
owner-gated like every card tap; a missing file answers that the details are no
longer available.
"""

from __future__ import annotations

import contextlib
import logging
import pathlib
import re
import secrets
import tempfile
from typing import TYPE_CHECKING

from coffer.domain.channel.envelopes import ChoiceButton

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = ["DETAILS_KINDS", "apply_details_tap", "details_buttons", "load_details", "save_details"]

#: The callback kinds this card's buttons carry.
DETAILS_KINDS = ("details", "detailsfile")
_ID = re.compile(r"\A[0-9a-f]{16}\Z")
_GONE = "Those details are no longer available — ask again for them."


def _store() -> pathlib.Path:
    return pathlib.Path(tempfile.gettempdir()) / "coffer-channel-details"


def save_details(text: str) -> str:
    """Keep ``text`` for a later tap; return the id its buttons carry."""
    store = _store()
    store.mkdir(parents=True, exist_ok=True)
    details_id = secrets.token_hex(8)
    (store / f"{details_id}.md").write_text(text, encoding="utf-8")
    return details_id


def _path(details_id: str) -> pathlib.Path | None:
    if not _ID.match(details_id):
        return None  # never a path built from anything but our own ids
    path = _store() / f"{details_id}.md"
    return path if path.is_file() else None


def load_details(details_id: str) -> str | None:
    path = _path(details_id)
    return path.read_text(encoding="utf-8") if path is not None else None


def details_buttons(details_id: str) -> list[ChoiceButton]:
    return [
        ChoiceButton(label="Details", value=f"details:{details_id}"),
        ChoiceButton(label="As file", value=f"detailsfile:{details_id}"),
    ]


async def apply_details_tap(ctx: CommandContext, kind: str, details_id: str) -> None:
    """Post the details into the card's thread, or upload them as a file."""
    path = _path(details_id)
    if path is None:
        await ctx.say(_GONE)
        return
    caps = ctx.binding.adapter.capabilities
    # A reply "in the card's thread": the thread the card sits in, or — where
    # any message roots a thread (SeaTalk) — the one the card itself roots.
    thread_id = ctx.thread_id or (ctx.card_message_id if caps.direct_threads_are_replies else "")
    here = ctx.but(thread_id=thread_id)
    if kind == "detailsfile" and caps.supports_media:
        try:
            await ctx.binding.adapter.send_media(
                ctx.chat_id,
                str(path),
                as_photo=False,
                thread_id=thread_id,
                chat_kind=ctx.chat_kind,
            )
        except Exception:
            logging.getLogger(__name__).warning("channel.details.upload_failed", exc_info=True)
            await here.say(path.read_text(encoding="utf-8"))
        return
    await here.say(path.read_text(encoding="utf-8"))
    if ctx.card_message_id and caps.supports_card_update:
        with contextlib.suppress(Exception):
            await ctx.binding.adapter.update_card(
                ctx.chat_id,
                ctx.card_message_id,
                "Details posted in the thread.",
                details_buttons(details_id)[1:],
                chat_kind=ctx.chat_kind,
            )
