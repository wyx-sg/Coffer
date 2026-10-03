"""The opt-in statusline wrapper: forwards rate limits, always chains the original."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli import _client, usage_cmd
from coffer.surfaces.cli.main import app

_STDIN = json.dumps(
    {
        "model": {"id": "claude-opus-4-6"},
        "rate_limits": {"five_hour": {"used_percentage": 12, "resets_at": 1790000000}},
    }
)


def _original(tmp_path: Path) -> str:
    """A statusLine command that echoes its stdin's model and exits 3."""
    script = tmp_path / "orig.py"
    script.write_text(
        "import json, sys\n"
        "data = json.load(sys.stdin)\n"
        "print('orig:' + data['model']['id'])\n"
        "sys.exit(3)\n"
    )
    return f"{sys.executable} {script}"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the user's statusline command still runs with the daemon down",
)
def test_original_runs_with_the_same_stdin_when_the_daemon_is_down(
    tmp_path: Path, monkeypatch: Any
) -> None:
    # No daemon.json at all: nothing is spawned, nothing waits.
    monkeypatch.setattr(_client, "discover", lambda: None)
    spawned: list[bool] = []
    monkeypatch.setattr(_client, "client_or_exit", lambda: spawned.append(True))
    result = CliRunner().invoke(
        app, ["usage", "statusline", "--", _original(tmp_path)], input=_STDIN
    )
    assert result.exit_code == 3
    assert result.output == "orig:claude-opus-4-6\n"
    assert spawned == []


def test_a_dead_daemon_port_is_ignored_too(tmp_path: Path, monkeypatch: Any) -> None:
    info = DaemonInfo(
        version=1,
        pid=os.getpid(),
        port=1,
        token="t",
        started_at=datetime.now(tz=UTC),
        binary_path="x",
    )
    monkeypatch.setattr(_client, "discover", lambda: info)
    result = CliRunner().invoke(
        app, ["usage", "statusline", "--", _original(tmp_path)], input=_STDIN
    )
    assert (result.exit_code, result.output) == (3, "orig:claude-opus-4-6\n")


def test_forwards_rate_limits_to_a_running_daemon(tmp_path: Path, monkeypatch: Any) -> None:
    info = DaemonInfo(
        version=1,
        pid=os.getpid(),
        port=8123,
        token="tok",
        started_at=datetime.now(tz=UTC),
        binary_path="x",
    )
    monkeypatch.setattr(_client, "discover", lambda: info)
    sent: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        sent.append({"url": url, **kwargs})
        return httpx.Response(200, json={"accepted": True})

    monkeypatch.setattr(usage_cmd.httpx, "post", fake_post)
    result = CliRunner().invoke(app, ["usage", "statusline"], input=_STDIN)
    # With no original command the wrapper prints nothing.
    assert (result.exit_code, result.output) == (0, "")
    (call,) = sent
    assert call["url"] == "http://127.0.0.1:8123/api/v1/usage/quota/statusline"
    assert call["json"] == {"rate_limits": json.loads(_STDIN)["rate_limits"]}
    assert call["headers"] == {"X-Coffer-Token": "tok"}
    assert call["timeout"] <= 1.0


def test_argv_form_and_a_missing_command(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(_client, "discover", lambda: None)
    script = _original(tmp_path).split(" ")
    result = CliRunner().invoke(app, ["usage", "statusline", "--", *script], input=_STDIN)
    assert (result.exit_code, result.output) == (3, "orig:claude-opus-4-6\n")
    assert usage_cmd.run_original([str(tmp_path / "nope"), "x"], b"") == 127
    # Garbage on stdin is not Coffer's problem either.
    usage_cmd.forward_statusline(b"\xff not json")


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a quota read hands the statusline opt-in to an agent"
)
def test_quota_prompt_prints_the_hand_off_and_nothing_once_a_value_is_seen(
    monkeypatch: Any,
) -> None:
    prompt = "Edit /home/me/.claude/settings.json: add statusLine ..."
    served = {
        "agents": [
            {"agent_type": "claude_code", "windows": [], "handoff": {"prompt": prompt}},
            {"agent_type": "codex", "windows": [], "handoff": None},
        ]
    }

    def client() -> tuple[httpx.Client, None]:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=served))
        return httpx.Client(base_url="http://coffer.test/api/v1", transport=transport), None

    monkeypatch.setattr(usage_cmd._cli_client, "client_or_exit", client)
    out = CliRunner().invoke(app, ["usage", "quota", "--prompt"])
    assert (out.exit_code, out.output) == (0, prompt + "\n")

    served["agents"][0] = {"agent_type": "claude_code", "windows": [], "handoff": None}
    out = CliRunner().invoke(app, ["usage", "quota", "--prompt"])
    assert out.exit_code == 0 and prompt not in out.output
    assert "nothing to set up" in out.output
