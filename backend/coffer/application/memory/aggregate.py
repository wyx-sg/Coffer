"""The aggregation pass: the agents' own words, filed by repository.

This is the **input** half of the layer. It reads each registered, enabled
agent's native memory through that agent's reader, decides which partition
each entry belongs to, and writes the entry **verbatim** under that
partition's hidden ``.raw/``. It writes nothing else — no note, no index, no
retirement record — because those three belong to the distil pass, and the
one-writer-per-directory split is what makes "Keep distil out of the raw
directory" checkable by reading call sites rather than by trusting a comment.

``MemoryService`` (``service.py``) keeps the parts that need a database: which
agents are registered, which partitions already have a Resource row, and the
audit event. Everything here takes plain values and touches only the derived
tree, so the tricky parts — which repository a directory resolves to, and what
a second read of a changed source does to what the first wrote — are exercised
with a temp directory and no database at all.

Three decisions live here, and each one is a named past failure:

- **A partition is keyed on a repository, never on a working directory**
  (:class:`_Placer`). A worktree, a second clone and the main checkout are one
  repository and therefore one partition (see "Identify a partition by its repository").
- **A directory inside no repository files into ``global``'s ``.raw/``**
  (see "Create no partition for a non-repository directory"). It creates no partition of
  its own, and the distil pass judges the entry on its merits — keeping it in ``global``
  or keeping nothing. Six of sixteen partitions on the maintainer's live vault were
  dated scratch folders that the previous design turned into permanent partitions,
  holding material that could never reach the repository it was actually about.
- **Nothing here merges two agents' entries.** ``merge_duplicates`` used to
  live in this module and matched two facts on an identical normalised body or
  an identical ``(type, partition, title)``. Measured on 378 real facts from
  two agents it produced **zero** merges, because two agents never phrase
  anything the same way — so the merge moved to the distil pass, where it is a
  judgement about *meaning* made by a model (see "Record provenance and merge by
  meaning"). There is deliberately no literal comparison left here to be tempted to
  widen. There are no slugs either: a file name belongs to a note, and a note is written
  one layer up. A raw entry's file name is the origin key ``StoredRawEntry`` derives
  from the triple that identifies it, so a second pass over an unchanged source
  overwrites one file rather than accumulating a near-duplicate (see "Let only
  aggregation write raw entries").
"""

from __future__ import annotations

import os
import pathlib
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from coffer.domain.memory.errors import UnreadableMemory
from coffer.domain.memory.note import PERSONAL_TYPES
from coffer.domain.memory.partition import GLOBAL_PARTITION, disambiguate, partition_slug
from coffer.domain.memory.reader import MemoryReader, RawEntry
from coffer.domain.resource import Resource
from coffer.infrastructure.memory import raw_store, source_state, store
from coffer.infrastructure.memory.raw_store import StoredRawEntry
from coffer.infrastructure.memory.repository import Repository, resolve_repository

# ----- results (returned to callers of MemoryService.aggregate) -----------


@dataclass(frozen=True)
class SourceFailure:
    """One reader's ``UnreadableMemory`` for one source, isolated."""

    agent: str
    path: str
    reason: str


@dataclass(frozen=True)
class AggregationResult:
    """What one pass did, in the shape ``AggregationResultOut`` publishes.

    ``entries_written`` counts raw entries, not notes: aggregation writes no
    note at all (see "Keep raw entries verbatim and hidden"). A pass over an idle
    machine writes zero and skips every source, which is the steady state rather than a
    sign of trouble.
    """

    partitions: tuple[str, ...]
    entries_written: int
    sources_read: int
    sources_skipped: int
    failures: tuple[SourceFailure, ...]


# ----- the agent-kind seam --------------------------------------------------


@dataclass(frozen=True)
class AgentSource:
    """A registered, enabled agent Resource, reduced to what aggregation
    needs: its own resource name (an ``Origin.agent``), which reader applies
    to it, and the directory to hand that reader.

    Built by a resolver the composition root injects (mirroring
    ``SkillService``'s ``AgentSkillDirResolver``) so this package never reaches
    into the agent kind's own service — the cross-kind coupling Contracts
    5/5b/5c/5d fence every other kind off from.
    """

    agent: str
    agent_type: str
    config_dir: str


#: Given an ``agent``-kind Resource, return what aggregation needs from it.
AgentSourceResolver = Callable[[Resource], AgentSource]


# ----- partitions ------------------------------------------------------------


@dataclass(frozen=True)
class Placement:
    """One partition, by the only three things that identify it (see "Identify a
    partition by its repository").

    The same value serves as input and as output: the caller seeds a pass with
    the partitions that already have a Resource row, and the pass hands back
    the ones it filed into — including the repository it resolved, which the
    caller records on the row so a later session's ``cwd`` can be matched
    against it without re-walking a disk. ``global`` is the one placement with
    neither a key nor a path: it is not a repository, and nothing resolves *to*
    it by matching a directory.
    """

    name: str
    repository_key: str = ""
    repository_path: str = ""


