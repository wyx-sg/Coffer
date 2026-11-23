"""Each agent's own command line runs a whole Coffer turn (spec chat "Run a
turn through the agent's one-shot command").

Runs in the ``agent-cli`` CI job with ``COFFER_SMOKE_AGENT_CLI=1``, like
``test_agent_cli_smoke``. OpenCode and DeepSeek Harness answer from a stand-in
model server through the same adapter the daemon uses: one tool call, its
result, an answer, and a second turn on the same session; then the session is
found in the agent's own store (spec agent-registry "List the sessions an agent
keeps in its own store"), and OpenCode deletes it through its own command. Cursor signs in with
its own account, which CI has not got, so its test only proves the command
line Coffer builds is one Cursor accepts.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
from typing import Any

import pytest

from coffer.domain.agent.native_sessions import NativeSessionNotFound
from coffer.domain.chat.events import MessageEnd, TextDelta, ToolCall, ToolResult, TurnDone
from coffer.infrastructure.agent.cli_native_sessions import (
    DshNativeSessions,
    OpenCodeNativeSessions,
)
from coffer.infrastructure.chat.cli_turn import CliAgent, CliTurnAdapter
from coffer.infrastructure.chat.cursor_print import CursorPrint
from coffer.infrastructure.chat.dsh_headless import DshHeadless
from coffer.infrastructure.chat.opencode_run import OpenCodeRun

from .fake_responses import TEXT, StandIn

pytestmark = pytest.mark.skipif(
    os.environ.get("COFFER_SMOKE_AGENT_CLI") != "1",
    reason="runs in the agent-cli CI job, which installs the agents",
)


def _program(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        pytest.skip(f"{name} is not installed")
    return found


async def _turn(
    agent: CliAgent, binary: str, cwd: pathlib.Path, env: dict[str, str], resume: str | None
) -> tuple[list[Any], list[str]]:
    saved: list[str] = []

    async def sink(session_id: str) -> None:
        saved.append(session_id)

    adapter = CliTurnAdapter(
        agent=agent,
        binary=binary,
        cwd=str(cwd),
        env=env,
        model="stand-in",
        resume_session=resume,
        on_session=sink,
        system_context="COFFER-SMOKE-NOTE: you are answering a phone.",
    )
    events = [e async for e in await adapter.run_turn("say hi")]
    return [e for e in events if type(e).__name__ != "TurnProgress"], saved


def _assert_whole_turn(events: list[Any]) -> None:
    kinds = [type(e) for e in events]
    assert ToolCall in kinds and ToolResult in kinds, events
    assert TextDelta(text=TEXT) in events and MessageEnd() in events, events
    assert isinstance(events[-1], TurnDone), events


def _context_reached(seen: list[dict[str, Any]]) -> bool:
    return any("COFFER-SMOKE-NOTE" in json.dumps(s["req"]) for s in seen)


async def test_opencode_runs_a_turn_and_resumes_it(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opencode = _program("opencode")
    monkeypatch.setenv("HOME", str(tmp_path))
    for key in [k for k in os.environ if k.startswith("XDG_")]:
        monkeypatch.delenv(key)
    work = tmp_path / "work"
    work.mkdir()
    with StandIn() as upstream:
        config = tmp_path / ".config" / "opencode" / "opencode.json"
        config.parent.mkdir(parents=True)
        config.write_text(
            json.dumps(
                {
                    "provider": {
                        "coffer": {
                            "npm": "@ai-sdk/openai",
                            "name": "Coffer",
                            "options": {"baseURL": upstream.base_url, "apiKey": "cfr_smoke"},
                            "models": {
                                "stand-in": {
                                    "name": "stand-in",
                                    "limit": {"context": 100_000, "output": 32_000},
                                }
                            },
                        }
                    }
                }
            )
        )
        events, saved = await _turn(OpenCodeRun(), opencode, work, {}, None)
        _assert_whole_turn(events)
        assert saved and saved[0].startswith("ses_")
        assert _context_reached(upstream.seen)
        again, saved_again = await _turn(OpenCodeRun(), opencode, work, {}, saved[0])
        assert isinstance(again[-1], TurnDone), again
        assert saved_again == [], "the same session was continued"

    # The session is in OpenCode's own list, and goes through its own delete.
    sessions = OpenCodeNativeSessions(which=lambda _p: opencode, env=dict)
    config_dir = tmp_path / ".config" / "opencode"
    page = await sessions.list(config_dir, q=None, limit=10, position=None)
    listed = {s.session_id: s for s in page.items}
    assert saved[0] in listed, page
    assert listed[saved[0]].cwd == str(work)
    await sessions.delete(config_dir, saved[0])
    after = await sessions.list(config_dir, q=None, limit=10, position=None)
    assert saved[0] not in {s.session_id for s in after.items}
    with pytest.raises(NativeSessionNotFound):
        await sessions.delete(config_dir, saved[0])


async def test_deepseek_harness_runs_a_turn_and_resumes_it(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dsh = _program("dsh")
    monkeypatch.setenv("HOME", str(tmp_path))
    work = tmp_path / "work"
    work.mkdir()
    home = tmp_path / ".dsh"
    home.mkdir()
    with StandIn() as upstream:
        route = {
            "displayName": "Coffer",
            "api": "openai-responses",
            "baseURL": upstream.base_url,
            "apiKeyEnv": "COFFER_SMOKE_KEY",
            "models": [{"id": "stand-in", "contextWindow": 100_000}],
        }
        (home / "cordis.patch.yml").write_text(
            json.dumps([{"id": "llm-pi-ai", "config": {"providers": {"coffer": route}}}])
        )
        env = {"DSH_HOME": str(home), "COFFER_SMOKE_KEY": "cfr_smoke"}
        events, saved = await _turn(DshHeadless(), dsh, work, env, None)
        _assert_whole_turn(events)
        assert saved and saved[0].startswith("session-")
        assert _context_reached(upstream.seen)
        assert {s["req"].get("model") for s in upstream.seen} == {"stand-in"}
        again, saved_again = await _turn(DshHeadless(), dsh, work, env, saved[0])
        assert isinstance(again[-1], TurnDone), again
        assert saved_again == []

    # The session is in DeepSeek Harness's own store, with its folder.
    page = await DshNativeSessions().list(home, q=None, limit=10, position=None)
    listed = {s.session_id: s for s in page.items}
    assert saved[0] in listed, page
    assert listed[saved[0]].cwd == str(work)
    assert listed[saved[0]].last_activity_at is not None


async def test_cursor_accepts_the_command_coffer_builds(tmp_path: pathlib.Path) -> None:
    cursor = _program("cursor-agent")
    plan = await CursorPrint().plan(
        binary=cursor,
        prompt="say hi",
        model=None,
        resume=None,
        system_context="note",
        scratch=tmp_path,
    )
    env = {k: v for k, v in os.environ.items() if k != "CURSOR_API_KEY"}
    env["HOME"] = str(tmp_path)
    done = subprocess.run(
        plan.argv,
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
    )
    said = (done.stdout + done.stderr).lower()
    # Not signed in, so the run fails, but on the sign-in, not on a flag.
    assert "unknown option" not in said and "unknown argument" not in said, said
    assert "login" in said or "auth" in said or "api key" in said, said
