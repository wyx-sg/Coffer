"""Integration tests for the git transport + workspace IO against real git."""

from __future__ import annotations

import subprocess

from coffer.domain.sync.manifest import Manifest
from coffer.infrastructure.sync.git_repo import GitRepo
from coffer.infrastructure.sync.workspace import Workspace


def _bare_remote(tmp_path):  # type: ignore[no-untyped-def]
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    return remote


def _seed_file(repo: GitRepo, ws, name: str, content: str) -> None:  # type: ignore[no-untyped-def]
    (ws / name).write_text(content, encoding="utf-8")


def test_first_push_then_clone_round_trips(tmp_path) -> None:  # type: ignore[no-untyped-def]
    remote = _bare_remote(tmp_path)

    ws_a = tmp_path / "a"
    repo_a = GitRepo(ws_a)
    repo_a.ensure_repo(str(remote), "main")
    _seed_file(repo_a, ws_a, "hello.txt", "from A\n")
    assert repo_a.commit_all("first") is True
    repo_a.pull("main")  # empty remote: no-op
    repo_a.push("main")

    ws_b = tmp_path / "b"
    repo_b = GitRepo(ws_b)
    repo_b.ensure_repo(str(remote), "main")
    repo_b.pull("main")
    assert (ws_b / "hello.txt").read_text() == "from A\n"


def test_commit_all_noop_when_clean(tmp_path) -> None:  # type: ignore[no-untyped-def]
    remote = _bare_remote(tmp_path)
    ws = tmp_path / "a"
    repo = GitRepo(ws)
    repo.ensure_repo(str(remote), "main")
    _seed_file(repo, ws, "x.txt", "1\n")
    assert repo.commit_all("c1") is True
    assert repo.commit_all("c2") is False  # nothing changed


# No acceptance marker: this exercises the git-plumbing conflict/resolve
# primitives only; the auto-resolve scenario is covered at the service level
# (test_two_machine_sync.test_conflict_auto_resolves_newest_wins).
def test_conflicting_edits_detected_then_resolved(tmp_path) -> None:  # type: ignore[no-untyped-def]
    remote = _bare_remote(tmp_path)

    ws_a = tmp_path / "a"
    repo_a = GitRepo(ws_a)
    repo_a.ensure_repo(str(remote), "main")
    _seed_file(repo_a, ws_a, "f.txt", "base\n")
    repo_a.commit_all("base")
    repo_a.pull("main")
    repo_a.push("main")

    ws_b = tmp_path / "b"
    repo_b = GitRepo(ws_b)
    repo_b.ensure_repo(str(remote), "main")
    repo_b.pull("main")

    # Both machines edit the same line, A pushes first.
    _seed_file(repo_a, ws_a, "f.txt", "from A\n")
    repo_a.commit_all("a-edit")
    repo_a.pull("main")
    repo_a.push("main")

    _seed_file(repo_b, ws_b, "f.txt", "from B\n")
    repo_b.commit_all("b-edit")
    outcome = repo_b.pull("main")
    assert outcome.is_conflict
    assert "f.txt" in outcome.conflicted_paths
    assert repo_b.has_conflicts()

    # Resolve in favour of theirs (A's version) and the tree is clean again.
    repo_b.resolve("theirs", ["f.txt"])
    assert not repo_b.has_conflicts()
    assert (ws_b / "f.txt").read_text() == "from A\n"


def test_workspace_manifest_and_docs_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ws = Workspace(tmp_path / "ws")
    manifest = Manifest()
    ws.write_manifest(manifest)
    assert ws.read_manifest() == manifest

    ws.write_resource_docs(
        [
            {
                "kind": "mcp_server",
                "name": "confluence",
                "description": "wiki",
                "enabled": True,
                "config": {"transport": {"kind": "stdio"}},
            }
        ]
    )
    docs = ws.read_resource_docs()
    assert len(docs) == 1
    assert docs[0].name == "confluence"
    assert docs[0].config == {"transport": {"kind": "stdio"}}


def test_workspace_credential_blobs_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ws = Workspace(tmp_path / "ws")
    ws.write_credential_blobs({"cred-a": b"gAAAAAtoken", "cred-b": b"gAAAAAother"})
    blobs = ws.read_credential_blobs()
    assert blobs == {"cred-a": b"gAAAAAtoken", "cred-b": b"gAAAAAother"}


