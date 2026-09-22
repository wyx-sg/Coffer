"""Unattended rewriters over a vault that spans machines (spec vault-sync).

The knowledge **curation** pass rewrites the ``topics/`` lane with no diff
anyone approved. That is defensible on one machine and not on several, and the
spec's ``## Unattended rewriters`` section states three normative rules to make
it safe:

The acceptance scenario titles below still read "tidy" because that is what
`specs/vault-sync/spec.md` calls the pass; curation is what replaced it, and
the rules and the fields are the same three. The titles are matched as strings
by `scripts/audit_acceptance.py`, so they follow the spec rather than the code.

1. **An unattended rewriter of synced content names one owner machine**, and is
   a no-op everywhere else — otherwise two machines fold the same source into
   two *different* topic documents, git merges that cleanly (the two topics are
   additions at different paths), and the vault ends up holding the same
   knowledge twice with nothing in conflict.
2. **A pass and a converge round never overlap.** They both write the vault,
   and an export taken mid-rewrite is a torn snapshot git reads as a deliberate
   change. They take the same lock.
3. **Delete-versus-edit resolves toward the edit.** A fresh edit is something a
   person or an agent just decided; the owner's deletion is a housekeeping
   judgement the next pass will simply make again.

All three are implemented and tested for real below.
"""

from __future__ import annotations

import asyncio
import dataclasses
import pathlib
from datetime import UTC, datetime

import pytest

from coffer.domain.sync.convergence import ConvergeStatus
from coffer.domain.sync.diff import DeletionGuard
from tests.integration.sync.harness import settle, two_machines

pytestmark = pytest.mark.timeout(120)


@pytest.fixture
async def pair(tmp_path: pathlib.Path):
    a, b = await two_machines(tmp_path, guard=DeletionGuard(share=1.0, floor=100), shared_key=True)
    yield a, b
    await a.close()
    await b.close()


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a tidy pass and a converge round do not overlap"
)
async def test_a_round_waits_for_whatever_else_is_rewriting_the_vault(pair) -> None:
    """The lock is the mechanism, and it is the service's, not the round's.

    ``ConvergeService.lock`` is exposed precisely so the other writer of vault
    content — the curation pass — can take the same one. This holds it the way
    a pass in progress would and shows that a round genuinely waits rather than
    serializing a half-rewritten corpus.
    """
    a, _b = pair
    a.write_knowledge("notes", "one", "before the pass\n")
    await a.remote_config()
    lock = asyncio.Lock()
    service = a.service(lock=lock)
    assert service.lock is lock, "the pass and the round must share one lock"

    async with lock:
        # A pass is "in progress": it has the lock and is midway through
        # rewriting the corpus.
        round_task = asyncio.create_task(service.run_once())
        await asyncio.sleep(0.15)
        assert not round_task.done(), "the round serialized the vault mid-rewrite"
        # The rewrite finishes while the round is still waiting.
        a.write_knowledge("notes", "one", "after the pass\n")
        a.delete_knowledge("notes", "one")
        a.write_knowledge("notes", "merged", "after the pass\n")

    run = await round_task

    # It exported the finished corpus, never the torn one.
    assert run.status is ConvergeStatus.OK, run.error
    assert a.tree_text("knowledge/notes/merged.md") == "after the pass\n"
    assert a.tree_text("knowledge/notes/one.md") is None
    assert "knowledge/notes/merged.md" in await a.remote_paths()


