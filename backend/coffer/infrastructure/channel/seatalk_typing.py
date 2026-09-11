"""The SeaTalk "Typing…" cue, for both chat surfaces.

A helper module beside ``seatalk.py``, like ``seatalk_cards.py`` and
``seatalk_history.py``: the adapter keeps the port method, the routing and the
wire call live here so that file stays inside the size cap.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

#: ``post(path, body, retries=...)`` — the adapter's authenticated POST.
Post = Callable[..., Awaitable[Any]]


def typing_request(chat_id: str, thread_id: str, chat_kind: str) -> tuple[str, dict[str, Any]]:
    """The endpoint and body for the cue on either surface.

    Two endpoints, not one: a DM is addressed by ``employee_code`` and a group
    by ``group_id``. A group also takes the thread the turn answers in, so the
    cue appears where the reply will; omitted, it shows in the main channel —
    and an EMPTY ``thread_id`` is not the same as none, so it is left out
    entirely rather than sent blank.
    """
    if chat_kind != "group":
        return "/messaging/v2/single_chat_typing", {"employee_code": chat_id}
    body: dict[str, Any] = {"group_id": chat_id}
    if thread_id:
        body["thread_id"] = thread_id
    return "/messaging/v2/group_chat_typing", body


async def send_typing(post: Post, chat_id: str, thread_id: str, chat_kind: str) -> None:
    """Show the cue for its ~4 seconds, or fail silently.

    Best-effort and un-retried on purpose: the indicator expires in seconds, so
    a retried one arrives after it would have mattered. A group over 200 members
    has no indicator at all (the platform answers 7003), which is a fact about
    the group rather than something to report.
    """
    path, body = typing_request(chat_id, thread_id, chat_kind)
    with contextlib.suppress(Exception):
        await post(path, body, retries=0)
