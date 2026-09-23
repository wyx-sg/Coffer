"""A join states its case and its counts before applying (spec vault-sync
"Report a join before applying it").

Driven through the production :class:`ConvergeService` over two whole vaults
and one real bare repository, like the rest of this directory: what the
preview counts is what git says the remote changed, and "applied nothing" is
checked against the vault's own files and the machine's pointer.
"""

from __future__ import annotations

import pathlib
from datetime import date

import pytest

from coffer.domain.sync.convergence import ConvergeStatus, JoinKind
from coffer.domain.sync.diff import ChangeStatus, DeletionGuard
from tests.integration.sync.harness import VaultMachine, settle, two_machines

pytestmark = pytest.mark.timeout(120)


@pytest.fixture
async def pair(tmp_path: pathlib.Path):
    a, b = await two_machines(tmp_path, guard=DeletionGuard(share=1.0, floor=100), shared_key=True)
    yield a, b
    await a.close()
    await b.close()


async def _seeded(a: VaultMachine, b: VaultMachine) -> None:
    a.write_knowledge("notes", "shared", "one\ntwo\nthree\n")
    a.write_skill("shared-skill")
    await a.register("mcp_server", "files", {"value": "files"})
    await settle(a, b)


async def test_a_returning_join_states_its_case_and_counts_before_applying(pair) -> None:
    a, b = pair
    await _seeded(a, b)
    # The reinstall: B loses its pointer and working tree; its vault survives.
    b.state.forget()
    b.forget_worktree()
    # While B is away the remote changes two documents: one deleted, one added.
    a.delete_skill_files("shared-skill")
    a.write_knowledge("notes", "while-away", "written while b was gone\n")
    await a.adopt()
    await b.remote_config()
    service = b.service()

    preview = await service.preview_join()

    assert preview.joining is True
    assert preview.kind is JoinKind.RETURNING
    assert preview.ambiguous is False
    assert preview.last_converged_on == date.today()
    assert preview.remote_changed == 2
    # B still holds the note, the skill and the resource it had before.
    assert preview.vault_documents == 3
    # Nothing was applied: the pointer is still gone and the vault is as it was.
    assert await b.state.pointer() is None
    assert b.has_skill_files("shared-skill")
    assert b.read_knowledge("notes", "while-away") is None
    assert await b.audit_events("sync_run") == 0

    # The join it described is the join that then happens.
    run = await service.run_once(adopt=True)
    assert run.status is ConvergeStatus.OK, run.error
    assert run.join is JoinKind.RETURNING
    assert "skills/shared-skill/SKILL.md" in run.applied.paths(ChangeStatus.DELETED)
    assert b.read_knowledge("notes", "while-away") == "written while b was gone\n"


async def test_a_new_join_counts_everything_the_remote_holds(pair) -> None:
    a, b = pair
    a.write_knowledge("notes", "one", "1\n")
    a.write_knowledge("notes", "two", "2\n")
    await a.adopt()
    b.write_knowledge("notes", "mine", "b's own\n")
    await b.remote_config()

    preview = await b.service().preview_join()

    assert preview.joining is True
    assert preview.kind is JoinKind.NEW
    assert preview.last_converged_on is None
    assert preview.remote_changed == 2
    assert preview.vault_documents == 1
    assert await b.state.pointer() is None
    assert b.read_knowledge("notes", "one") is None


async def test_an_ambiguous_join_is_stated_and_still_waits_for_the_choice(pair) -> None:
    """A first round publishes a descriptor naming no commit, so a reinstall
    the same day leaves the base unrecoverable."""
    a, _b = pair
    a.write_knowledge("notes", "one", "first note\n")
    await a.remote_config()
    await a.adopt()
    a.state.forget()
    service = a.service()

    preview = await service.preview_join()

    assert preview.joining is True
    assert preview.ambiguous is True
    assert preview.kind is None
    assert preview.last_converged_on == date.today()
    assert preview.remote_changed is None
    assert await a.state.pointer() is None

    chosen = await service.preview_join(choice="keep-local")
    assert chosen.kind is JoinKind.NEW
    assert chosen.ambiguous is False


async def test_a_machine_that_already_joined_has_no_join_to_state(pair) -> None:
    a, _b = pair
    await a.remote_config()
    await a.adopt()
    pointer = await a.state.pointer()

    preview = await a.service().preview_join()

    assert preview.joining is False
    assert preview.kind is None
    assert await a.state.pointer() == pointer
