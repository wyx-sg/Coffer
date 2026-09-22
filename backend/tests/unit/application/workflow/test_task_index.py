"""The index a task opens with: every earlier task, and what it produced.

This is the module that replaced carrying the earlier tasks' transcripts
forward (FR-029, FR-031). The two properties worth pinning are that it costs a
LINE per task rather than a conversation, and that it never lies by omission —
a task that produced nothing is still in it.
"""

from __future__ import annotations

import pytest

from coffer.application.workflow.context_budget import INDEX_SHARE, estimate_tokens, share_of
from coffer.application.workflow.task_index import EarlierTask, render_index

from .fakes import FakeArtifactStore

RUN = "run-1"
RUN_DIR = "/vault/workflow/run-1"
CATALOGUE = f"{RUN_DIR}/CATALOG.md"


def index(tasks: list[EarlierTask], store: FakeArtifactStore | None = None) -> str:
    store = store or FakeArtifactStore()
    return render_index(tasks, store.list_artifacts(RUN), run_dir=RUN_DIR, catalogue_path=CATALOGUE)


def task(
    node_key: str,
    *,
    name: str = "A task",
    attempt: int = 1,
    status: str = "completed",
    failure_reason: str | None = None,
) -> EarlierTask:
    return EarlierTask(
        node_key=node_key,
        name=name,
        attempt=attempt,
        status=status,
        failure_reason=failure_reason,
    )


@pytest.mark.acceptance(
    spec="workflow", scenario="a later task opens with an index of what the run produced"
)
def test_each_task_is_one_row_naming_the_files_it_produced() -> None:
    store = FakeArtifactStore()
    store.add(RUN, "design", 1, "td.md")
    rendered = index([task("design", name="Tech design")], store)

    assert "`design` — Tech design" in rendered
    assert f"`{RUN_DIR}/artifacts/design/1/td.md`" in rendered


def test_the_index_costs_a_line_per_task_not_a_conversation() -> None:
    """The whole point of the change: forty tasks is forty lines.

    Pinned as a ratio rather than an absolute so the test survives rewording of
    the table. What it would catch is the regression that matters — somebody
    putting a task's summary, output or transcript back into a row, at which
    point the index grows with what the run SAID again rather than with how
    many tasks it has.
    """
    one = index([task("t0")])
    forty = index([task(f"t{i}") for i in range(40)])

    per_task = (estimate_tokens(forty) - estimate_tokens(one)) / 39
    assert per_task < 40


@pytest.mark.acceptance(
    spec="workflow", scenario="a task that produced nothing is still in the index"
)
def test_a_failed_or_skipped_task_is_listed_with_what_became_of_it() -> None:
    rendered = index(
        [
            task("code", name="Write it", status="failed", failure_reason="interrupted"),
            task("review", name="Review it", status="skipped"),
        ]
    )

    # Present, with the outcome — not absent, which would read to the next task
    # as "these steps never existed".
    assert "failed (interrupted)" in rendered
    assert "skipped" in rendered
    # And said out loud rather than left as an empty cell, which reads as a
    # rendering slip rather than as a fact.
    assert rendered.count("nothing") == 2


def test_only_the_artifacts_of_the_attempt_being_listed_are_named() -> None:
    """A retry supersedes; the index must not offer both answers.

    The port answers with the latest attempt of each task, so a row for attempt
    2 that also listed attempt 1's file would hand the next task a discarded
    deliverable beside the real one, with nothing to tell them apart.
    """
    store = FakeArtifactStore()
    store.add(RUN, "design", 1, "td.md")
    store.add(RUN, "design", 2, "td.md")
    rendered = index([task("design", attempt=2)], store)

    assert "artifacts/design/2/td.md" in rendered
    assert "artifacts/design/1/td.md" not in rendered


def test_a_run_whose_first_task_is_opening_says_so_rather_than_showing_an_empty_table() -> None:
    assert index([]) == "No task of this run has run before yours."


@pytest.mark.acceptance(
    spec="workflow", scenario="an index too long for the budget says what it left out"
)
def test_an_index_over_its_share_is_cut_oldest_first_and_points_at_the_catalogue() -> None:
    # Long names rather than many tasks, so the test states the rule without
    # depending on how many hundreds of rows the real ceiling happens to allow.
    many = [task(f"t{i}", name="n" * 400) for i in range(200)]
    rendered = index(many)

    assert estimate_tokens(rendered) <= share_of(INDEX_SHARE) + estimate_tokens(CATALOGUE)
    assert "omitted here" in rendered
    assert CATALOGUE in rendered
    # Oldest first: the newest task survives the cut, the oldest does not.
    assert "`t199`" in rendered
    assert "`t0` " not in rendered
