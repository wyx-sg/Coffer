"""Real-Git coverage for `_git_fetch_ref` — the init + fetch + checkout flow.

`test_skill_service.py` stubs the fetcher, so the actual Git invocation is
exercised only here. Each test drives a throwaway local repository, so no
network and no `check_url` round-trip is involved.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

from coffer.domain.errors import SourceFetchError
from coffer.infrastructure.skill.source_fetcher import _git_fetch_ref

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _git(args: list[str], cwd: pathlib.Path) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=_GIT_ENV,
    )
    return out.stdout.strip()


def _make_repo(path: pathlib.Path) -> str:
    """Create a one-commit repo with branch `main` and tag `v1`; return the SHA."""
    path.mkdir(parents=True, exist_ok=True)
    _git(["-c", "init.defaultBranch=main", "init", "--quiet"], cwd=path)
    # Allow fetching a bare SHA from this repo over the local transport.
    _git(["config", "uploadpack.allowAnySHA1InWant", "true"], cwd=path)
    _git(["config", "uploadpack.allowReachableSHA1InWant", "true"], cwd=path)
    (path / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\nbody\n")
    _git(["add", "-A"], cwd=path)
    _git(["commit", "--quiet", "-m", "first"], cwd=path)
    _git(["tag", "v1"], cwd=path)
    return _git(["rev-parse", "HEAD"], cwd=path)


@pytest.mark.asyncio
async def test_fetch_by_commit_sha(tmp_path):
    """The headline fix: a bare commit SHA is a valid ref (git clone --branch can't)."""
    repo = tmp_path / "upstream"
    sha = _make_repo(repo)
    dest = tmp_path / "dest"
    dest.mkdir()
    await _git_fetch_ref(git_url=str(repo), git_ref=sha, dest=dest, timeout=30.0)
    assert (dest / "SKILL.md").is_file()


@pytest.mark.asyncio
async def test_fetch_by_branch(tmp_path):
    repo = tmp_path / "upstream"
    _make_repo(repo)
    dest = tmp_path / "dest"
    dest.mkdir()
    await _git_fetch_ref(git_url=str(repo), git_ref="main", dest=dest, timeout=30.0)
    assert (dest / "SKILL.md").is_file()


@pytest.mark.asyncio
async def test_fetch_by_tag(tmp_path):
    repo = tmp_path / "upstream"
    _make_repo(repo)
    dest = tmp_path / "dest"
    dest.mkdir()
    await _git_fetch_ref(git_url=str(repo), git_ref="v1", dest=dest, timeout=30.0)
    assert (dest / "SKILL.md").is_file()


@pytest.mark.asyncio
async def test_rejects_option_like_ref(tmp_path):
    """A git_ref starting with '-' must be rejected before any subprocess runs."""
    repo = tmp_path / "upstream"
    _make_repo(repo)
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(SourceFetchError) as exc:
        await _git_fetch_ref(
            git_url=str(repo),
            git_ref="--upload-pack=/bin/false",
            dest=dest,
            timeout=30.0,
        )
    assert exc.value.reason == "invalid_git_ref"
