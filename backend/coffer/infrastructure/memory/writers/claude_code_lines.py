"""The lines Coffer writes about its Claude Code copies: the marked block of a
memory folder's ``MEMORY.md`` and the rules file (spec memory "Write the hub
into Claude Code's native memory", "Write global memories into a Claude Code
global project and point at them from a rules file").

The rules file is loaded into every session, so it lists only the **standing**
global memories (every one but a bullet of a Codex task group), one short line
each, and names the task groups the rest were learned in; the global folder's
``MEMORY.md`` block lists every global memory under its group, uncapped.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping, Sequence

from coffer.domain.memory.hub import AGENT_LABELS, CODEX, HubEntry, one_line
from coffer.domain.memory.sync_plan import CopyRecord, Target
from coffer.infrastructure.memory.codex_identity import is_profile, task_group

#: Every copy's file name starts with this.
COPY_PREFIX = "coffer_"
INDEX_NAME = "MEMORY.md"
#: Lines the block lists before naming the rest (of Claude Code's 200).
BLOCK_CAP = 30
#: The rules file's size bound. Every session loads it, so it stays near 2k
#: tokens; what does not fit is still in the global folder's ``MEMORY.md``.
RULES_MAX_BYTES = 8 * 1024
#: Characters of title and description a standing memory's line shows.
RULES_LINE_TEXT = 120
#: The bound on the line naming the task groups.
RULES_TOPICS_MAX_BYTES = 2 * 1024

#: The heading over the memories that apply whatever the task.
STANDING_HEADING = "About the person and how they work"

RULES_HEADER = (
    "# Memories from your other agents\n\n"
    "Coffer writes this file. Do not edit it: change the memory in the agent that "
    "wrote it, and Coffer brings the change here.\n"
)


def _newest_first(
    live: Sequence[tuple[str, CopyRecord]], targets: Mapping[str, Target]
) -> list[tuple[Target, str]]:
    """Each live copy's target and file name, the newest memory first."""
    return sorted(
        ((targets[rec.entry], pathlib.Path(path).name) for path, rec in live),
        key=lambda row: (row[0].entry.updated_at, row[1]),
        reverse=True,
    )


def _index_line(target: Target, name: str) -> str:
    entry = target.entry
    origin = AGENT_LABELS.get(entry.origin.agent, entry.origin.agent)
    title, gloss = _title_and_rest(entry.title, entry.description, 150)
    link = f"[{one_line(title, 80)}]({name})" if title else f"[{gloss}]({name})"
    gloss = gloss.lstrip(_SEPARATORS) if title else ""
    tail = f" — {gloss}" if gloss else ""
    return f"- {link}{tail} (from {origin})"


def index_lines(live: Sequence[tuple[str, CopyRecord]], targets: Mapping[str, Target]) -> list[str]:
    rows = _newest_first(live, targets)
    lines = [_index_line(target, name) for target, name in rows[:BLOCK_CAP]]
    rest = len(rows) - BLOCK_CAP
    if rest > 0:
        lines.append(f"- …and {rest} more Coffer memories in this folder ({COPY_PREFIX}*.md)")
    return lines


def _group_of(entry: HubEntry) -> str:
    """The task group a memory was learned in, or ``""`` for a standing one."""
    return task_group(entry.origin.source) if entry.origin.agent == CODEX else ""


def _split_global(
    rows: Sequence[tuple[Target, str]],
) -> tuple[list[tuple[Target, str]], dict[str, list[tuple[Target, str]]]]:
    """The standing memories (the profile first) and the rest by task group,
    each group in the order its newest memory comes."""
    standing: list[tuple[Target, str]] = []
    groups: dict[str, list[tuple[Target, str]]] = {}
    for row in rows:
        group = _group_of(row[0].entry)
        if group:
            groups.setdefault(group, []).append(row)
        else:
            standing.append(row)
    standing.sort(key=lambda row: not _pinned(row[0].entry))
    return standing, groups


def _pinned(entry: HubEntry) -> bool:
    return entry.origin.agent == CODEX and is_profile(entry.origin.source)


def global_index_lines(
    live: Sequence[tuple[str, CopyRecord]], targets: Mapping[str, Target]
) -> list[str]:
    """The global folder's block: every memory, the standing ones first, then
    each task group under its name. No session loads this file by itself, so it
    is not capped; the rules file points at it."""
    standing, groups = _split_global(_newest_first(live, targets))
    lines: list[str] = []
    if standing:
        lines += [f"## {STANDING_HEADING}", *(_index_line(t, n) for t, n in standing)]
    for group, rows in groups.items():
        lines += [f"## {one_line(group, 120)}", *(_index_line(t, n) for t, n in rows)]
    return lines


