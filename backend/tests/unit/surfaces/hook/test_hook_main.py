"""Unit tests for the ``coffer-hook`` console entrypoint (Slice 6).

Contract: the hook must NEVER raise and NEVER block the agent. Any failure
(no daemon.json, connection refused, timeout, non-200, bad JSON) → print
nothing and exit 0. SessionStart prints the additionalContext bundle; SessionEnd
POSTs the session-end signal and prints nothing.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.hook import main as hook_main


def _daemon_info() -> DaemonInfo:
    return DaemonInfo(
        version=1,
        pid=4242,
        port=8123,
        token="tok-secret",
        started_at=datetime(2026, 6, 22, tzinfo=UTC),
        binary_path="/bin/coffer-daemon",
    )


def _run(monkeypatch, capsys, *, stdin: str, argv: list[str], daemon=None, request_fn=None):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    monkeypatch.setattr(hook_main.sys, "argv", ["coffer-hook", *argv])
    monkeypatch.setattr(hook_main, "_read_daemon_info", lambda: daemon)
    if request_fn is not None:
        monkeypatch.setattr(hook_main, "_http", request_fn)
    code = None
    try:
        hook_main.run()
    except SystemExit as e:
        code = e.code if e.code is not None else 0
    out = capsys.readouterr().out
    return code, out


def test_session_start_prints_additional_context(monkeypatch, capsys):
    captured = {}

    def fake_http(method, url, *, token, body=None, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["token"] = token
        return 200, json.dumps({"additional_context": "RULES BUNDLE TEXT"})

    stdin = json.dumps({"hook_event_name": "SessionStart", "cwd": "/work/proj", "session_id": "s1"})
    code, out = _run(
        monkeypatch,
        capsys,
        stdin=stdin,
        argv=["--agent", "my-claude"],
        daemon=_daemon_info(),
        request_fn=fake_http,
    )
    assert code == 0
    payload = json.loads(out)
    assert payload == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "RULES BUNDLE TEXT",
        }
    }
    assert captured["method"] == "GET"
    assert "/api/v1/agents/my-claude/session-context" in captured["url"]
    assert "cwd=" in captured["url"]
    assert captured["token"] == "tok-secret"


def test_session_end_posts_and_prints_nothing(monkeypatch, capsys):
    captured = {}

    def fake_http(method, url, *, token, body=None, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["body"] = body
        return 200, ""

    stdin = json.dumps(
        {"hook_event_name": "SessionEnd", "cwd": "/work/proj", "session_id": "sess-9"}
    )
    code, out = _run(
        monkeypatch,
        capsys,
        stdin=stdin,
        argv=["--agent", "my-claude"],
        daemon=_daemon_info(),
        request_fn=fake_http,
    )
    assert code == 0
    assert out.strip() == ""
    assert captured["method"] == "POST"
    assert "/api/v1/agents/my-claude/sessions/sess-9/end" in captured["url"]
    assert captured["body"] == {"cwd": "/work/proj"}


def test_no_daemon_json_exits_zero_silent(monkeypatch, capsys):
    stdin = json.dumps({"hook_event_name": "SessionStart", "cwd": "/x", "session_id": "s"})
    code, out = _run(monkeypatch, capsys, stdin=stdin, argv=["--agent", "a"], daemon=None)
    assert code == 0
    assert out.strip() == ""


def test_http_error_exits_zero_silent(monkeypatch, capsys):
    def boom(method, url, *, token, body=None, timeout):
        raise ConnectionRefusedError("nope")

    stdin = json.dumps({"hook_event_name": "SessionStart", "cwd": "/x", "session_id": "s"})
    code, out = _run(
        monkeypatch,
        capsys,
        stdin=stdin,
        argv=["--agent", "a"],
        daemon=_daemon_info(),
        request_fn=boom,
    )
    assert code == 0
    assert out.strip() == ""


def test_non_200_exits_zero_silent(monkeypatch, capsys):
    def fake_http(method, url, *, token, body=None, timeout):
        return 500, "boom"

    stdin = json.dumps({"hook_event_name": "SessionStart", "cwd": "/x", "session_id": "s"})
    code, out = _run(
        monkeypatch,
        capsys,
        stdin=stdin,
        argv=["--agent", "a"],
        daemon=_daemon_info(),
        request_fn=fake_http,
    )
    assert code == 0
    assert out.strip() == ""


def test_bad_stdin_json_exits_zero_silent(monkeypatch, capsys):
    code, out = _run(
        monkeypatch,
        capsys,
        stdin="this is not json",
        argv=["--agent", "a"],
        daemon=_daemon_info(),
    )
    assert code == 0
    assert out.strip() == ""


def test_unknown_event_exits_zero_silent(monkeypatch, capsys):
    stdin = json.dumps({"hook_event_name": "Stop", "cwd": "/x", "session_id": "s"})
    code, out = _run(
        monkeypatch,
        capsys,
        stdin=stdin,
        argv=["--agent", "a"],
        daemon=_daemon_info(),
    )
    assert code == 0
    assert out.strip() == ""


def test_session_start_empty_context_prints_nothing(monkeypatch, capsys):
    def fake_http(method, url, *, token, body=None, timeout):
        return 200, json.dumps({"additional_context": ""})

    stdin = json.dumps({"hook_event_name": "SessionStart", "cwd": "/x", "session_id": "s"})
    code, out = _run(
        monkeypatch,
        capsys,
        stdin=stdin,
        argv=["--agent", "a"],
        daemon=_daemon_info(),
        request_fn=fake_http,
    )
    assert code == 0
    # empty bundle → no additionalContext emitted (nothing to inject)
    assert out.strip() == ""
