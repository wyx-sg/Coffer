"""``coffer memory hook``, ``coffer memory trigger …`` and ``coffer memory
delivered`` (spec memory "Fail open when Coffer cannot answer", "Install
delivery hooks explicitly and removably", "Count what memory delivered and
what was read", "Show what each agent is given at session start").

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
from coffer.domain.memory.delivery import MARKER
from coffer.domain.memory.trigger import KIND_BLOCK, Trigger
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.memory import trigger_store
from coffer.surfaces.cli.main import app as cli_app
from tests.integration.memory._hook_app import (
    HookApp,
    boot,
    distilled,
    extract_json,
    partitions,
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
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "make verify"},
            **common,
        },
    ]


# --- fail open ------------------------------------------------------------------------


@pytest.fixture
def armed_trigger(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Trigger:
    t = Trigger(
        id="node-20",
        note="coffer/node-20-for-make-verify",
        kind=KIND_BLOCK,
        command=r"^make\s+verify\b",
        armed_by="user",
    )
    trigger_store.write_trigger(t)
    return t


def _info() -> DaemonInfo:
    from datetime import UTC, datetime

    return DaemonInfo(
        version=1,
        pid=1,
        port=59999,
        token="t",
        started_at=datetime.now(tz=UTC),
        binary_path="/x",
    )


@pytest.mark.acceptance(
    spec="memory", scenario="the hook prints nothing and exits 0 with no daemon"
)
def test_no_daemon_prints_nothing_and_exits_0(
    armed_trigger: Trigger, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
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
    # Each of the three needed the daemon, so each looked for one.
    assert len(looked) == 3


@pytest.mark.acceptance(
    spec="memory", scenario="the hook prints nothing and exits 0 with no daemon"
)
@pytest.mark.parametrize("failure", ["raises", "timeout", "500", "not-json"])
def test_a_failing_daemon_prints_nothing_and_exits_0(
    failure: str, armed_trigger: Trigger, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
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
        {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}},
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "cat Makefile"},
        },
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"command": "make verify"},
        },
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "make verify"},
            "tool_response": "ok",
        },
        {"hook_event_name": "Stop"},
    ],
)
def test_a_fire_that_can_deliver_nothing_never_contacts_the_daemon(
    event: dict[str, Any], armed_trigger: Trigger, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _never(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("answered locally: no daemon lookup, no request")

    monkeypatch.setattr(memory_hook_cmd, "live_daemon", _never)
    monkeypatch.setattr(httpx, "post", _never)
    result = _hook({"session_id": "s1", "cwd": "/tmp", **event})
    assert result.exit_code == 0 and result.output == ""


def test_an_unarmed_trigger_does_not_send_its_command(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trigger_store.write_trigger(
        Trigger(id="p", note="coffer/x", kind=KIND_BLOCK, command="^make", proposed_by="distil")
    )
    posted: list[Any] = []
    monkeypatch.setattr(memory_hook_cmd, "live_daemon", _info)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: posted.append(k))
    ev = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "make"}}
    assert _hook(ev).output == ""
    assert posted == []


def test_tool_output_of_both_shapes_reaches_the_daemon_as_text() -> None:
    claude = {"stdout": "out", "stderr": "zsh: timeout: command not found", "interrupted": False}
    assert memory_hook_cmd._output_text(claude) == "out\nzsh: timeout: command not found"
    assert memory_hook_cmd._output_text("plain codex output") == "plain codex output"
    assert memory_hook_cmd._output_text(None) == ""
    assert len(memory_hook_cmd._output_text("x" * 50_000)) == 20_000


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
def test_both_agents_installed_commands_answer_prompt_and_guard(app: HookApp) -> None:
    cc = register(app.client, "claude_code")
    cx = register(app.client, "codex")
    repo, name = distilled(app)
    for uid in (cc, cx):
        r = app.client.post(f"/agents/{uid}/coffer-connection")
        assert r.status_code == 200, r.text
    r = app.client.post(
        "/memory/triggers",
        json={"note": f"{name}/node-20-for-make-verify", "command": r"^make\s+verify\b"},
    )
    assert r.status_code == 201, r.text
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

        response: Any = (
            {"stdout": "", "stderr": "", "interrupted": False, "isImage": False}
            if agent_type == "claude_code"
            else ""
        )
        pre = _run(
            argv,
            {
                "hook_event_name": "PreToolUse",
                "session_id": session,
                "cwd": str(repo),
                "tool_name": "Bash",
                "tool_input": {"command": "make verify"},
                "tool_use_id": "call-1",
                **extra,
            },
        )
        out = pre["hookSpecificOutput"]
        assert out["hookEventName"] == "PreToolUse"
        assert out["permissionDecision"] == "deny"
        assert note_file in out["permissionDecisionReason"]

        post = _runner.invoke(
            cli_app,
            argv,
            input=json.dumps(
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": session,
                    "cwd": str(repo),
                    "tool_name": "Bash",
                    "tool_input": {"command": "make verify"},
                    "tool_response": response,
                    **extra,
                }
            ),
        )
        assert post.exit_code == 0 and '"hookSpecificOutput"' not in post.output

    # What reached the daemon: the agent named by uid, the command and the cwd.
    guards = [p for p in app.posts if p["event"] == "PreToolUse"]
    assert {p["agent_uid"] for p in guards} == {cc, cx}
    assert {p["command"] for p in guards} == {"make verify"}
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


# --- delivered ------------------------------------------------------------------------------


def test_delivered_prints_the_overview_and_one_partitions_session_start_text(
    app: HookApp,
) -> None:
    uid = register(app.client, "claude_code")
    repo, name = distilled(app)
    _hook({"hook_event_name": "SessionStart", "session_id": "s", "cwd": str(repo)}, uid=uid)
    _hook(
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "s",
            "cwd": str(repo),
            "prompt": _PROMPT,
        },
        uid=uid,
    )

    overview = _runner.invoke(cli_app, ["memory", "delivered"])
    assert overview.exit_code == 0, overview.output
    assert "claude-code: 2 deliveries in 7 days" in overview.output

    as_json = extract_json(_runner.invoke(cli_app, ["memory", "delivered", "--json"]).output)
    (agent,) = as_json["agents"]
    assert agent["deliveries"] == 2
    assert agent["by_moment"] == {"prompt": 1, "session_start": 1}

    view = _runner.invoke(cli_app, ["memory", "delivered", name])
    assert view.exit_code == 0, view.output
    assert "== claude-code (SessionStart) ==" in view.output
    body = extract_json(
        _runner.invoke(
            cli_app, ["memory", "delivered", name, "--agent", "claude-code", "--json"]
        ).output
    )
    assert body["partition"] == name
    uid_of = partitions(app.client)[name]["uid"]
    direct = app.client.get(f"/memory/partitions/{uid_of}/delivered").json()
    assert body == direct
    assert body["agents"][0]["text"] in view.output
    none = extract_json(
        _runner.invoke(cli_app, ["memory", "delivered", name, "--agent", "nobody", "--json"]).output
    )
    assert none["agents"] == []
