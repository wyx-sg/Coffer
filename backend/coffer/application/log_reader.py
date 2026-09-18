"""Reading the daemon's own log file — the shared half of two readers.

The daemon log has two callers now: ``coffer__diagnose`` (an agent, at the
moment something broke) and the web Activity page (a human, scanning the same
timeline). Both need the same three decisions — read from the tail, keep an
unparseable line rather than drop it, and treat "unparseable" as error-level —
so they live here rather than being copied into a surface.

**The file is not one format**, and it never can be: ``daemon.log`` is also
where a detached daemon's stdout and stderr are redirected, so every child
process the daemon holds open a pipe to ends up writing into it in its own
shape.

*What Coffer itself writes* is one format, as of the day
:mod:`coffer.infrastructure.logging.setup` stopped formatting the fields off
its own records: a JSON object per line, keyed ``timestamp`` / ``level`` /
``logger`` / ``event``, for every record on every logger inside the daemon
process — its own modules, the MCP SDK's, asyncio's, and alembic's. That is
the shape :func:`_structured` tries first.

*What other processes write* is theirs to decide, and the rest of the parsers
below are the ones that have actually been observed in the file: uvicorn's
``ERROR:    …`` (it configures its own three loggers and keeps them off the
root), an upstream MCP server's rich panels and ``LEVEL - logger - message``
lines, and the zerolog of the cloudflared child a tunnel respawns
(``2026-09-14T06:29:20Z INF … key=value``). ``_BRACKETED`` is the one parser
kept for lines nothing writes any more: it reads the alembic-formatter shape
the daemon used to produce, and a log file written before that was fixed holds
them by the thousand inside the tail this module reads.

Everything is normalised onto the same four keys, and a line that matches none
of them is kept verbatim as ``raw`` — a reader that only understood Coffer's
JSON left the time, level and logger columns empty and dumped the whole line
into the message column, which is the bug this module exists to not have.

Pure: no I/O beyond reading the path it is handed, and no knowledge of who is
asking.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Read from the tail rather than the head: the interesting line is the last
#: one. Bounded so a 10 MB log cannot be pulled into memory.
TAIL_BYTES = 512 * 1024

#: CSI sequences (colour, cursor) and OSC strings. A child process writing to
#: a pipe is not always convinced it is not a terminal — the Codex app-server
#: colours its stderr, which the daemon relays into this file verbatim — and a
#: log viewer that renders `ESC[31m` as the text "[31m" is broken either way.
_ANSI = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))")

#: Every level token any of the writers below spells, onto the lowercase
#: vocabulary Coffer's own lines use — so one badge vocabulary serves the whole
#: file.
#: The 5-character truncations come from ``%(levelname)-5.5s``; the
#: 3-character ones from zerolog.
_LEVELS = {
    "TRACE": "debug",
    "TRC": "debug",
    "DEBUG": "debug",
    "DBG": "debug",
    "INFO": "info",
    "INF": "info",
    "WARN": "warning",
    "WARNI": "warning",
    "WARNING": "warning",
    "WRN": "warning",
    "ERROR": "error",
    "ERR": "error",
    "EXCEPTION": "error",
    "CRITI": "critical",
    "CRITICAL": "critical",
    "FATAL": "critical",
    "FTL": "critical",
}

#: Levels that ``errors_only`` keeps. A line whose level we could not read at
#: all is kept too (see ``matches_level``) — it is usually a traceback.
_ERROR_LEVELS = {"error", "critical", "exception"}

#: Log levels in order of severity, least to most. A filter names a floor and
#: everything at or above it survives — which is what a reader means by "show
#: me warnings": warnings AND the errors among them, not warnings alone.
_LEVEL_ORDER: tuple[str, ...] = ("debug", "info", "warning", "error", "critical")


def normalise_level(raw: str) -> str:
    """One level name from whatever a line called it.

    ``_LEVELS`` is the same table the parsers use, so a level read off a
    zerolog line and one read off Coffer's own JSON land on the same word.
    Returns ``""`` for anything the table does not know.
    """
    token = raw.strip()
    if not token:
        return ""
    if token.lower() in _LEVEL_ORDER:
        return token.lower()
    return _LEVELS.get(token.upper(), "")


def at_least(record: dict[str, Any], floor: str) -> bool:
    """Whether ``record`` is at or above ``floor`` on the severity scale.

    A record whose level cannot be read survives every floor: not knowing what
    a line was is not evidence that it was harmless — the same rule
    ``matches_level`` has always applied to the errors-only filter. An
    unrecognised floor filters nothing, for the same reason.
    """
    level = normalise_level(str(record.get("level", "")))
    wanted = normalise_level(floor)
    if not level or not wanted:
        return True
    return _LEVEL_ORDER.index(level) >= _LEVEL_ORDER.index(wanted)


# cloudflared (zerolog): `2026-09-14T06:29:20Z INF Registered tunnel … ip=…`
_ZEROLOG = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)"
    r"\s+(?P<level>[A-Z]{3})\s+(?P<event>.*)$"
)
# The daemon's own records, back when alembic's fileConfig had re-pointed the
# root handler at `%(levelname)-5.5s [%(name)s] %(message)s`:
# `WARNI [coffer.chat.codex] …`. Nothing writes this shape any more — the
# formatter is the daemon's own now, and env.py no longer calls fileConfig —
# but a log file written before that fix still holds these, so reading one
# must not regress into three empty columns per line.
_BRACKETED = re.compile(r"^(?P<level>[A-Z]{4,9})\s+\[(?P<logger>[^\]\s]+)\]\s+(?P<event>.*)$")
# another common stdlib formatter: `WARNING - mcp_atlassian.utils.toolsets - …`
_DASHED = re.compile(r"^(?P<level>[A-Z]{4,9})\s+-\s+(?P<logger>[\w.\-]+)\s+-\s+(?P<event>.*)$")
# uvicorn's default: `ERROR:    ASGI callable returned without completing…`
_PREFIXED = re.compile(r"^(?P<level>[A-Z]{4,9}):\s+(?P<event>.*)$")
# rich (FastMCP): `[09/10/26 17:53:12] INFO     Starting MCP server … server.py:2506`
_RICH = re.compile(
    r"^\[(?P<date>\d{2}/\d{2}/\d{2}) (?P<time>\d{2}:\d{2}:\d{2})\]"
    r"\s+(?P<level>[A-Z]{4,9})\s+(?P<event>.*)$"
)

_TRACEBACK_HEADER = "Traceback (most recent call last):"
#: A rich panel (FastMCP's startup banner) draws its own box; those rows belong
#: to the line that opened the panel, not to a row each.
_BOX_DRAWING = "│╭╮╯╰├┤┬┴┼─━┃┌┐└┘"


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


def strip_ansi(text: str) -> str:
    """``text`` without terminal escape sequences."""
    return _ANSI.sub("", text)


def _local_wall_clock_to_utc(date: str, time: str) -> str | None:
    """rich's ``MM/DD/YY HH:MM:SS`` — local wall clock, no offset — as UTC ISO.

    rich prints the daemon's local time and says nothing about the zone, so
    reading it back needs a zone from somewhere: this is a single-user,
    single-machine vault, so the machine reading the log is the machine that
    wrote it and its own zone is the right one. A row is then displayed at the
    wall-clock time the line claims, which is the whole point of the column.
    """
    try:
        naive = datetime.strptime(f"{date} {time}", "%m/%d/%y %H:%M:%S")
    except ValueError:
        return None
    return naive.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _structured(line: str) -> dict[str, Any] | None:
    """One line as a record, or None when no known writer's format fits."""
    if line.lstrip().startswith("{"):
        try:
            parsed = json.loads(line)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

    for pattern in (_ZEROLOG, _RICH, _BRACKETED, _DASHED, _PREFIXED):
        match = pattern.match(line)
        if match is None:
            continue
        fields = match.groupdict()
        level = _LEVELS.get(fields["level"])
        if level is None:
            # An all-caps word that is not a level — e.g. a message opening
            # with `NOTE: …`. Not this writer's line; keep looking.
            continue
        record: dict[str, Any] = {"level": level, "event": fields["event"].rstrip()}
        timestamp = fields.get("timestamp")
        if pattern is _RICH:
            timestamp = _local_wall_clock_to_utc(fields["date"], fields["time"])
        if timestamp:
            record["timestamp"] = timestamp
        if fields.get("logger"):
            record["logger"] = fields["logger"]
        return record
    return None


