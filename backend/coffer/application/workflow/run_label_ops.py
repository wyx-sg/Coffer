"""Rewriting what a run is CALLED and what it is for (spec workflow "Edit a
run's title and description as labels").

Split out of ``WorkflowRunService`` to keep that module under its line ceiling,
the way the resource lifecycle splits ``scope``, ``delete`` and ``rename`` out
of its own front door.

It is the only edit of a run that is not a command. Everything else there moves
the run and is folded from its log; this writes a label and appends nothing,
which is exactly why it reads differently from its neighbours and belongs in a
file that can say so.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.workflow.ports import RunRow
from coffer.domain.workflow.errors import RunLabelInvalid

if TYPE_CHECKING:  # pragma: no cover - a cycle at runtime, types only
    from coffer.application.workflow.run_service import WorkflowRunService


class KeepStored:
    """ "The caller said nothing about this field."

    Distinct from ``None``, which says "clear it". A partial edit needs both
    answers and ``None`` can only carry one of them — the bug that shape
    produces is a field silently erased by a request that never mentioned it.
    """


KEEP = KeepStored()


async def relabel_run(
    service: WorkflowRunService,
    run_id: str,
    *,
    title: str,
    description: str | KeepStored | None = KEEP,
) -> RunRow:
    """Rewrite what this run is CALLED and what it is for (spec workflow
    "Edit a run's title and description as labels").

    Not a signal and not a command: it advances nothing, takes no version
    and appends no event. A run's status, stage and position are folded
    from its log and only the engine writes them ("Rebuild a run from its
    event log"); its title is a label the developer typed at the moment
    they knew least about the work, and a label that cannot be corrected
    makes a list of forty runs unreadable.

    Still guarded by ownership ("Advance a run only on the machine that
    owns it"): a run this machine does not advance is read-only here, and
    that includes its label — otherwise two machines could disagree about
    what the same run is called with nothing to reconcile them.
    """
    run = await service._cmd.require_run(run_id)
    service._cmd.guard(run, "relabel", None)
    clean = title.strip()
    if not clean:
        raise RunLabelInvalid("a run's title must not be empty")
    # ``KEEP`` and ``None`` are different answers: one is "the caller said
    # nothing about the description", the other is "clear it". Collapsing
    # them would make a title-only edit erase the words someone wrote about
    # this delivery a week ago.
    words = run.description if isinstance(description, KeepStored) else (description or None)
    updated = await service._runs.set_label(run_id, title=clean, description=words)
    # ``require_run`` just resolved it, so a miss here means it was deleted
    # between the two reads — the run the caller asked about is gone.
    return updated if updated is not None else run
