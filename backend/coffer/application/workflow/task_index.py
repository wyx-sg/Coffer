"""What the run has done so far, as the next task reads it (FR-029, FR-031).

A task opens with an **index**, not with anybody's conversation. One line per
task that ran before it — what it was, what became of it, and the path of each
file it produced — and the task opens what it needs from those paths.

The alternative was carrying the earlier tasks' transcripts forward, and it was
tried. It does not survive a real delivery: the opening message then grows with
every task that preceded it, so the fortieth task of a run cannot start at all,
and summarising the oldest of them only moves the ceiling. An index costs one
line per task however long the run gets, and a task that wants the detail is
one ``read`` away from it.

Two rules the index answers to, both of them about not lying by omission:

* **A task that produced nothing is still in the index.** Failed, skipped, or
  never reached — it appears, with what became of it. A task missing from the
  index reads as a task that never existed, and the next one then works from a
  hole it cannot see.
* **What is named is what is on disk.** The artifact rows come from the
  artifact store, never from a list something maintained, so a file deleted
  between two tasks stops being promised rather than being promised falsely.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from coffer.application.workflow.context_budget import (
    INDEX_SHARE,
    estimate_tokens,
    share_of,
)
from coffer.application.workflow.ports import ArtifactEntry

__all__ = [
    "EarlierTask",
    "EarlierTasksPort",
    "render_index",
]

#: ``ArtifactEntry.path`` is relative to the run's ``artifacts/`` directory;
#: the index quotes it relative to the run directory, which is what every other
#: path in a task's context is relative to.
_ARTIFACTS_PREFIX = "artifacts"

_COLUMNS = "| Task | Attempt | Outcome | Produced |"
_RULE = "| --- | --- | --- | --- |"


@dataclass(frozen=True)
class EarlierTask:
    """One task of this run that opened before the one now opening.

    ``name`` is carried rather than derived because the index is read by an
    agent that has to act on it, and "the design task" is a name a person and a
    model can both use where ``draft_td`` is a key only the engine cares about.

    ``failure_reason`` is the closed-vocabulary reason, not the agent's words.
    The next task needs to know THAT the one before it failed and roughly why —
    interrupted is a different fact from ran-and-was-wrong — and the detail, if
    it wants it, is in that task's own deliverable or its conversation.
    """

    node_key: str
    name: str
    attempt: int
    status: str
    failure_reason: str | None = None


class EarlierTasksPort(Protocol):
    """The run's earlier tasks, oldest first.

    A seam out of this kind: what a task is called comes from the run's frozen
    template and what became of it comes from its attempt row, and neither is
    the composer's to read. ``before_attempt_id`` is the attempt now opening —
    everything the run did up to it is history, and the attempt's own
    conversation is where the reader already is.

    It answers with the LATEST attempt of each task. An earlier attempt of the
    same task is superseded by definition: the run reopened it because what it
    produced was not right, and putting both in the index would offer the next
    task a choice between an answer and a discarded one.
    """

    async def earlier(self, run_id: str, before_attempt_id: str) -> Sequence[EarlierTask]: ...


def render_index(
    tasks: Sequence[EarlierTask],
    artifacts: Iterable[ArtifactEntry],
    *,
    run_dir: str,
    catalogue_path: str,
) -> str:
    """The index table, cut to its share of the budget, saying if it was cut."""
    if not tasks:
        return "No task of this run has run before yours."
    produced = _by_task(artifacts, run_dir)
    rows = [_row(task, produced.get((task.node_key, task.attempt), ())) for task in tasks]
    return _fit(rows, catalogue_path)


def _by_task(
    artifacts: Iterable[ArtifactEntry], run_dir: str
) -> dict[tuple[str, int], tuple[str, ...]]:
    grouped: dict[tuple[str, int], list[str]] = {}
    for entry in artifacts:
        key = (entry.node_key, entry.attempt)
        grouped.setdefault(key, []).append(f"`{run_dir}/{_ARTIFACTS_PREFIX}/{entry.path}`")
    return {key: tuple(sorted(paths)) for key, paths in grouped.items()}


def _row(task: EarlierTask, paths: tuple[str, ...]) -> str:
    outcome = task.status
    if task.failure_reason:
        outcome = f"{task.status} ({task.failure_reason})"
    # Said out loud rather than left as an empty cell: an empty cell reads as a
    # rendering slip, and "nothing" is a fact the next task should act on.
    made = "<br>".join(paths) if paths else "nothing"
    return f"| `{task.node_key}` — {task.name} | {task.attempt} | {outcome} | {made} |"


def _fit(rows: Sequence[str], catalogue_path: str) -> str:
    """Keep the newest rows that fit; name what that dropped (FR-047).

    Trimmed from the OLDEST, because the run's recent history is what the next
    task is continuing from. This is a backstop and is expected never to fire:
    a row is a line, and a run would have to be hundreds of tasks long to
    overrun. When it does fire it says so and says where the whole of it is,
    rather than handing over a table that is quietly short.
    """
    table = [_COLUMNS, _RULE, *rows]
    allowance = share_of(INDEX_SHARE)
    if estimate_tokens("\n".join(table)) <= allowance:
        return "\n".join(table)
    spent = estimate_tokens(_COLUMNS) + estimate_tokens(_RULE)
    kept: list[str] = []
    for row in reversed(rows):
        spent += estimate_tokens(row)
        if spent > allowance and kept:
            break
        kept.append(row)
    kept.reverse()
    dropped = len(rows) - len(kept)
    notice = (
        f"_The {dropped} oldest task(s) are omitted here — this run is longer than the "
        f"context budget holds. Every artifact this run has produced, including theirs, "
        f"is catalogued at `{catalogue_path}`._"
    )
    return "\n".join([notice, "", _COLUMNS, _RULE, *kept])
