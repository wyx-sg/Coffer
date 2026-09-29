"""Which of Coffer's notes an agent actually opened, read off the **paths** its
tool calls named (spec memory "Count what memory delivered and what was read").

Only the arguments of tool calls are looked at, and only for a path under the
memory root that names a note (``<root>/<partition>/notes/<slug>.md``): what a
note says, what a tool returned and what the user or the agent wrote are never
read out, stored or counted. Aggregation still reads no transcript (spec memory
"Read no transcripts or rollouts"); this is observability over file paths.

Claude Code keeps a session per ``<config>/projects/**/*.jsonl``; Codex per
``<config>/sessions/**/*.jsonl``. Only files touched inside the window are
opened, a line is parsed only when it mentions the memory root at all, and each
file's answer is cached by ``(mtime, size)`` for the daemon's lifetime.

``None`` — "unavailable" — when the agent's transcript directory is missing or
unreadable, or the agent type keeps none Coffer knows.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_SESSION_DIRS = {"claude_code": "projects", "codex": "sessions"}

#: (path, mtime_ns, size, root) -> the note keys that file's tool calls named.
_CACHE: dict[tuple[str, int, int, str], frozenset[str]] = {}


def _tool_inputs(record: Any) -> Iterator[str]:
    """Every tool-call argument string in one transcript record, both shapes."""
    if not isinstance(record, dict):
        return
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield json.dumps(block.get("input", {}), ensure_ascii=False)
    payload = record.get("payload")
    if isinstance(payload, dict) and payload.get("type") in (
        "function_call",
        "custom_tool_call",
        "local_shell_call",
    ):
        for key in ("arguments", "input", "action"):
            value = payload.get(key)
            if value is not None:
                yield value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _pattern(root: str) -> re.Pattern[str]:
    return re.compile(re.escape(root.rstrip("/")) + r"/([^/\s\"'\\]+)/notes/([^/\s\"'\\]+?)\.md")


def _scan_file(path: pathlib.Path, roots: tuple[str, ...], since: datetime) -> frozenset[str]:
    found: set[str] = set()
    patterns = [_pattern(r) for r in roots]
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not any(r in line for r in roots):
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            stamp = record.get("timestamp") if isinstance(record, dict) else None
            if isinstance(stamp, str):
                try:
                    if datetime.fromisoformat(stamp.replace("Z", "+00:00")) < since:
                        continue
                except ValueError:
                    pass
            for text in _tool_inputs(record):
                for pattern in patterns:
                    for m in pattern.finditer(text):
                        found.add(f"{m.group(1)}/{m.group(2)}")
    return frozenset(found)


def notes_read(
    agent_type: str, config_dir: pathlib.Path, memory_root: pathlib.Path, since: datetime
) -> set[str] | None:
    """The ``<partition>/<slug>`` of every note the agent's tool calls named
    since ``since``, or ``None`` when that cannot be computed."""
    sub = _SESSION_DIRS.get(agent_type)
    if sub is None:
        return None
    base = config_dir / sub
    if not base.is_dir():
        return None
    roots = tuple(dict.fromkeys((str(memory_root), str(memory_root.resolve()))))
    cutoff = since.timestamp()
    found: set[str] = set()
    try:
        for path in base.rglob("*.jsonl"):
            try:
                st = path.stat()
            except OSError:
                continue
            if st.st_mtime < cutoff:
                continue
            key = (str(path), st.st_mtime_ns, st.st_size, "|".join(roots))
            cached = _CACHE.get(key)
            if cached is None:
                try:
                    cached = _scan_file(path, roots, since)
                except OSError:
                    continue
                _CACHE[key] = cached
            found.update(cached)
    except OSError as e:
        logger.warning("memory.transcript_reads.unavailable; dir=%s error=%s", base, e)
        return None
    return found


def clear_cache() -> None:
    _CACHE.clear()


__all__ = ["clear_cache", "notes_read"]