GLOBAL_PLACEMENT = Placement(name=GLOBAL_PARTITION)


@dataclass(frozen=True)
class PartitionTouch:
    """A partition this pass wrote into, and the repository it resolved to.

    It used to carry the agents whose memory the partition came from as well,
    for one consumer: ``MemoryService._register_partition`` seeded the row's
    per-agent scope with them. That scope is gone — a partition aggregated
    from one agent was thereby hidden from every other one, which is the
    opposite of what a shared memory layer is for — and with it the only
    reason this pass ever tracked *whose* entry landed where. Nothing else
    read the field, so it is not computed any more rather than computed and
    ignored.
    """

    placement: Placement


@dataclass(frozen=True)
class AggregationOutcome:
    """The pass's own result plus what the caller must persist for it.

    Split in two because registering a Resource is a database write and this
    module has none: the pass reports which partitions it filed into and what
    repository each resolved to, and ``MemoryService`` turns that into
    registrations and config updates.
    """

    result: AggregationResult
    touched: tuple[PartitionTouch, ...]


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _home_dir() -> str:
    """The developer's home directory, by the same rule ``paths.py`` uses.

    An entry whose project root IS this directory is about the person, not a
    project, and files into ``global`` whatever its type says (see "File personal entries
    into global").
    """
    return str(pathlib.Path(os.environ.get("HOME", "~")).expanduser()).rstrip("/")


def _source_failure(agent: str, path: str, exc: Exception) -> SourceFailure:
    """One source's failure, whatever shape it took.

    A reader is meant to raise ``UnreadableMemory`` for a file it cannot
    parse, but a reader has bugs like any code, and the isolation "Fail a
    broken reader loudly and in isolation" asks for is only worth anything if it holds
    for the failure nobody anticipated: one file that trips a reader must cost that
    file, not the whole pass.
    """
    if isinstance(exc, UnreadableMemory):
        return SourceFailure(agent=agent, path=exc.path, reason=exc.reason)
    return SourceFailure(agent=agent, path=path, reason=f"{type(exc).__name__}: {exc}")


class _Placer:
    """Decides which partition one raw entry files into, and names a new one.

    Held across a whole pass rather than recomputed per entry for two reasons.
    The cheap one: resolving a repository walks a directory tree and reads a
    ``.git/config``, and one agent's memory names the same handful of working
    directories hundreds of times. The load-bearing one: a name minted for a
    repository this pass has not seen before must not be minted twice, so the
    set of claimed names has to outlive a single entry.
    """

    def __init__(self, known: Sequence[Placement]) -> None:
        self._by_key = {p.repository_key: p for p in known if p.repository_key}
        self._claimed = {p.name for p in known} | {GLOBAL_PARTITION}
        self._by_directory: dict[str, Placement] = {}
        self._home = _home_dir()

    def place(self, entry: RawEntry) -> Placement:
        """Where ``entry`` belongs (see "File personal entries into global" and "Create no
        partition for a non-repository directory").

        Three routes to ``global``, and they are different rules that happen to
        agree: an entry **about the person** goes there whichever repository it
        was learned in; an entry with no working directory has nothing else to
        say; and an entry learned in a directory inside no repository goes there
        too — into ``global``'s ``.raw/``, creating no partition, for the distil
        pass to keep or discard on its merits.
        """
        if entry.type in PERSONAL_TYPES:
            return GLOBAL_PLACEMENT
        directory = (entry.project_root or "").rstrip("/")
        if not directory or directory == self._home:
            return GLOBAL_PLACEMENT
        cached = self._by_directory.get(directory)
        if cached is None:
            cached = self._resolve(directory)
            self._by_directory[directory] = cached
        return cached

    def _resolve(self, directory: str) -> Placement:
        repository = resolve_repository(directory)
        if repository is None or not repository.key:
            return GLOBAL_PLACEMENT
        known = self._by_key.get(repository.key)
        if known is not None:
            return known
        placement = self._mint(repository)
        self._by_key[repository.key] = placement
        self._claimed.add(placement.name)
        return placement

    def _mint(self, repository: Repository) -> Placement:
        """A placement for a repository no partition answers for yet.

        The name is the repository's own, readably — never an id, which is the
        failure that got the previous per-project store removed: nobody could
        tell which project a ``project-<ULID>`` store belonged to. Two
        repositories that share a directory name are told apart by prefixing a
        parent segment (``work-api`` vs ``personal-api``), not by a number.

        Preferring the *remote's* last segment over the local directory's is
        what keeps two clones under different local names from racing to create
        two partitions that ``repository_key`` would then insist are one.
        """
        base = partition_slug(repository.name or repository.root)
        name = (
            disambiguate(repository.root, frozenset(self._claimed))
            if base in self._claimed
            else base
        )
        return Placement(name=name, repository_key=repository.key, repository_path=repository.root)


