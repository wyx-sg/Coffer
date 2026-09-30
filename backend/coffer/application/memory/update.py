"""Update memory: aggregate, then distil what the aggregation left new (spec memory
"Update memory in one action").

Aggregation and distillation are two passes over two directories, but a person has
one intent — "bring the notes up to date" — and either pass alone leaves the notes
stale: aggregation only fills ``.raw/``, and distil only reads what is already
there. So ``POST /api/v1/memory/sync`` and ``coffer memory sync`` run both, in that
order, and the web UI offers them as one **Update memory** button.

**Only partitions with undistilled raw entries are distilled.** An entry is
undistilled when no note's provenance and no ``RETIRED.md`` record names it (see
"Distil incrementally in two stages"); a partition holding none would get nothing
from a pass but a rewritten index, so it is not visited. That is also what makes
the answer useful: ``distilled`` names what actually changed. With no internal
connection the pass is the mechanical one (see "Distil mechanically with no internal
connection") — ``MemoryService.distil`` decides that, not this module.

**A partition already being distilled is skipped, not failed (see "Run one distil
pass per partition at a time").** The claim is the same upkeep-runs key, on the same
uid, that the unattended sweep takes, so whichever arrives first holds it. The
caller asked for *memory* to be updated, and the pass already running is doing that
very thing, so the partition is reported under ``skipped`` and the rest proceed.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.application.memory.aggregate import AggregationResult
from coffer.application.memory.distil import has_undistilled
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.application.upkeep_runs import UPKEEP_RUNS, UpkeepRunRegistry

#: The in-flight entry Update memory itself holds while it runs, beside the
#: per-partition claims (spec memory "Show Update memory's progress"). Not a
#: uid — uids are ULIDs — so it can never collide with a partition's claim.
#: It carries ``done``/``total`` over the partitions left to distil, which is
#: what "Distilling 2 of 5 partitions" reads; while it has none yet, the
#: action is still reading the agents' memory.
UPDATE_RUN = "update"


@dataclass(frozen=True)
class UpdateResult:
    """What one Update memory action did.

    ``distilled`` and ``skipped`` are partition **names** — what a person reads —
    in the order the partitions were visited, which is by name.
    """

    aggregation: AggregationResult
    #: Partitions that held undistilled raw entries and were distilled.
    distilled: tuple[str, ...]
    #: Partitions that held undistilled raw entries but whose distil pass was
    #: already running elsewhere; that pass covers them.
    skipped: tuple[str, ...]


async def update_memory(
    service: MemoryService,
    *,
    actor: str,
    runs: UpkeepRunRegistry = UPKEEP_RUNS,
) -> UpdateResult:
    """Aggregate every agent's memory, then distil each partition it left new.

    The partition list is read AFTER the aggregation, so a partition the pass
    has just created is distilled in the same action. A distil that raises
    propagates: the pass degrades a bad model answer to nothing rather than
    raising (see "Record what each distil pass did"), so an exception here is a
    fault the caller should see, not a busy partition.
    """
    async with runs.claimed(KIND_MEMORY, UPDATE_RUN) as tracked:
        aggregation = await service.aggregate(actor=actor)
        distilled: list[str] = []
        skipped: list[str] = []
        pending = [p for p in await service.list_partitions() if has_undistilled(p.name)]
        for done, partition in enumerate(pending):
            if tracked:
                runs.progress(KIND_MEMORY, UPDATE_RUN, done=done, total=len(pending))
            async with runs.claimed(KIND_MEMORY, partition.uid) as claimed:
                if not claimed:
                    skipped.append(partition.name)
                    continue
                await service.distil(partition.uid, actor=actor)
            distilled.append(partition.name)
    return UpdateResult(aggregation=aggregation, distilled=tuple(distilled), skipped=tuple(skipped))


__all__ = ["UPDATE_RUN", "UpdateResult", "update_memory"]
