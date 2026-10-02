"""One page of the rounds history, by keyset (spec vault-sync: the history is
newest first and grows at the head, so it pages by the last round read rather
than by offset)."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.application.sync.round_ports import RoundHistoryPort
from coffer.application.sync.views import RoundPage
from coffer.domain.pagination import decode_cursor, paginate, position_of, time_and_id
from coffer.domain.sync.rounds import RoundRecord

_TAG = "sync_runs"


def _finished(record: RoundRecord) -> datetime:
    """When a round finished, as the history orders and pages by it."""
    parsed = datetime.fromisoformat(record.finished_at)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def page_rounds(history: RoundHistoryPort, limit: int, cursor: str | None) -> RoundPage:
    after = time_and_id(decode_cursor(cursor, list_tag=_TAG, filters={}), int)
    rows = await history.recent(limit + 1, after)
    page = paginate(
        rows, limit, list_tag=_TAG, filters={}, key=lambda r: position_of(_finished(r), r.id)
    )
    return RoundPage(tuple(page.items), await history.count(), page.next_cursor)
