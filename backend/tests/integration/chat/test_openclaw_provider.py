"""OpenclawProvider integration tests (openclaw non-streaming JSON provider).

Mirrors ``test_cursor_provider.py`` in mechanics but for openclaw's shape
(ADR-044):

- ``init_conversation`` IGNORES the conversation cwd (openclaw has no cwd flag —
  turns run in its own agent workspace) and stores only the model override.
- ``build_adapter`` returns an ``OpenclawAgentAdapter`` that drives a turn over
  a canned ``openclaw agent --json --local`` result blob (a fake spawn — no real
  ``openclaw`` binary and no model call), yielding TurnStarted → one TextDelta →
  TurnDone.
- The session key is Coffer-derived (``coffer-<conversation_id>``), passed as
  ``--session-key`` on every turn — nothing is discovered or persisted.
- COFFER_PROVIDER_KEY is injected into the subprocess env when a key resolves
  (the projected openclaw.json provider block references ``${...}``).
- ``availability()`` reflects the injected ``which``.

A live end-to-end turn against the real openclaw is exercised separately (the
ADR-044 adapter smoke probe); these tests pin the subprocess/parse mechanics.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.events import TextDelta, TurnDone, TurnError, TurnStarted
from coffer.domain.chat.message import Message, Role, TextBlock
from coffer.domain.errors import ConversationNotFound
from coffer.infrastructure.chat.openclaw_agent import OpenclawAgentAdapter
from coffer.infrastructure.chat.openclaw_provider import OpenclawProvider, session_key_for
from coffer.infrastructure.chat.persistence import ConversationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

# ---------------------------------------------------------------------------
# Fakes — a canned openclaw process + a spawn recording its argv/cwd/env
# ---------------------------------------------------------------------------


class _FakeStream:
    """A fake ``StreamReader``: ``read()`` yields everything, ``readline()``
    yields line by line then ``b""`` at EOF (the adapter reads stdout whole and
    drains stderr line-wise)."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._lines = data.splitlines(keepends=True)
        self._i = 0

    async def read(self) -> bytes:
        data, self._data = self._data, b""
        return data

    async def readline(self) -> bytes:
        if self._i >= len(self._lines):
            return b""
        line = self._lines[self._i]
        self._i += 1
        return line


class _FakeProc:
    def __init__(self, stdout: bytes, returncode: int = 0) -> None:
        self.stdout = _FakeStream(stdout)
        self.stderr = _FakeStream(b"log line\nboom detail\n" if returncode else b"")
        self.returncode = returncode
        self.killed = False

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.killed = True


class _FakeSpawn:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self._stdout = stdout.encode()
        self._rc = returncode
        self.last_argv: list[str] | None = None
        self.last_cwd: str | None = None
        self.last_env: dict[str, str] | None = None

    async def __call__(self, argv: Any, cwd: str, env: dict[str, str] | None) -> _FakeProc:
        self.last_argv = list(argv)
        self.last_cwd = cwd
        self.last_env = env
        return _FakeProc(self._stdout, self._rc)


def _result_blob(text: str = "PONG") -> str:
    # The real `openclaw agent --json --local` blob shape, captured live on
    # 2026.6.11: payloads top-level, everything else under `meta`.
    return json.dumps(
        {
            "payloads": [{"text": text, "mediaUrl": None}],
            "meta": {
                "finalAssistantVisibleText": text,
                "stopReason": "stop",
                "completion": {"stopReason": "stop", "finishReason": "stop"},
                "executionTrace": {
                    "winnerProvider": "deepseek",
                    "winnerModel": "deepseek-v4-flash",
                    "fallbackUsed": False,
                    "runner": "embedded",
                },
            },
        }
    )


# ---------------------------------------------------------------------------
# Helpers (mirror test_cursor_provider.py)
# ---------------------------------------------------------------------------


async def _repo(tmp_path: Any) -> tuple[ConversationRepo, Any]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return ConversationRepo(session_maker(engine)), engine


def _conv(agent_key: str = "openclaw") -> Conversation:
    now = datetime.now(tz=UTC)
    return Conversation(
        id=uuid.uuid4().hex,
        agent_key=agent_key,
        title="t",
        model_id=None,
        created_at=now,
        updated_at=now,
    )


