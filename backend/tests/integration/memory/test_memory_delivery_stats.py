"""The delivery overview and the instructions files an agent keeps (spec
memory "Count what memory delivered and what was read", "Leave per-turn rules
to the agent's own instructions", "Install delivery hooks explicitly and
removably").

The whole daemon on a fake home (``_hook_app.boot``). Fires are real: each is a
``POST /memory/hook`` the daemon audits, and the one that must fall outside the
seven-day window is moved there in the database afterwards. The transcripts are
files written under the fake agent config directories, shaped like each
agent's own.
"""

from __future__ import annotations

import json
import pathlib
import shlex
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.domain.memory.delivery import DELIVERY_EVENTS, MARKER
from coffer.surfaces.cli.main import app as cli_app
from tests.integration.memory._hook_app import (
    HookApp,
    audit,
    boot,
    distilled,
    fire,
    register,
)

_runner = CliRunner()
_PROMPT = "why does make verify fail with undici AbortSignal under node"


@pytest.fixture
def app(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HookApp]:
    yield from boot(tmp_path, monkeypatch)


def _overview(app: HookApp) -> dict[str, dict[str, Any]]:
    r = app.client.get("/memory/deliveries")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window_days"] == 7
    return {a["agent_type"]: a for a in body["agents"]}


def _age_fire(app: HookApp, fire_id: int, days: int) -> None:
    """Move one audited fire ``days`` into the past, in the daemon's own
    database — the only way a test gets a fire older than the window."""
    with sqlite3.connect(app.home / "c.db") as db:
        (stamp,) = db.execute("SELECT timestamp FROM audit_log WHERE id = ?", (fire_id,)).fetchone()
        old = datetime.fromisoformat(stamp) - timedelta(days=days)
        db.execute(
            "UPDATE audit_log SET timestamp = ? WHERE id = ?",
            (old.isoformat(sep=" "), fire_id),
        )


def _claude_transcript(app: HookApp, name: str) -> None:
    """A Claude Code session whose tool calls read two notes (one twice) and
    whose message text names a third — which must not count."""
    notes = app.home / ".coffer" / "derived" / "memory" / name / "notes"
    now = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")

    def tool_use(path: pathlib.Path) -> dict[str, Any]:
        return {
            "type": "assistant",
            "timestamp": now,
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t",
                        "name": "Read",
                        "input": {"file_path": str(path)},
                    }
                ],
            },
        }

    third = notes / "filler-coffer-3.md"
    records = [
        {"type": "user", "timestamp": now, "message": {"role": "user", "content": _PROMPT}},
        tool_use(notes / "node-20-for-make-verify.md"),
        tool_use(notes / "filler-coffer-1.md"),
        tool_use(notes / "node-20-for-make-verify.md"),
        {
            "type": "assistant",
            "timestamp": now,
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": f"You could also open {third}"}],
            },
        },
        {
            "type": "user",
            "timestamp": now,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t", "content": f"see {third}"}],
            },
        },
    ]
    session = app.home / ".claude" / "projects" / "-work-coffer" / "abc-session.jsonl"
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


@pytest.mark.acceptance(
    spec="memory", scenario="the overview counts a week of deliveries and the notes read"
)
@pytest.mark.acceptance(spec="memory", scenario="notes read is unavailable without transcripts")
def test_the_overview_counts_a_weeks_fires_and_the_notes_read(app: HookApp) -> None:
    cc = register(app.client, "claude_code")
    cx = register(app.client, "codex")
    repo, name = distilled(app)
    r = app.client.post(
        "/memory/triggers",
        json={"note": f"{name}/node-20-for-make-verify", "command": r"^make\s+verify\b"},
    )
    assert r.status_code == 201, r.text
    where = {"cwd": str(repo)}

    # One fire that will be aged out of the window, then five inside it.
    fire(app.client, cc, "SessionStart", session_id="old", **where)
    (old,) = audit(app.client, "memory_delivery_fired")
    for s in ("a", "b", "c"):
        fire(app.client, cc, "SessionStart", session_id=s, **where)
    assert fire(app.client, cc, "UserPromptSubmit", session_id="a", prompt=_PROMPT, **where)
    assert fire(
        app.client,
        cc,
        "PreToolUse",
        session_id="a",
        tool_name="Bash",
        command="make verify",
        **where,
    )
    _age_fire(app, old["id"], days=10)
    fire(app.client, cx, "SessionStart", session_id="cx", **where)
    _claude_transcript(app, name)
    assert not (app.home / ".codex" / "sessions").exists()

    stats = _overview(app)
    claude = stats["claude_code"]
    assert claude["agent_uid"] == cc
    assert claude["deliveries"] == 5
    assert claude["by_moment"] == {"guard": 1, "prompt": 1, "session_start": 3}
    newest = max(
        f["timestamp"]
        for f in audit(app.client, "memory_delivery_fired")
        if f["resource_name"] == "claude-code"
    )
    assert datetime.fromisoformat(claude["last_delivered_at"].replace("Z", "+00:00")) == (
        datetime.fromisoformat(newest.replace("Z", "+00:00"))
    )
    assert claude["notes_read"] == 2
    assert claude["notes_read_status"] == "available"

    codex = stats["codex"]
    assert codex["deliveries"] == 1
    assert codex["notes_read"] is None
    assert codex["notes_read_status"] == "unavailable"

    for entry in stats.values():
        assert set(entry) == {
            "agent_uid",
            "agent_name",
            "agent_type",
            "deliveries",
            "by_moment",
            "last_delivered_at",
            "notes_read",
            "notes_read_status",
        }
        assert not any("install" in k or "trust" in k for k in entry)

    plain = _runner.invoke(cli_app, ["memory", "delivered"])
    assert plain.exit_code == 0, plain.output
    assert "claude-code: 5 deliveries in 7 days, notes read: 2" in plain.output
    assert "codex: 1 deliveries in 7 days, notes read: unavailable" in plain.output


