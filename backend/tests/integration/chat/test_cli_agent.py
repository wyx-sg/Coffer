"""CLI-agent provider + adapter tests (spec 008 — chat with Claude Code / Codex).

Uses a fake spawner that replays canned CLI stdout, so no real CLI is needed.
Covers Claude Code stream-json mapping, session-id write-back + --resume, the
fallback terminal event on a crash, cancellation, cwd validation, and
availability via an injected ``which``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

import pytest

from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.events import TextDelta, ToolCall, ToolResult, TurnDone, TurnError
from coffer.domain.chat.message import Message, Role, TextBlock
from coffer.domain.errors import AgentConfigRejected
from coffer.infrastructure.chat.cli_agent import CliAgentAdapter
from coffer.infrastructure.chat.cli_providers import (
    ClaudeCodeDialect,
    ClaudeCodeProvider,
    CodexDialect,
    CodexProvider,
)
from coffer.infrastructure.chat.persistence import ConversationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeProcess:
    def __init__(self, lines: list[str], code: int = 0) -> None:
        self._lines = lines
        self._code = code
        self.terminated = False

    async def stdout_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line

    async def wait(self) -> int:
        return self._code

    def terminate(self) -> None:
        self.terminated = True


def _spawner(lines: list[str], code: int = 0):
    captured: dict = {}

    async def spawn(argv: Sequence[str], cwd: str, env):  # type: ignore[no-untyped-def]
        captured["argv"] = list(argv)
        captured["cwd"] = cwd
        return _FakeProcess(lines, code)

    spawn.captured = captured  # type: ignore[attr-defined]
    return spawn


class _NoApprovals:
    async def wait(self, request_id: str):  # pragma: no cover - never used here
        raise AssertionError("CLI agents do not request approval in v1")


def _user_turn(text: str) -> list[Message]:
    return [
        Message(
            id=uuid.uuid4().hex,
            conversation_id="c1",
            seq=0,
            role=Role.USER,
            content=[TextBlock(text=text)],
            status="complete",
            model_id=None,
            prompt_tokens=None,
            completion_tokens=None,
            created_at=datetime.now(tz=UTC),
        )
    ]


async def _collect(adapter: CliAgentAdapter, history: list[Message]):
    stream = await adapter.run_turn(history=history, approvals=_NoApprovals())
    return [ev async for ev in stream]


CLAUDE_STREAM = [
    '{"type":"system","subtype":"init","session_id":"sess-1"}',
    '{"type":"assistant","session_id":"sess-1","message":{"content":['
    '{"type":"text","text":"Let me check."},'
    '{"type":"tool_use","id":"tu_1","name":"Bash","input":{"command":"ls"}}]}}',
    '{"type":"user","message":{"content":['
    '{"type":"tool_result","tool_use_id":"tu_1","content":"file.txt","is_error":false}]}}',
    '{"type":"assistant","session_id":"sess-1","message":{"content":['
    '{"type":"text","text":"There is one file."}]}}',
    '{"type":"result","subtype":"success","session_id":"sess-1","result":"done",'
    '"usage":{"input_tokens":12,"output_tokens":7}}',
]


def _codex_lines(*objs: dict) -> list[str]:
    """Render captured codex event objects back to the JSONL the CLI emits."""
    return [json.dumps(o) for o in objs]


# Real `codex exec --json` output captured from codex-cli 0.125.0. The stream is
# flat JSONL: thread.started (carries thread_id), turn.started, item.started /
# item.completed (content only on completion), turn.completed (usage), and on
# failure both an `error` and a `turn.failed`. Frozen here as the dialect's
# contract so a future codex output change is caught by these tests.
CODEX_HELLO = _codex_lines(
    {"type": "thread.started", "thread_id": "019ebef7-14cb-7aa1-aa58-d3d66d709467"},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "pong"}},
    {
        "type": "turn.completed",
        "usage": {
            "input_tokens": 24855,
            "cached_input_tokens": 2432,
            "output_tokens": 19,
            "reasoning_output_tokens": 12,
        },
    },
)

# A turn that runs one shell command then replies. The command's item.completed
# carries BOTH the command and its result (exit_code + aggregated_output); its
# item.started repeats the same id with partial data and must be ignored.
_CODEX_CMD = "/bin/zsh -lc 'echo coffer-tool-test'"
CODEX_COMMAND = _codex_lines(
    {"type": "thread.started", "thread_id": "019ebef8-2b1d-7380-bc0e-139e489a414b"},
    {"type": "turn.started"},
    {
        "type": "item.started",
        "item": {
            "id": "item_0",
            "type": "command_execution",
            "command": _CODEX_CMD,
            "aggregated_output": "",
            "exit_code": None,
            "status": "in_progress",
        },
    },
    {
        "type": "item.completed",
        "item": {
            "id": "item_0",
            "type": "command_execution",
            "command": _CODEX_CMD,
            "aggregated_output": "coffer-tool-test\n",
            "exit_code": 0,
            "status": "completed",
        },
    },
    {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "done"}},
    {
        "type": "turn.completed",
        "usage": {
            "input_tokens": 49925,
            "cached_input_tokens": 26880,
            "output_tokens": 34,
            "reasoning_output_tokens": 0,
        },
    },
)


# ---------------------------------------------------------------------------
# Adapter / dialect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claude_stream_maps_to_events_and_saves_session():
    saved: list[str] = []

    async def on_session(sid: str) -> None:
        saved.append(sid)

    adapter = CliAgentAdapter(
        dialect=ClaudeCodeDialect(),
        cwd="/tmp",
        resume_session=None,
        extra={},
        spawn=_spawner(CLAUDE_STREAM),
        on_session=on_session,
    )
    events = await _collect(adapter, _user_turn("what files are here?"))
    types = [type(e) for e in events]
    assert types[0].__name__ == "TurnStarted"
    assert TextDelta in types and ToolCall in types and ToolResult in types
    done = events[-1]
    assert isinstance(done, TurnDone)
    assert (done.prompt_tokens, done.completion_tokens) == (12, 7)
    # First TextDelta carries the assistant text; the tool call is mapped.
    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert deltas == ["Let me check.", "There is one file."]
    calls = [e for e in events if isinstance(e, ToolCall)]
    assert calls[0].tool_name == "Bash" and calls[0].tool_input == {"command": "ls"}
    results = [e for e in events if isinstance(e, ToolResult)]
    assert results[0].tool_name == "Bash" and results[0].error is None
    assert saved == ["sess-1"]  # session id persisted for --resume


@pytest.mark.asyncio
async def test_resume_session_is_passed_and_not_re_saved():
    spawn = _spawner(CLAUDE_STREAM)
    saved: list[str] = []

    async def on_session(sid: str) -> None:
        saved.append(sid)

    adapter = CliAgentAdapter(
        dialect=ClaudeCodeDialect(),
        cwd="/work",
        resume_session="sess-1",
        extra={"permission_mode": "acceptEdits"},
        spawn=spawn,
        on_session=on_session,
    )
    await _collect(adapter, _user_turn("continue"))
    argv = spawn.captured["argv"]  # type: ignore[attr-defined]
    assert "--resume" in argv and "sess-1" in argv
    assert "--permission-mode" in argv and "acceptEdits" in argv
    assert spawn.captured["cwd"] == "/work"  # type: ignore[attr-defined]
    assert saved == []  # unchanged session id is not re-saved (stream == resume)


@pytest.mark.asyncio
async def test_crash_without_result_yields_fallback_turn_error():
    adapter = CliAgentAdapter(
        dialect=ClaudeCodeDialect(),
        cwd="/tmp",
        resume_session=None,
        extra={},
        spawn=_spawner(['{"type":"system","subtype":"init","session_id":"s"}'], code=1),
        on_session=_dummy_sink,
    )
    events = await _collect(adapter, _user_turn("hi"))
    assert isinstance(events[-1], TurnError)
    assert events[-1].code == "cli_exit"


@pytest.mark.asyncio
async def test_empty_prompt_is_rejected():
    adapter = CliAgentAdapter(
        dialect=ClaudeCodeDialect(),
        cwd="/tmp",
        resume_session=None,
        extra={},
        spawn=_spawner([]),
        on_session=_dummy_sink,
    )
    events = await _collect(adapter, [])
    assert len(events) == 1 and isinstance(events[0], TurnError)
    assert events[0].code == "empty_prompt"


async def _dummy_sink(sid: str) -> None:
    return None


# ---------------------------------------------------------------------------
# Codex dialect — verified against real `codex exec --json` output
# ---------------------------------------------------------------------------


def _codex_adapter(lines: list[str], on_session=_dummy_sink, **kw):  # type: ignore[no-untyped-def]
    return CliAgentAdapter(
        dialect=CodexDialect(),
        cwd="/tmp",
        resume_session=None,
        extra={},
        spawn=_spawner(lines, **kw),
        on_session=on_session,
    )


@pytest.mark.asyncio
async def test_codex_stream_maps_to_events_and_saves_session():
    saved: list[str] = []

    async def on_session(sid: str) -> None:
        saved.append(sid)

    adapter = _codex_adapter(CODEX_HELLO, on_session=on_session)
    events = await _collect(adapter, _user_turn("ping"))

    assert type(events[0]).__name__ == "TurnStarted"
    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert deltas == ["pong"], "agent_message item maps to assistant text"
    done = events[-1]
    assert isinstance(done, TurnDone)
    # usage maps input_tokens/output_tokens (cached/reasoning are ignored).
    assert (done.prompt_tokens, done.completion_tokens) == (24855, 19)
    # thread.started's thread_id is the session id, persisted for --resume.
    assert saved == ["019ebef7-14cb-7aa1-aa58-d3d66d709467"]


@pytest.mark.asyncio
async def test_codex_command_execution_emits_one_tool_call_and_result():
    adapter = _codex_adapter(CODEX_COMMAND)
    events = await _collect(adapter, _user_turn("run echo"))

    calls = [e for e in events if isinstance(e, ToolCall)]
    results = [e for e in events if isinstance(e, ToolResult)]
    # item.started must NOT also produce a call — content is only on completion.
    assert len(calls) == 1, "the command's item.started must not duplicate the tool call"
    assert calls[0].tool_name == "shell"
    assert calls[0].tool_input == {"command": _CODEX_CMD}
    # The completed command carries its own result — emitted as a ToolResult.
    assert len(results) == 1
    assert results[0].error is None
    assert results[0].output == {"output": "coffer-tool-test\n", "exit_code": 0}
    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert deltas == ["done"]


@pytest.mark.asyncio
async def test_codex_failed_command_maps_to_tool_error():
    """A non-zero exit_code (status 'failed') maps the command's result to a
    ToolResult error, not a success output."""
    lines = _codex_lines(
        {"type": "thread.started", "thread_id": "t-fail"},
        {
            "type": "item.completed",
            "item": {
                "id": "item_0",
                "type": "command_execution",
                "command": "/bin/zsh -lc 'ls /no/such/coffer-xyz'",
                "aggregated_output": "ls: /no/such/coffer-xyz: No such file or directory\n",
                "exit_code": 1,
                "status": "failed",
            },
        },
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
    )
    events = await _collect(_codex_adapter(lines), _user_turn("bad ls"))

    results = [e for e in events if isinstance(e, ToolResult)]
    assert len(results) == 1
    assert results[0].output is None
    assert results[0].error is not None and "No such file" in results[0].error


@pytest.mark.asyncio
async def test_codex_file_change_emits_tool_call_and_result():
    lines = _codex_lines(
        {"type": "thread.started", "thread_id": "t-fc"},
        {
            "type": "item.completed",
            "item": {
                "id": "item_2",
                "type": "file_change",
                "changes": [{"path": "/tmp/x.txt", "kind": "add"}],
                "status": "completed",
            },
        },
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
    )
    events = await _collect(_codex_adapter(lines), _user_turn("write a file"))

    calls = [e for e in events if isinstance(e, ToolCall)]
    results = [e for e in events if isinstance(e, ToolResult)]
    assert len(calls) == 1 and calls[0].tool_name == "file_change"
    assert calls[0].tool_input == {"changes": [{"path": "/tmp/x.txt", "kind": "add"}]}
    assert len(results) == 1 and results[0].error is None
    assert results[0].output == {"changes": [{"path": "/tmp/x.txt", "kind": "add"}]}


@pytest.mark.asyncio
async def test_codex_failed_turn_emits_a_single_turn_error():
    """codex emits BOTH an `error` and a `turn.failed` for one failure — the
    dialect must emit exactly ONE TurnError, not two terminal events."""
    msg = "The 'no-such-model' model is not supported"
    lines = _codex_lines(
        {"type": "thread.started", "thread_id": "t-err"},
        {"type": "turn.started"},
        {"type": "error", "message": msg},
        {"type": "turn.failed", "error": {"message": msg}},
    )
    events = await _collect(_codex_adapter(lines, code=1), _user_turn("use bad model"))

    errors = [e for e in events if isinstance(e, TurnError)]
    assert len(errors) == 1, "the error + turn.failed pair must yield one TurnError"
    assert errors[0].code == "cli_error"
    assert "not supported" in errors[0].message


def test_codex_build_argv_fresh_and_resume():
    """Verified argv shape: `codex exec --json <prompt>`, and resume is
    `codex exec resume <session_id> --json <prompt>`."""
    dialect = CodexDialect()
    assert dialect.build_argv("hi", resume_session=None, extra={}) == [
        "codex",
        "exec",
        "--json",
        "hi",
    ]
    assert dialect.build_argv("hi", resume_session="sid-1", extra={}) == [
        "codex",
        "exec",
        "resume",
        "sid-1",
        "--json",
        "hi",
    ]


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


async def _repo(tmp_path) -> tuple[ConversationRepo, object]:  # type: ignore[no-untyped-def]
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return ConversationRepo(session_maker(engine)), engine


def _conv(agent_key: str) -> Conversation:
    now = datetime.now(tz=UTC)
    return Conversation(
        id=uuid.uuid4().hex,
        agent_key=agent_key,
        title="t",
        model_id=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_provider_requires_existing_cwd(tmp_path):
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv("claude_code"))
    provider = ClaudeCodeProvider(conversations=repo)
    with pytest.raises(AgentConfigRejected):
        await provider.init_conversation(conv.id, {})  # missing cwd
    with pytest.raises(AgentConfigRejected):
        await provider.init_conversation(conv.id, {"cwd": "/no/such/dir/xyz"})
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    stored = await repo.get_agent_config(conv.id)
    assert stored["cwd"] == str(tmp_path)
    await engine.dispose()


@pytest.mark.asyncio
async def test_provider_build_adapter_resumes_stored_session(tmp_path):
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv("claude_code"))
    spawn = _spawner(CLAUDE_STREAM)
    provider = ClaudeCodeProvider(conversations=repo, spawn=spawn)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("hello"))
    # Session id from the stream was written back onto the conversation.
    cfg = await repo.get_agent_config(conv.id)
    assert cfg["session_id"] == "sess-1"
    await engine.dispose()


@pytest.mark.asyncio
async def test_availability_reflects_binary_on_path(tmp_path):
    repo, engine = await _repo(tmp_path)
    present = ClaudeCodeProvider(conversations=repo, which=lambda _b: "/usr/bin/claude")
    absent = CodexProvider(conversations=repo, which=lambda _b: None)
    assert await present.availability() is True
    assert await absent.availability() is False
    assert present.agent_key == "claude_code"
    assert CodexProvider(conversations=repo).agent_key == "codex"
    await engine.dispose()
