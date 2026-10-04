"""Row <-> domain helpers for the chat repos: content JSON codec and the
conversation-listing filter."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import or_, text

from coffer.application.chat.conversation_repo import EVERY, Narrowing
from coffer.domain.chat.message import ContentBlock, block_from_dict, block_to_dict
from coffer.infrastructure.chat.persistence_models import ConversationModel

#: How ``_encode_content`` spells a text block's type — what
#: ``MessageRepo.latest_with_text`` filters rows on.
_TEXT_BLOCK_MARK = json.dumps({"type": "text"})[1:-1]


def _encode_content(blocks: list[ContentBlock]) -> str:
    """Serialize content blocks to JSON text for DB storage."""
    return json.dumps([block_to_dict(b) for b in blocks])


def _decode_content(raw: str) -> list[ContentBlock]:
    """Deserialize JSON text from DB into a list of ContentBlock."""
    data: list[dict[str, Any]] = json.loads(raw)
    return [block_from_dict(d) for d in data]


#: A conversation has a message with a text block that holds ``:pattern``.
_MESSAGE_TEXT_MATCH = (
    "EXISTS (SELECT 1 FROM chat_messages AS m, json_each(m.content) AS blk "
    "WHERE m.conversation_id = conversations.id "
    "AND json_extract(blk.value, '$.type') = 'text' "
    "AND json_extract(blk.value, '$.text') LIKE :pattern ESCAPE '\\')"
)


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _listing_filter(
    stmt: Any,
    *,
    archived: bool,
    contains: str | None,
    narrow: Narrowing = EVERY,
) -> Any:
    """Narrow a ``ConversationModel`` statement to one listing: active or archived,
    and, with ``contains``, the conversations whose title or any text block of any
    message holds it (case-insensitive). The message text is read out of the JSON
    column, so characters the JSON escapes (CJK, quotes) still match. ``narrow``
    keeps its sources (``coffer`` is ``channel_uid IS NULL``, any other token a
    channel uid) and its agent keys."""
    stmt = stmt.where(
        ConversationModel.archived_at.isnot(None)
        if archived
        else ConversationModel.archived_at.is_(None)
    )
    if narrow.sources:
        uids = [s for s in narrow.sources if s != "coffer"]
        clauses = []
        if len(uids) != len(narrow.sources):
            clauses.append(ConversationModel.channel_uid.is_(None))
        if uids:
            clauses.append(ConversationModel.channel_uid.in_(uids))
        stmt = stmt.where(or_(*clauses))
    if narrow.agents:
        stmt = stmt.where(ConversationModel.agent_key.in_(narrow.agents))
    if contains:
        pattern = f"%{_like_escape(contains)}%"
        in_messages = text(_MESSAGE_TEXT_MATCH).bindparams(pattern=pattern)
        stmt = stmt.where(or_(ConversationModel.title.ilike(pattern, escape="\\"), in_messages))
    return stmt
