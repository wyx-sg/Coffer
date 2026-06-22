"""Parser for Codex's global native-memory file (``~/.codex/memories/MEMORY.md``).

Unlike Claude Code's per-project ``memory/*.md`` fact files, Codex keeps a single
*global* memory document organised as ``# Task Group:`` blocks. Each group carries
exactly one ``applies_to: cwd=<paths>; reuse_rule=...`` line whose ``cwd`` value
routes the group to one or more project working directories (the value may list
several paths joined by prose like `` and ``/`` plus ``/`` from ``, and may contain
``~`` or ``*``). This module is pure text logic — turning the document into one
:class:`CodexMemoryEntry` per group; the infrastructure layer reads the file,
groups entries by cwd into stores, and routes imports per project.
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


__all__ = ["CodexMemoryEntry", "parse_codex_memory"]
