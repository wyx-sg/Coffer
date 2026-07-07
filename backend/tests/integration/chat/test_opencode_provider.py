"""OpencodeProvider integration tests (spec 008 / ADR-040 — opencode-run provider).

Mirrors ``test_codex_provider.py`` but for ``OpencodeProvider``:
- ``init_conversation`` defaults/validates the cwd and stores the model.
- ``build_adapter`` returns an ``OpencodeRunAdapter`` that drives a turn over a
  canned ``opencode run --format json`` stdout stream (a fake spawn — no real
  ``opencode`` binary and no model call), yielding the platform events and
  persisting the discovered session id.
- resume passes ``--session <id>`` on the next turn.
- ``COFFER_PROVIDER_KEY`` is injected (merged) when a connection is active.
- ``availability()`` reflects the injected ``which``.

This substitutes for a live end-to-end run, which is not exercisable in the build
sandbox (opencode's model calls hang there).
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
from coffer.infrastructure.chat.opencode_agent import OpencodeRunAdapter
from coffer.infrastructure.chat.opencode_provider import OpencodeProvider
from coffer.infrastructure.chat.persistence import ConversationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

# ---------------------------------------------------------------------------
# Fakes — a canned opencode process + a spawn recording its argv/cwd/env
# ---------------------------------------------------------------------------


class _FakeStream:
    """An async-iterable stdout that also answers ``read()`` (used for stderr)."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    async def __aiter__(self) -> Any:  # pragma: no cover - trivial
        for line in self._lines:
            yield line

    async def read(self) -> bytes:
        return b"".join(self._lines)


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


def _turn_lines(session_id: str = "ses_x", text: str = "hi") -> list[str]:
    return [
        f'{{"type":"text","id":"p1","text":"{text}","sessionID":"{session_id}"}}\n',
        '{"type":"step-finish","reason":"stop","tokens":{"input":10,"output":1}}\n',
    ]


# ---------------------------------------------------------------------------
# Helpers (mirror test_codex_provider.py)
# ---------------------------------------------------------------------------


async def _repo(tmp_path: Any) -> tuple[ConversationRepo, Any]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return ConversationRepo(session_maker(engine)), engine


def _conv(agent_key: str = "opencode") -> Conversation:
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


async def _collect(adapter: OpencodeRunAdapter, history: list[Message]) -> list[Any]:
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
    provider = OpencodeProvider(conversations=repo)

    await provider.init_conversation(conv.id, {})
    stored = await repo.get_agent_config(conv.id)
    assert stored.cwd == str(tmp_path / ".coffer" / "workspace")
    assert (tmp_path / ".coffer" / "workspace").is_dir()

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_rejects_non_directory_cwd(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = OpencodeProvider(conversations=repo)

    with pytest.raises(AgentConfigRejected) as exc:
        await provider.init_conversation(conv.id, {"cwd": "/no/such/dir/xyz"})
    assert exc.value.reason == "cwd_not_a_directory"

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_stores_cwd_and_model(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = OpencodeProvider(conversations=repo)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path), "model": "gpt-5"})
    stored = await repo.get_agent_config(conv.id)
    assert stored.cwd == str(tmp_path)
    assert stored.model == "gpt-5"

    await engine.dispose()


# ---------------------------------------------------------------------------
# build_adapter — drives a turn over canned stdout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_yields_text_and_synthesised_turn_done(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    spawn = _FakeSpawn(_turn_lines(text="hi"))
    provider = OpencodeProvider(conversations=repo, spawn=spawn)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    assert isinstance(adapter, OpencodeRunAdapter)

    events = await asyncio.wait_for(_collect(adapter, _user_turn("hey", conv.id)), timeout=5)

    assert isinstance(events[0], TurnStarted)
    assert TextDelta(text="hi") in events
    done = events[-1]
    assert isinstance(done, TurnDone)
    assert done.prompt_tokens == 10
    assert done.completion_tokens == 1
    # argv carries the headless flags + the prompt as the trailing positional.
    assert spawn.last_argv is not None
    assert spawn.last_argv[:5] == [
        "opencode",
        "run",
        "--format",
        "json",
        "--dangerously-skip-permissions",
    ]
    assert spawn.last_argv[-1] == "hey"
    assert spawn.last_cwd == str(tmp_path)

    await engine.dispose()


@pytest.mark.asyncio
async def test_turn_persists_session_and_resumes_next_turn(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    spawn1 = _FakeSpawn(_turn_lines(session_id="ses_abc"))
    provider = OpencodeProvider(conversations=repo, spawn=spawn1)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})

    adapter1 = await provider.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter1, _user_turn("hi", conv.id)), timeout=5)
    cfg = await repo.get_agent_config(conv.id)
    assert cfg.session_id == "ses_abc"

    # Next turn resumes the persisted session via --session.
    spawn2 = _FakeSpawn(_turn_lines(session_id="ses_abc"))
    provider2 = OpencodeProvider(conversations=repo, spawn=spawn2)
    adapter2 = await provider2.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter2, _user_turn("again", conv.id)), timeout=5)
    assert spawn2.last_argv is not None
    assert "--session" in spawn2.last_argv
    assert "ses_abc" in spawn2.last_argv

    await engine.dispose()


@pytest.mark.asyncio
async def test_nonzero_exit_yields_turn_error(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    # No parseable events + a non-zero exit → a synthesised TurnError.
    spawn = _FakeSpawn(["not-json log line\n"], returncode=1)
    provider = OpencodeProvider(conversations=repo, spawn=spawn)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)

    events = await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)
    assert any(isinstance(e, TurnError) and e.code == "opencode_run_failed" for e in events)

    await engine.dispose()


@pytest.mark.asyncio
async def test_build_adapter_raises_conversation_not_found(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    provider = OpencodeProvider(conversations=repo, spawn=_FakeSpawn(_turn_lines()))
    with pytest.raises(ConversationNotFound):
        await provider.build_adapter("nonexistent-conv-id")
    await engine.dispose()


# ---------------------------------------------------------------------------
# COFFER_PROVIDER_KEY injection (ADR-032 env_key seam, shared with Codex)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_key_injected_and_merged(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    spawn = _FakeSpawn(_turn_lines())

    async def resolve_key() -> str | None:
        return "sk-opencode-abc"

    provider = OpencodeProvider(conversations=repo, spawn=spawn, resolve_key=resolve_key)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)

    assert spawn.last_env is not None
    assert spawn.last_env["COFFER_PROVIDER_KEY"] == "sk-opencode-abc"
    assert "PATH" in spawn.last_env  # merged with the daemon env, not replaced

    await engine.dispose()


@pytest.mark.asyncio
async def test_no_active_key_inherits_daemon_env(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    spawn = _FakeSpawn(_turn_lines())

    async def resolve_key() -> str | None:
        return None

    provider = OpencodeProvider(conversations=repo, spawn=spawn, resolve_key=resolve_key)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)
    assert spawn.last_env is None

    await engine.dispose()


# ---------------------------------------------------------------------------
# availability + on_conversation_deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_availability_reflects_injected_which(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    present = OpencodeProvider(conversations=repo, which=lambda _b: "/opt/homebrew/bin/opencode")
    absent = OpencodeProvider(conversations=repo, which=lambda _b: None)
    assert await present.availability() is True
    assert await absent.availability() is False
    assert present.agent_key == "opencode"
    await engine.dispose()


@pytest.mark.asyncio
async def test_on_conversation_deleted_is_noop(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    provider = OpencodeProvider(conversations=repo)
    await provider.on_conversation_deleted("any-id")
    await engine.dispose()
