"""CursorProvider integration tests (cursor-agent stream-json provider).

Mirrors ``test_opencode_provider.py`` but for ``CursorProvider``:
- ``init_conversation`` defaults/validates the cwd (cursor binds no model).
- ``build_adapter`` returns a ``CursorRunAdapter`` that drives a turn over a
  canned ``cursor-agent -p --output-format stream-json`` NDJSON stream (a fake
  spawn — no real ``cursor-agent`` binary and no Cursor-backend call), yielding
  the platform events and persisting the discovered session id.
- resume passes ``--resume <id>`` on the next turn.
- NO key injection: cursor uses its own auth, so the env handed to spawn is None.
- ``availability()`` reflects the injected ``which``.

This substitutes for a live end-to-end run, which is not exercisable in the build
sandbox: cursor-agent is locked to Cursor's backend and needs Cursor's own auth
(``cursor-agent login`` / ``CURSOR_API_KEY``).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.events import TextDelta, TurnDone, TurnError, TurnStarted
from coffer.domain.chat.message import Message, Role, TextBlock
from coffer.domain.errors import AgentConfigRejected, ConversationNotFound
from coffer.infrastructure.chat.cursor_agent import CursorRunAdapter
from coffer.infrastructure.chat.cursor_provider import CursorProvider
from coffer.infrastructure.chat.persistence import ConversationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

# ---------------------------------------------------------------------------
# Fakes — a canned cursor-agent process + a spawn recording its argv/cwd/env
# ---------------------------------------------------------------------------


#: A sentinel stdout line the fake turns into a ``ValueError`` to exercise the
#: adapter's over-long-line skip path (StreamReader raises this beyond its limit).
_RAISE = b"__RAISE__\n"


class _FakeStream:
    """A fake ``StreamReader``: ``readline()`` yields each line then ``b''`` at EOF.

    A line equal to ``_RAISE`` raises ``ValueError`` (as StreamReader.readline
    does for an over-limit line) so the adapter's skip-and-continue path is tested.
    """

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)
        self._i = 0

    async def readline(self) -> bytes:
        if self._i >= len(self._lines):
            return b""
        line = self._lines[self._i]
        self._i += 1
        if line == _RAISE:
            raise ValueError("Separator is not found, and chunk exceed the limit")
        return line

    async def read(self) -> bytes:
        rest = self._lines[self._i :]
        self._i = len(self._lines)
        return b"".join(rest)


class _FakeProc:
    def __init__(self, stdout: list[bytes], returncode: int = 0) -> None:
        self.stdout = _FakeStream(stdout)
        self.stderr = _FakeStream([b"boom"] if returncode else [])
        self.returncode = returncode
        self.killed = False

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.killed = True


class _FakeSpawn:
    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self._lines = [ln.encode() for ln in lines]
        self._rc = returncode
        self.last_argv: list[str] | None = None
        self.last_cwd: str | None = None
        self.last_env: dict[str, str] | None = None

    async def __call__(self, argv: Any, cwd: str, env: dict[str, str] | None) -> _FakeProc:
        self.last_argv = list(argv)
        self.last_cwd = cwd
        self.last_env = env
        return _FakeProc(self._lines, self._rc)


def _turn_lines(session_id: str = "sess-x", text: str = "hi", is_error: bool = False) -> list[str]:
    return [
        f'{{"type":"system","subtype":"init","session_id":"{session_id}","model":"auto"}}\n',
        (
            '{"type":"assistant","message":{"role":"assistant","content":'
            f'[{{"type":"text","text":"{text}"}}]}}}}\n'
        ),
        f'{{"type":"result","subtype":"success","is_error":{str(is_error).lower()},'
        '"duration_ms":5}\n',
    ]


# ---------------------------------------------------------------------------
# Helpers (mirror test_opencode_provider.py)
# ---------------------------------------------------------------------------


async def _repo(tmp_path: Any) -> tuple[ConversationRepo, Any]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return ConversationRepo(session_maker(engine)), engine


def _conv(agent_key: str = "cursor") -> Conversation:
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


async def _collect(adapter: CursorRunAdapter, history: list[Message]) -> list[Any]:
    stream = await adapter.run_turn(history=history)
    return [ev async for ev in stream]


# ---------------------------------------------------------------------------
# init_conversation — cwd validation (parity with the other providers)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_conversation_defaults_missing_cwd_to_workspace(
    tmp_path: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = CursorProvider(conversations=repo)

    await provider.init_conversation(conv.id, {})
    stored = await repo.get_agent_config(conv.id)
    assert stored.cwd == str(tmp_path / ".coffer" / "workspace")
    assert (tmp_path / ".coffer" / "workspace").is_dir()

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_rejects_non_directory_cwd(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = CursorProvider(conversations=repo)

    with pytest.raises(AgentConfigRejected) as exc:
        await provider.init_conversation(conv.id, {"cwd": "/no/such/dir/xyz"})
    assert exc.value.reason == "cwd_not_a_directory"

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_stores_cwd_and_binds_no_model(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = CursorProvider(conversations=repo)

    # A chat-supplied model is ignored — cursor binds no model.
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path), "model": "gpt-5"})
    stored = await repo.get_agent_config(conv.id)
    assert stored.cwd == str(tmp_path)
    assert stored.model is None

    await engine.dispose()


# ---------------------------------------------------------------------------
# build_adapter — drives a turn over canned NDJSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_yields_text_and_synthesised_turn_done(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    spawn = _FakeSpawn(_turn_lines(text="hi"))
    provider = CursorProvider(conversations=repo, spawn=spawn)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    assert isinstance(adapter, CursorRunAdapter)

    events = await asyncio.wait_for(_collect(adapter, _user_turn("hey", conv.id)), timeout=5)

    assert isinstance(events[0], TurnStarted)
    assert TextDelta(text="hi") in events
    done = events[-1]
    assert isinstance(done, TurnDone)
    assert done.stop_reason == "end_turn"
    # argv carries the headless flags + the prompt as the trailing positional; no
    # --model is projected (cursor uses its own account default).
    assert spawn.last_argv is not None
    assert spawn.last_argv[:6] == [
        "cursor-agent",
        "-p",
        "--output-format",
        "stream-json",
        "--force",
        "--trust",
    ]
    assert spawn.last_argv[-1] == "hey"
    assert "--model" not in spawn.last_argv
    assert spawn.last_cwd == str(tmp_path)
    # Cursor uses its own auth: no custom env is projected into the subprocess.
    assert spawn.last_env is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_turn_persists_session_and_resumes_next_turn(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    spawn1 = _FakeSpawn(_turn_lines(session_id="sess-abc"))
    provider = CursorProvider(conversations=repo, spawn=spawn1)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})

    adapter1 = await provider.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter1, _user_turn("hi", conv.id)), timeout=5)
    cfg = await repo.get_agent_config(conv.id)
    assert cfg.session_id == "sess-abc"

    # Next turn resumes the persisted chat via --resume.
    spawn2 = _FakeSpawn(_turn_lines(session_id="sess-abc"))
    provider2 = CursorProvider(conversations=repo, spawn=spawn2)
    adapter2 = await provider2.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter2, _user_turn("again", conv.id)), timeout=5)
    assert spawn2.last_argv is not None
    assert "--resume" in spawn2.last_argv
    assert "sess-abc" in spawn2.last_argv

    await engine.dispose()


@pytest.mark.asyncio
async def test_nonzero_exit_yields_turn_error(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    # No parseable events + a non-zero exit → a synthesised TurnError.
    spawn = _FakeSpawn(["not-json log line\n"], returncode=1)
    provider = CursorProvider(conversations=repo, spawn=spawn)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)

    events = await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)
    assert any(isinstance(e, TurnError) and e.code == "cursor_run_failed" for e in events)

    await engine.dispose()


@pytest.mark.asyncio
async def test_result_is_error_true_yields_turn_error(tmp_path: Any) -> None:
    # A clean exit (code 0) but the result marker's is_error=true → TurnError.
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    spawn = _FakeSpawn(_turn_lines(is_error=True))
    provider = CursorProvider(conversations=repo, spawn=spawn)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)

    events = await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)
    assert any(isinstance(e, TurnError) and e.code == "cursor_run_failed" for e in events)

    await engine.dispose()


@pytest.mark.asyncio
async def test_over_long_stdout_line_is_skipped(tmp_path: Any) -> None:
    # A line beyond the reader limit makes readline() raise ValueError; the adapter
    # skips it and keeps processing the surrounding lines (no deadlock, no crash).
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    lines = [
        '{"type":"system","subtype":"init","session_id":"sess-x"}\n',
        "__RAISE__\n",
        (
            '{"type":"assistant","message":{"role":"assistant","content":'
            '[{"type":"text","text":"hi"}]}}\n'
        ),
        '{"type":"result","subtype":"success","is_error":false}\n',
    ]
    spawn = _FakeSpawn(lines)
    provider = CursorProvider(conversations=repo, spawn=spawn)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)

    events = await asyncio.wait_for(_collect(adapter, _user_turn("hey", conv.id)), timeout=5)
    assert TextDelta(text="hi") in events
    assert isinstance(events[-1], TurnDone)

    await engine.dispose()


@pytest.mark.asyncio
async def test_build_adapter_raises_conversation_not_found(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    provider = CursorProvider(conversations=repo, spawn=_FakeSpawn(_turn_lines()))
    with pytest.raises(ConversationNotFound):
        await provider.build_adapter("nonexistent-conv-id")
    await engine.dispose()


# ---------------------------------------------------------------------------
# availability + on_conversation_deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_availability_reflects_injected_which(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    present = CursorProvider(conversations=repo, which=lambda _b: "/opt/homebrew/bin/cursor-agent")
    absent = CursorProvider(conversations=repo, which=lambda _b: None)
    assert await present.availability() is True
    assert await absent.availability() is False
    assert present.agent_key == "cursor"
    await engine.dispose()


@pytest.mark.asyncio
async def test_on_conversation_deleted_is_noop(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    provider = CursorProvider(conversations=repo)
    await provider.on_conversation_deleted("any-id")
    await engine.dispose()