def test_a_codex_rollout_counts_the_notes_its_shell_calls_named(app: HookApp) -> None:
    register(app.client, "claude_code")  # whose memory fills the partition
    register(app.client, "codex")
    _repo, name = distilled(app)
    note = (
        app.home / ".coffer" / "derived" / "memory" / name / "notes" / "node-20-for-make-verify.md"
    )
    now = datetime.now(tz=UTC).isoformat()
    rollout = app.home / ".codex" / "sessions" / "2026" / "09" / "30" / "rollout-1.jsonl"
    rollout.parent.mkdir(parents=True)
    records = [
        {
            "timestamp": now,
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell",
                "arguments": json.dumps({"command": ["cat", str(note)]}),
            },
        },
        {
            "timestamp": now,
            "type": "response_item",
            "payload": {
                "type": "message",
                "content": [{"type": "output_text", "text": str(note).replace("node-20", "x")}],
            },
        },
    ]
    rollout.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    codex = _overview(app)["codex"]
    assert codex["notes_read"] == 1
    assert codex["notes_read_status"] == "available"


# --- connecting an agent, and every hook firing ---------------------------------------


def _coffer_entries(settings: pathlib.Path) -> dict[str, list[str]]:
    data = json.loads(settings.read_text(encoding="utf-8"))
    return {
        event: [
            h["command"]
            for group in groups
            for h in group.get("hooks", [])
            if MARKER in h.get("command", "")
        ]
        for event, groups in data.get("hooks", {}).items()
    }


def _argv(command: str, cwd: pathlib.Path) -> list[str]:
    call = command.split(";", 1)[1].replace('"$PWD"', shlex.quote(str(cwd)))
    return shlex.split(call)[1:]


@pytest.mark.acceptance(
    spec="memory", scenario="connecting an agent leaves its instructions files untouched"
)
def test_connecting_and_firing_every_hook_leaves_claude_md_and_agents_md_untouched(
    app: HookApp,
) -> None:
    claude_md = app.home / ".claude" / "CLAUDE.md"
    agents_md = app.home / ".codex" / "AGENTS.md"
    claude_md.write_bytes("# Rules\n\n请用简体中文回复。\n".encode())
    agents_md.write_bytes(b"# Codex\n\nAlways answer tersely.\n")
    before = (claude_md.read_bytes(), agents_md.read_bytes())

    cc = register(app.client, "claude_code")
    cx = register(app.client, "codex")
    repo, name = distilled(app)
    r = app.client.post(
        "/memory/triggers",
        json={"note": f"{name}/node-20-for-make-verify", "command": r"^make\s+verify\b"},
    )
    assert r.status_code == 201, r.text
    for uid in (cc, cx):
        r = app.client.post(f"/agents/{uid}/coffer-connection")
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "connected"

    settings = {
        cc: app.home / ".claude" / "settings.json",
        cx: app.home / ".codex" / "hooks.json",
    }
    for uid, path in settings.items():
        entries = _coffer_entries(path)
        assert sorted(entries) == sorted(DELIVERY_EVENTS)
        for event in DELIVERY_EVENTS:
            (command,) = entries[event]
            argv = shlex.split(command.split(";", 1)[1])
            assert pathlib.Path(argv[0]).is_absolute()
            assert argv[1:5] == ["memory", "hook", "--agent-uid", uid]

        argv = _argv(entries["SessionStart"][0], repo)
        events = [
            {"hook_event_name": "SessionStart", "source": "startup"},
            {"hook_event_name": "UserPromptSubmit", "prompt": _PROMPT},
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "make verify"},
            },
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "make verify"},
                "tool_response": "ok",
            },
        ]
        for ev in events:
            result = _runner.invoke(
                cli_app, argv, input=json.dumps({"session_id": uid, "cwd": str(repo), **ev})
            )
            assert result.exit_code == 0, result.output

    fired = {f["details"]["moment"] for f in audit(app.client, "memory_delivery_fired")}
    assert {"session_start", "prompt", "guard"} <= fired
    assert (claude_md.read_bytes(), agents_md.read_bytes()) == before
