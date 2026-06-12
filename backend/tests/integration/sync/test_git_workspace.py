"""Integration tests for the git transport + workspace IO against real git."""

from __future__ import annotations

import subprocess

import pytest

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


@pytest.mark.acceptance(spec="010-sync", scenario="conflicting edits stop the run for resolution")
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
