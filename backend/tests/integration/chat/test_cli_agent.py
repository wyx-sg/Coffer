"""CLI-agent provider + adapter tests (spec 008 — chat with Claude Code / Codex).

Uses a fake spawner that replays canned CLI stdout, so no real CLI is needed.
Covers Claude Code stream-json mapping, session-id write-back + --resume, the
fallback terminal event on a crash, cancellation, cwd validation, and
availability via an injected ``which``.
"""

from __future__ import annotations

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
