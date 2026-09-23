"""What a run reads: add, upload, remove."""

from __future__ import annotations

import pytest

from coffer.application.workflow.inputs_service import InputNotFound
from coffer.domain.workflow.errors import NotThisMachine, RunTerminal
from coffer.domain.workflow.run import (
    REPO_MOUNT_LINK,
    REPO_MOUNT_WORKTREE,
    RunInput,
    RunInputKind,
    RunSignal,
)

from .conftest import Engine, build_engine


async def test_a_run_starts_reading_nothing(engine: Engine) -> None:
    run = await engine.create()

    assert await engine.inputs.list_inputs(run.id) == ()


@pytest.mark.acceptance(
    spec="workflow", scenario="an input can be added and removed while the run is going"
)
async def test_a_collection_and_a_link_can_be_mounted_while_the_run_is_going(
    engine: Engine,
) -> None:
    """At any point in the run's life, not only at creation."""
    run = await engine.started()

    await engine.inputs.add_input(
        run.id, kind=RunInputKind.KNOWLEDGE, ref="team-docs", label="Team docs"
    )
    mounted = await engine.inputs.add_input(
        run.id, kind=RunInputKind.LINK, ref="https://example.invalid/ticket/1"
    )

    assert mounted == (
        RunInput(kind=RunInputKind.KNOWLEDGE, ref="team-docs", label="Team docs"),
        RunInput(kind=RunInputKind.LINK, ref="https://example.invalid/ticket/1"),
    )


async def test_mounting_the_same_thing_twice_is_saying_it_once(engine: Engine) -> None:
    run = await engine.create()

    await engine.inputs.add_input(run.id, kind=RunInputKind.KNOWLEDGE, ref="team-docs")
    mounted = await engine.inputs.add_input(
        run.id, kind=RunInputKind.KNOWLEDGE, ref="team-docs", label="Now with a label"
    )

    assert mounted == (
        RunInput(kind=RunInputKind.KNOWLEDGE, ref="team-docs", label="Now with a label"),
    )


async def test_mounting_an_input_does_not_bump_the_runs_version(engine: Engine) -> None:
    # It changes what the NEXT node opens with; it advances nothing, so every
    # client holding a version keeps a valid one.
    run = await engine.started()

    await engine.inputs.add_input(run.id, kind=RunInputKind.LINK, ref="https://x.invalid")

    assert (await engine.latest(run.id)).version == run.version


@pytest.mark.acceptance(
    spec="workflow", scenario="an uploaded file becomes an input the nodes can read"
)
async def test_an_uploaded_file_lands_under_the_run_and_carries_its_size(engine: Engine) -> None:
    """Spec workflow "Store an uploaded input under the run's directory"."""
    run = await engine.create()

    mounted = await engine.inputs.upload_input(
        run.id, filename="prd.pdf", content=b"x" * 2048, label="The PRD"
    )

    # ``path`` is absolute, and that is the point of it: the file lands in the
    # run's ``inputs/`` while a node runs in its ``workspace/``, so a path
    # relative to the working directory would climb out with ``..``.
    assert mounted == (
        RunInput(
            kind=RunInputKind.FILE,
            ref="prd.pdf",
            label="The PRD",
            size=2048,
            path=f"/runs/{run.id}/inputs/prd.pdf",
        ),
    )
    assert engine.uploads.files[(run.id, "prd.pdf")] == b"x" * 2048
    assert engine.inputs.inputs_dir(run.id) == f"/fake/workflows/{run.id}/inputs"


async def test_a_second_upload_of_the_same_name_is_a_second_file(engine: Engine) -> None:
    run = await engine.create()

    await engine.inputs.upload_input(run.id, filename="prd.pdf", content=b"one")
    mounted = await engine.inputs.upload_input(run.id, filename="prd.pdf", content=b"two")

    assert [item.ref for item in mounted] == ["prd.pdf", "prd-2.pdf"]


async def test_removing_an_uploaded_file_takes_its_bytes_with_it(engine: Engine) -> None:
    run = await engine.create()
    await engine.inputs.upload_input(run.id, filename="prd.pdf", content=b"bytes")

    remaining = await engine.inputs.remove_input(run.id, "prd.pdf")

    assert remaining == ()
    assert engine.uploads.files == {}


