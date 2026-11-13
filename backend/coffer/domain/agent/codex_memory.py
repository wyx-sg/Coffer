"""Parsers for Codex's native memory files.

``memories/MEMORY.md`` is a single *global* document organised as
``# Task Group:`` blocks. Each group carries one ``applies_to: cwd=<paths>;
reuse_rule=...`` line whose ``cwd`` value routes the group to one or more
project working directories (the value may list several paths joined by
prose, and may contain ``~`` or ``*``). :func:`parse_codex_memory` turns the
document into one :class:`CodexMemoryEntry` per group; the agent page's
native-memory listing (``infrastructure.agent.codex_memory_store``) groups
them by cwd.

``memories_v2/memory_summary.md`` lists what Codex holds as topic bullets
under ``## What's in Memory`` (:func:`parse_codex_v2_topics`); the agent page
lists them, and the memory sync's reader
(``infrastructure.memory.readers.codex``) publishes each as one memory.

Pure text logic: this module only knows Codex's file *format*.
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
# Prose punctuation a path token can pick up at its end: "(work in /a/b)." gives
# "/a/b)." and the path is "/a/b".
_PATH_TRAIL = ").:'\"`]"

# The summary section listing one bullet per topic.
_TOPICS_HEADING = "What's in Memory"


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
            cwds = tuple(
                path for path in (p.rstrip(_PATH_TRAIL) for p in _PATH_RE.findall(value)) if path
            )
        entries.append(CodexMemoryEntry(title=title, cwds=cwds, body=block.strip()))
    return entries


#: The ``###`` heading Codex's v2 summary files older topics under; below it
#: the ``####`` lines are project scopes rather than dates.
_V2_OLDER_HEADING = "Older Memory Topics"
# A v2 topic bullet: an optional ``rollout_summaries/<file>`` pointer, a dash,
# then the sentence, and an optional trailing ``; thread_id=<id>``.
_V2_POINTER_RE = re.compile(
    r"^rollout_summaries/(?P<file>[^\s/]+\.md)\s+[\u2014\u2013-]+\s+(?P<rest>.*)$"
)
_V2_THREAD_RE = re.compile(r";?\s*thread_id=(?P<id>[^\s;]+)\s*$")


@dataclass(frozen=True)
class CodexV2Topic:
    """One bullet of a v2 ``memory_summary.md``'s ``## What's in Memory``.

    Codex's v2 memory (``~/.codex/memories_v2/``) has no ``MEMORY.md``: the
    summary is the whole consolidated memory, and each piece of project work is
    one bullet under ``### <project scope>`` and ``#### <date>``::

        - rollout_summaries/<file> — <sentence>; thread_id=<id>
          - <label>: <pointer>

    The scope is a name Codex chose ("Account Jira delivery"), not a path; the
    working directory is only in the pointed-to summary's header, which
    ``infrastructure.agent_files.codex_rollout_summaries`` reads. Under
    ``### Older Memory Topics`` the ``####`` line is the scope and there is no
    date."""

    scope: str
    date: str
    #: The ``rollout_summaries/`` file name, or ``""`` when none is given.
    rollout_file: str
    #: The sentence, without the pointer and the thread id.
    text: str
    #: The bullet as written, with its indented details.
    body: str


def parse_codex_v2_topics(text: str) -> list[CodexV2Topic]:
    """The topic bullets of a v2 summary's ``## What's in Memory``."""
    topics: list[CodexV2Topic] = []
    h3 = h4 = ""
    current: list[str] = []
    meta: tuple[str, str, str, str] | None = None

    def flush() -> None:
        if meta is not None:
            scope, date, file, sentence = meta
            topics.append(CodexV2Topic(scope, date, file, sentence, "\n".join(current).strip()))

    for line in section_text(text, _TOPICS_HEADING).splitlines():
        if line.startswith("### "):
            flush()
            meta, current = None, []
            h3, h4 = line[4:].strip(), ""
            continue
        if line.startswith("#### "):
            flush()
            meta, current = None, []
            h4 = line[5:].strip()
            continue
        if line.startswith("- "):
            flush()
            bullet = line[2:].strip()
            file = ""
            pointer = _V2_POINTER_RE.match(bullet)
            if pointer is not None:
                file, bullet = pointer.group("file"), pointer.group("rest")
            sentence = _V2_THREAD_RE.sub("", bullet).strip()
            older = h3 == _V2_OLDER_HEADING
            meta = (h4 if older else h3, "" if older else h4, file, sentence)
            current = [line]
            continue
        if meta is not None and line.strip():
            current.append(line)
    flush()
    return [t for t in topics if t.text]


def section_text(block: str, heading: str) -> str:
    """The raw text under a ``## <heading>`` line in ``block``, up to the next
    ``#`` or ``##`` heading (or the end of ``block``).

    """
    pattern = re.compile(
        rf"^## {re.escape(heading)}[ \t]*$(?P<body>.*?)(?=^#{{1,2}} |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(block)
    return match.group("body") if match else ""


__all__ = [
    "CodexMemoryEntry",
    "CodexV2Topic",
    "parse_codex_memory",
    "parse_codex_v2_topics",
    "section_text",
]
