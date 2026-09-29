"""The one cursor every growing list pages by (spec resource-framework "Page
growing lists by an opaque cursor").

A list that can grow while it is read — the audit log, the MCP invocation log,
an agent's transcript sessions, the chat conversation listings — cannot page by
``offset``: a row written at the head between two reads shifts every later page,
so rows repeat or are skipped. It pages by **keyset** instead: the answer names
the last row it held, and the next read asks for the rows strictly after that
row in the list's order. The order always ends in a unique id, so "after" is
never ambiguous.

The cursor is opaque to the client — urlsafe base64 (no padding) of compact
JSON — and holds three things:

* ``l`` — the list it was issued for (a tag such as ``"audit"``);
* ``f`` — a fingerprint of the filters it was issued with;
* ``p`` — the keyset position: the last row's sort value(s) and its unique id.

Binding the cursor to its list and filters is what makes a stale or foreign one
an error rather than a silently wrong page: a position is only "after" in the
order it was taken from. Anything that does not decode, or names another list
or other filters, is :class:`CursorInvalid` (``400 CURSOR_INVALID``).

Kind-agnostic and pure: surfaces and application both use it, and the
repositories only ever see a decoded position.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from coffer.domain.error_base import CofferError

_JSON_SEPARATORS = (",", ":")


class CursorInvalid(CofferError):  # noqa: N818
    """A ``cursor`` that does not decode, or was issued for another list or
    other filters. Maps to 400: the request is wrong, and resending it
    unchanged never succeeds."""

    code = "CURSOR_INVALID"

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid cursor: {detail}")
        self.detail = detail


@dataclass(frozen=True)
class Page[T]:
    """One page of a growing list: its rows and the cursor for the next page.

    ``next_cursor`` is ``None`` exactly when no row follows ``items``.
    """

    items: list[T]
    next_cursor: str | None


def _fingerprint(filters: Mapping[str, Any]) -> str:
    canonical = json.dumps(dict(filters), sort_keys=True, separators=_JSON_SEPARATORS, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def encode_cursor(list_tag: str, filters: Mapping[str, Any], position: Sequence[Any]) -> str:
    """The opaque cursor naming ``position`` in the list ``list_tag`` filtered by
    ``filters``. ``position`` holds JSON scalars (datetimes are passed as ISO
    strings by :func:`position_of`)."""
    payload = {"l": list_tag, "f": _fingerprint(filters), "p": list(position)}
    raw = json.dumps(payload, separators=_JSON_SEPARATORS).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor(
    cursor: str | None, *, list_tag: str, filters: Mapping[str, Any]
) -> list[Any] | None:
    """The keyset position ``cursor`` names, or ``None`` for no cursor (the
    first page). Raises :class:`CursorInvalid` when it does not decode or was
    issued for another list or other filters."""
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, binascii.Error, UnicodeError) as exc:
        raise CursorInvalid("it is not a cursor this daemon issued") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("p"), list):
        raise CursorInvalid("it is not a cursor this daemon issued")
    if payload.get("l") != list_tag:
        raise CursorInvalid(f"it was issued for another list, not {list_tag!r}")
    if payload.get("f") != _fingerprint(filters):
        raise CursorInvalid("it was issued with other filters; restart from the first page")
    position: list[Any] = payload["p"]
    return position


def position_of(*values: Any) -> list[Any]:
    """A keyset position as JSON scalars — a datetime becomes its ISO form."""
    return [v.isoformat() if isinstance(v, datetime) else v for v in values]


def time_and_id(position: list[Any] | None, id_type: type) -> tuple[datetime, Any] | None:
    """Read a ``[iso timestamp, id]`` position back, or refuse it as invalid."""
    if position is None:
        return None
    if len(position) != 2 or not isinstance(position[0], str):
        raise CursorInvalid("its position does not fit this list")
    ts_raw, row_id = position
    if not isinstance(row_id, id_type) or isinstance(row_id, bool):
        raise CursorInvalid("its position does not fit this list")
    try:
        return datetime.fromisoformat(ts_raw), row_id
    except ValueError as exc:
        raise CursorInvalid("its position does not fit this list") from exc


def paginate[T](
    rows: Sequence[T],
    limit: int,
    *,
    list_tag: str,
    filters: Mapping[str, Any],
    key: Callable[[T], Sequence[Any]],
) -> Page[T]:
    """Cut ``rows`` — fetched with ``limit + 1`` — to a page.

    The extra row is how "does anything follow?" is answered without a count:
    when it is there, the page is the first ``limit`` rows and the cursor names
    the last of them; when it is not, this is the last page.
    """
    items = list(rows[:limit])
    if len(rows) <= limit or not items:
        return Page(items=items, next_cursor=None)
    return Page(items=items, next_cursor=encode_cursor(list_tag, filters, key(items[-1])))


__all__ = [
    "CursorInvalid",
    "Page",
    "decode_cursor",
    "encode_cursor",
    "paginate",
    "position_of",
    "time_and_id",
]
