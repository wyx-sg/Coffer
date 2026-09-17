"""Composing the session-start payload: the whole index, and where the bodies
are (spec memory FR-028, FR-029, FR-030).

Delivery is no longer a digest. It is **the index** — every non-retired note
in the current repository's partition and in ``global``, one line each, from
``index.index_line`` — followed by the **absolute path** of the directory the
bodies live in. Nothing here names a tool, and that omission is the design:
every consumer of this payload is a process on this machine with filesystem
access. A hook-driven Claude Code session and a hook-driven Codex session
both read files as their ordinary way of reaching their own memory, and a
channel-driven turn (FR-031) drives a **local** Claude Code or Codex through
``claude-agent-sdk`` with ``bypassPermissions`` — see
``infrastructure/chat/claude_sdk_agent.py`` — rather than answering out of the
daemon. Pointing such a reader at a tool is what the previous design did, and
in three weeks it produced exactly zero calls.

Three things this module is deliberately narrow about:

* **It never resolves a cwd's partition from scratch, and it has no caller
  identity to resolve anything against.** :class:`MemoryPort` below is the
  narrow slice of ``MemoryService`` this needs — the enabled partitions, a
  partition's notes, the partition list — so a unit test can fake it with no
  database at all, and the production composition root hands in the real
  service unchanged (structural typing: the Protocol is not a base class
  ``MemoryService`` has to inherit from). There is deliberately no ``agent``
  among those: every enabled partition is composed for every agent (FR-013),
  because memory aggregated from several agents exists so each of them can
  read what the others learned.
* **It reads the notes as the distil pass left them.** There is no second
  judgement on top: no hide, no pin, no status. A retired note is not
  filtered here because it is not here — retirement takes the file out of
  ``notes/`` and writes ``RETIRED.md`` (FR-025), so ``list_notes`` cannot
  return one. That is stated on the port, because it is the port's promise
  to keep.
* **It renders no line of its own.** The delivered line *is* the index's
  line, so it comes from ``index.index_line`` and is sorted by
  ``index.recency`` — the same renderer and the same definition of "newest"
  that write ``MEMORY.md``. What it does not borrow is the file: the index
  on disk is the distil pass's output, which may not exist yet, and this
  module composes from the ``MemoryPort`` instead.

The ceiling and who wins it are documented on
:data:`DEFAULT_CEILING_TOKENS` and in :func:`compose_context`.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from coffer.application.memory.index import index_line, recency
from coffer.domain.memory.budget import estimate_tokens
from coffer.domain.memory.note import Note
from coffer.domain.memory.partition import GLOBAL_PARTITION
from coffer.infrastructure.memory import paths as memory_paths

#: The ceiling on a composed payload, sized **for an index** rather than for a
#: handful of lines (FR-030). Three real figures set it:
#:
#: * Claude Code loads its own whole index — 94 entries, **~9k tokens** — into
#:   every session of its own accord. That is the ecosystem's demonstrated
#:   price for not searching, paid by a host that has to fit its own budget.
#: * This vault's ``coffer`` partition index is **~3k tokens**.
#: * Its ``global`` index is **~1.5k tokens** after distillation.
#:
#: So the ordinary composed payload here is ~4.5k, and the ceiling is set at
#: roughly **2.7x** that and above Claude Code's own single-index load. It is
#: a guard against the assumption in the spec breaking — a partition that
#: grows past what an index can be — not a budget meant to bind on the
#: ordinary path. The previous design's ~600 tokens bound on **every** path,
#: and delivered 8 of 189 entries.
DEFAULT_CEILING_TOKENS = 12000


class PartitionView(Protocol):
    """What composing needs to know about one partition: its name and the
    repository it was learned in (FR-014).

    Read-only properties rather than an import of ``service.PartitionSummary``,
    so this module does not depend on the shape of a management-surface
    value object — and so a test can pass a two-field stub.
    """

    @property
    def name(self) -> str: ...

    @property
    def repository_path(self) -> str: ...


class MemoryPort(Protocol):
    """The slice of ``MemoryService`` composing a context needs: which
    partitions are served and what is in them, never aggregation. Matches
    ``MemoryService``'s real signatures structurally, so the production
    service satisfies it with no adapter.

    ``list_notes`` answers from the partition's ``notes/`` directory, which
    is what makes FR-025 hold on this path: a retired note's file has left
    that directory, so there is no retired note to exclude. A cache that
    outlived the file would break the guarantee silently, which is exactly
    how the previous design went on serving 11 dead facts.
    """

    async def enabled_partitions(self) -> Sequence[str]: ...

    async def list_notes(self, partition: str) -> Sequence[Note]: ...

    async def list_partitions(self) -> Sequence[PartitionView]: ...


@dataclass(frozen=True)
class ComposedContext:
    """What ``compose_context`` hands back: the text, which partition it
    resolved ``cwd`` to, and enough accounting for a caller — or a test — to
    confirm the ceiling rule actually held (FR-030)."""

    text: str
    partition: str
    notes_included: int
    notes_omitted: int


def _ordered(notes: Iterable[Note]) -> tuple[Note, ...]:
    """Newest first, by ``index.recency`` — not a second definition of it.

    Under a ceiling this order *is* the trim rule: FR-030 drops the oldest
    lines, which is the tail of this sequence.
    """
    return tuple(sorted(notes, key=recency, reverse=True))


def _notes_dir(partition: str) -> str:
    """The absolute path of one partition's ``notes/`` directory."""
    return str(memory_paths.notes_dir(partition))


