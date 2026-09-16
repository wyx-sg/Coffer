"""Defects found reviewing vault-sync before it landed, kept as regressions.

Each of these failed when it was written, against behaviour the spec requires.
They are here rather than folded into the other suites because what they guard
is one thing: every one of them was a way for a document to be deleted, or a
deletion to be undone, that nobody asked for — and each looked correct until a
test with two real vaults and a real remote said otherwise.

Two come from one seam, between a **held** round and the round that resumes it:
a confirmation was checked against a remote ref the round had not refreshed, so
"has the remote moved?" could only answer no; and one flag waived both guard
directions, so agreeing to publish deletions also agreed to apply them. The
rest: a pointer outliving the working tree that gave it meaning, a rollback the
next round quietly undid, an export publishing a row it could not render as
though the user had deleted it, and a manifest written on every round that
nothing ever read — so the one refusal that kept two Coffer builds from
trampling each other's layout did not exist.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.sync.convergence import ConvergeStatus, GuardDirection
from coffer.domain.sync.diff import DeletionGuard
from coffer.domain.sync.errors import SyncBundleTooNew
from coffer.domain.sync.manifest import MANIFEST_PATH, SCHEMA_VERSION
from tests.integration.sync.harness import (
    MACHINE_A,
    MACHINE_B,
    another_coffer_pushes,
    bare_remote,
    build_machine,
    settle,
)

pytestmark = pytest.mark.timeout(180)

#: A machine that may publish any deletion it likes, so a test can stage the
#: damage without its own guard holding it first.
UNGUARDED = DeletionGuard(share=1.0, floor=10**6)


async def _pair(tmp_path: pathlib.Path):
    """``a`` guards its rounds normally; ``b`` is free to push anything."""
    url = bare_remote(tmp_path / "remote.git")
    a = await build_machine(
        name="laptop",
        machine_id=MACHINE_A,
        root=tmp_path / "machine-a",
        remote_url=url,
        with_credentials=False,
    )
    b = await build_machine(
        name="desktop",
        machine_id=MACHINE_B,
        root=tmp_path / "machine-b",
        remote_url=url,
        guard=UNGUARDED,
        with_credentials=False,
    )
    return a, b


async def test_a_confirmation_does_not_authorise_deletions_the_remote_added_since(
    tmp_path: pathlib.Path,
) -> None:
    """spec vault-sync ``## Safety`` / ``ConvergeRound.run``:

    "the deletion guard is skipped for exactly that tip. If the remote has moved
    since, the guard runs again and the round is held afresh, because the user's
    'yes' was an answer about a specific set of documents."
    """
    a, b = await _pair(tmp_path)
    for i in range(40):
        a.write_knowledge("notes", f"n{i:02d}", f"body {i}\n")
    await settle(a, b)
    assert len(b.knowledge_paths()) == 40

    # The other machine deletes 25 of the 40 and pushes. That is what the user
    # is about to be shown.
    for i in range(25):
        b.delete_knowledge("notes", f"n{i:02d}")
    await b.converge()

    held = await a.converge()
    assert held.status is ConvergeStatus.AWAITING_CONFIRMATION
    assert held.pending is not None
    shown = set(held.pending.paths)
    assert len(shown) == 25

    # While the user is looking at that list, the other machine deletes ten
    # more and pushes again. The confirmation was never about these.
    for i in range(25, 35):
        b.delete_knowledge("notes", f"n{i:02d}")
    await b.converge()

    resumed = await a.confirm()

    survivors = a.knowledge_paths()
    unseen = {f"notes/n{i:02d}.md" for i in range(25, 35)}
    assert unseen <= survivors, (
        f"{len(unseen - survivors)} documents the user was never shown were deleted "
        f"by their confirmation (round: {resumed.status})"
    )


async def test_confirming_a_publish_hold_does_not_waive_the_apply_guard(
    tmp_path: pathlib.Path,
) -> None:
    """spec vault-sync ``## Safety``: the circuit breaker runs "in both
    directions", and a hold is raised in one of them. Saying "yes, publish my
    deletions" is not saying "yes, delete whatever the remote has dropped"."""
    a, b = await _pair(tmp_path)
    for i in range(40):
        a.write_knowledge("notes", f"n{i:02d}", f"body {i}\n")
        a.write_skill(f"s{i:02d}")
    await settle(a, b)
    assert len(b.knowledge_paths()) == 40

    # The other machine drops 25 skills and pushes: on its own, an apply-side
    # breach here.
    for i in range(25):
        b.delete_skill_files(f"s{i:02d}")
    await b.converge()

    # This machine drops 25 notes: on its own, a publish-side breach, and the
    # one the round reaches first.
    for i in range(25):
        a.delete_knowledge("notes", f"n{i:02d}")

    held = await a.converge()
    assert held.status is ConvergeStatus.AWAITING_CONFIRMATION
    assert held.pending is not None
    assert held.pending.direction is GuardDirection.PUBLISH
    assert all(p.startswith("knowledge/") for p in held.pending.paths)

    resumed = await a.confirm()

    assert a.has_skill_files("s00"), (
        "confirming a publish-side hold silently applied 25 skill deletions the "
        f"apply-side guard should have held (round: {resumed.status})"
    )


