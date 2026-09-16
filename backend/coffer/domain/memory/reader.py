"""The port every native-memory reader implements (spec memory FR-004).

Two agents, two undocumented private formats, one shape: list the source
files under an agent's own `config_dir` without opening them (`sources`),
then parse one of those files into the facts it holds (`read`). Splitting the
two lets the caller hash a file cheaply to decide whether it changed
(FR-006) before paying to parse it.

Everything here is a plain value or a `Protocol` — no filesystem access, no
YAML, no agent-specific knowledge. The two adapters that actually walk a
disk live in `coffer.infrastructure.memory.readers`; this module is what they
both promise to satisfy, and what the aggregation pass composes against
instead of a concrete reader class (so a third agent, when one earns the
abstraction per FR-037, is one more adapter, not a change here).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SourceFile:
    """One native memory file, cheap to compare across syncs.

    `digest` is a content hash, not a size or an mtime, because a native tool
    may rewrite a file with the same bytes at a new mtime (or vice versa on a
    filesystem with coarse mtime resolution) — FR-006's skip-unchanged check
    needs to survive either.
    """

    #: Absolute path of the native file.
    path: str
    #: Content hash, so aggregation can skip a file whose content is unchanged
    #: since the last pass (FR-006) without re-parsing it.
    digest: str


@dataclass(frozen=True)
class RawFact:
    """One fact as a reader first sees it, before it becomes a domain `Fact`.

    This is deliberately thinner than `coffer.domain.memory.fact.Fact`: it
    carries no origin, status or supersession — those are the aggregator's
    job to attach once it knows which partition the fact lands in and what
    else already lives there. A reader only ever answers "what does this one
    source file say", nothing about how it relates to any other fact.
    """

    #: Short human title. From the source's own words when it has one
    #: (Claude Code's frontmatter `name`); otherwise derived defensibly by the
    #: reader, which documents the choice where it makes it.
    title: str
    #: Longer human description, same provenance rule as `title`.
    description: str
    #: One of `coffer.domain.memory.fact.FACT_TYPES`.
    type: str
    #: The source's own words, verbatim (FR-014) — never a paraphrase, so the
    #: fact stays quotable back to where it came from.
    body: str
    #: Where inside the source file this fact lives — a heading, a bullet's
    #: content hash, or empty when the whole file is the fact. Half of the
    #: stable identity FR-015 needs; the reader is responsible for it being
    #: the same string on a second, unchanged read.
    anchor: str
    #: Absolute project root this fact was learned in, or "" when the fact is
    #: about the person rather than any one project (a Codex profile, or a
    #: task group with no recorded `cwd`).
    project_root: str
    #: The source's own timestamp for this fact, when it records one at all.
    source_written_at: str = ""


class MemoryReader(Protocol):
    """What one agent's native-memory adapter must provide."""

    #: `"claude_code"` or `"codex"` — matches the registered agent's type, so
    #: the aggregator knows which reader to hand which `config_dir`.
    agent_type: str

    def sources(self, config_dir: str) -> tuple[SourceFile, ...]:
        """List this agent's native memory files under `config_dir`.

        Must not raise for one unreadable file — skip it and keep listing the
        rest (a directory-listing failure is a filesystem problem, not a
        format problem, and FR-005's isolation still applies: one bad path
        must not blank the whole list).
        """
        ...

    def read(self, source: SourceFile) -> tuple[RawFact, ...]:
        """Parse one source file into the facts it holds.

        Raises `coffer.domain.memory.errors.UnreadableMemory` — never returns
        a partial tuple — when the file cannot be parsed (FR-005): the caller
        is expected to catch it per file, record the reason, and carry on
        with everything else.
        """
        ...
