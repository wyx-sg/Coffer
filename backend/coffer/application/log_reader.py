"""Reading the daemon's own log file — the shared half of two readers.

The daemon log has two callers now: ``coffer__diagnose`` (an agent, at the
moment something broke) and the web Activity page (a human, scanning the same
timeline). Both need the same three decisions — read from the tail, keep an
unparseable line rather than drop it, and treat "unparseable" as error-level —
so they live here rather than being copied into a surface.

Pure: no I/O beyond reading the path it is handed, and no knowledge of who is
asking.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: Read from the tail rather than the head: the interesting line is the last
#: one. Bounded so a 10 MB log cannot be pulled into memory.
TAIL_BYTES = 512 * 1024


def tail_lines(path: Path, *, max_bytes: int = TAIL_BYTES) -> list[str]:
    """The last lines of a file, best-effort. Never raises."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            blob = fh.read()
    except OSError:
        return []
    text = blob.decode("utf-8", errors="replace")
    if len(blob) == max_bytes and "\n" in text:
        # The window almost certainly cut the first line in half.
        text = text.split("\n", 1)[1]
    return [ln for ln in text.splitlines() if ln.strip()]


def parse_log_line(line: str) -> dict[str, Any]:
    """A structlog JSON line as a dict; a non-JSON line as raw text.

    Upstream servers now log to their own files, but a stray non-JSON line
    (a traceback, a library writing straight to stderr) must not make the
    whole tool fail — it is often the most interesting line in the file.
    """
    try:
        parsed = json.loads(line)
    except ValueError:
        return {"raw": line}
    return parsed if isinstance(parsed, dict) else {"raw": line}


def matches_level(record: dict[str, Any], errors_only: bool) -> bool:
    if not errors_only:
        return True
    level = str(record.get("level", "")).lower()
    return level in {"error", "critical", "exception"} or "raw" in record


__all__ = ["TAIL_BYTES", "matches_level", "parse_log_line", "tail_lines"]
