"""What one remembered fact is, once it has been read out of an agent.

Every value here is **derived**: it came out of some agent's own memory and can
be produced again from it (spec memory FR-023). Nothing about a fact is stored
anywhere else, which is what makes the whole tree disposable — delete it, run
aggregation again, and the same facts come back.

:func:`origin_key` survives that disposability having once carried the
developer's hide/pin/supersede/settle decisions across a recomputation. Those
decisions are gone (the partition surface is a file tree now, with no per-fact
action to record), but the key stays: :attr:`Fact.key` is still how organise
names one fact from inside another's frontmatter, and it still has to mean the
same thing on the next pass.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

#: A fact about the person — a preference, a standing instruction. Lands in
#: ``global`` whichever project it was learned in (FR-012).
TYPE_USER = "user"
#: Guidance the developer gave about how to work. Also about the person.
TYPE_FEEDBACK = "feedback"
#: A fact about one project: a decision, a trap, a piece of its history.
TYPE_PROJECT = "project"

FACT_TYPES = frozenset({TYPE_USER, TYPE_FEEDBACK, TYPE_PROJECT})

#: Types that belong to the person rather than to any one project, and so are
#: filed in ``global`` regardless of where they were learned (FR-012).
PERSONAL_TYPES = frozenset({TYPE_USER, TYPE_FEEDBACK})

STATUS_ACTIVE = "active"
STATUS_SUPERSEDED = "superseded"


@dataclass(frozen=True)
class Origin:
    """Where a fact was read from, and when.

    Kept on every fact because "which agent already knows this" is half of
    what makes an aggregated view worth reading, and because it is the only
    way back to the source when a fact looks wrong.
    """

    #: The registered agent's resource name (e.g. ``claude-code``).
    agent: str
    #: Absolute path of the native file it was read out of.
    native_path: str
    #: Where inside that file — a heading, a bullet, or empty when the whole
    #: file is the fact. Part of the identity, so a file holding many facts
    #: yields many stable ones.
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

    Hashed rather than concatenated because it ends up in a database column
    and in file frontmatter, and an absolute path in either is noise that also
    leaks the shape of the user's disk into places it does not belong.
    """
    digest = hashlib.sha256("\x00".join((agent, native_path, anchor)).encode("utf-8"))
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class Fact:
    """One thing an agent learned, normalised out of its native memory."""

    #: Readable slug; also the file name inside the partition.
    slug: str
    title: str
    description: str
    #: One of :data:`FACT_TYPES`.
    type: str
    #: The source's own words. Never a paraphrase — summarising happens in the
    #: derived digest, so a fact stays quotable back to its origin (FR-021).
    body: str
    #: ``global`` or a project partition's slug.
    partition: str
    #: Every place this fact was seen. Two agents that learned the same thing
    #: produce one fact with two origins, not two facts (FR-022).
    origins: tuple[Origin, ...] = field(default_factory=tuple)
    status: str = STATUS_ACTIVE
    #: The ``key`` of the fact that replaced this one, when one did.
    superseded_by: str = ""
    #: Keys of facts this one disagrees with. Organise flags the pair when it
    #: cannot decide between them; nothing settles it afterwards, so the flag
    #: stands until a later pass has grounds to withdraw it (FR-033).
    conflicts_with: tuple[str, ...] = field(default_factory=tuple)

    @property
    def key(self) -> str:
        """How one fact names another across a recomputation (FR-022).

        The smallest origin key wins, so a fact that gains a second origin on
        a later pass keeps the identity it had — a merge must not silently
        move a ``superseded_by`` or ``conflicts_with`` reference off the fact
        it was written about.
        """
        return min((o.key for o in self.origins), default=origin_key("", self.slug, ""))
