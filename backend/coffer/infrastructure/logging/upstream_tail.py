"""The newest lines of one upstream MCP server's log file, for its page.

The file (``logs/upstream/<name>.log``, rolled aside to ``.log.1``) holds what
the server printed on stderr and the lines Coffer wrote about starting and
stopping it (``<ISO timestamp> coffer <text>``, see ``files.write_coffer_line``).
Only the tail is read, backwards from the end in blocks and capped per file, so
a server that has logged for weeks costs a page read nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from coffer.infrastructure.logging.files import COFFER_LINE_SOURCE, upstream_log_path

_BLOCK = 64 * 1024
_MAX_BYTES_PER_FILE = 1024 * 1024
_COFFER_LINE = re.compile(
    r"^(?P<at>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?) "
    + re.escape(COFFER_LINE_SOURCE)
    + r" (?P<text>.*)$"
)


@dataclass(frozen=True)
class LogLine:
    text: str
    source: str  # "coffer" | "stderr"
    at: datetime | None


@dataclass(frozen=True)
class LogTail:
    path: Path | None
    lines: list[LogLine]  # newest first
    truncated: bool


def _tail(path: Path, want: int) -> tuple[list[str], bool]:
    """Up to ``want`` last lines of ``path`` (oldest first) and whether more exist."""
    try:
        size = path.stat().st_size
    except OSError:
        return [], False
    budget = min(size, _MAX_BYTES_PER_FILE)
    data = b""
    with path.open("rb") as fh:
        pos = size
        while pos > size - budget and data.count(b"\n") <= want:
            step = min(_BLOCK, pos - (size - budget))
            pos -= step
            fh.seek(pos)
            data = fh.read(step) + data
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    more = pos > 0
    if more and lines:
        lines = lines[1:]  # the first line was cut mid-way
    if len(lines) > want:
        return lines[-want:], True
    return lines, more


def _parse(raw: str) -> LogLine:
    m = _COFFER_LINE.match(raw)
    if m is None:
        return LogLine(text=raw, source="stderr", at=None)
    try:
        at = datetime.fromisoformat(m.group("at").replace("Z", "+00:00"))
    except ValueError:
        at = None
    return LogLine(text=m.group("text"), source=COFFER_LINE_SOURCE, at=at)


def read_upstream_tail(server_name: str, limit: int) -> LogTail:
    """The newest ``limit`` lines of ``server_name``'s log, from ``.log`` then ``.log.1``."""
    current = upstream_log_path(server_name)
    backup = current.with_suffix(".log.1")
    if not current.exists() and not backup.exists():
        return LogTail(path=None, lines=[], truncated=False)
    newest, more = _tail(current, limit) if current.exists() else ([], False)
    lines = newest
    if len(lines) < limit and backup.exists():
        older, more = _tail(backup, limit - len(lines))
        lines = older + lines
    parsed = [_parse(line) for line in reversed(lines) if line.strip()]
    return LogTail(path=current if current.exists() else backup, lines=parsed, truncated=more)


__all__ = ["LogLine", "LogTail", "read_upstream_tail"]