def _trim_notice(dropped: int, notes_path: str) -> str:
    """The line a trim leaves behind (FR-030).

    It names the count **and the directory**, because that is what makes a
    trim here a small loss rather than the old design's large one: every line
    that did not fit is still a file, at a path now stated, reachable with an
    ordinary read. The previous design's equivalent line named a tool nobody
    called.
    """
    return f"({dropped} older line(s) not shown — those notes are files in {notes_path})"


def _resolve_cwd_partition(partitions: Sequence[PartitionView], cwd: str) -> str:
    """Map ``cwd`` to its partition the way aggregation named it: by the
    absolute **repository** path recorded on the partition's own Resource,
    never recomputed here.

    Matching on the repository rather than on a working directory is what
    makes a worktree and a second clone resolve to the partition their main
    checkout contributes to (FR-014) — a session opened in
    ``repo/.claude/worktrees/x`` is a session about ``repo``.

    The longest matching repository wins, so a repository nested inside
    another checked-out one resolves to the inner one. An unknown, blank or
    unresolvable ``cwd`` — including one under no recorded repository —
    yields ``global``, which the spec treats as a normal answer, not an
    error: a directory that is not a repository gets no partition (FR-015).
    """
    stripped = (cwd or "").strip()
    if not stripped:
        return GLOBAL_PARTITION
    try:
        target = pathlib.Path(stripped).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return GLOBAL_PARTITION

    best_name: str | None = None
    best_depth = -1
    for summary in partitions:
        if summary.name == GLOBAL_PARTITION or not summary.repository_path:
            continue
        try:
            root = pathlib.Path(summary.repository_path).expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if target != root and root not in target.parents:
            continue
        depth = len(root.parts)
        if depth > best_depth:
            best_depth = depth
            best_name = summary.name
    return best_name or GLOBAL_PARTITION


def _repository_of(partitions: Sequence[PartitionView], name: str) -> str:
    for summary in partitions:
        if summary.name == name:
            return summary.repository_path
    return ""


class _Ceiling:
    """Tracks the tokens left, with each section's trim notice reserved up
    front so a trim can never crowd out the line that announces it."""

    def __init__(self, total_tokens: int) -> None:
        self._remaining = total_tokens

    def reserve(self, text: str) -> None:
        self._remaining -= estimate_tokens(text)

    def spend(self, text: str) -> None:
        self._remaining -= estimate_tokens(text)

    def fits(self, text: str) -> bool:
        return estimate_tokens(text) <= self._remaining


def _take(notes: Sequence[Note], ceiling: _Ceiling) -> list[str]:
    """As many lines as fit, newest first, stopping at the first that does not.

    Stopping rather than skipping is the point: FR-030 drops **the oldest**
    lines, so what survives is a contiguous prefix of a newest-first list.
    """
    taken: list[str] = []
    for note in notes:
        line = index_line(note)
        if not ceiling.fits(line):
            break
        ceiling.spend(line)
        taken.append(line)
    return taken