def _entries_by_source() -> dict[str, tuple[StoredRawEntry, ...]]:
    """Every raw entry already on disk, grouped by the native file it came from.

    Two questions are answered from this one read, and they are the two halves
    of the layer's only real trap ("Keep the memory tree derived and local"): *may this source be
    skipped* — only if its digest matches **and** the entries it produced are
    still here — and *what did a re-read of it stop producing*, which is
    whatever is here and is not written again: a bullet the agent deleted from
    its own memory, or an entry that now resolves to a different partition.

    Reading every entry back parses every file under every ``.raw/``: the
    honest cost of keeping the answer on disk rather than in a table this layer
    is forbidden to add (see "Add no table of its own"), over files that are small and local.
    """
    found: dict[str, list[StoredRawEntry]] = defaultdict(list)
    for partition in store.list_partitions():
        for stored in raw_store.list_raw_entries(partition):
            found[stored.native_path].append(stored)
    return {path: tuple(entries) for path, entries in found.items()}


def run_aggregation(
    *,
    agents: Sequence[AgentSource],
    readers: Mapping[str, MemoryReader],
    known: Sequence[Placement],
    now: Callable[[], str] = _utc_now,
) -> AggregationOutcome:
    """One pass over every agent handed in, writing only ``.raw/``.

    **The skip is never taken on a digest alone.** ``source_state`` records
    what each native file hashed to last pass, and a match says the *source*
    has not changed — it does not say the entries that source produced are
    still on disk. "Keep the memory tree derived and local" requires that deleting the
    memory tree and re-syncing rebuilds it *with that cache deliberately left behind*,
    so the match is combined with the presence of the entries themselves; a source whose
    entries are gone is read again however familiar its hash looks. A source that
    legitimately yields no entries is therefore re-read every pass, which costs one
    parse of a file that says nothing.

    **A source that will not parse leaves everything it produced standing**
    (see "Fail a broken reader loudly and in isolation"). Its digest is deliberately not
    recorded either, so the next pass tries again rather than treating the broken format
    as the new normal, and nothing it wrote is pruned — a reader that breaks on an
    agent's format change must not empty that agent's contribution.

    **No partition is ever deleted here.** One whose repository is gone is
    surfaced as unresolvable for the developer to decide about (see "Report unresolvable
    partitions"), and one whose sources fell silent still holds notes the distil pass
    wrote: deleting a partition on the strength of one quiet pass is how a de-registered
    agent would take a repository's whole memory with it.
    """
    placer = _Placer(known)
    standing_by_source = _entries_by_source()
    old_state = source_state.load()
    new_state: dict[str, str] = {}
    failures: list[SourceFailure] = []
    # Doubles as the set of partitions this pass filed into: every raw entry
    # written records its placement here, so the keys are exactly the touched
    # partitions. A separate ``touched`` map used to sit beside it, keyed the
    # same way but holding the contributing agents' names — the seed for a
    # per-agent scope that no longer exists.
    placements: dict[str, Placement] = {}
    sources_read = 0
    sources_skipped = 0
    entries_written = 0

    for agent_source in agents:
        reader = readers.get(agent_source.agent_type)
        if reader is None:
            continue  # no reader for this agent type: silent
        for source in reader.sources(agent_source.config_dir):
            standing = standing_by_source.get(source.path, ())
            if old_state.get(source.path) == source.digest and standing:
                sources_skipped += 1
                new_state[source.path] = source.digest
                continue

            try:
                entries = reader.read(source)
            except Exception as exc:
                failures.append(_source_failure(agent_source.agent, source.path, exc))
                continue

            sources_read += 1
            new_state[source.path] = source.digest
            captured_at = now()
            written: set[tuple[str, str]] = set()
            for entry in entries:
                placement = placer.place(entry)
                stored = StoredRawEntry(
                    partition=placement.name,
                    agent=agent_source.agent,
                    native_path=source.path,
                    captured_at=captured_at,
                    entry=entry,
                )
                raw_store.write_raw_entry(stored)
                entries_written += 1
                written.add((stored.partition, stored.entry_id))
                placements[placement.name] = placement

            for stale in standing:
                if (stale.partition, stale.entry_id) not in written:
                    raw_store.delete_raw_entry(stale.partition, stale.entry_id)

    source_state.save(new_state)
    return AggregationOutcome(
        result=AggregationResult(
            partitions=tuple(sorted(placements)),
            entries_written=entries_written,
            sources_read=sources_read,
            sources_skipped=sources_skipped,
            failures=tuple(failures),
        ),
        touched=tuple(PartitionTouch(placement=placements[name]) for name in sorted(placements)),
    )


__all__ = [
    "GLOBAL_PLACEMENT",
    "AgentSource",
    "AgentSourceResolver",
    "AggregationOutcome",
    "AggregationResult",
    "PartitionTouch",
    "Placement",
    "SourceFailure",
    "run_aggregation",
]