def _user_turn(text: str, conv_id: str = "c1") -> list[Message]:
    return [
        Message(
            id=uuid.uuid4().hex,
            conversation_id=conv_id,
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


async def _collect(adapter: OpenclawAgentAdapter, history: list[Message]) -> list[Any]:
    stream = await adapter.run_turn(history=history)
    return [ev async for ev in stream]


# ---------------------------------------------------------------------------
# init_conversation — cwd is IGNORED (no cwd semantics), model stored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_conversation_ignores_cwd_and_stores_model(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = OpenclawProvider(conversations=repo)

    # A supplied cwd — even a nonexistent one — is neither validated nor stored:
    # openclaw has no cwd flag and always runs in its own agent workspace.
    await provider.init_conversation(
        conv.id, {"cwd": "/no/such/dir/xyz", "model": "deepseek/deepseek-v4-flash"}
    )
    stored = await repo.get_agent_config(conv.id)
    assert stored.cwd is None
    assert stored.model == "deepseek/deepseek-v4-flash"

    await engine.dispose()


# ---------------------------------------------------------------------------
# build_adapter — drives a turn over the canned result blob
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_yields_text_and_turn_done_from_the_blob(tmp_path: Any, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    spawn = _FakeSpawn(_result_blob(text="PONG"))
    provider = OpenclawProvider(conversations=repo, spawn=spawn)

    await provider.init_conversation(conv.id, {})
    adapter = await provider.build_adapter(conv.id)
    assert isinstance(adapter, OpenclawAgentAdapter)

    events = await asyncio.wait_for(_collect(adapter, _user_turn("ping", conv.id)), timeout=5)

    assert isinstance(events[0], TurnStarted)
    assert events[1] == TextDelta(text="PONG")
    done = events[-1]
    assert isinstance(done, TurnDone)
    assert done.stop_reason == "stop"
    # The execution trace's winner stamps the assistant message.
    assert adapter.model_id == "deepseek/deepseek-v4-flash"

    # argv: the headless embedded turn with Coffer's deterministic session key;
    # no --model when the conversation carries no override.
    assert spawn.last_argv is not None
    assert spawn.last_argv[:5] == [
        "openclaw",
        "agent",
        "--agent",
        "main",
        "--session-key",
    ]
    assert spawn.last_argv[5] == session_key_for(conv.id) == f"coffer-{conv.id}"
    assert spawn.last_argv[-4:] == ["-m", "ping", "--json", "--local"]
    assert "--model" not in spawn.last_argv
    # No resolve_key wired → the subprocess inherits the daemon env unchanged.
    assert spawn.last_env is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_model_override_is_passed_and_key_injected(tmp_path: Any, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    spawn = _FakeSpawn(_result_blob())

    async def _key() -> str | None:
        return "sk-test-123"

    provider = OpenclawProvider(conversations=repo, spawn=spawn, resolve_key=_key)
    await provider.init_conversation(conv.id, {"model": "coffer/gpt-5"})
    adapter = await provider.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)

    assert spawn.last_argv is not None
    i = spawn.last_argv.index("--model")
    assert spawn.last_argv[i + 1] == "coffer/gpt-5"
    # The key lands in the env var the projected provider block references,
    # MERGED over the daemon env (PATH must survive).
    assert spawn.last_env is not None
    assert spawn.last_env["COFFER_PROVIDER_KEY"] == "sk-test-123"
    assert "PATH" in spawn.last_env

    await engine.dispose()


@pytest.mark.asyncio
async def test_nonzero_exit_yields_turn_error_with_stderr_tail(tmp_path: Any, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    spawn = _FakeSpawn("", returncode=1)
    provider = OpenclawProvider(conversations=repo, spawn=spawn)
    await provider.init_conversation(conv.id, {})
    adapter = await provider.build_adapter(conv.id)

    events = await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)
    err = events[-1]
    assert isinstance(err, TurnError)
    assert err.code == "openclaw_run_failed"
    assert "boom detail" in err.message

    await engine.dispose()


@pytest.mark.asyncio
async def test_unparseable_stdout_yields_parse_error(tmp_path: Any, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    spawn = _FakeSpawn("not json at all", returncode=0)
    provider = OpenclawProvider(conversations=repo, spawn=spawn)
    await provider.init_conversation(conv.id, {})
    adapter = await provider.build_adapter(conv.id)

    events = await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)
    err = events[-1]
    assert isinstance(err, TurnError)
    assert err.code == "openclaw_parse_failed"

    await engine.dispose()


@pytest.mark.asyncio
async def test_build_adapter_raises_conversation_not_found(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    provider = OpenclawProvider(conversations=repo, spawn=_FakeSpawn(_result_blob()))
    with pytest.raises(ConversationNotFound):
        await provider.build_adapter("nonexistent-conv-id")
    await engine.dispose()


# ---------------------------------------------------------------------------
# availability + on_conversation_deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_availability_reflects_injected_which(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    present = OpenclawProvider(conversations=repo, which=lambda _b: "/opt/homebrew/bin/openclaw")
    absent = OpenclawProvider(conversations=repo, which=lambda _b: None)
    assert await present.availability() is True
    assert await absent.availability() is False
    assert present.agent_key == "openclaw"
    await engine.dispose()


@pytest.mark.asyncio
async def test_on_conversation_deleted_is_noop(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    provider = OpenclawProvider(conversations=repo)
    await provider.on_conversation_deleted("any-id")
    await engine.dispose()
