"""What one note is — Coffer's own unit of memory.

Spec memory "Store each note as one Markdown file with frontmatter" and "Write
notes in Coffer's own words".

A note is **Coffer's writing**, not an agent's. It is distilled from one or
more raw entries read out of the agents' native memories, covers one topic,
and is rewritten in place as later material arrives ("Keep one topic per
note"). That is the
whole of the reversal recorded in
[Aggregate Agent Memory](../../../docs/decisions/aggregate-agent-memory-never-write-it.md):
the previous design stored the sources' own words, which meant Codex's
untitled prose bullets arrived as 284 entries whose title, description and
body were one sentence three times over — against the 16 entries Codex's own
index had already distilled the same material into.

Verbatim survives one layer down. Every note names the raw entries it was
built from (:class:`Origin`), and those live under the partition's ``.raw/``
exactly as they were read, so a note's claim is still traceable to an agent's
own file even though the note does not quote it.

Everything here is still **derived** ("Keep the memory tree derived and
local"): delete the tree, run
aggregation and distil again, and an equivalent set comes back — the same
subjects from the same sources, not necessarily the same wording, because the
product is a distillation rather than a copy.

There is no status field and no ``superseded_by``. A note that a later one
contradicts does not sit here marked dead: it leaves ``notes/`` and is
recorded in ``RETIRED.md`` (:mod:`coffer.domain.memory.retired`), which is
what makes the removal survive the next pass.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

#: Something about the person — a preference, a fact about who they are. Lands
#: in ``global`` whichever repository it was learned in ("File personal entries
#: into global").
TYPE_USER = "user"
#: Guidance the developer gave about how to work. Filed by where it was learned,
#: like a project entry: given in a repository it binds that repository, and
#: only without one does it land in ``global``.
TYPE_FEEDBACK = "feedback"
#: Something about one repository: a decision, a trap, a piece of its history.
TYPE_PROJECT = "project"

NOTE_TYPES = frozenset({TYPE_USER, TYPE_FEEDBACK, TYPE_PROJECT})

#: Types that belong to the person rather than to any one repository, and so
#: are filed in ``global`` regardless of where they were learned. ``feedback``
#: is deliberately not among them: a standing instruction given inside a
#: repository ("run the gates before pushing here") is that repository's, and
#: filing it globally would hand it to every other project's sessions.
PERSONAL_TYPES = frozenset({TYPE_USER})


@dataclass(frozen=True)
class Origin:
    """One raw entry a note was built from, and where it came from.

    This is the note's provenance ("Record provenance and merge by meaning").
    It answers two questions that are
    both load-bearing: *which of my agents already knows this*, which is half
    of what makes an aggregated view worth reading at all, and *where do I go
    to check*, since the note is Coffer's paraphrase and the entry under
    ``.raw/`` is not.
    """

    #: The registered agent's resource name (e.g. ``claude-code``).
    agent: str
    #: Absolute path of the native file it was read out of.
    native_path: str
    #: Where inside that file — a heading, a bullet's content hash, or empty
    #: when the whole file is the entry. Part of the stable identity, so a
    #: file holding many entries yields many stable ones.
    anchor: str = ""
    #: When Coffer read it.
    captured_at: str = ""
    #: When the source itself says it was written, when it says at all.
    source_written_at: str = ""

    @property
    def key(self) -> str:
        return origin_key(self.agent, self.native_path, self.anchor)


def origin_key(agent: str, native_path: str, anchor: str) -> str:
    """A short, stable id for one (agent, file, anchor) triple.

    Hashed rather than concatenated because it ends up in file frontmatter,
    and an absolute path there is noise that also leaks the shape of the
    user's disk into a file the user shares with nobody but reads often.
    """
    digest = hashlib.sha256("\x00".join((agent, native_path, anchor)).encode("utf-8"))
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class Note:
    """One topic, written by Coffer, filed in one partition."""

    #: Readable slug; also the file name inside the partition's ``notes/``.
    slug: str
    title: str
    #: One line, written to be read on its own: it *is* the index entry, and
    #: the index is what a session is actually given ("Write each index line
    #: to stand on its own").
    description: str
    #: One of :data:`NOTE_TYPES`.
    type: str
    #: Coffer's own prose. Not a quote of any source — the sources
    #: are reachable through :attr:`origins` and ``.raw/``.
    body: str
    #: ``global`` or a repository partition's slug.
    partition: str
    #: Every raw entry this note was built from. Two agents that recorded the
    #: same lesson in different words produce **one** note naming both —
    #: a judgement the distil pass makes on meaning, because a literal
    #: comparison of two agents' prose matches nothing.
    origins: tuple[Origin, ...] = field(default_factory=tuple)
    created_at: str = ""
    updated_at: str = ""
    #: Search terms the source supplied for this material, when it did —
    #: Codex states them per task group, and the index line repeats them so
    #: the next agent does not have to guess a word ("Write each index line to
    #: stand on its own").
    search_terms: tuple[str, ...] = field(default_factory=tuple)

    @property
    def key(self) -> str:
        """How one note is named from outside its own file.

        The smallest origin key wins, so a note that gains a second origin on
        a later pass keeps the identity it had — a merge must not silently
        move a reference off the note it was written about.
        """
        return min((o.key for o in self.origins), default=origin_key("", self.slug, ""))

    @property
    def agents(self) -> tuple[str, ...]:
        """The distinct agents behind this note, in first-seen order."""
        seen: list[str] = []
        for origin in self.origins:
            if origin.agent and origin.agent not in seen:
                seen.append(origin.agent)
        return tuple(seen)


__all__ = [
    "NOTE_TYPES",
    "PERSONAL_TYPES",
    "TYPE_FEEDBACK",
    "TYPE_PROJECT",
    "TYPE_USER",
    "Note",
    "Origin",
    "origin_key",
]
