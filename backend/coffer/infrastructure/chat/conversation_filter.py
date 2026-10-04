"""The conversation listing's filter, as a statement narrowing."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func

from coffer.application.chat.conversation_repo import EVERY, Narrowing
from coffer.infrastructure.chat.persistence_models import ConversationModel


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listing_filter(stmt: Any, *, contains: str | None, narrow: Narrowing = EVERY) -> Any:
    """Narrow a ``ConversationModel`` statement to the listing: only channel
    conversations (``channel_uid`` set; Coffer keeps no other), then ``narrow``'s
    channel uids and agent keys, then, with ``contains``, the conversations whose
    title or working directory (``agent_config``'s ``cwd``) holds it,
    case-insensitively. The conversation's text is not searched: Coffer does not
    keep it."""
    stmt = stmt.where(ConversationModel.channel_uid.isnot(None))
    if narrow.sources:
        stmt = stmt.where(ConversationModel.channel_uid.in_(narrow.sources))
    if narrow.agents:
        stmt = stmt.where(ConversationModel.agent_key.in_(narrow.agents))
    if contains:
        pattern = f"%{_like_escape(contains)}%"
        cwd = func.json_extract(ConversationModel.agent_config, "$.cwd")
        stmt = stmt.where(
            ConversationModel.title.ilike(pattern, escape="\\")
            | func.coalesce(cwd, "").ilike(pattern, escape="\\")
        )
    return stmt
