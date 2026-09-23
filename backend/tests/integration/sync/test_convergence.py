"""Two vaults converging through a real git remote (spec vault-sync).

Every test here drives the production :class:`ConvergeRound` over two whole
vaults and one real **bare** repository on disk. Nothing below the git binary
is faked, because git's three-way merge is the thing under test: it is what
decides whose edit survives and — the point of the whole design — whether a
document the other machine no longer has was *deleted* or merely *never held*.
A fake mirror would assert our own beliefs about that, which is exactly the
belief a regression would break.

The four scenarios this file exists for are the 2026-07-10 mutual deletion in
its four disguises: a stale machine, a machine returning without its pointer, a
machine returning with nothing left in its vault, and a machine meeting the
remote for the first time. Each one is a different answer to "is this absence a
decision?", and getting any of them wrong loses the user's data.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.agent.sync_reconcile import AgentImportGate
from coffer.domain.credential_errors import CredentialUnreadable
from coffer.domain.sync.convergence import ConvergeStatus, GuardDirection, JoinKind
from coffer.domain.sync.diff import ChangeStatus, DeletionGuard
from tests.integration.sync.harness import VaultMachine, settle, two_machines

pytestmark = pytest.mark.timeout(120)


def added(diff) -> tuple[str, ...]:
    return diff.paths(ChangeStatus.ADDED)


def deleted(diff) -> tuple[str, ...]:
    return diff.paths(ChangeStatus.DELETED)


@pytest.fixture
async def pair(tmp_path: pathlib.Path):
    """Two fresh machines that have never met."""
    a, b = await two_machines(tmp_path)
    yield a, b
    await a.close()
    await b.close()


@pytest.fixture
async def keyed(tmp_path: pathlib.Path):
    """Two machines that already share a master key.

    The key never travels inside the repository, so a scenario about which
    ciphertext wins presupposes the out-of-band bootstrap has happened —
    otherwise the second machine cannot read either blob and the question
    does not arise.
    """
    a, b = await two_machines(tmp_path, shared_key=True)
    yield a, b
    await a.close()
    await b.close()


@pytest.fixture
async def roomy(tmp_path: pathlib.Path):
    """Two machines with a deletion guard that a single deletion cannot trip.

    The guard's default — 20% of an area — is tripped by deleting the only
    document in it, which is correct and is tested on its own below. Scenarios
    about *deletion propagating* would otherwise be testing the guard instead,
    so they raise the threshold rather than pad every vault with filler.

    They also share a master key, because a machine that cannot decrypt a
    credential cannot register the resource citing it — the row is held for
    retry, which is right, but it makes the machine a poor witness to anything
    else.
    """
    a, b = await two_machines(tmp_path, guard=DeletionGuard(share=1.0, floor=100), shared_key=True)
    yield a, b
    await a.close()
    await b.close()


async def _seeded(a: VaultMachine, b: VaultMachine) -> None:
    """A vault on A, converged onto B, both machines quiet and in agreement."""
    a.write_knowledge("notes", "shared", "one\ntwo\nthree\n")
    a.write_skill("shared-skill")
    await a.register("mcp_server", "files", {"value": "files"})
    await settle(a, b)


# --- the ordinary round -----------------------------------------------------


@pytest.mark.acceptance(spec="vault-sync", scenario="a changed vault converges and pushes")
async def test_a_changed_vault_commits_and_pushes(pair) -> None:
    a, _b = pair
    a.write_knowledge("notes", "first", "hello\n")

    run = await a.adopt()

    assert run.status is ConvergeStatus.OK, run.error
    assert run.commit
    assert "knowledge/notes/first.md" in added(run.published)
    # The commit is on the remote's branch, not merely in the local history.
    assert "knowledge/notes/first.md" in await a.remote_paths()
    assert await a.remote_text("knowledge/notes/first.md") == "hello\n"
    # The pointer is the commit that was pushed, so the next round diffs from it.
    assert await a.state.pointer() == run.commit


@pytest.mark.acceptance(spec="vault-sync", scenario="an unchanged vault makes no commit")
async def test_an_unchanged_vault_makes_no_commit(pair) -> None:
    a, b = pair
    await _seeded(a, b)
    before = await a.remote_commit_count()
    local_before = await a.local_commit_count()

    run = await a.adopt()

    assert run.status is ConvergeStatus.NO_CHANGE
    assert await a.remote_commit_count() == before
    assert await a.local_commit_count() == local_before
    # A success, not a skip: nothing was left outstanding for the next round.
    assert run.ok


@pytest.mark.acceptance(spec="vault-sync", scenario="a remote addition lands in the vault")
async def test_a_remote_addition_is_registered_here(pair) -> None:
    a, b = pair
    await settle(a, b)
    await a.register("mcp_server", "weather", {"value": "weather"})
    await a.converge()
    hooks_before = b.hook.runs

    run = await b.converge()

    assert run.status is ConvergeStatus.OK, run.error
    assert "weather" in await b.resource_names("mcp_server")
    registered = await b.find("mcp_server", "weather")
    assert registered is not None and registered.config["value"] == "weather"
    # The kind's import gate ran before the row was written...
    assert any(cfg.get("value") == "weather" for cfg in b.gate.seen)
    # ...and its post-import hook re-applied this machine's side effects after.
    assert b.hook.runs == hooks_before + 1
    assert await b.state.pointer() == run.commit


@pytest.mark.acceptance(spec="vault-sync", scenario="a remote deletion is applied")
async def test_a_remote_deletion_removes_files_rows_and_credentials(roomy) -> None:
    a, b = roomy
    a.write_skill("doomed")
    a.set_credential("mcp/doomed/token", "s3cret")
    await a.register("mcp_server", "doomed", {"value": "x", "credential_ref": "mcp/doomed/token"})
    a.write_skill("kept")
    await a.register("mcp_server", "kept", {"value": "y"})
    await settle(a, b)
    assert b.has_skill_files("doomed")
    assert b.has_credential("mcp/doomed/token")
    audited_before = await b.audit_events("resource_deleted")

    a.delete_skill_files("doomed")
    await a.delete_resource("mcp_server", "doomed")
    await a.converge()

    run = await b.converge()

    assert run.status is ConvergeStatus.OK, run.error
    assert not b.has_skill_files("doomed")
    assert await b.resource_names("mcp_server") == ["kept"]
    # Deleting the resource released the credential no remaining resource cites.
    assert not b.has_credential("mcp/doomed/token")
    assert await b.audit_events("resource_deleted") > audited_before
    assert "skills/doomed/SKILL.md" in deleted(run.applied)


@pytest.mark.acceptance(spec="vault-sync", scenario="a local-only document survives a round")
async def test_a_local_only_document_survives_and_is_published(pair) -> None:
    a, b = pair
    await _seeded(a, b)
    b.write_knowledge("notes", "only-here", "mine\n")

    run = await b.adopt()

    assert b.read_knowledge("notes", "only-here") == "mine\n"
    assert "knowledge/notes/only-here.md" in added(run.published)
    assert "knowledge/notes/only-here.md" in await b.remote_paths()
    # And the other machine picks it up rather than deleting it back.
    await a.adopt()
    assert a.read_knowledge("notes", "only-here") == "mine\n"


# --- the 2026-07-10 incident, in its four disguises -------------------------


@pytest.mark.acceptance(spec="vault-sync", scenario="a stale machine does not resurrect a deletion")
async def test_a_stale_machine_applies_the_deletion_instead_of_reverting_it(roomy) -> None:
    """The incident in test form.

    B converges, then goes quiet while A deletes a skill and pushes. B's
    pointer now predates the deletion. When B comes back it must **apply** the
    deletion, because B made no change to that path relative to its own base —
    and it must not push its still-present copy back, which is how the two
    machines used to undo each other.
    """
    a, b = roomy
    await _seeded(a, b)
    assert b.has_skill_files("shared-skill")

    # B goes quiet here. Everything below happens while it is offline.
    a.delete_skill_files("shared-skill")
    deletion = await a.adopt()
    assert "skills/shared-skill/SKILL.md" in deleted(deletion.published)
    assert "skills/shared-skill/SKILL.md" not in await a.remote_paths()

    run = await b.adopt()

    assert run.status is ConvergeStatus.OK, run.error
    assert "skills/shared-skill/SKILL.md" in deleted(run.applied)
    assert not b.has_skill_files("shared-skill")
    # B published nothing about that path: it never changed it.
    assert "skills/shared-skill/SKILL.md" not in added(run.published)

    # And the deletion stays dead on A, which is the half that used to fail.
    after = await a.converge()
    assert not a.has_skill_files("shared-skill")
    assert "skills/shared-skill/SKILL.md" not in await a.remote_paths()
    assert "skills/shared-skill/SKILL.md" not in added(after.applied)


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a returning machine does not resurrect what was deleted while it was away",
)
async def test_a_returning_machine_recovers_its_base_and_takes_the_deletion(roomy) -> None:
    """A reinstall takes ``~/.coffer`` but the vault's files were restored.

    B's pointer, retry set and working tree are gone; its knowledge and skills
    are not. Treated as a *new* machine it would take the union and republish
    every document A deleted while it was away — with no conflict raised,
    because a union has no base to disagree with. Its id is in the registry, so
    it must be recognised as returning and recover its base from its own
    published descriptor instead.
    """
    a, b = roomy
    await _seeded(a, b)
    assert b.has_skill_files("shared-skill")
    published_base = await b.remote_text(f"machines/{b.machine_id}.yaml")
    assert published_base and "last_converged_commit:" in published_base

    # The reinstall: local convergence state and the working tree go; the vault
    # itself survives, which is what makes this dangerous.
    b.state.forget()
    b.forget_worktree()

    a.delete_skill_files("shared-skill")
    await a.adopt()

    run = await b.adopt()

    assert run.join is JoinKind.RETURNING
    assert run.status is ConvergeStatus.OK, run.error
    assert "skills/shared-skill/SKILL.md" in deleted(run.applied)
    assert not b.has_skill_files("shared-skill")
    # Nothing was undone on the remote, which is the failure this rule prevents.
    assert "skills/shared-skill/SKILL.md" not in await b.remote_paths()
    # B's own documents are still here — a returning machine is not rebuilt.
    assert b.read_knowledge("notes", "shared") == "one\ntwo\nthree\n"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a returning machine with an empty vault does not publish the loss"
)
async def test_a_returning_machine_whose_vault_is_gone_is_held_not_published(pair) -> None:
    """The same shape, reached from the other side.

    A reinstall that took the vault with it leaves an empty vault and a
    recoverable pointer, and the merge would read that as "this machine deleted
    everything". Coffer cannot tell a wiped disk from a deliberate purge, so the
    publish-side circuit breaker stops the round and asks.
    """
    a, b = pair
    for i in range(12):
        a.write_knowledge("notes", f"n{i}", f"note {i}\n")
        a.write_skill(f"skill-{i}")
    await settle(a, b)
    assert len(b.knowledge_paths()) == 12
    remote_before = await b.remote_paths()

    b.state.forget()
    b.forget_worktree()
    await b.wipe_vault()

    run = await b.adopt()

    assert run.status is ConvergeStatus.AWAITING_CONFIRMATION
    assert run.pending is not None
    assert run.pending.direction is GuardDirection.PUBLISH
    assert {area for area, _d, _t in run.pending.breaches} >= {"knowledge", "skills"}
    assert len(run.pending.paths) >= 24
    # Nothing was pushed, so the other machines are untouched.
    assert await b.remote_paths() == remote_before
    assert await a.converge() is not None
    assert len(a.knowledge_paths()) == 12


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a damaged machine rebuilds from the remote instead of publishing its loss",
)
async def test_a_damaged_machine_rebuilds_instead_of_publishing_its_loss(pair) -> None:
    """The third answer, for the machine the first two do not serve.

    Confirming a publish-side hold spreads the loss to every other machine;
    rejecting leaves this one refusing the same round forever. Rebuild replaces
    this vault with the remote's, discards what only this machine had, and
    pushes nothing.
    """
    a, b = pair
    for i in range(12):
        a.write_knowledge("notes", f"n{i}", f"note {i}\n")
    await settle(a, b)
    remote_before = await b.remote_paths()

    b.state.forget()
    b.forget_worktree()
    await b.wipe_vault()
    # A document only the damaged machine holds — a rebuild must discard it
    # rather than publish it, which is what separates rebuild from confirm.
    b.write_knowledge("notes", "local-only", "written after the wipe\n")

    held = await b.adopt()
    assert held.status is ConvergeStatus.AWAITING_CONFIRMATION

    run = await b.rebuild()

    assert run.status is ConvergeStatus.OK
    assert len(b.knowledge_paths()) == 12
    assert not any("local-only" in p for p in b.knowledge_paths())
    # Nothing was pushed: the remote is exactly as the healthy machine left it.
    assert await b.remote_paths() == remote_before
    # And the hold is cleared, so the next round is an ordinary one.
    assert await b.state.pending() is None


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a new machine takes the union and deletes nothing"
)
async def test_a_new_machine_takes_the_union(pair) -> None:
    """A machine the registry has never seen. Its base is the empty tree, so
    the diff can only contain additions — deletion is structurally impossible
    here rather than merely avoided."""
    a, b = pair
    a.write_knowledge("notes", "from-a", "a\n")
    await a.register("mcp_server", "only-on-a", {"value": "a"})
    await settle(a)

    b.write_knowledge("notes", "from-b", "b\n")
    await b.register("mcp_server", "only-on-b", {"value": "b"})

    run = await b.adopt()

    assert run.join is JoinKind.NEW
    assert run.status is ConvergeStatus.OK, run.error
    assert run.applied.counts()["deleted"] == 0
    assert run.published.counts()["deleted"] == 0
    # Everything the remote held is here...
    assert b.read_knowledge("notes", "from-a") == "a\n"
    assert "only-on-a" in await b.resource_names("mcp_server")
    # ...and everything this machine already had is still here.
    assert b.read_knowledge("notes", "from-b") == "b\n"
    assert "only-on-b" in await b.resource_names("mcp_server")
    # The next round publishes both, and A ends up with the union too.
    await b.converge()
    await a.converge()
    assert a.read_knowledge("notes", "from-b") == "b\n"
    assert sorted(await a.resource_names("mcp_server")) == ["only-on-a", "only-on-b"]


# --- merging and conflict ---------------------------------------------------


@pytest.mark.acceptance(
    spec="vault-sync", scenario="concurrent edits to different parts of one document merge"
)
async def test_two_machines_appending_to_different_ends_of_a_note_merge(pair) -> None:
    a, b = pair
    a.write_knowledge("notes", "shared", "middle\n" * 8)
    await settle(a, b)

    a.write_knowledge("notes", "shared", "FROM A\n" + "middle\n" * 8)
    b.write_knowledge("notes", "shared", "middle\n" * 8 + "FROM B\n")
    await a.converge()

    run = await b.converge()

    assert run.status is ConvergeStatus.OK, run.error
    assert run.conflicts == ()
    merged = b.read_knowledge("notes", "shared")
    assert merged is not None
    assert merged.startswith("FROM A\n")
    assert merged.endswith("FROM B\n")
    await a.converge()
    assert a.read_knowledge("notes", "shared") == merged


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a real conflict stops the round without touching the vault"
)
async def test_a_real_conflict_aborts_the_round_and_leaves_the_vault_alone(pair) -> None:
    a, b = pair
    a.write_knowledge("notes", "shared", "original\n")
    await settle(a, b)
    pointer_before = await b.state.pointer()

    a.write_knowledge("notes", "shared", "A's version\n")
    b.write_knowledge("notes", "shared", "B's version\n")
    # B also has an unrelated local note, to prove nothing else was applied.
    b.write_knowledge("notes", "untouched", "still here\n")
    await a.converge()
    b.resolver.enabled = False  # no internal model configured

    run = await b.converge()

    assert run.status is ConvergeStatus.CONFLICT
    assert run.conflicts == ("knowledge/notes/shared.md",)
    assert run.agent_resolved == ()
    # The vault is exactly as it was.
    assert b.read_knowledge("notes", "shared") == "B's version\n"
    assert b.read_knowledge("notes", "untouched") == "still here\n"
    assert await b.state.pointer() == pointer_before
    # And the working tree that holds the conflict is the one the status names.
    assert b.worktree.is_dir()


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an agent-resolved conflict is validated and reported"
)
async def test_an_agent_resolution_that_validates_is_applied_and_named(pair) -> None:
    a, b = pair
    await a.register("mcp_server", "contested", {"value": "original"})
    await settle(a, b)

    await a.edit_config("mcp_server", "contested", {"value": "from-a"})
    await b.edit_config("mcp_server", "contested", {"value": "from-b"})
    await a.converge()

    uid = await b.uid("mcp_server", "contested")
    path = await b.doc_path("mcp_server", "contested")
    b.resolver.enabled = True
    b.resolver.writes[path] = (
        b"config:\n  value: reconciled\ndescription: null\nkind: mcp_server\n"
        b"name: contested\nuid: " + uid.encode() + b"\n"
    )

    run = await b.converge()

    assert run.status is ConvergeStatus.OK, run.error
    assert run.agent_resolved == (path,)
    assert run.conflicts == ()
    resolved = await b.find("mcp_server", "contested")
    assert resolved is not None and resolved.config["value"] == "reconciled"
    # It was an ordinary merge result from there on: it reached the remote.
    assert "reconciled" in (await b.remote_text(path) or "")


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an agent resolution that fails validation is not applied"
)
@pytest.mark.acceptance(
    spec="vault-sync", scenario="a resolution that fails is still reported with its path"
)
async def test_an_agent_resolution_leaving_a_conflict_marker_is_refused(pair) -> None:
    a, b = pair
    await a.register("mcp_server", "contested", {"value": "original"})
    await settle(a, b)
    pointer_before = await b.state.pointer()

    await a.edit_config("mcp_server", "contested", {"value": "from-a"})
    await b.edit_config("mcp_server", "contested", {"value": "from-b"})
    await a.converge()

    uid = await b.uid("mcp_server", "contested")
    path = await b.doc_path("mcp_server", "contested")
    b.resolver.enabled = True
    # It claims the path, but what it wrote still carries git's markers.
    b.resolver.writes[path] = (
        b"uid: " + uid.encode() + b"\nkind: mcp_server\nname: contested\nconfig:\n"
        b"<<<<<<< ours\n  value: from-b\n=======\n  value: from-a\n>>>>>>> theirs\n"
    )

    run = await b.converge()

    assert run.status is ConvergeStatus.CONFLICT
    assert run.conflicts == (path,)
    assert run.agent_resolved == ()
    local = await b.find("mcp_server", "contested")
    assert local is not None and local.config["value"] == "from-b"
    assert await b.state.pointer() == pointer_before


@pytest.mark.acceptance(spec="vault-sync", scenario="the fresher credential ciphertext wins")
async def test_the_fresher_ciphertext_wins_regardless_of_commit_order(keyed) -> None:
    """Two machines re-encrypt one ref. A Fernet token carries its encryption
    time in cleartext, so the two can be ordered without the key — and must be,
    because the alternative is the blob whose machine synced last winning."""
    a, b = keyed
    a.set_credential("mcp/shared/token", "original")
    await a.register("mcp_server", "shared", {"value": "s", "credential_ref": "mcp/shared/token"})
    await settle(a, b)

    # B re-encrypts first; A re-encrypts a second later and pushes last.
    b.set_credential("mcp/shared/token", "from-b")
    _sleep_past_a_fernet_second()
    a.set_credential("mcp/shared/token", "from-a")
    await a.converge()

    run = await b.converge()

    assert run.status is ConvergeStatus.OK, run.error
    assert b.credential_store.get("mcp/shared/token") == "from-a"
    await a.converge()
    assert a.credential_store.get("mcp/shared/token") == "from-a"


# --- holding paths back, guards, snapshots ----------------------------------


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a failed apply holds the path back instead of deleting it"
)
async def test_a_path_that_will_not_apply_is_held_and_retried(pair) -> None:
    a, b = pair
    await settle(a, b)
    await a.register("mcp_server", "needs-setup", {"value": "not-ready"})
    await a.converge()

    # B's import gate refuses this document for now.
    b.gate.refuse_value = "not-ready"
    first = await b.converge()

    path = await a.doc_path("mcp_server", "needs-setup")
    assert [p for p, _reason in first.failures] == [path]
    assert await b.find("mcp_server", "needs-setup") is None
    retry, not_applicable = await b.state.held_paths()
    assert path in retry and path not in not_applicable

    # The next round exports the vault. The document is still in the tree and
    # is NOT committed as a deletion, because "could not absorb" is not
    # "the user deleted it".
    second = await b.converge()
    assert b.tree_text(path) is not None
    assert path not in deleted(second.published)
    assert path in await b.remote_paths()
    assert [p for p, _reason in second.failures] == [path]

    # A retry-set path is pending, not failed once and forgotten: the round
    # re-attempts it even though no later diff mentions it (it is unchanged in
    # every one of them — that is what "the failure was local" means). So once
    # this machine can take the document, an ordinary round absorbs it and the
    # hold clears.
    b.gate.refuse_value = None

    third = await b.converge()

    assert third.failures == ()
    registered = await b.find("mcp_server", "needs-setup")
    assert registered is not None and registered.config["value"] == "not-ready"
    retry_after, _na = await b.state.held_paths()
    assert path not in retry_after


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a failed apply holds the path back instead of deleting it"
)
async def test_a_path_that_can_never_apply_here_is_recorded_as_not_applicable(pair) -> None:
    a, b = pair
    await settle(a, b)
    await a.register("mcp_server", "wrong-machine", {"value": "never"})
    await a.converge()

    b.gate.refuse_value = "never"
    b.gate.refuse_permanently = True
    run = await b.converge()

    path = await a.doc_path("mcp_server", "wrong-machine")
    retry, not_applicable = await b.state.held_paths()
    assert path in not_applicable and path not in retry
    # Said to be not applicable here, and not presented as a failure to chase.
    assert run.failures == ()
    assert run.not_applicable == (path,)
    # Preserved exactly like a retry-set path: the next export must not publish
    # it as a deletion. And not retried: the next round re-checks the gate's
    # precondition, finds it still unmet, and neither applies nor reports it.
    second = await b.converge()
    assert path in await b.remote_paths()
    assert await b.find("mcp_server", "wrong-machine") is None
    assert second.failures == ()
    assert second.not_applicable == ()
    retry, not_applicable = await b.state.held_paths()
    assert path in not_applicable and path not in retry


async def test_an_agent_whose_config_dir_is_missing_here_is_not_applicable(
    pair, tmp_path: pathlib.Path
) -> None:
    """The production gate, not a stand-in: an agent installed on A whose
    config directory does not exist on B."""
    a, b = pair
    await settle(a, b)
    b.use_gate(AgentImportGate())
    await a.register(
        "agent",
        "installed-elsewhere",
        {"type": "claude_code", "config_dir": str(tmp_path / "only-on-a" / ".claude")},
    )
    await a.converge()

    run = await b.converge()

    path = await a.doc_path("agent", "installed-elsewhere")
    assert run.failures == ()
    assert run.not_applicable == (path,)
    retry, not_applicable = await b.state.held_paths()
    assert path in not_applicable and path not in retry
    assert await b.find("agent", "installed-elsewhere") is None

    second = await b.converge()
    assert second.failures == ()
    assert second.not_applicable == ()
    assert path in await b.remote_paths()

    # The agent is installed here later: the next ordinary round applies it.
    (tmp_path / "only-on-a" / ".claude").mkdir(parents=True)
    third = await b.converge()

    assert third.failures == ()
    assert await b.find("agent", "installed-elsewhere") is not None
    retry, not_applicable = await b.state.held_paths()
    assert path not in retry and path not in not_applicable


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an oversized deletion is held for confirmation"
)
async def test_an_oversized_deletion_is_held_then_confirmed(pair) -> None:
    a, b = pair
    for i in range(10):
        a.write_knowledge("notes", f"n{i}", f"note {i}\n")
    await settle(a, b)
    assert len(b.knowledge_paths()) == 10

    for i in range(10):
        a.delete_knowledge("notes", f"n{i}")
    # A is the damaged machine here, so its own publish-side guard fires first;
    # confirming lets it through, which is what puts the deletion on the remote.
    held = await a.converge()
    assert held.status is ConvergeStatus.AWAITING_CONFIRMATION
    assert held.pending is not None
    assert held.pending.direction is GuardDirection.PUBLISH
    assert len(held.pending.paths) == 10
    await a.confirm()
    assert await a.remote_paths() and not [
        p for p in await a.remote_paths() if p.startswith("knowledge/")
    ]

    # Now B meets it, and the apply-side guard holds the same diff.
    incoming = await b.converge()
    assert incoming.status is ConvergeStatus.AWAITING_CONFIRMATION
    assert incoming.pending is not None
    assert incoming.pending.direction is GuardDirection.APPLY
    assert sorted(incoming.pending.paths) == sorted(f"knowledge/notes/n{i}.md" for i in range(10))
    # Nothing was applied while it waits.
    assert len(b.knowledge_paths()) == 10

    confirmed = await b.confirm()
    assert confirmed.status is ConvergeStatus.OK, confirmed.error
    assert b.knowledge_paths() == set()


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an oversized deletion is held for confirmation"
)
async def test_rejecting_a_held_round_leaves_the_vault_untouched(pair) -> None:
    a, b = pair
    for i in range(10):
        a.write_knowledge("notes", f"n{i}", f"note {i}\n")
    await settle(a, b)
    for i in range(10):
        a.delete_knowledge("notes", f"n{i}")
    await a.confirm() if (await a.converge()).pending else None

    held = await b.converge()
    assert held.status is ConvergeStatus.AWAITING_CONFIRMATION
    pointer_before = await b.state.pointer()

    await b.reject()

    assert len(b.knowledge_paths()) == 10
    assert await b.state.pointer() == pointer_before
    assert await b.state.pending() is None


@pytest.mark.acceptance(spec="vault-sync", scenario="a round can be rolled back")
async def test_a_round_can_be_rolled_back_to_its_pre_apply_snapshot(roomy) -> None:
    a, b = roomy
    await _seeded(a, b)
    assert b.read_knowledge("notes", "shared") == "one\ntwo\nthree\n"

    a.write_knowledge("notes", "shared", "rewritten by A\n")
    a.write_knowledge("notes", "extra", "new from A\n")
    await a.adopt()
    applied = await b.adopt()
    assert applied.status is ConvergeStatus.OK, applied.error
    assert b.read_knowledge("notes", "shared") == "rewritten by A\n"
    assert b.read_knowledge("notes", "extra") == "new from A\n"
    snapshots = await b.snapshots()
    assert snapshots, "the round must tag its pre-apply state"

    rolled = await b.rollback()

    assert rolled.status is ConvergeStatus.OK
    assert b.read_knowledge("notes", "shared") == "one\ntwo\nthree\n"
    assert b.read_knowledge("notes", "extra") is None
    # ``commit`` names the snapshot it came back from — the answer to "from
    # where?", which is the only thing the caller did not already know.
    assert rolled.commit == (
        await b.snapshots() and await b.mirror.resolve_revision((await b.snapshots())[0])
    )
    # And the pointer does NOT follow it. That is what makes the undo stick:
    # moved back, the next round would re-derive the very diff just undone and
    # the worker would re-apply it on its next tick.
    assert await b.state.pointer() != rolled.commit
    assert (await b.converge()).status is not ConvergeStatus.FAILED
    assert b.read_knowledge("notes", "shared") == "one\ntwo\nthree\n"
    assert b.read_knowledge("notes", "extra") is None


@pytest.mark.acceptance(
    spec="vault-sync", scenario="restore brings back a document deleted last week"
)
async def test_restore_returns_a_deleted_skill_without_discarding_later_work(roomy) -> None:
    a, b = roomy
    a.write_skill("archived")
    a.write_knowledge("notes", "old", "old\n")
    await settle(a, b)
    before_deletion = await a.mirror.head()
    assert before_deletion

    a.delete_skill_files("archived")
    await a.converge()
    await b.converge()
    assert not b.has_skill_files("archived")

    # B gains something after the deletion, which a restore must not discard.
    b.write_knowledge("notes", "since", "gained since\n")
    await b.converge()

    run = await b.restore(before_deletion)

    assert b.has_skill_files("archived")
    assert b.read_knowledge("notes", "since") == "gained since\n"
    assert "skills/archived/SKILL.md" in added(run.applied)
    assert deleted(run.applied) == (), "a restore must not discard what came after it"

    # And the restore holds. The pointer did not move back, so the next round
    # publishes the recovered skill as the ordinary addition it is rather than
    # letting the remote's old deletion of it win a second time.
    after = await b.converge()

    assert "skills/archived/SKILL.md" in added(after.published)
    assert b.has_skill_files("archived")
    assert "skills/archived/SKILL.md" in await b.remote_paths()
    await a.converge()
    assert a.has_skill_files("archived")


# --- what must never travel -------------------------------------------------


@pytest.mark.acceptance(spec="vault-sync", scenario="the master key never enters the repository")
async def test_the_repository_carries_ciphertext_and_no_key_material(pair) -> None:
    a, b = pair
    a.set_credential("mcp/files/token", "s3cret-value")
    await a.register("mcp_server", "files", {"value": "f", "credential_ref": "mcp/files/token"})
    await settle(a)

    blob = await a.remote_text("credentials/mcp/files/token.enc")
    assert blob and blob.startswith("gAAAAA")  # a Fernet token, not plaintext
    assert "s3cret-value" not in blob

    key = a.master_key.export_key()
    assert key is not None
    for path in await a.remote_paths():
        content = await a.remote_text(path)
        assert content is None or key.decode() not in content

    # A machine holding the ciphertext without the key reports the ref locked
    # rather than failing decryption silently.
    await b.adopt()
    await b.converge()
    assert b.credentials.locked_refs() == ["mcp/files/token"]
    # "Locked", not "silently wrong": reading it here is refused outright.
    with pytest.raises(CredentialUnreadable):
        b.credential_store.get("mcp/files/token")


def _sleep_past_a_fernet_second() -> None:
    """Fernet's timestamp has one-second resolution, so two encryptions in the
    same second are indistinguishable and the comparator keeps the incumbent —
    correctly. A test about which one is fresher has to cross the boundary."""
    import time

    time.sleep(1.05)


# --- a move is not a deletion (spec vault-sync FR-090) ----------------------


def _relayout(machine: VaultMachine, names: list[str]) -> None:
    """Move documents from ``notes/`` into ``notes/sources/``, byte for byte.

    The knowledge two-lane rewrite, which is what put the user's vault on this
    path: every document changed its address and not one changed its content.
    """
    for name in names:
        body = machine.read_knowledge("notes", name)
        assert body is not None
        machine.write_knowledge("notes/sources", name, body)
        machine.delete_knowledge("notes", name)


@pytest.mark.acceptance(spec="vault-sync", scenario="a re-layout publishes without asking")
async def test_a_relayout_publishes_unattended_and_lands_on_the_other_machine(pair) -> None:
    """The measured bug: 56 of 58 knowledge documents moved into a
    subdirectory, the guard counted the deletions alone, and the vault sat
    awaiting a confirmation for a day for a round that lost nothing.
    """
    a, b = pair
    names = [f"n{i:02d}" for i in range(30)]
    for name in names:
        a.write_knowledge("notes", name, f"body of {name}\n")
    await settle(a, b)
    assert len(b.knowledge_paths()) == 30

    _relayout(a, names)
    published = await a.converge()

    assert published.status is ConvergeStatus.OK, published.error
    assert published.pending is None
    assert await a.state.pending() is None
    # The diff genuinely carries all 60 changes; it is the *guard* that now
    # tells the 30 deletions from the 30 documents receiving their content.
    assert len(deleted(published.published)) == 30
    assert len(added(published.published)) == 30
    assert {p for p in await a.remote_paths() if p.startswith("knowledge/")} == {
        f"knowledge/notes/sources/{name}.md" for name in names
    }

    # And the machine on the receiving end absorbs it just as unattended.
    applied = await b.converge()

    assert applied.status is ConvergeStatus.OK, applied.error
    assert applied.pending is None
    assert b.knowledge_paths() == {f"notes/sources/{name}.md" for name in names}
    assert b.read_knowledge("notes/sources", "n00") == "body of n00\n"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an oversized deletion is held for confirmation"
)
async def test_a_mass_deletion_beside_a_relayout_is_still_held_for_the_deletion(pair) -> None:
    """The other half of the pair, and the half that must not have moved: the
    deletions with nowhere to reappear are counted, held and listed on their
    own, without 20 relocations padding the list the user has to read."""
    a, b = pair
    names = [f"n{i:02d}" for i in range(30)]
    for name in names:
        a.write_knowledge("notes", name, f"body of {name}\n")
    await settle(a, b)

    _relayout(a, names[:20])
    for name in names[20:]:
        a.delete_knowledge("notes", name)

    held = await a.converge()

    assert held.status is ConvergeStatus.AWAITING_CONFIRMATION
    assert held.pending is not None
    assert held.pending.direction is GuardDirection.PUBLISH
    assert held.pending.breaches == (("knowledge", 10, 30),)
    assert sorted(held.pending.paths) == [f"knowledge/notes/{name}.md" for name in names[20:]]
    # Nothing was published: the round stops before the push either way.
    assert len({p for p in await a.remote_paths() if p.startswith("knowledge/")}) == 30


def _body(name: str) -> str:
    """A document with enough lines that adding one keeps the two sides
    recognisably the same — the shape of a real serialized document, and what
    makes the difference between git pairing the rename and not."""
    return "\n".join(f"{name} line {i}" for i in range(12)) + "\n"


def _relayout_rewriting(machine: VaultMachine, names: list[str]) -> None:
    """Move documents AND rewrite them, which is what a layout migration *is*.

    Giving every resource an immutable uid renamed each document and added a
    ``uid:`` line to it. Byte-for-byte pairing cannot see that, so the guard
    read 28 of 28 resources as lost; git had reported the same diff as 28
    renames all along.
    """
    for name in names:
        body = machine.read_knowledge("notes", name)
        assert body is not None
        machine.write_knowledge("notes/sources", name, body + f"uid: {name}-uid\n")
        machine.delete_knowledge("notes", name)


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a re-layout that rewrites its documents publishes without asking"
)
async def test_a_relayout_that_rewrites_its_documents_publishes_unattended(pair) -> None:
    """The 2026-09-19 bug: the vault was held for four days over a migration
    this project shipped, with nothing lost. Exact-bytes pairing could not see
    it because the migration edited every document on its way; git's rename
    detection can (spec vault-sync FR-090).
    """
    a, b = pair
    names = [f"n{i:02d}" for i in range(30)]
    for name in names:
        a.write_knowledge("notes", name, _body(name))
    await settle(a, b)
    assert len(b.knowledge_paths()) == 30

    _relayout_rewriting(a, names)
    published = await a.converge()

    assert published.status is ConvergeStatus.OK, published.error
    assert published.pending is None
    assert await a.state.pending() is None
    assert len(deleted(published.published)) == 30
    assert len(added(published.published)) == 30
    assert {p for p in await a.remote_paths() if p.startswith("knowledge/")} == {
        f"knowledge/notes/sources/{name}.md" for name in names
    }

    applied = await b.converge()

    assert applied.status is ConvergeStatus.OK, applied.error
    assert applied.pending is None
    assert b.knowledge_paths() == {f"notes/sources/{name}.md" for name in names}


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a wiped area is held although rename pairings are consulted"
)
async def test_a_wipe_is_still_held_now_that_pairings_are_consulted(pair) -> None:
    """The argument that admitting a similarity judgement is safe, tested
    rather than asserted: a pairing can only excuse a deletion that has an
    addition to be paired *with*, and a wipe has none.
    """
    a, b = pair
    names = [f"n{i:02d}" for i in range(30)]
    for name in names:
        a.write_knowledge("notes", name, _body(name))
    await settle(a, b)

    for name in names:
        a.delete_knowledge("notes", name)

    held = await a.converge()

    assert held.status is ConvergeStatus.AWAITING_CONFIRMATION
    assert held.pending is not None
    assert held.pending.direction is GuardDirection.PUBLISH
    assert held.pending.breaches == (("knowledge", 30, 30),)
    assert len({p for p in await a.remote_paths() if p.startswith("knowledge/")}) == 30


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a hold is released once its diff no longer breaches"
)
async def test_a_hold_whose_breach_has_gone_releases_itself(pair) -> None:
    """A latch is an unanswered question about one diff, not a state a vault
    sits in. The user's vault was held on a question the guard would no longer
    ask, and every later round re-reported it instead of re-deriving it — which
    is why a day of hourly rounds changed nothing.
    """
    a, b = pair
    names = [f"n{i:02d}" for i in range(30)]
    for name in names:
        a.write_knowledge("notes", name, f"body of {name}\n")
    await settle(a, b)

    for name in names[:10]:
        a.delete_knowledge("notes", name)
    held = await a.converge()
    assert held.status is ConvergeStatus.AWAITING_CONFIRMATION
    assert await a.state.pending() is not None

    # Nobody answers. The reason for the question goes away instead: the
    # documents are back, whether from a restore, a re-sync of the source or a
    # defect on this machine being fixed.
    for name in names[:10]:
        a.write_knowledge("notes", name, f"body of {name}\n")

    resumed = await a.converge()

    assert resumed.ok, resumed.error
    assert resumed.pending is None
    assert await a.state.pending() is None
    assert len({p for p in await a.remote_paths() if p.startswith("knowledge/")}) == 30