def test_workspace_namespaced_credential_blobs_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Credential refs are namespaced with slashes (e.g. channel/seatalk/app-secret,
    # provider/agnes/key). Writing must create the nested parent dirs, and reading
    # must reconstruct the full slash ref — not just the file stem.
    refs = {
        "channel/seatalk/app-secret": b"gAAAAAseatalk",
        "channel/telegram/bot-token": b"gAAAAAtelegram",
        "provider/agnes/key": b"gAAAAAagnes",
        "flat.LEGACY_KEY": b"gAAAAAlegacy",
    }
    ws = Workspace(tmp_path / "ws")
    ws.write_credential_blobs(refs)
    assert ws.read_credential_blobs() == refs


def test_machine_entry_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    from coffer.domain.sync.models import MachineEntry

    ws = Workspace(tmp_path / "ws", trees=[])
    entry = MachineEntry(
        machine_id="01AAAAAAAAAAAAAAAAAAAAAAAA",
        display_name="studio",
        platform="darwin",
        os_version="25.5.0",
        coffer_version="0.1.1",
        last_sync_at=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
    )
    ws.write_machine_entry(entry)
    # Writing one machine's entry never touches another's.
    other = MachineEntry(machine_id="01BBBBBBBBBBBBBBBBBBBBBBBB", display_name="laptop")
    ws.write_machine_entry(other)

    entries = {e.machine_id: e for e in ws.read_machine_entries()}
    assert entries[entry.machine_id] == entry
    assert entries[other.machine_id].display_name == "laptop"
    assert entries[other.machine_id].last_sync_at is None


def test_git_has_changes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    remote = _bare_remote(tmp_path)
    ws = tmp_path / "a"
    repo = GitRepo(ws)
    repo.ensure_repo(str(remote), "main")
    assert repo.has_changes() is False
    _seed_file(repo, ws, "x.txt", "1\n")
    assert repo.has_changes() is True
    repo.commit_all("c")
    assert repo.has_changes() is False


def test_credential_case_alias_converges_to_local_casing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A ref differing from an existing blob only by case must replace it —
    two case variants in one git index break every checkout on macOS (the
    2026-07-10 pre-v3 `telegram/` vs `Telegram/` incident)."""
    ws = Workspace(tmp_path / "ws")
    ws.write_credential_blobs({"channel/telegram/bot-token": b"old"})
    ws.write_credential_blobs({"channel/Telegram/bot-token": b"new"}, delete_missing=False)
    blobs = ws.read_credential_blobs()
    assert blobs == {"channel/Telegram/bot-token": b"new"}


def test_credential_blobs_preserved_until_first_import(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Foreign ciphertext (arrived via pull, not yet imported) survives an
    export with delete_missing=False and is removed once deletions are allowed."""
    ws = Workspace(tmp_path / "ws")
    ws.write_credential_blobs({"foreign-ref": b"theirs"})
    ws.write_credential_blobs({"local-ref": b"ours"}, delete_missing=False)
    assert set(ws.read_credential_blobs()) == {"foreign-ref", "local-ref"}
    ws.write_credential_blobs({"local-ref": b"ours"}, delete_missing=True)
    assert set(ws.read_credential_blobs()) == {"local-ref"}


def test_mirror_out_without_deletions_keeps_foreign_tree_files(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """delete_missing=False mirror-out copies local adds/changes but never
    deletes workspace files absent locally (the first-sync merge guard)."""
    live = tmp_path / "live-knowledge"
    live.mkdir(parents=True)
    (live / "mine.md").write_text("mine\n", encoding="utf-8")
    ws = Workspace(tmp_path / "ws", trees=[("knowledge", live)])
    ws_tree = tmp_path / "ws" / "knowledge"
    ws_tree.mkdir(parents=True)
    (ws_tree / "foreign.md").write_text("theirs\n", encoding="utf-8")

    ws.mirror_trees_out(delete_missing=False)
    assert (ws_tree / "mine.md").read_text() == "mine\n"
    assert (ws_tree / "foreign.md").read_text() == "theirs\n"

    ws.mirror_trees_out(delete_missing=True)
    assert not (ws_tree / "foreign.md").exists()


def test_tombstone_round_trips_slashed_credential_refs(tmp_path):
    """Credential tombstones use the ref as the name; refs contain slashes
    (channel/Telegram/bot-token), so the file nests below the kind dir and
    must still round-trip through write/read/remove."""
    from datetime import UTC, datetime

    from coffer.domain.sync.models import Tombstone

    ws = Workspace(tmp_path / "ws")
    ts = Tombstone(
        kind="credential",
        name="channel/Telegram/bot-token",
        deleted_at=datetime(2026, 7, 10, tzinfo=UTC),
        by="M1",
    )
    ws.write_tombstone(ts)
    got = ws.read_tombstones()
    assert [(t.kind, t.name) for t in got] == [("credential", "channel/Telegram/bot-token")]
    ws.remove_tombstone("credential", "channel/Telegram/bot-token")
    assert ws.read_tombstones() == []