def parse_log_line(line: str) -> dict[str, Any]:
    """One line as a record: the writer's fields where we can read them.

    One of Coffer's own lines arrives as its own dict; every other writer's
    line is normalised onto ``timestamp`` / ``level`` / ``logger`` / ``event``.
    A line that fits none of them is kept whole as ``{"raw": …}`` rather than
    dropped — it is often the most interesting line in the file.
    """
    clean = strip_ansi(line).rstrip()
    return _structured(clean) or {"raw": clean}


def _is_continuation(line: str, *, in_traceback: bool) -> bool:
    """Whether ``line`` continues the record above it rather than starting one.

    A traceback's frames are indented, its header is not, and its final
    ``SomeError: …`` line is not either — so the header opens a block that the
    first unindented line inside it closes (the caller tracks that in
    ``in_traceback``). Anything else indented, or drawn as a panel border, is
    the tail of a wrapped message.
    """
    head = line[:1]
    return (
        in_traceback
        or line.strip() == _TRACEBACK_HEADER
        or head.isspace()
        or (head != "" and head in _BOX_DRAWING)
    )


def parse_log_lines(lines: Iterable[str]) -> list[dict[str, Any]]:
    """Parsed records, oldest-first, with continuation lines folded in.

    A traceback is not four hundred log records with no time, level or logger:
    it is the tail of the one record that raised. Those lines are attached to
    that record under ``continuation`` — visible when the row is expanded,
    rather than as a run of empty rows pushing the record that explains them
    off the page.
    """
    records: list[dict[str, Any]] = []
    in_traceback = False
    for line in lines:
        clean = strip_ansi(line).rstrip()
        if not clean.strip():
            continue
        structured = _structured(clean)
        if structured is not None:
            records.append(structured)
            in_traceback = False
            continue
        if _is_continuation(clean, in_traceback=in_traceback) and records:
            records[-1].setdefault("continuation", []).append(clean)
        else:
            records.append({"raw": clean})
        # The header opens the block; the first unindented line inside it (the
        # exception itself, already attached above) closes it.
        in_traceback = clean.strip() == _TRACEBACK_HEADER or (in_traceback and clean[:1].isspace())
    return records


def matches_level(record: dict[str, Any], errors_only: bool) -> bool:
    """Whether ``record`` survives the ``errors_only`` filter.

    A record whose level we could not read at all survives too: not knowing
    what a line was is not evidence that it was harmless.
    """
    if not errors_only:
        return True
    level = str(record.get("level", "")).lower()
    return level in _ERROR_LEVELS or not level


__all__ = [
    "TAIL_BYTES",
    "at_least",
    "matches_level",
    "normalise_level",
    "parse_log_line",
    "parse_log_lines",
    "strip_ansi",
    "tail_lines",
]
