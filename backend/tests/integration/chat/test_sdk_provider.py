"""ClaudeSdkProvider integration tests (spec channels — SDK-backed Claude provider).

Covers the ``ClaudeSdkProvider`` surface:
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
from coffer.domain.chat.errors import AgentConfigRejected, ConversationNotFound
from coffer.domain.chat.message import Message, Role, TextBlock
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
        self.connected_prompt: str | list[dict[str, Any]] | None = None
        self.disconnected = False

    async def connect(self, prompt: str | list[dict[str, Any]]) -> None:
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


def _conv(agent_key: str = "claude_code", *, channel_name: str | None = None) -> Conversation:
    now = datetime.now(tz=UTC)
    return Conversation(
        id=uuid.uuid4().hex,
        agent_key=agent_key,
        title="t",
        created_at=now,
        updated_at=now,
        channel_name=channel_name,
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


async def _collect(adapter: ClaudeSdkAgentAdapter, history: list[Message]) -> list[Any]:
    stream = await adapter.run_turn(history=history)
    return [ev async for ev in stream]


# ---------------------------------------------------------------------------
# init_conversation — cwd validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_conversation_defaults_missing_cwd_to_workspace(  # type: ignore[no-untyped-def]
    tmp_path, monkeypatch
) -> None:
    # No cwd given (a channel without a workspace, or a chat draft with the
    # working-dir UI removed) must NOT fail the turn — it falls back to the
    # Coffer-managed workspace under ~/.coffer, creating it on first use.
    monkeypatch.setenv("HOME", str(tmp_path))
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = ClaudeSdkProvider(conversations=repo)

    await provider.init_conversation(conv.id, {})
    stored = await repo.get_agent_config(conv.id)
    expected = str(tmp_path / ".coffer" / "workspace")
    assert stored.cwd == expected
    assert (tmp_path / ".coffer" / "workspace").is_dir()

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
async def test_init_conversation_stores_cwd(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = ClaudeSdkProvider(conversations=repo)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    stored = await repo.get_agent_config(conv.id)
    assert stored.cwd == str(tmp_path)
    # AgentConfig has no permission field — agents always run with full permissions.
    assert stored.model is None  # nothing beyond cwd persisted

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_persists_model_and_adapter_passes_it(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The model in agent_config is persisted (previously dropped) and reaches
    the SDK options, so a chat-chosen model actually takes effect."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, captured = _make_factory(_simple_messages())
    provider = ClaudeSdkProvider(conversations=repo, session_factory=factory)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path), "model": "opus"})
    stored = await repo.get_agent_config(conv.id)
    assert stored.model == "opus"

    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("hi", conv.id))
    assert captured[0].model == "opus"

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_persists_effort_and_adapter_passes_it(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The reasoning level travels the same road the model does. Claude Code
    takes it as its own option (the SDK renders it as ``--effort``), so it must
    survive creation and reach ``ClaudeAgentOptions`` — a draft that chose one
    is choosing it for the FIRST turn, which is the one already running by the
    time anything could set it afterwards."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, captured = _make_factory(_simple_messages())
    provider = ClaudeSdkProvider(conversations=repo, session_factory=factory)

    await provider.init_conversation(
        conv.id, {"cwd": str(tmp_path), "model": "opus", "effort": "xhigh"}
    )
    stored = await repo.get_agent_config(conv.id)
    assert stored.effort == "xhigh"

    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("hi", conv.id))
    assert captured[0].effort == "xhigh"

    await engine.dispose()


@pytest.mark.asyncio
async def test_no_effort_chosen_sends_none_so_the_cli_keeps_its_own(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Unset must be OMITTED rather than sent as a guess: the CLI then runs at
    whatever its own config says, which is where Coffer started."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, captured = _make_factory(_simple_messages())
    provider = ClaudeSdkProvider(conversations=repo, session_factory=factory)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("hi", conv.id))

    assert captured[0].effort is None

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
    assert cfg.session_id == "sess-sdk"

    # Second build_adapter must pass resume_session.
    adapter2 = await provider.build_adapter(conv.id)
    factory2, captured2 = _make_factory(_simple_messages("sess-sdk"))
    provider2 = ClaudeSdkProvider(conversations=repo, session_factory=factory2)
    adapter2 = await provider2.build_adapter(conv.id)
    await _collect(adapter2, _user_turn("hi again", conv.id))
    assert len(captured2) == 1
    assert captured2[0].resume == "sess-sdk"

    await engine.dispose()


@pytest.mark.acceptance(
    spec="channels",
    scenario="the channel-driven agent is told it is on a chat channel",
)
@pytest.mark.asyncio
async def test_channel_conversation_appends_system_context(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A channel-originated conversation makes build_adapter inject a system-prompt
    note (channel name + mobile/no-dialogs guidance) onto Claude Code's preset."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv(channel_name="Telegram"))
    factory, captured = _make_factory(_simple_messages())

    async def _models(agent_key: str) -> list[str]:
        return ["fable", "sonnet"]

    provider = ClaudeSdkProvider(conversations=repo, session_factory=factory, list_models=_models)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("hi", conv.id))

    system_prompt = captured[0].system_prompt
    assert isinstance(system_prompt, dict)
    assert system_prompt["type"] == "preset"
    assert system_prompt["preset"] == "claude_code"
    assert "Telegram" in system_prompt["append"]
    # The channel note and the model note are composed into one append.
    assert "no model override" in system_prompt["append"]

    await engine.dispose()


@pytest.mark.acceptance(
    spec="memory",
    scenario="a channel turn carries the index without a hook",
)
@pytest.mark.asyncio
async def test_channel_conversation_appends_memory_context(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A channel-driven turn gets the memory index through this same
    system-prompt append — no session-start hook, no install (spec memory
    FR-053). The provider never builds the payload itself: it calls the
    injected composer, the same seam ``list_models`` already uses, so the
    chat/provider layer never reaches into the memory kind directly."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv(channel_name="Telegram"))
    factory, captured = _make_factory(_simple_messages())

    calls: list[tuple[str, str]] = []

    async def _memory(agent_key: str, cwd: str) -> str | None:
        calls.append((agent_key, cwd))
        # The real composer's shape (application/memory/index.index_line): a
        # line per note naming the file its body is in, not a budgeted digest.
        # A stub that keeps the old shape teaches a reader the wrong payload.
        return (
            "## Coffer memory\nKnown about you:\n"
            "- **Likes tabs** (`likes-tabs.md`) — Two spaces are not a tab."
        )

    provider = ClaudeSdkProvider(
        conversations=repo, session_factory=factory, compose_memory_context=_memory
    )

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("hi", conv.id))

    append = captured[0].system_prompt["append"]
    assert "## Coffer memory" in append
    assert "- **Likes tabs** (`likes-tabs.md`)" in append
    # Resolved lazily per turn, keyed by this agent and the conversation's cwd —
    # never guessed or hardcoded (mirrors how ``list_models`` is called).
    assert calls == [("claude_code", str(tmp_path))]

    await engine.dispose()


@pytest.mark.asyncio
async def test_no_memory_to_deliver_appends_no_header(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """When the composer has nothing to deliver, the turn carries no memory
    header at all — an empty ``## Coffer memory`` section would be worse than
    saying nothing."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv(channel_name="Telegram"))
    factory, captured = _make_factory(_simple_messages())

    async def _memory(agent_key: str, cwd: str) -> str | None:
        return None

    provider = ClaudeSdkProvider(
        conversations=repo, session_factory=factory, compose_memory_context=_memory
    )

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("hi", conv.id))

    assert "Coffer memory" not in captured[0].system_prompt["append"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_web_conversation_never_gets_memory_context(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A non-channel (web UI) turn is not the "channel-driven turn" spec memory
    FR-053 names — even a wired composer must not be consulted for it (the
    agent's own hook, FR-054, is the delivery path there instead)."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())  # no channel_name
    factory, captured = _make_factory(_simple_messages())

    async def _memory(agent_key: str, cwd: str) -> str | None:
        raise AssertionError("memory composer must not be called for a non-channel turn")

    provider = ClaudeSdkProvider(
        conversations=repo, session_factory=factory, compose_memory_context=_memory
    )

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("hi", conv.id))

    assert "Coffer memory" not in captured[0].system_prompt["append"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_web_conversation_gets_the_model_note_only(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A non-channel (web UI) conversation gets no channel guidance, but still
    gets the model note — the agent cannot otherwise tell which model Coffer put
    it on, and left to itself it guesses wrong."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())  # no channel_name
    factory, captured = _make_factory(_simple_messages())

    async def _models(agent_key: str) -> list[str]:
        return ["fable", "sonnet"]

    provider = ClaudeSdkProvider(conversations=repo, session_factory=factory, list_models=_models)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path), "model": "fable"})
    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("hi", conv.id))

    system_prompt = captured[0].system_prompt
    assert isinstance(system_prompt, dict)
    append = system_prompt["append"]
    assert "`fable`" in append
    assert "sonnet" in append
    assert "chat channel — " not in append  # no channel guidance for a web turn

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
    assert cfg.session_id == "sess-42"

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
