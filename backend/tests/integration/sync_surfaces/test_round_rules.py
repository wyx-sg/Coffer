"""Round rules the Sync page and the CLI rely on (spec vault-sync): a quiet
round makes no commit, the reconciler runs after a round that applied
something, a stale machine takes a deletion, a hold is asked again once a
side moves, curation waits while a round waits, the master key never
travels, and the routes cover every operation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundStatus
from coffer.domain.sync.stops import Answer

from .harness import joined

DOC = "knowledge/team/on-call.md"


def _remote_files(url: str) -> list[str]:
    done = subprocess.run(
        ["git", "--git-dir", url, "ls-tree", "-r", "--name-only", "main"],
        capture_output=True,
        check=True,
    )
    return done.stdout.decode().split()


@pytest.mark.acceptance(spec="vault-sync", scenario="an unchanged vault makes no commit")
def test_a_round_with_nothing_to_say_makes_no_commit(tmp_path: Path) -> None:
    (mac,) = joined(tmp_path, "Mac")
    head = mac.repo.head()
    got = mac.round()
    assert got.status is RoundStatus.NOTHING_TO_DO
    assert mac.repo.head() == head
    assert mac.run(mac.history.recent(1))[0].status is RoundStatus.NOTHING_TO_DO


@pytest.mark.acceptance(spec="vault-sync", scenario="a remote addition lands in the vault")
@pytest.mark.acceptance(
    spec="vault-sync", scenario="a round that applied changes runs one reconcile pass"
)
def test_the_reconciler_runs_once_after_a_round_that_applied_something(tmp_path: Path) -> None:
    mac, mini = joined(tmp_path, "Mac", "Mini")
    passes: list[int] = []

    async def reconcile() -> None:
        passes.append(1)

    mini.service._after_apply = reconcile
    mac.put("knowledge/team/deploy.md", "Deploy on Tuesdays.\n")
    mac.round()
    assert mini.round().applied
    assert passes == [1]
    assert mini.round().status is RoundStatus.NOTHING_TO_DO
    assert passes == [1]


@pytest.mark.acceptance(spec="vault-sync", scenario="a round diffs from the shared history")
@pytest.mark.acceptance(spec="vault-sync", scenario="a stale machine does not resurrect a deletion")
def test_a_machine_that_did_not_touch_a_file_takes_its_deletion(tmp_path: Path) -> None:
    mac, mini = joined(tmp_path, "Mac", "Mini")
    for i in range(10):  # so one deletion is not a mass deletion
        mac.put(f"knowledge/team/filler-{i}.md", f"filler {i}\n")
    mac.round()
    mini.round()
    mac.remove(DOC)
    mac.round()
    mini.put("knowledge/team/mini.md", "written while behind\n")
    assert mini.round().status is RoundStatus.PULLED_AND_PUSHED
    assert mini.disk(DOC) is None
    mac.round()
    assert mac.disk(DOC) is None
    assert DOC not in _remote_files(mac.url)


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a hold is released once its diff no longer breaches"
)
def test_a_hold_is_asked_again_once_the_files_came_back(tmp_path: Path) -> None:
    (mac,) = joined(tmp_path, "Mac")
    paths = [f"knowledge/bulk/n{i:02}.md" for i in range(22)]
    for p in paths:
        mac.put(p, p)
    mac.round()
    mac.remove(*paths)
    assert mac.round().status is RoundStatus.HELD
    for p in paths:
        mac.put(p, p)
    got = mac.round()
    assert got.status is not RoundStatus.HELD
    assert mac.state.stop() is None


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a curation pass is skipped while a round is unresolved"
)
def test_curation_is_told_to_wait_while_a_round_waits_for_a_person(tmp_path: Path) -> None:
    mac, mini = joined(tmp_path, "Mac", "Mini")
    assert mini.run(mini.service.divergence_outstanding()) is False
    mac.put(DOC, "Mac rotates on Mondays.\n")
    mac.round()
    mini.put(DOC, "Mini rotates on Fridays.\n")
    assert mini.round().status is RoundStatus.STOPPED
    assert mini.run(mini.service.divergence_outstanding()) is True
    mini.run(mini.service.answer(DOC, Answer.MINE))
    mini.run(mini.service.continue_round())
    assert mini.run(mini.service.divergence_outstanding()) is False


@pytest.mark.acceptance(spec="vault-sync", scenario="the master key never enters the repository")
def test_a_remote_carrying_secret_holds_ciphertext_and_no_key(tmp_path: Path) -> None:
    (mac,) = joined(tmp_path, "Mac")
    # The key file sits beside the vault, as ~/.coffer/master.key does.
    (mac.root / "master.key").write_bytes(b"not-a-real-key-but-never-pushed\n")
    mac.run(mac.service.set_remote(SyncRemote(url=mac.url, include_secret=True)))
    mac.run(mac.service.join())
    mac.put("secret/provider/p1/key.enc", "gAAAAAB-ciphertext\n")
    mac.round()
    files = _remote_files(mac.url)
    assert "secret/provider/p1/key.enc" in files
    assert not any("master" in f or f.endswith(".key") for f in files)
    assert {f.split("/")[0] for f in files} <= {"knowledge", "machines", "secret", "manifest.json"}
    for f in files:
        blob = subprocess.run(
            ["git", "--git-dir", mac.url, "show", f"main:{f}"], capture_output=True, check=True
        ).stdout
        assert b"not-a-real-key" not in blob


@pytest.mark.acceptance(spec="vault-sync", scenario="the HTTP API serves every sync operation")
def test_the_routes_cover_every_sync_operation() -> None:
    import coffer.surfaces.http.sync_routes
    import coffer.surfaces.http.sync_stop_routes  # noqa: F401  (registers on the router)
    from coffer.surfaces.http.sync_dependencies import router

    served = {
        (method, str(getattr(route, "path", "")).removeprefix(router.prefix))
        for route in router.routes
        for method in getattr(route, "methods", ())
    }
    wanted = {
        ("GET", "/status"),
        ("POST", "/run"),
        ("GET", "/runs"),
        ("GET", "/runs/{run_id}"),
        ("GET", "/runs/{run_id}/rollback-plan"),
        ("POST", "/runs/{run_id}/rollback"),
        ("GET", "/remote"),
        ("PUT", "/remote"),
        ("DELETE", "/remote"),
        ("POST", "/remote/check"),
        ("GET", "/join/preview"),
        ("POST", "/join"),
        ("GET", "/join-choices"),
        ("POST", "/join-choices"),
        ("GET", "/stop"),
        ("POST", "/stop/files/answer"),
        ("POST", "/stop/files/editor"),
        ("GET", "/stop/files/versions"),
        ("POST", "/stop/handoff"),
        ("POST", "/stop/files/discard"),
        ("POST", "/join-choices/editor"),
        ("POST", "/join-choices/handoff"),
        ("POST", "/join-choices/discard"),
        ("POST", "/remote/restore"),
        ("POST", "/machines/{machine_id}/restore"),
        ("POST", "/continue"),
        ("POST", "/hold/confirm"),
        ("POST", "/hold/restore"),
        ("POST", "/plaintext/push-anyway"),
        ("GET", "/machines"),
        ("PATCH", "/machines/self"),
        ("DELETE", "/machines/{machine_id}"),
        ("GET", "/key/fingerprint"),
        ("POST", "/key/import"),
    }
    assert wanted <= served, sorted(wanted - served)
    assert not any("key/export" in path for _m, path in served)


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an arriving memory trigger is written into the vault"
)
def test_a_memory_trigger_reaches_the_other_machine(tmp_path: Path) -> None:
    mac, mini = joined(tmp_path, "Mac", "Mini")
    trigger = "memory-triggers/standup.md"
    body = "---\nwhen: every weekday\n---\nSummarise yesterday.\n"
    mac.put(trigger, body)
    mac.round()
    mini.round()
    assert mini.disk(trigger) == body.encode()