async def test_a_lost_working_tree_does_not_wedge_every_later_round(
    tmp_path: pathlib.Path,
) -> None:
    """The working tree is a cache — ``~/.coffer/sync`` — while the pointer
    lives in ``coffer.db``. Losing the cache must not be unrecoverable: the
    pointer names a commit the remote still has, and a round can fetch it."""
    a, b = await _pair(tmp_path)
    a.write_knowledge("notes", "kept", "only this machine has it\n")
    await settle(a, b)
    assert await a.state.pointer() is not None

    a.forget_worktree()

    service = a.service()
    await a.remote_config()
    first = await service.run_once()
    second = await service.run_once()

    assert a.read_knowledge("notes", "kept") is not None
    assert ConvergeStatus.FAILED not in (first.status, second.status), (
        f"every round fails after the working tree is lost: {first.error}"
    )


async def test_a_rolled_back_round_is_not_re_applied_by_the_next_one(
    tmp_path: pathlib.Path,
) -> None:
    """spec vault-sync ``## Safety`` / ``### Scenario: a round can be rolled back``.

    A rollback is the operator's remedy for an apply that should not have
    happened. A remedy the background worker undoes fifteen minutes later is
    not one.
    """
    a, b = await _pair(tmp_path)
    # Ten documents, one deleted: under both the share and the floor, so the
    # apply lands without the circuit breaker asking first.
    for i in range(10):
        a.write_knowledge("notes", f"n{i}", f"body {i}\n")
    a.write_knowledge("notes", "keep", "wanted\n")
    await settle(a, b)

    b.delete_knowledge("notes", "keep")
    await b.converge()
    await a.converge()
    assert a.read_knowledge("notes", "keep") is None, "the deletion did not apply"

    await a.rollback()
    assert a.read_knowledge("notes", "keep") is not None, "the rollback did not restore it"

    await a.converge()

    assert a.read_knowledge("notes", "keep") is not None, (
        "the next round silently re-applied the deletion the user rolled back"
    )