#: What a title's remainder can open with to follow the title directly.
_JOINERS = (";", ",", ".", ":", " ")
#: Separators trimmed off a remainder that is shown on its own.
_SEPARATORS = " ;,.:->"


def _title_and_rest(title: str, description: str, limit: int) -> tuple[str, str]:
    """``title`` and what ``description`` adds to it, each on one line.

    A Codex memory has no title of its own: its title is the first clause of its
    text, and its description is the whole text, so printing both repeats that
    clause. When the description begins with the title, only the remainder is
    returned (``""`` when there is none); when the title is a cut-off stem of the
    description, the title is dropped (``""``) and the description returned."""
    t, d = one_line(title, 10_000), one_line(description, 10_000)
    if not d or d == t:
        return t, ""
    if d.startswith(t):
        rest = d[len(t) :]
        if not rest.strip():
            return t, ""
        # Keep the separator that joined the clause to the rest ("; ", " -> ").
        return t, (" " if rest[0] == " " else "") + one_line(rest, limit)
    for ellipsis in ("...", "…"):
        stem = t[: -len(ellipsis)].rstrip() if t.endswith(ellipsis) else ""
        if stem and d.startswith(stem):
            return "", one_line(d, limit)
    return t, one_line(d, limit)


def _rules_text(entry: HubEntry) -> str:
    """A standing memory's title, and as much of what its description adds as
    fits in :data:`RULES_LINE_TEXT` characters."""
    title, gloss = _title_and_rest(entry.title, entry.description, RULES_LINE_TEXT)
    if not title:
        return gloss
    title = one_line(title, RULES_LINE_TEXT)
    room = RULES_LINE_TEXT - len(title) - 2  # the ": " a gloss may need
    if room < 40:
        return f"**{title}**"
    _, gloss = _title_and_rest(entry.title, entry.description, room)
    if not gloss:
        return f"**{title}**"
    sep = "" if gloss[:1] in _JOINERS else ": "
    return f"**{title}**{sep}{gloss}"


def _topics_line(groups: Mapping[str, Sequence[tuple[Target, str]]]) -> str:
    names = [f"{one_line(group, 60)} ({len(rows)})" for group, rows in groups.items()]
    line = ""
    for i, name in enumerate(names):
        more = f"; …and {len(names) - i} more topics" if i else ""
        candidate = f"{line}; {name}" if line else name
        if len(candidate.encode("utf-8")) + len(more.encode("utf-8")) > RULES_TOPICS_MAX_BYTES:
            return line + f"; …and {len(names) - i} more topics"
        line = candidate
    return line


def render_rules(
    folder: pathlib.Path,
    live: Sequence[tuple[str, CopyRecord]],
    targets: Mapping[str, Target],
) -> str:
    """Where the global memories are, one short line per standing memory, and
    the task groups the rest were learned in. Every session loads this, so it
    holds no memory text and stays within :data:`RULES_MAX_BYTES`."""
    standing, groups = _split_global(_newest_first(live, targets))
    parts = [
        RULES_HEADER
        + "\nThese memories are about the person, or were learned outside any project. "
        f"Their files are in `{folder}`; read one when its line is relevant to the task.\n"
    ]
    tail = ""
    if groups:
        tail = (
            "\n## Learned in specific tasks\n\n"
            f"`{folder / INDEX_NAME}` lists these by topic; when the task matches a topic, "
            f"read that list and then the files it names. Topics: {_topics_line(groups)}.\n"
        )
    size = len(parts[0].encode("utf-8")) + len(tail.encode("utf-8"))
    if standing:
        heading = f"\n## {STANDING_HEADING}\n\n"
        parts.append(heading)
        size += len(heading.encode("utf-8"))
        more = f"- …and {{}} more, listed in `{folder / INDEX_NAME}`.\n"
        # Room for the line naming the rest, should any be left out.
        budget = RULES_MAX_BYTES - len(more.format(len(standing)).encode("utf-8"))
        lines = [f"- {_rules_text(target.entry)} ({name})\n" for target, name in standing]
        if size + sum(len(line.encode("utf-8")) for line in lines) <= RULES_MAX_BYTES:
            budget = RULES_MAX_BYTES
        listed = 0
        for line in lines:
            if size + len(line.encode("utf-8")) > budget:
                break
            parts.append(line)
            size += len(line.encode("utf-8"))
            listed += 1
        if listed < len(standing):
            parts.append(more.format(len(standing) - listed))
    parts.append(tail)
    return "".join(parts)


__all__ = [
    "BLOCK_CAP",
    "COPY_PREFIX",
    "INDEX_NAME",
    "RULES_LINE_TEXT",
    "RULES_MAX_BYTES",
    "global_index_lines",
    "index_lines",
    "render_rules",
]
