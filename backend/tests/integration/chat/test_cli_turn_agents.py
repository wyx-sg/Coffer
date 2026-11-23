"""OpenCode, Cursor and DeepSeek Harness turns over their one-shot commands
(spec chat "Run a turn through the agent's one-shot command").

A Python script stands in for each CLI: it records the command line, the
environment Coffer added and its stdin, then prints the lines the real CLI
printed in a recorded run (OpenCode 1.19 / 2.3 and dsh 0.2.2 against a stand-in
model server; Cursor from its documented stream-json). The real CLIs are
exercised by the agent-cli smoke tests.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import stat
import sys
from typing import Any

import pytest

from coffer.domain.chat.events import (
    MessageEnd,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
    TurnStarted,
)
from coffer.infrastructure.chat.cli_turn import CliAgent, CliTurnAdapter
from coffer.infrastructure.chat.cursor_print import CONTEXT_OPEN, CursorPrint
from coffer.infrastructure.chat.dsh_headless import DshHeadless
from coffer.infrastructure.chat.opencode_run import OpenCodeRun, _majors

_FAKE = """#!{python}
import json, os, sys, time
argv = sys.argv[1:]
if argv == ["--version"]:
    print(os.environ.get("FAKE_VERSION", "1.19.6"))
    sys.exit(0)
stdin = "" if sys.stdin is None or sys.stdin.closed else sys.stdin.read()
added = {{k: v for k, v in os.environ.items() if k.startswith(("OPENCODE_", "COFFER_", "PWD"))}}
patch = None
if "--patch" in argv:
    patch = json.load(open(argv[argv.index("--patch") + 1]))
ctx = None
if "OPENCODE_CONFIG_CONTENT" in os.environ:
    files = json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])["instructions"]
    ctx = open(files[-1]).read()
with open(os.environ["FAKE_RECORD"], "a") as f:
    f.write(json.dumps({{"argv": argv, "stdin": stdin, "env": added, "patch": patch,
                        "ctx": ctx, "cwd": os.getcwd()}}) + "\\n")
resuming = any(a in argv for a in ("--session", "--session-id", "--resume"))
if resuming and os.environ.get("FAKE_FORGET"):
    sys.stderr.write("Error: Session not found\\n")
    sys.exit(1)
lines = open(os.environ["FAKE_LINES"]).read().splitlines()
for line in lines:
    print(line, flush=True)
if os.environ.get("FAKE_SLEEP"):
    time.sleep(60)