@pytest.mark.acceptance(spec="vault-sync", scenario="tidy runs only on its owner machine")
async def test_curation_names_one_owner_machine_and_is_a_no_op_elsewhere(pair) -> None:
    """The gate must answer True on exactly one machine of a converged pair.

    Asserting on ``curate_runs_on`` rather than on a pass actually running is
    deliberate: the failure being prevented is two machines *writing*, and that
    decision is made here, before any model is reached. A test that needed an
    internal model configured would be testing the curation pass instead.
    """
    from coffer.domain.internal_engine_config import GlobalInternalEngineConfig

    a, b = pair
    await settle(a, b)

    enabled_here = GlobalInternalEngineConfig(
        model="m", updated_at=datetime.now(tz=UTC), auto_curate_enabled=True
    )
    # No owner: a single-machine vault, where "here" is the only answer.
    assert enabled_here.curate_runs_on(a.machine_id) is True
    assert enabled_here.curate_runs_on(b.machine_id) is True

    owned_by_a = dataclasses.replace(enabled_here, curate_owner_machine_id=a.machine_id)
    assert owned_by_a.curate_runs_on(a.machine_id) is True
    assert owned_by_a.curate_runs_on(b.machine_id) is False, (
        "the pass ran on a machine that does not own it — two machines "
        "rewriting one corpus produce duplicate topic documents that git "
        "merges cleanly and nothing ever reports"
    )

    # An owner naming a machine nobody has heard of stops curation everywhere.
    # No curation costs a stale `topics/` lane; curation everywhere costs
    # duplicated knowledge no merge can see.
    orphaned = dataclasses.replace(enabled_here, curate_owner_machine_id="0000000000000000")
    assert orphaned.curate_runs_on(a.machine_id) is False
    assert orphaned.curate_runs_on(b.machine_id) is False

    # Off beats ownership.
    off = dataclasses.replace(owned_by_a, auto_curate_enabled=False)
    assert off.curate_runs_on(a.machine_id) is False


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an owner naming a machine that is gone is reported, not silent"
)
async def test_an_orphaned_owner_is_a_reportable_fault_and_can_be_taken_over(pair) -> None:
    """The half the test above could not say, against a real registry.

    ``curate_runs_on`` answers False for an owner that is another live machine
    and False for an owner that no longer exists, and those two are a vault
    that is fine and a vault whose curation stopped everywhere. Until this the
    difference was unrepresentable, so the second one looked exactly like the
    first and nothing in the product said otherwise (spec vault-sync FR-098).
    """
    from coffer.domain.internal_engine_config import (
        CurationOwner,
        GlobalInternalEngineConfig,
    )

    a, b = pair
    await settle(a, b)
    known = [m.descriptor.machine_id for m in await a.registry.list(a.bundle)]
    assert {a.machine_id, b.machine_id} <= set(known), "the pair should both be registered"

    config = GlobalInternalEngineConfig(
        model="m", updated_at=datetime.now(tz=UTC), auto_curate_enabled=True
    )
    owned_by_b = dataclasses.replace(config, curate_owner_machine_id=b.machine_id)
    orphaned = dataclasses.replace(config, curate_owner_machine_id="0000000000000000")

    # The timer cannot tell these apart, which is the whole problem.
    assert owned_by_b.curate_runs_on(a.machine_id) is False
    assert orphaned.curate_runs_on(a.machine_id) is False

    # A surface can.
    assert owned_by_b.curation_owner(a.machine_id, known) is CurationOwner.OTHER
    assert orphaned.curation_owner(a.machine_id, known) is CurationOwner.UNKNOWN

    # And taking it over here resolves it, without anything having to guess.
    taken = dataclasses.replace(orphaned, curate_owner_machine_id=a.machine_id)
    assert taken.curation_owner(a.machine_id, known) is CurationOwner.SELF
    assert taken.curate_runs_on(a.machine_id) is True


@pytest.mark.acceptance(spec="vault-sync", scenario="an edit outlives a tidy deletion")
async def test_an_edit_beats_a_curation_deletion_without_reporting_a_conflict(pair) -> None:
    a, b = pair
    a.write_knowledge("notes", "merged-away", "the original note\n")
    await settle(a, b)

    # A owns curation: its pass merged this note elsewhere and deleted it.
    a.delete_knowledge("notes", "merged-away")
    a.write_knowledge("notes", "topic", "the original note, now part of a topic\n")
    await a.converge()

    # B edited the same note before it converged.
    b.write_knowledge("notes", "merged-away", "the original note, with B's edit\n")
    b.resolver.enabled = False

    run = await b.converge()

    assert run.conflicts == (), "delete-versus-edit is not a conflict; the edit wins"
    assert b.read_knowledge("notes", "merged-away") == "the original note, with B's edit\n"
