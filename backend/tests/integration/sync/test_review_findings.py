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
next round quietly undid, and an export publishing a row it could not render as
though the user had deleted it.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.sync.convergence import ConvergeStatus, GuardDirection
from coffer.domain.sync.diff import DeletionGuard
from tests.integration.sync.harness import (
    MACHINE_A,
    MACHINE_B,
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
