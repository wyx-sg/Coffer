"""Converge-round requirements with no scenario of their own until OpenSpec
(spec vault-sync).

Each test drives the production :class:`ConvergeRound` over whole vaults and a
real bare repository, through the two-machine harness, and asserts one
requirement's scenario as the spec states it.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest
import yaml

from coffer.domain.sync.convergence import ConvergeStatus, JoinKind
from coffer.domain.sync.diff import ChangeStatus, DeletionGuard
from tests.integration.sync.harness import BRANCH, bare_remote, settle, two_machines

pytestmark = pytest.mark.timeout(120)


@pytest.fixture
async def pair(tmp_path: pathlib.Path):
    a, b = await two_machines(tmp_path, shared_key=True)
    yield a, b
    await a.close()
    await b.close()


@pytest.fixture
async def roomy(tmp_path: pathlib.Path):
    """A guard one deletion cannot trip, so a scenario about deletion is not a
    scenario about the guard."""
    a, b = await two_machines(tmp_path, guard=DeletionGuard(share=1.0, floor=100), shared_key=True)
    yield a, b
    await a.close()
    await b.close()


def _git(repo: pathlib.Path | str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True
    )


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a remote rebuilt from one machine loses nothing"
)
async def test_a_remote_rebuilt_from_one_machine_loses_nothing(pair) -> None:
    a, _b = pair
    a.write_knowledge("notes", "alpha", "alpha\n")
    a.write_knowledge("notes", "beta", "beta\n")
    a.write_skill("demo")
    await a.register("mcp_server", "files", {"value": "files"})
    await settle(a)
    vault_docs = {
        "knowledge/notes/alpha.md",
        "knowledge/notes/beta.md",
        "skills/demo/SKILL.md",
        await a.doc_path("mcp_server", "files"),
    }
    assert vault_docs <= await a.remote_paths()

    # The remote is lost and recreated empty at the same address.
    shutil.rmtree(a.remote_url)
    bare_remote(pathlib.Path(a.remote_url))
    assert await a.remote_commit_count() == 0

    run = await a.converge()

    assert run.ok, (run.status, run.error)
    assert vault_docs <= await a.remote_paths()
    assert await a.remote_text("knowledge/notes/alpha.md") == "alpha\n"
    # The machine's vault is exactly what it was.
    assert a.knowledge_paths() == {"notes/alpha.md", "notes/beta.md"}
    assert a.has_skill_files("demo")
    assert await a.resource_names("mcp_server") == ["files"]


@pytest.mark.acceptance(
    spec="vault-sync", scenario="machine-local files never reach the working tree"
)
async def test_machine_local_files_never_reach_the_working_tree(pair) -> None:
    a, _b = pair
    # ``a.root`` is this machine's ``~/.coffer``; coffer.db already lives there.
    assert a.db_path.is_file()
    (a.root / "daemon-config.json").write_text('{"port": 8000}\n', encoding="utf-8")
    (a.root / "logs").mkdir()
    (a.root / "logs" / "daemon.log").write_text("a log line\n", encoding="utf-8")
    (a.root / "memory" / "projects" / "p1").mkdir(parents=True)
    (a.root / "memory" / "projects" / "p1" / "fact.md").write_text("fact\n", encoding="utf-8")
    a.write_knowledge("notes", "kept", "kept\n")

    run = await a.adopt()

    assert run.ok, (run.status, run.error)
    tree = a.tree_paths()
    remote = await a.remote_paths()
    assert "knowledge/notes/kept.md" in tree
    for paths in (tree, remote):
        for path in paths:
            name = path.rsplit("/", 1)[-1]
            assert name not in {"coffer.db", "daemon-config.json", "daemon.log", "fact.md"}, path
            assert not path.startswith(("memory/", "logs/")), path


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a round diffs from the pointer stored on this machine"
)
async def test_a_round_diffs_from_the_pointer_stored_on_this_machine(pair) -> None:
    a, _b = pair
    a.write_knowledge("notes", "first", "first\n")
    await a.adopt()
    await a.converge()
    a.write_knowledge("notes", "second", "second\n")
    await a.converge()

    stored = await a.state.pointer()
    descriptor = yaml.safe_load(await a.remote_text(f"machines/{a.machine_id}.yaml") or "")
    published_commit = descriptor["last_converged_commit"]
    # The descriptor is restamped once a day, so what it publishes lags the
    # pointer this machine keeps for itself.
    assert published_commit and published_commit != stored

    a.write_knowledge("notes", "third", "third\n")
    run = await a.converge()

    assert run.status is ConvergeStatus.OK, run.error
    assert [c.path for c in run.published.changes] == ["knowledge/notes/third.md"]
    assert await a.state.pointer() == run.commit


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a drifted working tree is reset to the pointer first"
)
async def test_a_drifted_working_tree_is_reset_to_the_pointer_first(pair) -> None:
    a, _b = pair
    for i in range(10):
        a.write_knowledge("notes", f"n{i}", f"note {i}\n")
    await settle(a)
    pointer = await a.state.pointer()

    # A crashed round left HEAD on a commit that dropped a note the vault holds.
    (a.worktree / "knowledge" / "notes" / "n0.md").unlink()
    assert await a.mirror.stage_all()
    drift = await a.mirror.commit("a round that never finished")
    assert drift != pointer

    run = await a.converge()

    assert run.ok, (run.status, run.error)
    # The drifted commit was discarded before serializing: it is not in the
    # history the round built on and published.
    assert _git(a.remote_url, "merge-base", "--is-ancestor", drift, BRANCH).returncode != 0
    assert "knowledge/notes/n0.md" not in run.published.paths(ChangeStatus.DELETED)
    assert "knowledge/notes/n0.md" in await a.remote_paths()
    assert a.read_knowledge("notes", "n0") == "note 0\n"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a held path leaves the retry set once it applies"
)
async def test_a_held_path_leaves_the_retry_set_once_it_applies(pair) -> None:
    a, b = pair
    await settle(a, b)
    await a.register("mcp_server", "later", {"value": "not-ready"})
    await a.converge()
    path = await a.doc_path("mcp_server", "later")

    b.gate.refuse_value = "not-ready"
    await b.converge()
    retry, _na = await b.state.held_paths()
    assert path in retry

    b.gate.refuse_value = None
    absorbed = await b.converge()

    assert absorbed.failures == ()
    assert await b.find("mcp_server", "later") is not None
    retry, not_applicable = await b.state.held_paths()
    assert path not in retry and path not in not_applicable

    # Out of the set means out of the set: the next round does not try again.
    b.gate.seen.clear()
    after = await b.converge()
    assert after.failures == ()
    assert all(seen.get("value") != "not-ready" for seen in b.gate.seen)


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="an ordinary round on a machine without a pointer still detects the join",
)
async def test_an_ordinary_round_without_a_pointer_still_detects_the_join(roomy) -> None:
    a, b = roomy
    a.write_knowledge("notes", "shared", "shared\n")
    a.write_skill("shared-skill")
    await settle(a, b)
    assert b.has_skill_files("shared-skill")

    # B forgets its pointer; its vault survives.
    b.state.forget()
    b.forget_worktree()
    a.delete_skill_files("shared-skill")
    await a.converge()

    # The ordinary service round — what the timer and ``coffer sync now`` run —
    # not ``coffer sync adopt``.
    await b.remote_config()
    run = await b.service().run_once()

    # Detected and reported, not applied: only an explicit adopt joins.
    assert run.join is JoinKind.RETURNING, (run.status, run.error)
    assert run.status is ConvergeStatus.AWAITING_JOIN, run.error
    assert run.join_report is not None and run.join_report.base is not None
    assert b.has_skill_files("shared-skill")

    joined = await b.service().run_once(adopt=True)
    assert joined.join is JoinKind.RETURNING, (joined.status, joined.error)
    assert joined.status is ConvergeStatus.OK, joined.error
    # The base came from B's descriptor, so A's deletion is applied, not undone.
    assert not b.has_skill_files("shared-skill")
    assert "skills/shared-skill/SKILL.md" not in await b.remote_paths()


@pytest.mark.acceptance(
    spec="vault-sync", scenario="one path that fails to apply does not stop the round"
)
async def test_one_path_that_fails_to_apply_does_not_stop_the_round(pair) -> None:
    a, b = pair
    await settle(a, b)
    await a.register("mcp_server", "broken", {"value": "refused-here"})
    await a.register("mcp_server", "fine", {"value": "fine"})
    a.write_knowledge("notes", "fine", "fine\n")
    await a.converge()
    broken = await a.doc_path("mcp_server", "broken")

    b.gate.refuse_value = "refused-here"
    run = await b.converge()

    assert run.status is ConvergeStatus.OK, run.error
    assert await b.find("mcp_server", "fine") is not None
    assert b.read_knowledge("notes", "fine") == "fine\n"
    assert await b.find("mcp_server", "broken") is None
    assert len(run.failures) == 1
    failed_path, reason = run.failures[0]
    assert failed_path == broken
    assert reason
    assert await b.state.pointer() == run.commit


@pytest.mark.acceptance(spec="vault-sync", scenario="a round never reaches back into history")
async def test_a_round_never_reaches_back_into_history(roomy) -> None:
    a, b = roomy
    for i in range(5):
        a.write_knowledge("notes", f"n{i}", f"note {i}\n")
    await settle(a, b)
    a.delete_knowledge("notes", "n0")
    await settle(a, b)
    assert "knowledge/notes/n0.md" not in await a.remote_paths()
    # It survives only in the remote's history.
    assert _git(a.remote_url, "log", "--oneline", BRANCH, "--", "knowledge/notes/n0.md").stdout

    await settle(a, b)

    assert a.read_knowledge("notes", "n0") is None
    assert b.read_knowledge("notes", "n0") is None
    assert "knowledge/notes/n0.md" not in await a.remote_paths()