async def compose_context(
    memory: MemoryPort,
    *,
    cwd: str,
    ceiling_tokens: int = DEFAULT_CEILING_TOKENS,
) -> ComposedContext:
    """Build the session-start payload (FR-028): what is known about the
    developer, then the whole index of this repository's partition, then the
    absolute path of that partition's ``notes/``.

    **When the two partitions compete for the ceiling, the current repository
    wins.** The order of the text is FR-028's — ``global`` first, because it
    is short and it frames everything after it — but the order of *spending*
    is the reverse: the repository's lines are taken first and ``global``
    gets what is left. This is the direct reversal of the previous design,
    which filled its ~600 tokens with ``global`` first and therefore
    delivered, on a live vault of 189 entries, 8 lines of which **none** were
    about the project the session was open in. The partition a session is
    open in is the one it is about.

    With nothing to deliver, the text is empty rather than a bare header:
    FR-031's channel turn appends this only when it is non-empty, and an
    empty memory header is worse than none.
    """
    served = set(await memory.enabled_partitions())
    partitions = await memory.list_partitions()
    project_partition = _resolve_cwd_partition(partitions, cwd)

    global_notes: Sequence[Note] = ()
    if GLOBAL_PARTITION in served:
        global_notes = await memory.list_notes(GLOBAL_PARTITION)
    project_notes: Sequence[Note] = ()
    if project_partition != GLOBAL_PARTITION and project_partition in served:
        project_notes = await memory.list_notes(project_partition)

    seen = {n.key: n for n in list(global_notes) + list(project_notes)}
    global_visible = _ordered(n for n in seen.values() if n.partition == GLOBAL_PARTITION)
    project_visible = (
        _ordered(n for n in seen.values() if n.partition == project_partition)
        if project_partition != GLOBAL_PARTITION
        else ()
    )

    total = len(global_visible) + len(project_visible)
    if not total:
        return ComposedContext(
            text="", partition=project_partition, notes_included=0, notes_omitted=0
        )

    global_dir = _notes_dir(GLOBAL_PARTITION)
    project_dir = _notes_dir(project_partition) if project_visible else ""
    body_dir = project_dir or global_dir

    header = "## Coffer memory"
    global_heading = "Known about you:"
    repository = _repository_of(partitions, project_partition)
    where = f" ({repository})" if repository else ""
    project_heading = (
        f"Memory for this repository — partition `{project_partition}`{where}:"
        if project_visible
        else "No memory filed for this working directory — it is in no repository Coffer "
        "has aggregated yet."
    )
    closing = (
        f"Each line names its note's file. The bodies are Markdown files in {body_dir} — "
        "read one as a file, the way you read your own memory."
    )

    ceiling = _Ceiling(ceiling_tokens)
    for scaffolding in (header, global_heading, project_heading, closing):
        ceiling.reserve(scaffolding)
    if project_visible:
        ceiling.reserve(_trim_notice(len(project_visible), project_dir))
    if global_visible:
        ceiling.reserve(_trim_notice(len(global_visible), global_dir))

    # The repository first, deliberately: see this function's docstring.
    project_lines = _take(project_visible, ceiling)
    global_lines = _take(global_visible, ceiling)

    lines = [header]
    if global_visible:
        lines.append(global_heading)
        lines.extend(global_lines)
        dropped = len(global_visible) - len(global_lines)
        if dropped:
            lines.append(_trim_notice(dropped, global_dir))
    lines.append(project_heading)
    lines.extend(project_lines)
    dropped = len(project_visible) - len(project_lines)
    if dropped:
        lines.append(_trim_notice(dropped, project_dir))
    lines.append(closing)

    included = len(global_lines) + len(project_lines)
    return ComposedContext(
        text="\n".join(lines),
        partition=project_partition,
        notes_included=included,
        notes_omitted=total - included,
    )


__all__ = [
    "DEFAULT_CEILING_TOKENS",
    "ComposedContext",
    "MemoryPort",
    "PartitionView",
    "compose_context",
]
