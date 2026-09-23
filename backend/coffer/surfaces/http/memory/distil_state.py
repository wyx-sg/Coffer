"""The distil pass runner, held for the route and typed for the worker.

Mirrors ``surfaces/http/knowledge/tidy_state.py``: a setter the composition
root calls once and a getter the route depends on, so a pass can be started
from two places without either of them constructing it.

What the runner *is* changed with the redesign, and the change matters here.
The organise pass was a free function in the application layer, so this module
held a closure over the model port and the route made its own audit call
afterwards. Distil is a method on ``MemoryService`` — it needs the partition's
Resource row for the repository path the index restates, and it records
``memory_distilled`` itself with whichever actor asked for it. So the runner
below is ``MemoryService.distil``, bound, and a caller passes ``actor`` rather
than auditing on its own: a second record written at the route would put two
rows in the log for one pass, and they would disagree about the actor the
moment the scheduled sweep ran.

The ``actor`` keyword is the whole reason this is a Protocol rather than a
``Callable`` alias. The worker in ``memory_wiring.start_distil_worker`` passes
``distil_worker.WORKER_ACTOR`` and the route passes the requesting actor, which
is what lets the audit log tell an unattended distillation apart from one a
person asked for ("Audit every lifecycle act").
"""

from __future__ import annotations

from typing import Protocol

from coffer.application.memory.distil import DistilResult


class DistilRunner(Protocol):
    """One partition through the distil pass, attributed to an actor.

    Structural, so ``MemoryService.distil`` satisfies it with no adapter and a
    test can substitute a plain async function.

    The partition is named by its **uid**, not by its label. A pass spends a
    model and rewrites every note in a directory, so what it is aimed at has to
    be the thing that cannot be edited while it runs (ADR
    resource-identity-is-an-immutable-uid); the service resolves the row and
    reads the directory name off it. It is also what makes the route's
    upkeep-runs claim and the worker's claim collide the way "Run one distil
    pass per partition at a time" needs them to — both key on this same value,
    with neither translating.
    """

    async def __call__(self, uid: str, *, actor: str = ...) -> DistilResult: ...


_distil_runner: DistilRunner | None = None


def set_distil_runner(runner: DistilRunner) -> None:
    """Called by the composition root once on startup."""
    global _distil_runner
    _distil_runner = runner


def get_distil_runner() -> DistilRunner:
    """FastAPI Depends() target."""
    if _distil_runner is None:
        raise RuntimeError("distil runner not initialised")
    return _distil_runner


__all__ = ["DistilRunner", "get_distil_runner", "set_distil_runner"]
