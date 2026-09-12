"""Fitting a reply into one SeaTalk stream.

Pure text helpers split out of ``live_text`` (which reached its size budget):
a stream carries a bounded amount of text, so an interim snapshot is clipped
and a finished one is cut at a paragraph the rest can follow from.
"""

from __future__ import annotations

from coffer.infrastructure.channel.render import (
    chunk_text,
    escape_seatalk_literal,
    split_leading_mention,
)
from coffer.infrastructure.channel.seatalk_parse import split_to_byte_limit

#: How much of a reply one SeaTalk stream may carry. The platform caps a stream
#: at 4096 characters; this budget is in UTF-8 BYTES (CJK is 3 bytes/char) and
#: leaves headroom for the markdown escaping the final snapshot adds. Anything
#: past it is handed back to the caller and sent as ordinary chunked messages.
_STREAM_BYTE_BUDGET = 3600


def _clip_tail_bytes(text: str, budget: int) -> str:
    """Keep the TAIL of ``text`` within ``budget`` UTF-8 bytes, behind a leading
    ellipsis — an interim snapshot shows the newest words, not the oldest."""
    if len(text.encode("utf-8")) <= budget:
        return text
    return "…" + split_to_byte_limit(text, budget)[-1]


def interim_snapshot(text: str) -> str:
    """One in-flight snapshot, ready for the wire: clipped to the stream budget
    and escaped so nothing in it is interpreted.

    FR-070 shapes the order. Every snapshot — the opening one included — carries
    the @mention at its head, because the platform decides @ notifications when
    the message is CREATED. So the mention is split off before the tail clip
    (which shortens from the front and would otherwise eat it) and re-joined
    afterwards, and the body is escaped rather than rendered: a reply cut
    mid-word can end inside an unclosed ``*`` or ``_``.

    Escaping can only grow the body, and the budget below is in BYTES against a
    platform cap counted in CHARACTERS — ~500 characters of headroom on an
    all-ASCII snapshot, far more on CJK. That is the same headroom the final
    snapshot's rendering has always relied on.
    """
    prefix, body = split_leading_mention(text)
    budget = _STREAM_BYTE_BUDGET - len(prefix.encode("utf-8"))
    return prefix + escape_seatalk_literal(_clip_tail_bytes(body, budget))


def _split_for_stream(text: str) -> tuple[str, str]:
    """``(head, remainder)``: the most a stream may carry, and the rest.

    A reply's length is unknown until it ends, so a stream that overruns the
    platform's per-stream cap finishes at the limit and the remainder is handed
    back to be sent as ordinary chunked messages — the alternative (refusing to
    stream anything that *might* grow too long) would withhold the live reply
    from every turn to serve the rare one.
    """
    if len(text.encode("utf-8")) <= _STREAM_BYTE_BUDGET:
        return text, ""
    chunks = chunk_text(text, _STREAM_BYTE_BUDGET)  # paragraph-aware first
    pieces = split_to_byte_limit(chunks[0], _STREAM_BYTE_BUDGET)  # then byte-safe
    rest = [part for part in ["".join(pieces[1:]), *chunks[1:]] if part]
    return pieces[0], "\n\n".join(rest)
