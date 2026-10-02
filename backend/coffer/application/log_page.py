"""Paging backwards through the daemon log file, a window of bytes at a time.

The log is a plain text file that only grows, so the newest records are at its
end and a reader that wants a page of them has no business reading the whole
file — or even a fixed 512 KB tail — to answer for thirty lines. This reads a
small window ending at a byte offset, parses just that window, keeps the
records a page asks for, and names the byte offset of the oldest record it
kept: that offset **is** the cursor for the next page (spec resource-framework
"Page growing lists by an opaque cursor"). A file only grows at its end, so an
offset into it stays valid however much is appended afterwards — which is the
same reason a keyset position survives new rows at the head of a table.

A window starts at an arbitrary byte, so its first line is usually cut in
half and the first records it holds may belong to a record that began before
it. Both are dropped: the window's usable records start at its first
*structured* record, and the offset of that record is where the next, older
window ends. Nothing is lost and nothing is parsed twice as part of a page.

Pure: no knowledge of HTTP, and no I/O beyond reading the path it is handed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coffer.application.log_reader import parse_log_lines_indexed

#: The first window a page reads. Thirty records of Coffer's own JSON lines are
#: well inside it, so a normal page is one read of this size.
FIRST_WINDOW = 64 * 1024
#: A window never grows past this: a single traceback larger than it is read
#: in pieces rather than pulled into memory whole.
MAX_WINDOW = 4 * 1024 * 1024
#: The most one request reads, however sparse the matches: a filter that
#: matches almost nothing gives up with a cursor instead of reading a whole
#: 20 MB file inside one request.
MAX_SCAN = 16 * 1024 * 1024


@dataclass(frozen=True)
class LogPage:
    """Matching records newest-first, and where the next older page begins."""

    records: list[dict[str, Any]] = field(default_factory=list)
    #: The byte offset each record starts at, parallel to ``records``: a stable
    #: identity for a line (the file only grows at its end).
    offsets: list[int] = field(default_factory=list)
    #: The byte offset the next page ends at, or ``None`` when no older record
    #: remains (the start of the file, or the ``since`` bound, was reached).
    next_before: int | None = None


def _read(path: Path, start: int, end: int) -> bytes:
    with path.open("rb") as fh:
        fh.seek(start)
        return fh.read(end - start)


def read_log_page(
    path: Path,
    *,
    before: int | None,
    limit: int,
    accept: Callable[[dict[str, Any]], bool],
    since_iso: str | None = None,
    max_scan: int = MAX_SCAN,
) -> LogPage:
    """One newest-first page of the records ``accept`` keeps, ending at ``before``.

    ``before`` is a byte offset (``None`` for the end of the file). A record
    older than ``since_iso`` ends the page for good, as the log is in time
    order. Never raises on a missing or unreadable file: that is an empty page.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return LogPage()
    end = size if before is None else min(before, size)
    window = FIRST_WINDOW
    scanned = 0
    out: list[dict[str, Any]] = []
    starts: list[int] = []

    while end > 0:
        if scanned >= max_scan:
            # Gave up on a sparse filter: hand back what there is, and a cursor.
            return LogPage(out, starts, end)
        start = max(0, end - window)
        try:
            blob = _read(path, start, end)
        except OSError:
            return LogPage(out, starts, None)
        scanned += end - start

        # Each line with the byte offset it starts at. A window that does not
        # begin at the file's start begins mid-line: that first piece is cut.
        parts = blob.split(b"\n")
        offsets: list[int] = []
        lines: list[str] = []
        position = start
        for index, part in enumerate(parts):
            if (index > 0 or start == 0) and part.strip():
                offsets.append(position)
                lines.append(part.decode("utf-8", errors="replace"))
            position += len(part) + 1

        indexed = parse_log_lines_indexed(lines)
        floor = 0
        if start > 0:
            # Records before the first structured one may be the tail of a
            # record that began in an older window (a traceback's frames); they
            # are read again as part of that window.
            first = next((i for i, (_, rec) in enumerate(indexed) if "raw" not in rec), None)
            if first is None:
                if window >= MAX_WINDOW:
                    end = start
                else:
                    window = min(window * 2, MAX_WINDOW)
                continue
            indexed = indexed[first:]
            floor = offsets[indexed[0][0]]

        for line_index, record in reversed(indexed):
            at = str(record.get("timestamp", ""))
            if since_iso is not None and at and at < since_iso:
                return LogPage(out, starts, None)
            if accept(record):
                out.append(record)
                starts.append(offsets[line_index])
                if len(out) >= limit:
                    oldest = offsets[line_index]
                    return LogPage(out, starts, oldest if oldest > 0 else None)
        end = floor
        window = FIRST_WINDOW

    return LogPage(out, starts, None)


__all__ = ["FIRST_WINDOW", "MAX_SCAN", "MAX_WINDOW", "LogPage", "read_log_page"]
