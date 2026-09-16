"""Rendering a partition's index: one line per note, for two readers that must
not drift apart (spec memory FR-029).

This module owns what "one line per note" looks like, and that one shape
reaches two readers by two different callers:

* **``MEMORY.md``**, written by the distil pass from :func:`render_index`.
  Its reader is the **person** who opens a partition as a folder (FR-037),
  and the agent that reads the file directly — which is exactly what both
  supported hosts do with their own index.
* **The delivered payload**, composed by ``context.py`` from
  :func:`index_line`. FR-028 makes delivery *the whole index*, so the
  delivered line must be the index's line, not a second rendering of the
  same idea. ``context.py`` cannot reuse :func:`render_index` wholesale (it
  composes from a ``MemoryPort``, spends a ceiling line by line, and
  interleaves two partitions), so it reuses the **line**, which is the part
  FR-029 actually names.

**A line has to be sufficient on its own.** That is FR-029's demand and it is
the lesson of the measured failure: the previous design delivered eight lines
and a tool name, and in three weeks no agent ever followed the pointer. An
index that is shown entirely only pays off if reading it is usually the end
of the errand, so the conclusion goes *into* the line rather than being
promised by it. Claude Code's own index, on the maintainer's machine, is this
shape — ``- [slug](slug.md) — a sentence that already answers the question``
— and it is why 94 entries are worth ~9k tokens of every session to it.

Two things the line always carries beyond the conclusion:

* **Its file name.** The body is reached with an ordinary file read (FR-022,
  FR-028), so the line names the file to read. It names it *relative* — the
  directory is stated once, by whichever surface is rendering: ``MEMORY.md``
  sits beside ``notes/``, and delivery states the absolute path of that
  directory. A line that spelled the absolute path itself would be the same
  ~60 characters of ``/Users/...`` repeated on every one of a hundred lines.
* **The source's own search terms**, where it supplied any (FR-004). Codex
  states them per task group — its own answer to "what would you look this up
  by" — and discarding them is what left the previous design's retrieval to
  guesswork.

Pure and synchronous: no filesystem, no model. Keeping the render incapable
of I/O is what guarantees FR-024's path — an installation with **no** internal
connection still gets a real index, grouped and readable, because nothing here
can silently depend on a model having run first.

Retired notes need no filtering here. A retirement takes the note's file out
of ``notes/`` and records it in ``RETIRED.md`` (FR-025), so a retired note is
not among the notes handed to either function. There is no ``status`` field
left to check, and that is deliberate: the previous design marked a fact dead
and went on serving it.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.memory.note import (
    TYPE_FEEDBACK,
    TYPE_PROJECT,
    TYPE_USER,
    Note,
)

#: Group order: project notes first (what makes this partition distinct),
#: then the two personal types. Any type outside this tuple (a future
#: ``NOTE_TYPES`` addition, or a hand-edited file with a stray value) is
#: still rendered — appended afterwards, sorted for determinism — rather
#: than silently dropped.
_TYPE_ORDER = (TYPE_PROJECT, TYPE_USER, TYPE_FEEDBACK)

_TYPE_LABELS = {
    TYPE_PROJECT: "Project",
    TYPE_USER: "About the developer",
    TYPE_FEEDBACK: "Feedback and standing instructions",
}


def recency(note: Note) -> str:
    """The latest timestamp attached to ``note``, for a newest-first sort.

    The **one** definition of "newest", shared by ``MEMORY.md`` and by
    delivery, because two copies of it drift exactly the way two copies of
    "one line per note" did: ``context.py`` used to read ``captured_at``
    alone, so a note timestamped only at its source scored ``""`` and sorted
    last in the delivery while sorting correctly in the file. That mattered
    more than it sounds — under a ceiling, the sort order *is* which notes
    survive a trim (FR-030).

    The answer is the note's **own** ``updated_at`` — when Coffer last wrote
    it — and the rest of the chain exists only for a note that does not carry
    one. It is a *fallback* chain and deliberately not a ``max()`` across
    everything datable, which is what it was and which was wrong twice over.

    An origin's ``captured_at`` says when Coffer **read a source**, not when
    this note changed; a source re-read without changing leaves the note
    exactly as it was. Worse, a ``max()`` collapses the whole ordering in the
    one state where it matters most: right after a rebuild every note is
    written, and every origin captured, in a single pass, so every note ties
    on that one timestamp, the sort degenerates to whatever order the notes
    arrived in, and a trim then drops from the tail — which under
    ``reverse=True`` on equal keys is the *newest* note, the exact opposite of
    FR-030. That is not hypothetical: it is how this function was caught.

    ISO-8601 strings sort lexically in chronological order. A note with no
    timestamp anywhere (a hand-edited file can manage it) sorts last rather
    than raising.
    """
    if note.updated_at:
        return note.updated_at
    if note.created_at:
        return note.created_at
    stamps = [s for o in note.origins for s in (o.captured_at, o.source_written_at) if s]
    return max(stamps, default="")


def index_line(note: Note) -> str:
    """One note as one line — the shape both readers get (module docstring).

    ``- **Title** (`slug.md`) — the conclusion · look up: term, term``

    The title names it, the file name says where the body is, the description
    *is* the answer for most lines, and the search terms are the source's own
    (FR-004). Never the body: a body is a file, and the whole point of
    handing over the index is that the body is one read away when it is
    wanted.

    A note whose frontmatter lost its title falls back to its slug. Notes are
    derived from agents' own memory files, so a blank title is reachable, and
    naming *which* note it is beats emphasising nothing.
    """
    title = note.title.strip() or note.slug
    parts = [f"- **{title}** (`{note.slug}.md`)"]
    description = " ".join(note.description.split())
    if description:
        parts.append(f" — {description}")
    terms = [term.strip() for term in note.search_terms if term.strip()]
    if terms:
        parts.append(f" · look up: {', '.join(terms)}")
    return "".join(parts)


def _type_order_key(type_: str) -> tuple[int, str]:
    if type_ in _TYPE_ORDER:
        return (_TYPE_ORDER.index(type_), "")
    return (len(_TYPE_ORDER), type_)


def render_index(notes: Sequence[Note], *, partition: str, repository_path: str) -> str:
    """The whole ``MEMORY.md`` for one partition — grouped, newest first.

    The header restates the partition's repository path because **the
    partition has to explain itself to a human browsing it** (FR-014). It is
    the only place that can: there is no ``README.md`` beside it any more,
    the directory name is a slug, and a partition collects a repository's
    main checkout, its worktrees and its second clones — so "which project is
    this?" is a real question with a non-obvious answer.

    The second header line says where the bodies are, in the same breath, so
    the file works for a reader who arrived at it with no other context: the
    lines name ``<slug>.md`` and this says those live in ``notes/`` beside
    this file. Delivery makes the same statement with an absolute path
    (FR-028); this is its local form.
    """
    lines = [f"# {partition} — Coffer memory", ""]
    if repository_path:
        lines.append(f"Memory learned while working in `{repository_path}`.")
    else:
        lines.append("What is known about the developer, wherever they are working.")
    lines.append("Each line names its note's file: the bodies are in `notes/`, beside this one.")
    lines.append("")

    if not notes:
        lines.append("No notes yet.")
        return "\n".join(lines) + "\n"

    by_type: dict[str, list[Note]] = {}
    for note in notes:
        by_type.setdefault(note.type, []).append(note)

    for type_ in sorted(by_type, key=_type_order_key):
        group = sorted(by_type[type_], key=recency, reverse=True)
        lines.append(f"## {_TYPE_LABELS.get(type_, type_)}")
        lines.extend(index_line(n) for n in group)
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


__all__ = ["index_line", "recency", "render_index"]
