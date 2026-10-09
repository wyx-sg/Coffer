"""``coffer memory hook`` and ``coffer memory delivered`` (spec memory "Fail
open when Coffer cannot answer", "Install delivery hooks explicitly and
removably", "Count what memory delivered and what was read", "Show what each
agent is given at session start").

``hook`` is run the way an agent's hook runner runs it: through the CLI with
the agent's own hook JSON on stdin. Its only ways out of the process are
``live_daemon`` and ``httpx.post``, so the fail-open tests replace exactly
those; the daemon-backed tests boot the whole app on a fake home
(``tests/integration/memory/_hook_app.py``), connect both agents, read the
command each one's settings file now carries, and run that.
"""

from __future__ import annotations

import json
import pathlib
import shlex
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

import coffer.surfaces.cli.memory_hook_cmd as memory_hook_cmd
from coffer.domain.channel_turn import CHANNEL_TURN_ENV
from coffer.domain.memory.delivery import MARKER
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from tests.integration.memory._hook_app import (
    HookApp,
    boot,
    distilled,
    register,
)

_runner = CliRunner()
_PROMPT = "why does make verify fail with undici AbortSignal under node"


def _hook(stdin: dict[str, Any], *, uid: str = "agent-uid", cwd: str = "") -> Any:
    return _runner.invoke(
        cli_app,
        ["memory", "hook", "--agent-uid", uid, "--cwd", cwd],
        input=json.dumps(stdin),
    )


def _events(cwd: str) -> list[dict[str, Any]]:
    common = {"session_id": "s1", "cwd": cwd}
    return [
        {"hook_event_name": "SessionStart", "source": "startup", **common},
        {"hook_event_name": "UserPromptSubmit", "prompt": _PROMPT, **common},
    ]


# --- fail open ------------------------------------------------------------------------


def _info() -> DaemonInfo:
    from datetime import UTC, datetime

    return DaemonInfo(
        version=1,
        pid=1,
        port=59999,
        token="t",
        started_at=datetime.now(tz=UTC),
    )


