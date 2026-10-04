"""The instructions files an agent keeps (spec memory "Leave per-turn rules to
the agent's own instructions", "Install delivery hooks explicitly and
removably").

The whole daemon on a fake home (``_hook_app.boot``). Fires are real: each is a
``POST /memory/hook`` the daemon audits.
"""

from __future__ import annotations

import json
import pathlib
import shlex
from collections.abc import Iterator

import pytest
from typer.testing import CliRunner

from coffer.domain.memory.delivery import DELIVERY_EVENTS, MARKER
from coffer.surfaces.cli.main import app as cli_app
from tests.integration.memory._hook_app import (
    HookApp,
    audit,
    boot,
    distilled,
    register,
)

_runner = CliRunner()
_PROMPT = "why does make verify fail with undici AbortSignal under node"


@pytest.fixture
def app(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[HookApp]:
    yield from boot(tmp_path, monkeypatch)


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
    repo, _name = distilled(app)
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
        ]
        for ev in events:
            result = _runner.invoke(
                cli_app, argv, input=json.dumps({"session_id": uid, "cwd": str(repo), **ev})
            )
            assert result.exit_code == 0, result.output

    fired = {f["details"]["moment"] for f in audit(app.client, "memory_delivery_fired")}
    assert fired == {"session_start", "prompt"}
    assert (claude_md.read_bytes(), agents_md.read_bytes()) == before
