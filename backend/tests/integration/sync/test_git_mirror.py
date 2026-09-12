"""The git adapter, against a real local bare repository — no network.

Spec vault-export-import ``## Backup``. These tests shell out to the real git
binary on purpose: the adapter's whole job is to be right about git's actual
behaviour, and a mocked subprocess would only assert our own assumptions.
"""

from __future__ import annotations

import pathlib
import subprocess
import tempfile

import pytest

from coffer.infrastructure.sync.git_mirror import GitMirror, GitMirrorError


@pytest.fixture
def remote(tmp_path: pathlib.Path) -> pathlib.Path:
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )
    return bare


@pytest.fixture
def worktree(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "worktree"


@pytest.mark.asyncio
async def test_ensure_repo_initializes_and_sets_origin(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    assert (worktree / ".git").is_dir()
    out = subprocess.run(
        ["git", "-C", str(worktree), "remote", "get-url", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip() == str(remote)


@pytest.mark.asyncio
async def test_ensure_repo_adopts_an_existing_repository(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    worktree.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(worktree)], check=True, capture_output=True)
    (worktree / "already-here.txt").write_text("kept")
    subprocess.run(["git", "-C", str(worktree), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-m",
            "history",
        ],
        check=True,
        capture_output=True,
    )

    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")

    log = subprocess.run(
        ["git", "-C", str(worktree), "log", "--oneline"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "history" in log.stdout
    assert (worktree / "already-here.txt").exists()


@pytest.mark.asyncio
async def test_stage_all_reports_whether_anything_changed(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    assert await mirror.stage_all() is False

    (worktree / "a.txt").write_text("one")
    assert await mirror.stage_all() is True
    await mirror.commit("first")
    assert await mirror.stage_all() is False


@pytest.mark.asyncio
async def test_commit_and_push_reach_the_remote(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    sha = await mirror.commit("first")
    assert sha
    await mirror.push(branch="main", token=None)

    out = subprocess.run(
        ["git", "-C", str(remote), "log", "--oneline", "main"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "first" in out.stdout


@pytest.mark.asyncio
async def test_push_failure_raises_with_a_redacted_message(
    worktree: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    missing = tmp_path / "nope.git"
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(missing), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    await mirror.commit("first")

    with pytest.raises(GitMirrorError) as excinfo:
        await mirror.push(branch="main", token="sup3rsecret")
    assert "sup3rsecret" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_unpushed_commits_are_detected(worktree: pathlib.Path, remote: pathlib.Path) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    await mirror.commit("first")
    assert await mirror.has_unpushed(branch="main") is True
    await mirror.push(branch="main", token=None)
    assert await mirror.has_unpushed(branch="main") is False


@pytest.mark.asyncio
async def test_resolve_revision_accepts_a_date(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    first = await mirror.commit("first")
    (worktree / "a.txt").write_text("two")
    await mirror.stage_all()
    await mirror.commit("second")

    resolved = await mirror.resolve_revision("2999-01-01")
    assert resolved  # a far-future date resolves to the tip
    assert (await mirror.resolve_revision(first)).startswith(first[:7])


@pytest.mark.acceptance(
    spec="vault-export-import",
    scenario="the push credential never reaches the repository",
)
@pytest.mark.asyncio
async def test_the_token_never_lands_in_git_config(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    await mirror.commit("first")
    await mirror.push(branch="main", token="sup3rsecret")
    assert "sup3rsecret" not in (worktree / ".git" / "config").read_text()


@pytest.mark.asyncio
async def test_the_askpass_helper_does_not_outlive_the_push(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    """The helper carrying the token is deleted even though the push succeeded."""
    tmp = pathlib.Path(tempfile.gettempdir())
    before = set(tmp.glob("coffer-askpass-*"))
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    await mirror.commit("first")
    await mirror.push(branch="main", token="sup3rsecret")
    assert set(tmp.glob("coffer-askpass-*")) == before


@pytest.mark.asyncio
async def test_ensure_repo_repoints_a_changed_origin(
    worktree: pathlib.Path, remote: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    other = tmp_path / "other.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(other)], check=True, capture_output=True
    )
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(other), branch="main")
    await mirror.ensure_repo(remote_url=str(remote), branch="main")

    out = subprocess.run(
        ["git", "-C", str(worktree), "remote", "get-url", "origin"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip() == str(remote)


@pytest.mark.asyncio
async def test_a_date_before_any_backup_has_no_revision(
    worktree: pathlib.Path, remote: pathlib.Path
) -> None:
    mirror = GitMirror(worktree)
    await mirror.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await mirror.stage_all()
    await mirror.commit("first")

    with pytest.raises(GitMirrorError):
        await mirror.resolve_revision("2000-01-01")


@pytest.mark.asyncio
async def test_clone_then_read_an_earlier_revision_and_come_back(
    worktree: pathlib.Path, remote: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """The restore path on a machine with no working tree of its own."""
    source = GitMirror(worktree)
    await source.ensure_repo(remote_url=str(remote), branch="main")
    (worktree / "a.txt").write_text("one")
    await source.stage_all()
    first = await source.commit("first")
    (worktree / "a.txt").write_text("two")
    await source.stage_all()
    await source.commit("second")
    await source.push(branch="main", token=None)

    fresh_path = tmp_path / "fresh"
    fresh = GitMirror(fresh_path)
    await fresh.clone(remote_url=str(remote), branch="main", token=None)
    assert (fresh_path / "a.txt").read_text() == "two"
    await fresh.fetch(token=None)
    assert await fresh.head() is not None

    await fresh.checkout(await fresh.resolve_revision(first))
    assert (fresh_path / "a.txt").read_text() == "one"

    await fresh.checkout_branch("main")
    assert (fresh_path / "a.txt").read_text() == "two"
