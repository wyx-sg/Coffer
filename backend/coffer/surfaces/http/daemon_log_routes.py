"""``GET /api/v1/daemon/logs`` — one page of the daemon log, newest first.

Mounted under the daemon router (``daemon_routes``), which owns the prefix.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from coffer.application.daemon_log_handoff import daemon_error_handoff, is_environment_error
from coffer.application.log_page import read_log_page
from coffer.application.log_reader import TAIL_BYTES, at_least, matches_level
from coffer.domain.pagination import CursorInvalid, decode_cursor, encode_cursor
from coffer.infrastructure.logging.files import log_dir
from coffer.infrastructure.platform.host import machine_label
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.handoff_schemas import handoff_out
from coffer.surfaces.http.schemas import DaemonLogListOut, DaemonLogRecordOut

router = APIRouter()


def _handoff_for(record: dict[str, Any]) -> str | None:
    """The agent prompt for an error about the environment; None for any other record."""
    level = _lift(record, "level")
    message = _lift(record, "event")
    folded = record.get("continuation")
    continuation = [str(line) for line in folded] if isinstance(folded, list) else []
    if not is_environment_error(level, message, continuation):
        return None
    return daemon_error_handoff(
        logger=_lift(record, "logger"),
        message=message,
        continuation=continuation,
        machine=machine_label(),
    )


def _lift(record: dict[str, Any], key: str) -> str | None:
    """A parsed field as a string, or None when the line did not carry it."""
    return str(record[key]) if key in record else None


@router.get(
    "/logs",
    response_model=DaemonLogListOut,
    # The router itself is unauthenticated so /status can serve as a readiness
    # probe; log contents are not probe material, so this route carries its own
    # token dependency.
    dependencies=[Depends(require_token)],
)
async def list_daemon_logs(
    since: datetime | None = Query(default=None),  # noqa: B008
    errors_only: bool = Query(default=False),
    #: Severity floor: everything at or above it survives. "Errors only" was
    #: the only choice this surface offered, which made a warning — the level
    #: most worth noticing before something breaks — visible only by reading
    #: the whole file. ``errors_only`` stays for callers that already send it.
    level: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = Query(
        default=None,
        description=(
            "The previous page's next_cursor. Bound to the filters it was "
            "issued with; any other value is 400 CURSOR_INVALID."
        ),
    ),
    q: str | None = Query(
        default=None,
        description="Only the records whose message, logger, level or folded lines hold this text.",
    ),
    with_total: bool = Query(
        default=False,
        description="Also count the matching records in the file's recent tail (a bounded read).",
    ),
    trace_id: str | None = Query(
        default=None,
        description="Only the lines written under this correlation id (a request's or a turn's).",
    ),
) -> DaemonLogListOut:
    """One page of ``daemon.log``, newest-first — the same record ``coffer log daemon``
    reads, for the human looking at the Activity page.

    The file interleaves several writers' formats (see ``log_reader``); they
    are normalised there onto the same fields, so every row here carries the
    time, level and logger its line actually stated. A page reads a small
    window of bytes from the end of the file (or from the cursor's offset) and
    parses only that (see ``log_page``); the work follows the page, not the
    file."""
    # The lexical prefilter below only holds while both sides are UTC: the log
    # writes `…Z`, so a `since` carrying `+08:00` would compare as a later
    # string than the very instant it names and cut the window at the top.
    # Normalise here, once, rather than per line. A naive `since` is read as
    # UTC, which is the only clock the log keeps.
    if since is not None:
        since = since.replace(tzinfo=UTC) if since.tzinfo is None else since.astimezone(UTC)
    since_iso = since.isoformat() if since is not None else None
    log_file = log_dir() / "daemon.log"
    needle = q.strip().lower() if q else ""

    def accept(record: dict[str, Any]) -> bool:
        if not matches_level(record, errors_only) or not at_least(record, level):
            return False
        if trace_id is not None and record.get("trace_id") != trace_id:
            return False
        return not needle or needle in _haystack(record)

    filters = {
        "since": since_iso,
        "errors_only": errors_only,
        "level": level,
        "trace_id": trace_id,
        "q": needle,
    }
    position = decode_cursor(cursor, list_tag="daemon_log", filters=filters)
    before = _offset_of(position)

    # File reads and JSON parsing are blocking work: off the event loop, so a
    # busy page of the log never stalls the requests beside it.
    page = await asyncio.to_thread(
        read_log_page, log_file, before=before, limit=limit, accept=accept, since_iso=since_iso
    )
    total: int | None = None
    floor = False
    if with_total:
        window = await asyncio.to_thread(
            read_log_page,
            log_file,
            before=None,
            limit=_COUNT_LIMIT,
            accept=accept,
            since_iso=since_iso,
            max_scan=TAIL_BYTES,
        )
        total = len(window.records)
        floor = window.next_before is not None
    return DaemonLogListOut(
        records=[
            DaemonLogRecordOut(
                timestamp=_lift(record, "timestamp"),
                level=_lift(record, "level"),
                event=_lift(record, "event"),
                offset=offset,
                record=record,
                handoff=handoff_out(_handoff_for(record)),
            )
            for record, offset in zip(page.records, page.offsets, strict=True)
        ],
        next_cursor=(
            encode_cursor("daemon_log", filters, [page.next_before])
            if page.next_before is not None
            else None
        ),
        total=total,
        total_is_floor=floor,
        path=str(log_file),
    )


#: The most records a count reads; far above what 512 KB of log can hold.
_COUNT_LIMIT = 1_000_000


def _offset_of(position: list[Any] | None) -> int | None:
    """The byte offset a decoded cursor names, or refuse it."""
    if position is None:
        return None
    if len(position) != 1 or not isinstance(position[0], int) or isinstance(position[0], bool):
        raise CursorInvalid("its position does not fit this list")
    return position[0]


def _haystack(record: dict[str, Any]) -> str:
    """The lowercased text a free-text search matches: what the row says."""
    parts = [
        str(record.get("event", "")),
        str(record.get("raw", "")),
        str(record.get("logger", "")),
        str(record.get("level", "")),
        *(str(x) for x in record.get("continuation", [])),
    ]
    return " ".join(parts).lower()
