"""Log-file plumbing: where upstream noise goes, and what gets cleaned up.

Two measured problems, one module.

**Upstream noise evicted Coffer's own record.** The MCP SDK writes each stdio
upstream's stderr to the daemon's own stderr, which lands in ``daemon.log``.
Upstreams are chatty and Coffer is not, so a live log held 4,277 lines of which
62 were Coffer's — and rotation (10 MB with 3 backups) had carried the rest away inside two
months. Giving each upstream its own file keeps ``daemon.log`` about Coffer.

**Nothing was ever deleted.** The shim writes one file per process start and
2,137 of them had accumulated (40 MB) since June, with no rotation and no
prune. :func:`prune_log_dir` is the retention worker's counterpart for files:
the audit and invocation tables already age out on a cadence, and log files now
ride the same one.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TextIO

from coffer.infrastructure.vault.home import logs_dir

_logger = logging.getLogger(__name__)

#: One upstream's stderr before it is rolled aside. Small on purpose: this is a
#: debugging tail, not an archive, and there is one file per registered server.
_UPSTREAM_MAX_BYTES = 2 * 1024 * 1024

#: How long a per-process shim log or a rolled-aside upstream log is kept.
#: Long enough to investigate yesterday's failure, short enough that an
#: untended install does not accumulate a year of them.
DEFAULT_MAX_AGE_DAYS = 7

#: Filenames the pruner owns. `daemon.log` and its rotations are deliberately
#: absent — RotatingFileHandler already bounds those, and deleting a file it
#: holds an open handle to would break logging until the next restart.
_PRUNABLE_GLOBS = ("shim-*.log", "upstream/*.log.1")

#: The source word on a line Coffer itself wrote into an upstream's log file.
COFFER_LINE_SOURCE = "coffer"


def log_dir() -> Path:
    """The directory Coffer writes logs to (``COFFER_LOG_DIR`` overrides)."""
    custom = os.environ.get("COFFER_LOG_DIR")
    if custom:
        return Path(custom)
    return logs_dir()


def upstream_log_path(server_name: str) -> Path:
    """Where one upstream MCP server's stderr file lives.

    Keyed on the server's NAME (the label): the file is for a person reading it,
    and the one place that computes it is shared by the writer below and the
    server page's log read, so the two cannot disagree. The rolled-aside backup
    is the same path with ``.1`` appended.
    """
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in server_name) or "upstream"
    return log_dir() / "upstream" / f"{safe}.log"


class LineSink(Protocol):
    """Where an upstream's log lines go: its log file, or a sink in front of it
    that masks the values Coffer injected into the child
    (``infrastructure.mcp.stderr_mask.MaskedSink``)."""

    def write(self, text: str, /) -> int: ...

    def flush(self) -> None: ...


def write_coffer_line(sink: LineSink, text: str) -> None:
    """Append one Coffer-authored line to an upstream's log file.

    ``<ISO-8601 UTC timestamp> coffer <text>`` — the prefix is what the log read
    uses to tell Coffer's own lines (how it started and stopped the server) from
    what the server printed on stderr. Best-effort: never raises.
    """
    stamp = datetime.now(tz=UTC).isoformat(timespec="seconds")
    try:
        sink.write(f"{stamp} {COFFER_LINE_SOURCE} {text}\n")
        sink.flush()
    except (OSError, ValueError):
        return


def open_upstream_errlog(server_name: str) -> TextIO | None:
    """Open the append-mode stderr sink for one upstream MCP server.

    ``None`` when the file cannot be opened, which the caller treats as "use
    the default" — a logging problem must never stop a server from starting.

    Rotation is a single roll-aside at open time rather than a handler: the
    file descriptor is handed to a subprocess that holds it for its whole life,
    so nothing can rotate it underneath. One backup is kept; the previous one
    is replaced, and the pruner ages it out.
    """
    path = upstream_log_path(server_name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size >= _UPSTREAM_MAX_BYTES:
            path.replace(path.with_suffix(".log.1"))
        return path.open("a", encoding="utf-8", errors="replace")
    except OSError:
        _logger.debug("log.upstream_errlog_unavailable", extra={"server": server_name})
        return None


def prune_log_dir(*, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> int:
    """Delete log files older than ``max_age_days``. Returns how many went.

    Best-effort and never raises: a file that vanished under us, or one we
    cannot remove, is skipped. Pruning logs must not be able to fail a
    retention run that also prunes real data.
    """
    directory = log_dir()
    if not directory.is_dir():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for pattern in _PRUNABLE_GLOBS:
        for path in directory.glob(pattern):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
    if removed:
        _logger.info("log.pruned", extra={"removed": removed, "max_age_days": max_age_days})
    return removed
