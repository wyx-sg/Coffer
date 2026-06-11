"""Real-Git coverage for `_git_fetch_ref` — the init + fetch + checkout flow.

`test_skill_service.py` stubs the fetcher, so the actual Git invocation is
exercised only here. Each test drives a throwaway local repository, so no
network and no `check_url` round-trip is involved.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import shutil
import subprocess

import pytest

from coffer.domain.errors import SourceFetchError
from coffer.infrastructure.skill import source_fetcher
from coffer.infrastructure.skill.source_fetcher import _git_fetch_ref, _run_git

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


@pytest.fixture(autouse=True)
def _allow_file_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fetcher only enables git's `file` transport under this test-only
    knob (CODE-L5); these tests fetch from throwaway local repos."""
    monkeypatch.setenv("COFFER_GIT_ALLOW_FILE", "1")


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
async def test_check_url_runs_off_the_event_loop(tmp_path, monkeypatch):
    """CODE-M4: the SSRF guard's blocking DNS resolution (socket.getaddrinfo)
    must be offloaded to a worker thread so a slow/unresponsive resolver cannot
    freeze the whole daemon event loop (every session, every route).

    We prove the offload by recording the thread `check_url` runs on and
    asserting it is NOT the main thread (the event loop's thread).
    """
    import threading

    from coffer.infrastructure.skill.source_fetcher import GitSourceFetcher

    main_thread = threading.current_thread()
    seen: dict[str, threading.Thread] = {}

    def _recording_check_url(url: str) -> str:
        seen["thread"] = threading.current_thread()
        return url

    monkeypatch.setattr(source_fetcher, "check_url", _recording_check_url)

    # Force _git_fetch_ref to no-op so the test stays offline and fast — we only
    # care that check_url was reached and ran off-loop.
    async def _noop_fetch(**kwargs):
        (kwargs["dest"] / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\n")

    monkeypatch.setattr(source_fetcher, "_git_fetch_ref", _noop_fetch)

    fetcher = GitSourceFetcher()
    async with fetcher.fetched(git_url="https://example.com/r.git", git_ref="main"):
        pass

    assert "thread" in seen, "check_url was never invoked"
    assert seen["thread"] is not main_thread, "check_url ran on the event-loop thread"


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
async def test_timeout_kills_and_reaps_subprocess(tmp_path, monkeypatch):
    """On timeout the child is killed AND awaited, so no zombie/warning leaks.

    A real `git` against a local repo finishes too fast to time out reliably,
    so we stub `create_subprocess_exec` with a process whose `communicate()`
    blocks forever. The timeout branch must call both `kill()` and `wait()`.
    """
    killed = {"value": False}
    waited = {"value": False}

    class _HangingProc:
        returncode = None

        async def communicate(self):
            await asyncio.Event().wait()  # never resolves

        def kill(self):
            killed["value"] = True

        async def wait(self):
            waited["value"] = True
            return 0

    async def _fake_exec(*args, **kwargs):
        return _HangingProc()

    monkeypatch.setattr(source_fetcher.asyncio, "create_subprocess_exec", _fake_exec)

    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(SourceFetchError) as exc:
        await _run_git(["fetch"], cwd=dest, timeout=0.05)
    assert exc.value.reason == "fetch_timed_out"
    assert killed["value"] is True
    assert waited["value"] is True


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