@pytest.mark.acceptance(
    spec="memory", scenario="the hook prints nothing and exits 0 with no daemon"
)
def test_no_daemon_prints_nothing_and_exits_0(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    looked: list[bool] = []

    def _no_daemon() -> None:
        looked.append(True)
        return None

    def _never(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("no daemon means no request")

    monkeypatch.setattr(memory_hook_cmd, "live_daemon", _no_daemon)
    monkeypatch.setattr(httpx, "post", _never)
    for ev in _events(str(tmp_path)):
        result = _hook(ev)
        assert result.exit_code == 0, result.output
        assert result.output == ""
    # Each of the two needed the daemon, so each looked for one.
    assert len(looked) == 2


@pytest.mark.acceptance(
    spec="memory", scenario="the hook prints nothing and exits 0 with no daemon"
)
@pytest.mark.parametrize("failure", ["raises", "timeout", "500", "not-json"])
def test_a_failing_daemon_prints_nothing_and_exits_0(
    failure: str, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _post(*_a: Any, **_k: Any) -> Any:
        if failure == "raises":
            raise httpx.ConnectError("All connection attempts failed")
        if failure == "timeout":
            raise httpx.ReadTimeout("slow")
        if failure == "500":
            return httpx.Response(500, json={"output": {"hookSpecificOutput": {}}})
        return httpx.Response(200, content=b"<html>")

    monkeypatch.setattr(memory_hook_cmd, "live_daemon", _info)
    monkeypatch.setattr(httpx, "post", _post)
    for ev in _events(str(tmp_path)):
        result = _hook(ev)
        assert result.exit_code == 0, result.output
        assert result.output == ""


def test_malformed_stdin_prints_nothing_and_exits_0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory_hook_cmd, "live_daemon", _info)
    for raw in ("", "not json", "[1, 2]", "null"):
        result = _runner.invoke(cli_app, ["memory", "hook", "--agent-uid", "a"], input=raw)
        assert result.exit_code == 0 and result.output == ""


@pytest.mark.parametrize(
    "event",
    [
        {"hook_event_name": "UserPromptSubmit", "prompt": "继续"},
        {"hook_event_name": "UserPromptSubmit", "prompt": "ok"},
        {"hook_event_name": "UserPromptSubmit", "prompt": "fix it"},
        {"hook_event_name": "Stop"},
    ],
)
def test_a_fire_that_can_deliver_nothing_never_contacts_the_daemon(
    event: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _never(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("answered locally: no daemon lookup, no request")

    monkeypatch.setattr(memory_hook_cmd, "live_daemon", _never)
    monkeypatch.setattr(httpx, "post", _never)
    result = _hook({"session_id": "s1", "cwd": "/tmp", **event})
    assert result.exit_code == 0 and result.output == ""


@pytest.mark.acceptance(
    spec="memory", scenario="a channel turn's own hook leaves the index and the notes to the turn"
)
def test_a_channel_turn_hook_leaves_the_index_and_the_notes_to_the_turn(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In a process Coffer spawned for a channel turn, the turn already carries
    the index and the notes its prompt names; the hook firing there answers
    neither, and records neither, so each arrives and is counted once. The
    hook reaches the daemon only in a session the developer drives."""
    posted: list[str] = []

    def _post(_url: str, **kw: Any) -> Any:
        posted.append(kw["json"]["event"])
        return httpx.Response(200, json={"output": None})

    monkeypatch.setenv(CHANNEL_TURN_ENV, "1")
    monkeypatch.setattr(memory_hook_cmd, "live_daemon", _info)
    monkeypatch.setattr(httpx, "post", _post)
    for ev in _events(str(tmp_path)):
        result = _hook(ev)
        assert result.exit_code == 0 and result.output == ""
    assert posted == []

    # Unmarked — a session the developer drives — every one reaches the daemon.
    monkeypatch.delenv(CHANNEL_TURN_ENV)
    posted.clear()
    for ev in _events(str(tmp_path)):
        _hook(ev)
    assert posted == ["SessionStart", "UserPromptSubmit"]


# --- with the daemon: both agents' installed commands ----------------------------------------


@pytest.fixture
def app(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HookApp]:
    yield from boot(tmp_path, monkeypatch)


def _installed_args(path: pathlib.Path, cwd: pathlib.Path) -> list[str]:
    """The CLI arguments of the one Coffer command on ``UserPromptSubmit`` in
    an agent's settings file, ``$PWD`` expanded as the agent's shell would."""
    data = json.loads(path.read_text(encoding="utf-8"))
    commands = [
        h["command"]
        for group in data["hooks"]["UserPromptSubmit"]
        for h in group["hooks"]
        if MARKER in h["command"]
    ]
    (command,) = commands
    call = command.split(";", 1)[1]
    argv = shlex.split(call.replace('"$PWD"', shlex.quote(str(cwd))))
    assert pathlib.Path(argv[0]).is_absolute()
    return argv[1:]


def _run(argv: list[str], stdin: dict[str, Any]) -> dict[str, Any]:
    result = _runner.invoke(cli_app, argv, input=json.dumps(stdin))
    assert result.exit_code == 0, result.output
    lines = [ln for ln in result.output.splitlines() if ln.startswith('{"hookSpecificOutput"')]
    assert len(lines) == 1, result.output
    return dict(json.loads(lines[0]))


@pytest.mark.acceptance(
    spec="memory", scenario="both agents' hook fires answer in the JSON each reads"
)
@pytest.mark.acceptance(
    spec="memory", scenario="a Codex hook fire prints the session-start JSON Codex reads"
)
def test_both_agents_installed_commands_answer_session_start_and_prompt(app: HookApp) -> None:
    cc = register(app.client, "claude_code")
    cx = register(app.client, "codex")
    repo, name = distilled(app)
    for uid in (cc, cx):
        r = app.client.post(f"/agents/{uid}/coffer-connection")
        assert r.status_code == 200, r.text
    note_file = str(
        app.home / ".coffer" / "derived" / "memory" / name / "notes" / "node-20-for-make-verify.md"
    )

    shapes: dict[str, tuple[pathlib.Path, dict[str, Any]]] = {
        "claude_code": (
            app.home / ".claude" / "settings.json",
            {
                "transcript_path": str(app.home / ".claude" / "projects" / "x.jsonl"),
                "permission_mode": "default",
            },
        ),
        "codex": (
            app.home / ".codex" / "hooks.json",
            {"turn_id": "turn-1", "model": "gpt-5", "transcript_path": None},
        ),
    }
    for agent_type, (settings, extra) in shapes.items():
        argv = _installed_args(settings, repo)
        session = f"{agent_type}-session"
        start = _run(
            argv,
            {
                "hook_event_name": "SessionStart",
                "session_id": session,
                "cwd": str(repo),
                "source": "startup",
                **extra,
            },
        )
        out = start["hookSpecificOutput"]
        assert out["hookEventName"] == "SessionStart"
        assert out["additionalContext"]
        prompt = _run(
            argv,
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session,
                "cwd": str(repo),
                "prompt": _PROMPT,
                **extra,
            },
        )
        out = prompt["hookSpecificOutput"]
        assert out["hookEventName"] == "UserPromptSubmit"
        assert note_file in out["additionalContext"]
        # Neither agent is ever handed a permission decision.
        assert "permissionDecision" not in json.dumps([start, prompt])

    # What reached the daemon: the agent named by uid and the cwd.
    assert {p["agent_uid"] for p in app.posts} == {cc, cx}
    assert {p["cwd"] for p in app.posts} == {str(repo)}


def test_the_cwd_option_is_the_fallback_when_the_event_carries_none(app: HookApp) -> None:
    uid = register(app.client, "claude_code")
    repo, _name = distilled(app)
    result = _hook(
        {"hook_event_name": "UserPromptSubmit", "session_id": "s", "prompt": _PROMPT},
        uid=uid,
        cwd=str(repo),
    )
    assert result.exit_code == 0
    assert "node-20-for-make-verify.md" in result.output
    assert app.posts[-1]["cwd"] == str(repo)
