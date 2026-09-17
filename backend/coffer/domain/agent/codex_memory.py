"""Parser for Codex's global native-memory file (``~/.codex/memories/MEMORY.md``).

Unlike Claude Code's per-project ``memory/*.md`` entry files, Codex keeps a single
*global* memory document organised as ``# Task Group:`` blocks. Each group carries
exactly one ``applies_to: cwd=<paths>; reuse_rule=...`` line whose ``cwd`` value
routes the group to one or more project working directories (the value may list
several paths joined by prose like `` and ``/`` plus ``/`` from ``, and may contain
``~`` or ``*``). This module is pure text logic — turning the document into one
:class:`CodexMemoryEntry` per group (:func:`parse_codex_memory`), plus the
``## <heading>`` / ``- `` bullet-list shape both a group's body and the sibling
``memory_summary.md`` profile document use (:func:`section_text`,
:func:`section_bullets`), plus that summary's ``## What's in Memory`` topic
list, where Codex writes the **search terms** it would look each task group
up by (:func:`parse_codex_summary_topics`). Two callers compose these: the
agent page's native-memory listing (``infrastructure.agent.codex_memory_store``)
groups entries by cwd into one read-only store row per project; memory
aggregation's reader (``infrastructure.memory.readers.codex``) turns each
group's and the profile's own bullets into raw entries and carries the
summary's search terms onto them (spec memory FR-004). Which sections become
entries, how a bullet gets a title, how an entry's identity anchor is built,
and **which summary topic describes which task group** are all that reader's
own policy, not this module's — this module only knows Codex's file *format*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A Task Group heading; the title is everything after the literal prefix.
_GROUP_RE = re.compile(r"^# Task Group:[ \t]*(.*)$", re.MULTILINE)
# The single routing line inside a group; capture everything after ``cwd=``.
_APPLIES_RE = re.compile(r"^applies_to:[ \t]*cwd=(.*)$", re.MULTILINE)
# Path-like tokens inside a cwd value. Anchored to ``/`` or ``~`` and stopping at
# whitespace / ``;`` / ``,`` so prose words ("plus", "from") and the trailing
# ``; reuse_rule=...`` are never captured. Handles ``*`` wildcards inside a token.
_PATH_RE = re.compile(r"[~/][^\s;,]*")

# The summary section listing one bullet per remembered task group.
_TOPICS_HEADING = "What's in Memory"
# What separates a topic's title from the backticked search-term list that
# follows it: a colon, a space, then the first term's opening backtick. Matched
# at its *first* occurrence — a title may contain a colon, but not one followed
# immediately by a backticked token, which is the list's own signature.
_TOPIC_TERMS_SEP = ": `"
# One backticked term. Codex backticks every term it states; anything unquoted
# on that line is prose, and a caller is better served by no terms than by an
# invented one (spec memory FR-004).
_TERM_RE = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class CodexMemoryEntry:
    """One Codex ``# Task Group`` block, ready to route + import.

    ``cwds`` is the (possibly empty, possibly multi-) list of project working
    directories the group applies to, as written in the file (``~`` not yet
    expanded). ``body`` is the verbatim block text (heading through the line
    before the next group), suitable to import as a single memory.
    """

    title: str
    cwds: tuple[str, ...]
    body: str


def parse_codex_memory(text: str) -> list[CodexMemoryEntry]:
    """Split a Codex global-memory document into one entry per Task Group.

    Returns ``[]`` when the text has no ``# Task Group:`` headings (e.g. the
    ``memory_summary.md`` digest, which must not be fed here). Each group's
    ``cwds`` come from its single ``applies_to: cwd=...`` line (only the part
    before the first ``;`` is scanned, so ``reuse_rule`` text is never mistaken
    for a path); a group without that line yields an empty ``cwds`` tuple.
    """
    matches = list(_GROUP_RE.finditer(text))
    entries: list[CodexMemoryEntry] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[match.start() : end]
        title = match.group(1).strip()
        cwds: tuple[str, ...] = ()
        applies = _APPLIES_RE.search(block)
        if applies is not None:
            value = applies.group(1).split(";", 1)[0]
            cwds = tuple(_PATH_RE.findall(value))
        entries.append(CodexMemoryEntry(title=title, cwds=cwds, body=block.strip()))
    return entries


@dataclass(frozen=True)
class CodexSummaryTopic:
    """One bullet of ``memory_summary.md``'s ``## What's in Memory`` list.

    Codex's summary is the only place in either supported agent's memory where
    the source states, in its own voice, *what it would look this material up
    by*. The bullet reads::

        - <title>: `term`, `term`, `term`
          - desc: ...
          - learnings: ...

    ``title`` is everything before that backticked list; ``search_terms`` are
    the backticked tokens themselves, in the order written. The indented
    ``desc:`` / ``learnings:`` sub-bullets are deliberately not carried: they
    are Codex's second-order prose *about* a group whose own bullets the
    reader already reads out of ``MEMORY.md``, and this dataclass exists to
    rescue the terms, which have no other home.
    """

    title: str
    search_terms: tuple[str, ...]


def parse_codex_summary_topics(text: str) -> list[CodexSummaryTopic]:
    """The topic bullets of a summary document's ``## What's in Memory``.

    Returns ``[]`` for a document with no such section (a ``MEMORY.md``, say,
    which must not be fed here). Only *unindented* ``- `` lines are topics —
    the two-space-indented ``desc:`` / ``learnings:`` lines hang off a topic
    and are skipped — and the section is scanned under ``###``/``####``
    sub-headings without reading them, because those sub-headings are not
    dependable: they are usually the cwd and the date, but Codex also writes
    an ``### Older Memory Topics`` block whose ``####`` lines are cwds
    instead, and at least one heading on the maintainer's machine names a
    directory the topic's own ``desc:`` contradicts. Titles and terms are
    what this parse promises; routing is left to the caller, which has the
    task groups themselves to match against.

    A topic bullet stating no backticked term yields an empty
    ``search_terms`` rather than being dropped, so a caller can tell "Codex
    listed this group and named no terms" from "Codex never listed it".
    """
    topics: list[CodexSummaryTopic] = []
    for line in section_text(text, _TOPICS_HEADING).splitlines():
        if not line.startswith("- "):
            continue
        bullet = line[2:]
        split_at = bullet.find(_TOPIC_TERMS_SEP)
        if split_at < 0:
            topics.append(CodexSummaryTopic(title=bullet.strip(), search_terms=()))
            continue
        terms = tuple(term.strip() for term in _TERM_RE.findall(bullet[split_at:]))
        topics.append(
            CodexSummaryTopic(
                title=bullet[:split_at].strip(),
                search_terms=tuple(term for term in terms if term),
            )
        )
    return topics


def section_text(block: str, heading: str) -> str:
    """The raw text under a ``## <heading>`` line in ``block``, up to the next
    ``#`` or ``##`` heading (or the end of ``block``).

    Shared by both a Task Group's own body (``## Reusable knowledge`` and
    its sibling sections) and the global profile document's ``## User
    Profile`` / ``## User preferences`` — both use the identical
    ``## <heading>`` shape.
    """
    pattern = re.compile(
        rf"^## {re.escape(heading)}[ \t]*$(?P<body>.*?)(?=^#{{1,2}} |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(block)
    return match.group("body") if match else ""


def section_bullets(block: str, heading: str) -> list[str]:
    """The ``- `` bullets directly under a ``## <heading>`` section of ``block``."""
    bullets = []
    for line in section_text(block, heading).splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets


__all__ = [
    "CodexMemoryEntry",
    "CodexSummaryTopic",
    "parse_codex_memory",
    "parse_codex_summary_topics",
    "section_bullets",
    "section_text",
]
