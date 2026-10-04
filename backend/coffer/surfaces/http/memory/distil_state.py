"""The distil pass runner's type, for the worker that sweeps with it.

Distil is a method on ``MemoryService`` — it needs the partition's
Resource row for the repository path the index restates, and it records
``memory_distilled`` itself with whichever actor asked for it. So the runner
below is ``MemoryService.distil``, bound, and a caller passes ``actor`` rather
than auditing on its own: a second record written by the caller would put two
rows in the log for one pass, and they would disagree about the actor the
moment the scheduled sweep ran.

The ``actor`` keyword is the whole reason this is a Protocol rather than a
``Callable`` alias. The worker in ``memory_wiring.start_distil_worker`` passes
``distil_worker.WORKER_ACTOR``, and Update memory calls ``MemoryService.distil``
with the requesting actor, which is what lets the audit log tell an unattended
distillation apart from one a person asked for ("Audit every lifecycle act").
"""

from __future__ import annotations

from typing import Protocol

from coffer.application.memory.distil import DistilResult


class DistilRunner(Protocol):
    """One partition through the distil pass, attributed to an actor.

    Structural, so ``MemoryService.distil`` satisfies it with no adapter and a
    test can substitute a plain async function.

    The partition is named by its **uid**, not by its label. A pass rewrites
    the notes and index of a directory, so what it is aimed at has to
    be the thing that cannot be edited while it runs (ADR
    identity-is-the-uid-inside-the-file); the service resolves the row and
    reads the directory name off it. It is also what makes Update memory's
    upkeep-runs claim and the worker's claim collide the way "Run one distil
    pass per partition at a time" needs them to — both key on this same value,
    with neither translating.
    """

    async def __call__(self, uid: str, *, actor: str = ...) -> DistilResult: ...


__all__ = ["DistilRunner"]
