"""The text Coffer writes into Claude Code: the marked block of a project's
``MEMORY.md`` (spec memory "Write the hub into Claude Code as text it loads",
ADR claude-code-reads-other-agents-memories-as-text).

Only text a session loads by itself reaches the model, so the block holds each
memory's **text**, never a pointer to a file, and loads only in that project.
It is bounded; what does not fit is named by count with the command that lists
it.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.memory.hub import AGENT_LABELS, one_line
from coffer.domain.memory.sync_plan import Target

#: The file name of the copies earlier builds wrote; the first sync removes them.
COPY_PREFIX = "coffer_"
INDEX_NAME = "MEMORY.md"
#: A project block's bound: it sits at the end of the project's ``MEMORY.md``,
#: of which Claude Code loads the first 200 lines and 25 KB.
BLOCK_MAX_BYTES = 4 * 1024
#: The characters of one memory's text.
MEMORY_TEXT_MAX = 800


def _ordered(targets: Sequence[Target]) -> list[Target]:
    """The newest memory first."""
    return sorted(targets, key=lambda t: (t.entry.updated_at, t.entry.id), reverse=True)


def memory_text(target: Target) -> str:
    """One memory on one line: its text, with its title in front when the text
    does not already open with it (a Codex memory's title is its first clause)."""
    entry = target.entry
    title = one_line(entry.title, 10_000)
    body = one_line(target.body, 10_000) or one_line(entry.description, 10_000)
    if not body or body == title:
        text = title
    elif not title or body.startswith(title.rstrip(".…")):
        text = body
    else:
        text = f"**{title}**: {body}"
    return one_line(text, MEMORY_TEXT_MAX)


def _line(target: Target) -> str:
    origin = AGENT_LABELS.get(target.entry.origin.agent, target.entry.origin.agent)
    return f"- {memory_text(target)} (from {origin})"


def _bounded(lines: Sequence[str], used: int, limit: int, more: str) -> list[str]:
    """As many of ``lines`` as fit in ``limit`` bytes after ``used``, then
    ``more`` (formatted with the count left out) when any were left out."""
    total = used + sum(len(line.encode("utf-8")) + 1 for line in lines)
    if total <= limit:
        return list(lines)
    budget = limit - len(more.format(len(lines)).encode("utf-8")) - 1
    out: list[str] = []
    for line in lines:
        size = len(line.encode("utf-8")) + 1
        if used + size > budget:
            break
        out.append(line)
        used += size
    return [*out, more.format(len(lines) - len(out))]


def block_lines(targets: Sequence[Target], project: str) -> list[str]:
    """A project's block: its memories' text, newest first, bounded."""
    lines = [_line(t) for t in _ordered(targets)]
    more = f"- …and {{}} more from your other agents: `coffer memory entries --project {project}`"
    return _bounded(lines, 0, BLOCK_MAX_BYTES, more)


__all__ = [
    "BLOCK_MAX_BYTES",
    "COPY_PREFIX",
    "INDEX_NAME",
    "MEMORY_TEXT_MAX",
    "block_lines",
    "memory_text",
]