async def test_removing_a_collection_only_unmounts_it(engine: Engine) -> None:
    run = await engine.create()
    await engine.inputs.add_input(run.id, kind=RunInputKind.KNOWLEDGE, ref="team-docs")
    await engine.inputs.upload_input(run.id, filename="prd.pdf", content=b"bytes")

    remaining = await engine.inputs.remove_input(run.id, "team-docs")

    assert [item.ref for item in remaining] == ["prd.pdf"]
    # The run never owned the collection, so nothing of it was deleted — and
    # the uploaded file that stayed mounted still has its bytes.
    assert engine.uploads.files == {(run.id, "prd.pdf"): b"bytes"}


async def test_unmounting_something_that_is_not_mounted_is_refused(engine: Engine) -> None:
    run = await engine.create()

    with pytest.raises(InputNotFound):
        await engine.inputs.remove_input(run.id, "never-mounted")


async def test_an_aborted_run_reads_nothing_more(engine: Engine) -> None:
    run = await engine.started()
    await engine.runs.signal(run.id, RunSignal.ABORT, version=run.version)

    with pytest.raises(RunTerminal):
        await engine.inputs.add_input(run.id, kind=RunInputKind.LINK, ref="https://x.invalid")


async def test_a_run_another_machine_owns_is_read_only_here() -> None:
    """Spec workflow "Advance a run only on the machine that owns it"."""
    owner = build_engine(machine_id="machine-a")
    run = await owner.create()
    visitor = build_engine(machine_id="machine-b")
    visitor.run_repo.rows = owner.run_repo.rows

    assert await visitor.inputs.list_inputs(run.id) == ()
    with pytest.raises(NotThisMachine):
        await visitor.inputs.add_input(run.id, kind=RunInputKind.LINK, ref="https://x.invalid")


# -- repository inputs -------------------------------------------------------


async def test_mounting_a_repository_records_where_the_checkout_landed(engine: Engine) -> None:
    run = await engine.create()

    mounted = await engine.inputs.add_input(
        run.id, kind=RunInputKind.REPO, ref="/Users/dev/work/account", label="the service"
    )

    assert mounted == (
        RunInput(
            kind=RunInputKind.REPO,
            ref="/Users/dev/work/account",
            label="the service",
            path=f"/fake/workflows/{run.id}/workspace/account",
            mount=REPO_MOUNT_WORKTREE,
        ),
    )
    # The run's directory exists before anything is checked out into it.
    assert engine.artifacts.created[-1] == run.id


async def test_a_directory_that_is_not_a_repository_is_recorded_as_a_link(engine: Engine) -> None:
    engine.repos.mount_kind = REPO_MOUNT_LINK
    run = await engine.create()

    (mounted,) = await engine.inputs.add_input(
        run.id, kind=RunInputKind.REPO, ref="/Users/dev/notes"
    )

    # Spec workflow "Give a mounted repository its own checkout": the context
    # has to be able to say which it got, so the input carries it rather than
    # implying an isolation it does not have.
    assert mounted.mount == REPO_MOUNT_LINK


async def test_two_repositories_with_the_same_basename_get_their_own_checkouts(
    engine: Engine,
) -> None:
    run = await engine.create()

    await engine.inputs.add_input(run.id, kind=RunInputKind.REPO, ref="/a/account")
    mounted = await engine.inputs.add_input(run.id, kind=RunInputKind.REPO, ref="/b/account")

    assert [item.path for item in mounted] == [
        f"/fake/workflows/{run.id}/workspace/account",
        f"/fake/workflows/{run.id}/workspace/account-2",
    ]


async def test_a_repository_that_cannot_be_mounted_is_not_half_added(engine: Engine) -> None:
    engine.repos.fail = RuntimeError("no such directory")
    run = await engine.create()

    with pytest.raises(RuntimeError):
        await engine.inputs.add_input(run.id, kind=RunInputKind.REPO, ref="/gone")

    assert await engine.inputs.list_inputs(run.id) == ()


async def test_unmounting_a_repository_gives_back_the_checkout(engine: Engine) -> None:
    run = await engine.create()
    (mounted,) = await engine.inputs.add_input(
        run.id, kind=RunInputKind.REPO, ref="/Users/dev/work/account"
    )

    remaining = await engine.inputs.remove_input(run.id, "/Users/dev/work/account")

    assert remaining == ()
    assert engine.repos.unmounted == [
        ("/Users/dev/work/account", mounted.path, REPO_MOUNT_WORKTREE)
    ]
    assert engine.repos.mounted == {}