async def test_a_resource_that_fails_to_serialize_is_not_published_as_a_deletion(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spec vault-sync ``## Why deletion is safe``: "Export writes differentially.
    It writes changed documents and removes documents the vault no longer holds."

    A document the vault still holds and this export could not render is not a
    document the vault no longer holds.
    """
    from coffer.application.sync import exporter as exporter_module

    a, b = await _pair(tmp_path)
    await a.register("mcp_server", "keep", {"value": "keep"})
    # Enough siblings that losing one stays under the publish-side guard, so
    # what this test measures is the export and not the circuit breaker.
    for i in range(10):
        await a.register("mcp_server", f"other{i}", {"value": f"other{i}"})
    await settle(a, b)
    assert await b.find("mcp_server", "keep") is not None

    real = exporter_module.resource_to_doc

    def explode(**kwargs):
        if kwargs.get("name") == "keep":
            raise RuntimeError("this row cannot be rendered on this build")
        return real(**kwargs)

    monkeypatch.setattr(exporter_module, "resource_to_doc", explode)

    await a.converge()
    monkeypatch.undo()
    await b.converge()

    assert await b.find("mcp_server", "keep") is not None, (
        "a row that merely failed to serialize here was published as a deletion "
        "and removed on the other machine"
    )


async def test_the_deletion_guard_sees_the_retry_set_too(tmp_path: pathlib.Path) -> None:
    """spec vault-sync ``## Safety``: the circuit breaker bounds what a round
    would *apply*, and the retry set is applied alongside the diff.

    A held path the tree has since dropped is absorbed as the deletion it now
    is. Twenty-five of those in one round is exactly the kind of deletion the
    guard exists to hold — and a guard that ran over the diff alone would let
    every one of them through unasked. The holds here are what a round that
    crashed between the merge and the apply leaves behind.
    """
    a, b = await _pair(tmp_path)
    for i in range(30):
        a.write_knowledge("notes", f"n{i:02d}", f"body {i}\n")
    await settle(a, b)

    ghosts = [f"knowledge/notes/ghost{i:02d}.md" for i in range(25)]
    for path in ghosts:
        await a.state.hold(path, applicable=True)

    run = await a.converge()

    assert run.status is ConvergeStatus.AWAITING_CONFIRMATION, (
        f"25 retry-set deletions were applied without the guard (round: {run.status})"
    )
    assert run.pending is not None
    assert run.pending.direction is GuardDirection.APPLY
    assert set(ghosts) <= set(run.pending.paths)
    assert ("knowledge", 25, 30) in run.pending.breaches
    assert len(a.knowledge_paths()) == 30


async def test_clearing_or_setting_the_remote_waits_for_the_round_in_flight(
    tmp_path: pathlib.Path,
) -> None:
    """``ConvergeService.clear_remote`` / ``set_remote`` take the round's lock.

    A round ends by writing the pointer. A clear that slipped in mid-round
    would be undone by that write, and the base the user asked to forget
    would let the next ``adopt`` skip the join detection. A ``set_remote``
    mid-round would repoint ``origin`` under a round that has already merged
    from the old one.
    """
    import asyncio

    from coffer.domain.sync.backup import BackupRemote

    a, b = await _pair(tmp_path)
    a.write_knowledge("notes", "kept", "kept\n")
    await settle(a, b)
    await a.remote_config()
    service = a.service()
    assert await service.get_remote() is not None

    started = asyncio.Event()
    release = asyncio.Event()
    real_run = a.round.run

    async def held_run(**kwargs):  # type: ignore[no-untyped-def]
        started.set()
        await release.wait()
        return await real_run(**kwargs)

    a.round.run = held_run  # type: ignore[method-assign]
    in_flight = asyncio.create_task(service.run_once())
    await started.wait()

    clearing = asyncio.create_task(service.clear_remote())
    setting = asyncio.create_task(
        service.set_remote(BackupRemote(url=a.remote_url, worktree_path=str(a.worktree)))
    )
    for _ in range(20):
        await asyncio.sleep(0)
    assert not clearing.done(), "clear_remote ran while a round held the lock"
    assert not setting.done(), "set_remote ran while a round held the lock"

    release.set()
    run = await in_flight
    assert run.status in (ConvergeStatus.OK, ConvergeStatus.NO_CHANGE)
    assert await clearing is True
    # The clear ran after the round's pointer write, so nothing resurrected it
    # — and the set that queued behind the clear then stored the remote again.
    assert await asyncio.wait_for(setting, 30) is not None
    await service.clear_remote()
    assert await a.state.pointer() is None
    assert await service.get_remote() is None


# --- two Coffer builds meeting on one remote --------------------------------


async def test_a_remote_written_in_a_newer_layout_is_refused_not_applied(
    tmp_path: pathlib.Path,
) -> None:
    """``domain/sync/manifest``: "a build that does not know a newer layout
    refuses the remote (``SYNC_BUNDLE_TOO_NEW``) rather than applying a
    partially-understood tree — or publishing into one".

    The manifest was written on every round and read on none, so the sentence
    describing that refusal described nothing: an older Coffer applied a bumped
    layout's documents without a word and — the worse half — went on converging
    the areas it *does* know from its own state, publishing a newer build's
    documents as deletions nobody made.
    """
    a, _b = await _pair(tmp_path)
    a.write_knowledge("notes", "mine", "my body\n")
    await settle(a)
    assert await a.remote_text(MANIFEST_PATH) is not None, "a round writes the manifest"

    another_coffer_pushes(
        a.remote_url, layout=SCHEMA_VERSION + 1, adding="knowledge/notes/from-a-newer-build.md"
    )
    commits = await a.remote_commit_count()

    with pytest.raises(SyncBundleTooNew) as refused:
        await a.converge()

    assert refused.value.found == SCHEMA_VERSION + 1
    assert a.read_knowledge("notes", "from-a-newer-build") is None, (
        "a document written in a layout this build does not understand was applied anyway"
    )
    assert await a.remote_commit_count() == commits, (
        "the refused round published into a tree it cannot read"
    )
    assert a.read_knowledge("notes", "mine") == "my body\n", "the vault must be untouched"


async def test_a_remote_at_this_layout_is_still_applied(tmp_path: pathlib.Path) -> None:
    """The gate refuses *newer*, not *foreign*. A tree written at this layout
    version — which is every other machine, almost always — is an ordinary
    round, and a gate that stopped those would have stopped sync."""
    a, _b = await _pair(tmp_path)
    await settle(a)

    another_coffer_pushes(
        a.remote_url, layout=SCHEMA_VERSION, adding="knowledge/notes/from-a-peer.md"
    )

    run = await a.converge()

    assert run.status is ConvergeStatus.OK
    assert a.read_knowledge("notes", "from-a-peer") == "written by another Coffer\n"