sys.stderr.write(os.environ.get("FAKE_STDERR", ""))
sys.exit(int(os.environ.get("FAKE_RC", "0")))
"""

OPENCODE_LINES = [
    {"type": "step_start", "sessionID": "ses_1", "part": {"type": "step-start"}},
    {
        "type": "tool_use",
        "sessionID": "ses_1",
        "part": {
            "type": "tool",
            "tool": "bash",
            "callID": "call_1",
            "id": "prt_1",
            "state": {"status": "completed", "input": {"command": "echo hi"}, "output": "hi\n"},
        },
    },
    {
        "type": "step_finish",
        "sessionID": "ses_1",
        "part": {"reason": "tool-calls", "tokens": {"input": 11, "output": 7}},
    },
    {"type": "text", "sessionID": "ses_1", "part": {"type": "text", "text": "Hello from mock."}},
    {
        "type": "step_finish",
        "sessionID": "ses_1",
        "part": {"reason": "stop", "tokens": {"input": 5, "output": 3}},
    },
]

DSH_LINES = [
    {"type": "session", "sessionId": "session-1", "cwd": "/x"},
    {"type": "status", "phase": "turn_start", "turn": 1},
    {"type": "tool_call", "callId": "call_1|fc_1", "tool": "bash", "input": {"command": "echo hi"}},
    {"type": "tool_result", "callId": "call_1|fc_1", "status": "completed", "result": "hi\n"},
    {
        "type": "status",
        "phase": "step_end",
        "turn": 1,
        "step": 1,
        "usage": {"inputTokens": 11, "outputTokens": 7},
    },
    {"type": "text", "text": "Hello from mock."},
    {"type": "status", "phase": "turn_end", "turn": 1, "reason": {"kind": "completed"}},
    {
        "type": "final",
        "sessionId": "session-1",
        "reason": {"kind": "completed"},
        "text": "Hello from mock.",
    },
]

CURSOR_LINES = [
    {
        "type": "system",
        "subtype": "init",
        "session_id": "c-1",
        "model": "Claude 4 Sonnet",
        "cwd": "/x",
    },
    {
        "type": "user",
        "session_id": "c-1",
        "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]},
    },
    {
        "type": "tool_call",
        "subtype": "started",
        "call_id": "t1",
        "session_id": "c-1",
        "tool_call": {"readToolCall": {"args": {"path": "README.md"}}},
    },
    {
        "type": "tool_call",
        "subtype": "completed",
        "call_id": "t1",
        "session_id": "c-1",
        "tool_call": {
            "readToolCall": {
                "args": {"path": "README.md"},
                "result": {"success": {"content": "# hi", "totalLines": 1}},
            }
        },
    },
    {
        "type": "assistant",
        "session_id": "c-1",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "Read it."}]},
    },
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Read it.",
        "session_id": "c-1",
    },
]


@pytest.fixture
def fake(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    script = tmp_path / "fake-cli"
    script.write_text(_FAKE.format(python=sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FAKE_RECORD", str(tmp_path / "record.jsonl"))
    _majors.clear()
    return script


def _lines(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, lines: list[Any]) -> None:
    path = tmp_path / "lines.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    monkeypatch.setenv("FAKE_LINES", str(path))


def _records(tmp_path: pathlib.Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in (tmp_path / "record.jsonl").read_text().splitlines()]


class _Saved:
    def __init__(self) -> None:
        self.ids: list[str] = []

    async def __call__(self, session_id: str) -> None:
        self.ids.append(session_id)


def _adapter(
    agent: CliAgent,
    binary: pathlib.Path,
    cwd: pathlib.Path,
    saved: _Saved,
    *,
    model: str | None = None,
    resume: str | None = None,
    context: str = "",
) -> CliTurnAdapter:
    return CliTurnAdapter(
        agent=agent,
        binary=str(binary),
        cwd=str(cwd),
        env={"COFFER_TURN_TOKEN": "tok"},
        model=model,
        resume_session=resume,
        on_session=saved,
        system_context=context,
    )


async def _run(adapter: CliTurnAdapter, prompt: str = "say hi") -> list[Any]:
    return [e async for e in await adapter.run_turn(prompt)]


def _shown(events: list[Any]) -> list[Any]:
    return [e for e in events if type(e).__name__ != "TurnProgress"]


@pytest.mark.acceptance(
    spec="chat", scenario="an OpenCode turn arrives as text, tools and its tokens"
)
@pytest.mark.parametrize("version", ["1.19.6", "opencode v2.3.2"])
async def test_opencode_turn(
    fake: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    monkeypatch.setenv("FAKE_VERSION", version)
    _lines(tmp_path, monkeypatch, OPENCODE_LINES)
    saved = _Saved()
    adapter = _adapter(
        OpenCodeRun(), fake, tmp_path, saved, model="m-1", context="COFFER-NOTE: phone"
    )
    events = _shown(await _run(adapter, "-starts with a dash"))

    assert isinstance(events[0], TurnStarted)
    assert events[1] == ToolCall(
        tool_use_id="call_1", tool_name="bash", tool_input={"command": "echo hi"}
    )
    assert isinstance(events[2], ToolResult) and events[2].output == {"output": "hi\n"}
    assert events[3:5] == [TextDelta(text="Hello from mock."), MessageEnd()]
    assert events[5] == TurnDone(prompt_tokens=16, completion_tokens=10, stop_reason="end_turn")
    assert saved.ids == ["ses_1"]

    rec = _records(tmp_path)[0]
    assert rec["argv"][:4] == ["run", "--format", "json", "--auto"]
    assert ("--standalone" in rec["argv"]) is version.startswith("opencode v2")
    assert rec["argv"][rec["argv"].index("--model") + 1] == "coffer/m-1"
    assert rec["argv"][-2:] == ["--", "-starts with a dash"]
    assert rec["stdin"] == ""
    assert rec["ctx"].startswith("COFFER-NOTE: phone")
    assert rec["env"]["COFFER_TURN_TOKEN"] == "tok"
    assert rec["cwd"] == str(tmp_path)
    # OpenCode takes its project folder from PWD, not the process's directory.
    assert rec["env"]["PWD"] == str(tmp_path)


async def test_opencode_resumes_its_session_and_keeps_a_named_model(
    fake: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _lines(tmp_path, monkeypatch, OPENCODE_LINES)
    saved = _Saved()
    await _run(_adapter(OpenCodeRun(), fake, tmp_path, saved, model="anthropic/x", resume="ses_1"))
    argv = _records(tmp_path)[0]["argv"]
    assert argv[argv.index("--session") + 1] == "ses_1"
    assert argv[argv.index("--model") + 1] == "anthropic/x"
    assert saved.ids == []  # the same session: nothing new to store


async def test_opencode_error_line_ends_the_turn(
    fake: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = {
        "type": "error",
        "sessionID": "ses_1",
        "error": {"name": "APIError", "data": {"message": "model not allowed here"}},
    }
    _lines(tmp_path, monkeypatch, [error])
    monkeypatch.setenv("FAKE_RC", "1")
    events = _shown(await _run(_adapter(OpenCodeRun(), fake, tmp_path, _Saved())))
    assert events[-1] == TurnError(code="opencode_error", message="model not allowed here")


@pytest.mark.acceptance(
    spec="chat",
    scenario=(
        "a DeepSeek Harness turn takes its message on stdin and its model and context from a patch"
    ),
)
async def test_dsh_turn(
    fake: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _lines(tmp_path, monkeypatch, DSH_LINES)
    saved = _Saved()
    adapter = _adapter(
        DshHeadless(), fake, tmp_path, saved, model="m-1", context="NOTE {{model}} here"
    )
    events = _shown(await _run(adapter, "say hi"))
    kinds = [type(e).__name__ for e in events]
    assert kinds == [
        "TurnStarted",
        "ToolCall",
        "ToolResult",
        "TextDelta",
        "MessageEnd",
        "TurnDone",
    ]
    assert events[-1] == TurnDone(prompt_tokens=11, completion_tokens=7, stop_reason="end_turn")
    assert saved.ids == ["session-1"]

    rec = _records(tmp_path)[0]
    assert rec["argv"][:2] == ["--profile", "headless"]
    for flag in ("--json", "--permission-mode", "--approval-policy"):
        assert flag in rec["argv"]
    assert rec["argv"][rec["argv"].index("--permission-mode") + 1] == "danger-full-access"
    assert rec["argv"][rec["argv"].index("--approval-policy") + 1] == "never"
    assert rec["argv"][-1] == "-"
    assert rec["stdin"] == "say hi"
    assert rec["patch"] == [
        {"id": "system-prompt", "config": {"personaSuffix": "NOTE { {model} } here"}},
        {"id": "agent-default-model", "config": {"provider": "coffer", "model": "m-1"}},
    ]


async def test_dsh_error_reason_is_the_turn_error(
    fake: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reason = {"kind": "error", "error": {"code": "INVALID_REQUEST", "message": "coffer API error"}}
    _lines(
        tmp_path,
        monkeypatch,
        [
            {"type": "session", "sessionId": "session-1"},
            {"type": "final", "sessionId": "session-1", "reason": reason, "text": ""},
        ],
    )
    monkeypatch.setenv("FAKE_RC", "1")
    events = _shown(await _run(_adapter(DshHeadless(), fake, tmp_path, _Saved())))
    assert events[-1] == TurnError(code="INVALID_REQUEST", message="coffer API error")


@pytest.mark.acceptance(
    spec="chat", scenario="a Cursor turn reads Coffer's note ahead of the message"
)
async def test_cursor_turn(
    fake: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _lines(tmp_path, monkeypatch, CURSOR_LINES)
    saved = _Saved()
    adapter = _adapter(CursorPrint(), fake, tmp_path, saved, model="gpt-5", context="NOTE")
    events = _shown(await _run(adapter, "hi"))
    assert events[1] == ToolCall(
        tool_use_id="t1", tool_name="read", tool_input={"path": "README.md"}
    )
    assert isinstance(events[2], ToolResult) and events[2].output == {
        "content": "# hi",
        "totalLines": 1,
    }
    assert events[3:5] == [TextDelta(text="Read it."), MessageEnd()]
    assert isinstance(events[5], TurnDone)
    assert adapter.model_id == "Claude 4 Sonnet"
    assert saved.ids == ["c-1"]

    argv = _records(tmp_path)[0]["argv"]
    assert argv[:6] == ["-p", "--output-format", "stream-json", "--force", "--trust", "--model"]
    assert argv[-1].startswith(CONTEXT_OPEN + "\nNOTE\n") and argv[-1].endswith("\n\nhi")


@pytest.mark.acceptance(spec="chat", scenario="a one-shot agent that fails says why")
async def test_failure_quotes_stderr(
    fake: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _lines(tmp_path, monkeypatch, [CURSOR_LINES[0]])
    monkeypatch.setenv("FAKE_RC", "1")
    monkeypatch.setenv("FAKE_STDERR", "Authentication required. Run cursor-agent login.\n")
    events = _shown(await _run(_adapter(CursorPrint(), fake, tmp_path, _Saved())))
    assert events[-1] == TurnError(
        code="cursor-agent_failed", message="Authentication required. Run cursor-agent login."
    )


@pytest.mark.acceptance(
    spec="chat", scenario="a one-shot agent's forgotten session is retried once as a fresh one"
)
@pytest.mark.parametrize("agent", [OpenCodeRun(), CursorPrint(), DshHeadless()])
async def test_forgotten_session_retried_fresh(
    fake: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, agent: CliAgent
) -> None:
    lines = {"opencode": OPENCODE_LINES, "cursor": CURSOR_LINES}.get(agent.agent_key, DSH_LINES)
    _lines(tmp_path, monkeypatch, lines)
    monkeypatch.setenv("FAKE_FORGET", "1")
    saved = _Saved()
    events = _shown(await _run(_adapter(agent, fake, tmp_path, saved, resume="old")))
    assert isinstance(events[-1], TurnDone)
    assert sum(isinstance(e, TurnStarted) for e in events) == 1
    records = _records(tmp_path)
    assert len(records) == 2
    assert "old" in records[0]["argv"] and "old" not in records[1]["argv"]
    assert saved.ids and saved.ids[-1] != "old"


@pytest.mark.acceptance(spec="chat", scenario="a stopped one-shot turn ends its process")
async def test_cancel_ends_the_process(
    fake: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _lines(tmp_path, monkeypatch, DSH_LINES[:2])
    monkeypatch.setenv("FAKE_SLEEP", "1")
    saved = _Saved()
    adapter = _adapter(DshHeadless(), fake, tmp_path, saved)
    seen: list[Any] = []

    async def consume() -> None:
        async for event in await adapter.run_turn("hi"):
            seen.append(event)

    task = asyncio.create_task(consume())
    for _ in range(200):
        if saved.ids or any(type(e).__name__ == "TurnProgress" for e in seen):
            break
        await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert saved.ids == ["session-1"]
    pids = list((tmp_path / ".coffer" / "upstream-pids").glob("dsh-headless-*.json"))
    assert pids == [], "the process was reaped and its record dropped"
