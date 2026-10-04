"""The daemon's setup state (spec daemon "Wait in a setup state when git is
missing or too old").

The app is built by ``create_app`` and its lifespan run for real; only the git
check is replaced, so a test can be a machine with no git, an old one, or one
where git appears between two checks. Every test runs in its own HOME.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.infrastructure.vault import git_requirement
from coffer.infrastructure.vault.git_requirement import FoundGit, GitCheck
from coffer.infrastructure.vault.home import vault_root
from coffer.surfaces.http import daemon_restart_routes, setup_state
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.daemon_restart_routes import SelfRestart, get_self_restart

_TOKEN = "setup-token"
_MISSING = GitCheck(usable=None, found=None)
_OLD = GitCheck(usable=None, found=FoundGit(path="/usr/bin/git", version=(2, 30)))
_NEW = FoundGit(path="/opt/homebrew/bin/git", version=(2, 45))


def _no_restart() -> SelfRestart:
    """A restart that starts nothing and exits nothing."""
    return SelfRestart(spawn_successor=lambda: 4242, exit_self=lambda: None)


@pytest.fixture(autouse=True)
def _fresh() -> Iterator[None]:
    daemon_restart_routes.reset_restart_state()
    yield
    setup_state.leave_setup()


def _daemon_json(home: Path) -> None:
    coffer = home / ".coffer"
    coffer.mkdir(parents=True, exist_ok=True)
    (coffer / "daemon.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pid": 1,
                "port": 8123,
                "token": _TOKEN,
                "started_at": datetime.now(tz=UTC).isoformat(),
                "binary_path": "/x",
            }
        )
    )


async def _serving(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *checks: GitCheck
) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    _daemon_json(tmp_path)
    answers = list(checks)
    monkeypatch.setattr(
        git_requirement, "check_git", lambda: answers.pop(0) if len(answers) > 1 else answers[0]
    )
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app),
            base_url="http://127.0.0.1:8123",
            headers={"X-Coffer-Token": _TOKEN},
        ) as client,
    ):
        yield client, app


@pytest.mark.acceptance(
    spec="daemon", scenario="a machine without git starts the daemon in its setup state"
)
async def test_no_git_serves_the_setup_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async for client, _app in _serving(monkeypatch, tmp_path, _MISSING):
        r = await client.get("/api/v1/daemon/status")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "setup"
        setup = body["setup"]
        assert setup["need"] == "git"
        assert setup["reason"] == "git_missing"
        assert setup["found"] is None
        assert setup["needed"] == "2.40"
        assert "git isn't installed on this machine" in setup["message"]
        assert "The vault keeps its history and syncs with git." in setup["message"]
        prompt = setup["handoff"]["prompt"]
        assert "Please install git on this machine." in prompt
        assert "brew" not in prompt and "xcode-select" not in prompt
        # Nothing touching the vault ran: no repository, no first commit.
        assert not (vault_root() / ".git").exists()
        # The web UI is still served (the SPA, or its placeholder from source).
        assert (await client.get("/")).status_code != 503


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a git older than 2.40 puts the daemon in its setup state with a hand-off",
)
async def test_an_old_git_reports_both_versions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async for client, _app in _serving(monkeypatch, tmp_path, _OLD):
        setup = (await client.get("/api/v1/daemon/status")).json()["setup"]
        assert setup["reason"] == "git_too_old"
        assert (setup["found"], setup["needed"]) == ("2.30", "2.40")
        assert "the git on this machine is 2.30" in setup["message"]
        prompt = setup["handoff"]["prompt"]
        assert "Please update git on this machine to version 2.40 or later." in prompt
        assert "run `git --version`" in prompt
        assert "brew" not in prompt and "xcode-select" not in prompt


@pytest.mark.acceptance(spec="daemon", scenario="the setup state refuses what needs the vault")
async def test_the_setup_state_refuses_vault_routes_and_mcp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async for client, _app in _serving(monkeypatch, tmp_path, _MISSING):
        for path in ("/api/v1/resources/mcp_server", "/api/v1/skills", "/mcp"):
            r = await client.get(path)
            assert r.status_code == 503, (path, r.text)
            error = r.json()["error"]
            assert error["code"] == "GIT_NEEDED"
            assert "git isn't installed" in error["message"]
            assert error["details"]["reason"] == "git_missing"
            assert "Please install git" in error["details"]["handoff"]["prompt"]
        # The four open routes still answer.
        assert (await client.get("/api/v1/daemon/status")).status_code == 200
        assert (await client.post("/api/v1/daemon/setup/check")).status_code == 200
        _app.dependency_overrides[get_self_restart] = _no_restart
        # No audit store is wired in the setup state; the restart still answers.
        assert (await client.post("/api/v1/daemon/restart")).status_code == 202


@pytest.mark.acceptance(
    spec="daemon", scenario="check again finds git and the restart finishes the start"
)
async def test_check_again_reports_git_once_it_is_there(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    found = GitCheck(usable=_NEW, found=_NEW, from_login_path=True)
    async for client, _app in _serving(monkeypatch, tmp_path, _MISSING, _MISSING, found):
        still = (await client.post("/api/v1/daemon/setup/check")).json()
        assert still["ready"] is False
        assert still["setup"]["reason"] == "git_missing"

        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        ready = (await client.post("/api/v1/daemon/setup/check")).json()
        assert ready == {"ready": True, "setup": None}
        # The login shell's git comes first for this daemon and its successor.
        assert os.environ["PATH"].split(os.pathsep)[0] == "/opt/homebrew/bin"


async def test_check_again_needs_the_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async for client, _app in _serving(monkeypatch, tmp_path, _MISSING):
        r = await client.post("/api/v1/daemon/setup/check", headers={"X-Coffer-Token": "wrong"})
        assert r.status_code == 401
