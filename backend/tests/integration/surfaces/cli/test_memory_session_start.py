"""``coffer memory session-start``, as an agent's hook runs it (spec memory
"Hand a session its project's memories at start"). In process against the
Typer app, with no daemon: the hook reads the hub's files directly."""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest
from typer.testing import CliRunner

from coffer.infrastructure.vault.home import vault_root
from coffer.surfaces.cli.main import app

_runner = CliRunner()


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "work" / "pay"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/acme/pay"],
        check=True,
    )
    topic = vault_root() / "memory" / "projects" / "github.com-acme-pay" / "testing.md"
    topic.parent.mkdir(parents=True)
    topic.write_text(
        "---\ntitle: Testing\ntype: feedback\nupdated: 2026-11-19\n---\n\nNever mock the vault.\n",
        encoding="utf-8",
    )
    return repo


@pytest.mark.acceptance(
    spec="memory", scenario="a session is handed its memories by the agent's hook"
)
def test_the_hook_prints_the_sessions_memories(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    out = _runner.invoke(app, ["memory", "session-start"], input=json.dumps({"cwd": str(repo)}))
    assert out.exit_code == 0, out.output
    assert '<coffer-memory project="github.com/acme/pay">' in out.stdout
    assert "Never mock the vault." in out.stdout
    assert "~/.coffer/vault/memory/projects/github.com-acme-pay/" in out.stdout


@pytest.mark.acceptance(
    spec="memory", scenario="a Coffer-started session is not handed its memories twice"
)
def test_a_session_coffer_started_or_outside_a_repo_gets_nothing(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    stdin = json.dumps({"cwd": str(repo)})
    twice = _runner.invoke(
        app, ["memory", "session-start"], input=stdin, env={"COFFER_MEMORY_IN_PROMPT": "1"}
    )
    assert twice.exit_code == 0 and twice.stdout == ""

    loose = tmp_path / "loose"
    loose.mkdir()
    outside = _runner.invoke(
        app, ["memory", "session-start"], input=json.dumps({"cwd": str(loose)})
    )
    assert outside.exit_code == 0 and outside.stdout == ""
    # Input it cannot read never fails the session.
    junk = _runner.invoke(app, ["memory", "session-start"], input="not json")
    assert junk.exit_code == 0
