"""ClaudeSdkProvider integration tests (spec 008 — SDK-backed Claude provider).

Mirrors ``test_cli_agent.py``'s provider suite but for ``ClaudeSdkProvider``:
- ``init_conversation`` rejects a missing or non-directory cwd.
- ``build_adapter`` returns a ``ClaudeSdkAgentAdapter`` with the right cwd / resume
  and a working session sink.
- ``availability()`` reflects the injected ``which``.

A fake ``SdkSessionFactory`` is injected throughout — no real ``claude`` binary or
network is touched.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
)
from claude_agent_sdk import TextBlock as SdkTextBlock

from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.message import Message, Role, TextBlock
from coffer.domain.errors import AgentConfigRejected, ConversationNotFound
from coffer.infrastructure.chat.claude_sdk_agent import ClaudeSdkAgentAdapter
from coffer.infrastructure.chat.claude_sdk_provider import ClaudeSdkProvider
from coffer.infrastructure.chat.persistence import ConversationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeSdkSession:
    """Replays canned SDK messages; does not touch the real claude binary."""

    def __init__(self, options: ClaudeAgentOptions, messages: list[Any]) -> None:
        self.options = options
        self._messages = messages
        self.connected_prompt: str | None = None
        self.disconnected = False

    async def connect(self, prompt: str) -> None:
        self.connected_prompt = prompt

    async def receive_messages(self) -> AsyncIterator[Any]:
        for msg in self._messages:
            yield msg

    async def interrupt(self) -> None:  # pragma: no cover
        pass

    async def disconnect(self) -> None:
        self.disconnected = True


def _make_factory(messages: list[Any]) -> tuple[Any, list[ClaudeAgentOptions]]:
    """Return (factory_callable, captured_options_list)."""
    captured: list[ClaudeAgentOptions] = []

    def factory(options: ClaudeAgentOptions) -> _FakeSdkSession:
        captured.append(options)
        return _FakeSdkSession(options, messages)

    return factory, captured


def _simple_messages(session_id: str = "sess-sdk") -> list[Any]:
    return [
        SystemMessage(subtype="init", data={"session_id": session_id}),
        AssistantMessage(content=[SdkTextBlock(text="hello")], model="claude"),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id=session_id,
            usage={"input_tokens": 5, "output_tokens": 3},
            total_cost_usd=0.0,
        ),
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _repo(tmp_path) -> tuple[ConversationRepo, Any]:  # type: ignore[no-untyped-def]
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return ConversationRepo(session_maker(engine)), engine


def _conv(agent_key: str = "claude_code") -> Conversation:
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


class _NoApprovals:
    async def wait(self, request_id: str) -> Any:  # pragma: no cover
        raise AssertionError("no approval expected")


async def _collect(adapter: ClaudeSdkAgentAdapter, history: list[Message]) -> list[Any]:
    stream = await adapter.run_turn(history=history, approvals=_NoApprovals())
    return [ev async for ev in stream]


# ---------------------------------------------------------------------------
# init_conversation — cwd validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_conversation_rejects_missing_cwd(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = ClaudeSdkProvider(conversations=repo)

    with pytest.raises(AgentConfigRejected) as exc:
        await provider.init_conversation(conv.id, {})
    assert exc.value.reason == "invalid_cwd"

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_rejects_non_directory_cwd(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = ClaudeSdkProvider(conversations=repo)

    with pytest.raises(AgentConfigRejected) as exc:
        await provider.init_conversation(conv.id, {"cwd": "/no/such/dir/xyz"})
    assert exc.value.reason == "cwd_not_a_directory"

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_stores_cwd_and_permission_mode(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = ClaudeSdkProvider(conversations=repo)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path), "permission_mode": "plan"})
    stored = await repo.get_agent_config(conv.id)
    assert stored["cwd"] == str(tmp_path)
    assert stored["permission_mode"] == "plan"

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_omits_permission_mode_when_absent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = ClaudeSdkProvider(conversations=repo)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    stored = await repo.get_agent_config(conv.id)
    assert stored["cwd"] == str(tmp_path)
    assert "permission_mode" not in stored

    await engine.dispose()


# ---------------------------------------------------------------------------
# build_adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_adapter_returns_sdk_adapter_with_correct_cwd(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, captured = _make_factory(_simple_messages())
    provider = ClaudeSdkProvider(conversations=repo, session_factory=factory)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)

    assert isinstance(adapter, ClaudeSdkAgentAdapter)
    # Drive one turn so options are captured.
    await _collect(adapter, _user_turn("hi", conv.id))
    assert len(captured) == 1
    assert captured[0].cwd == str(tmp_path)

    await engine.dispose()


@pytest.mark.asyncio
async def test_build_adapter_resumes_stored_session(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Session id written by the first turn is passed as resume_session on next."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, _captured = _make_factory(_simple_messages("sess-sdk"))
    provider = ClaudeSdkProvider(conversations=repo, session_factory=factory)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("hi", conv.id))

    # Session id must have been written back.
    cfg = await repo.get_agent_config(conv.id)
    assert cfg["session_id"] == "sess-sdk"

    # Second build_adapter must pass resume_session.
    adapter2 = await provider.build_adapter(conv.id)
    factory2, captured2 = _make_factory(_simple_messages("sess-sdk"))
    provider2 = ClaudeSdkProvider(conversations=repo, session_factory=factory2)
    adapter2 = await provider2.build_adapter(conv.id)
    await _collect(adapter2, _user_turn("hi again", conv.id))
    assert len(captured2) == 1
    assert captured2[0].resume == "sess-sdk"

    await engine.dispose()


@pytest.mark.asyncio
async def test_build_adapter_raises_conversation_not_found(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo, engine = await _repo(tmp_path)
    factory, _ = _make_factory([])
    provider = ClaudeSdkProvider(conversations=repo, session_factory=factory)

    with pytest.raises(ConversationNotFound):
        await provider.build_adapter("nonexistent-conv-id")

    await engine.dispose()


@pytest.mark.asyncio
async def test_build_adapter_session_sink_writes_back(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The on_session sink wired by build_adapter persists the session_id."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, _ = _make_factory(_simple_messages("sess-42"))
    provider = ClaudeSdkProvider(conversations=repo, session_factory=factory)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("go", conv.id))

    cfg = await repo.get_agent_config(conv.id)
    assert cfg["session_id"] == "sess-42"

    await engine.dispose()


# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_availability_reflects_injected_which(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo, engine = await _repo(tmp_path)

    present = ClaudeSdkProvider(conversations=repo, which=lambda _b: "/usr/bin/claude")
    absent = ClaudeSdkProvider(conversations=repo, which=lambda _b: None)

    assert await present.availability() is True
    assert await absent.availability() is False
    assert present.agent_key == "claude_code"

    await engine.dispose()


# ---------------------------------------------------------------------------
# on_conversation_deleted — no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_conversation_deleted_is_noop(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo, engine = await _repo(tmp_path)
    provider = ClaudeSdkProvider(conversations=repo)
    # Should complete without error.
    await provider.on_conversation_deleted("any-id")
    await engine.dispose()
