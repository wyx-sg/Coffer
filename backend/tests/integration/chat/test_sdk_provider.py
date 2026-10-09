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

from coffer.domain.chat.channel_note import ChannelNote
from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.errors import AgentConfigRejected, ConversationNotFound
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


#: The channel a bridged conversation points at. A uid, because that is what the
#: row stores (ADR identity-is-the-uid-inside-the-file) — the name reaches the
#: prompt only through the resolver the provider is handed.
_TELEGRAM_UID = "0b9d2f1a4c7e4b6a8d3f5c1e7a9b2d40"


async def _telegram_name(uid: str, conversation_id: str) -> ChannelNote | None:
    assert uid == _TELEGRAM_UID
    return ChannelNote(name="tg", platform="Telegram", chat_kind="direct")


def _conv(agent_key: str = "claude_code", *, channel_uid: str | None = None) -> Conversation:
    now = datetime.now(tz=UTC)
    return Conversation(
        id=uuid.uuid4().hex,
        agent_key=agent_key,
        title="t",
        created_at=now,
        updated_at=now,
        channel_uid=channel_uid,
    )


def _user_turn(text: str, conv_id: str = "c1") -> str:
    return text


async def _collect(adapter: ClaudeSdkAgentAdapter, prompt: str) -> list[Any]:
    stream = await adapter.run_turn(prompt)
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
    expected = str(tmp_path / ".coffer" / "content" / "workspace")
    assert stored.cwd == expected
    assert (tmp_path / ".coffer" / "content" / "workspace").is_dir()

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
@pytest.mark.acceptance(spec="chat", scenario="a turn carries no history")
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
@pytest.mark.acceptance(
    spec="chat", scenario="a channel-driven turn carries the channel note and the model note"
)
@pytest.mark.asyncio
async def test_channel_conversation_appends_system_context(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A channel-originated conversation makes build_adapter inject a system-prompt
    note (channel name + mobile/no-dialogs guidance) onto Claude Code's preset.

    The row holds the channel's uid; the human-readable name the note actually
    says is resolved from it at turn time, which is what lets the user rename
    the channel without every conversation bound to it going stale."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv(channel_uid=_TELEGRAM_UID))
    factory, captured = _make_factory(_simple_messages())

    async def _models(agent_key: str) -> list[str]:
        return ["fable", "sonnet"]

    provider = ClaudeSdkProvider(
        conversations=repo,
        session_factory=factory,
        list_models=_models,
        resolve_channel=_telegram_name,
    )

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("hi", conv.id))

    system_prompt = captured[0].system_prompt
    assert isinstance(system_prompt, dict)
    assert system_prompt["type"] == "preset"
    assert system_prompt["preset"] == "claude_code"
    assert "Telegram" in system_prompt["append"]
    # The channel note and the model note are composed into one append, in
    # that order, and nothing from the memory layer.
    append = system_prompt["append"]
    assert append.index("Telegram") < append.index("no model override")
    assert "memory" not in append.lower()

    await engine.dispose()


@pytest.mark.asyncio
async def test_a_channel_whose_name_will_not_resolve_still_gets_the_channel_note(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """The uid decides that this is a channel turn; the name is only colour.

    A channel deleted out from under a live thread leaves the uid unresolvable.
    If that downgraded the turn, the agent would lose the "short replies, you
    cannot click dialogs" contract for a
    reason that has nothing to do with where the user is sitting. So the note
    goes out either way, minus the name it cannot honestly give."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv(channel_uid=_TELEGRAM_UID))
    factory, captured = _make_factory(_simple_messages())

    async def _gone(uid: str, conversation_id: str) -> ChannelNote | None:
        return None

    provider = ClaudeSdkProvider(
        conversations=repo,
        session_factory=factory,
        resolve_channel=_gone,
    )

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await _collect(adapter, _user_turn("hi", conv.id))

    append = captured[0].system_prompt["append"]
    assert "You are replying in a chat channel" in append
    assert "MEDIA:/absolute/path" in append

    await engine.dispose()


@pytest.mark.acceptance(
    spec="chat", scenario="a channel-driven turn carries the channel note and the model note"
)
@pytest.mark.asyncio
async def test_web_conversation_gets_the_model_note_only(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A non-channel (web UI) conversation gets no channel guidance, but still
    gets the model note — the agent cannot otherwise tell which model Coffer put
    it on, and left to itself it guesses wrong."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())  # no channel binding
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
@pytest.mark.acceptance(spec="memory", scenario="a channel turn carries no memory from Coffer")
async def test_a_channel_turn_carries_no_memory_from_coffer(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Coffer puts no memory into a turn: a channel turn's Claude Code starts
    with the same environment as one the developer drives, and its system
    prompt names no memory. Its memory is what Claude Code reads itself."""
    repo, engine = await _repo(tmp_path)
    channel = await repo.create(_conv(channel_uid=_TELEGRAM_UID))
    web = await repo.create(_conv())
    envs: dict[str, dict[str, str]] = {}
    prompts: dict[str, str] = {}
    for conv in (channel, web):
        factory, captured = _make_factory(_simple_messages())
        provider = ClaudeSdkProvider(conversations=repo, session_factory=factory)
        await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
        adapter = await provider.build_adapter(conv.id)
        await _collect(adapter, _user_turn("hi", conv.id))
        envs[conv.id] = dict(captured[0].env)
        prompts[conv.id] = str(captured[0].system_prompt)

    assert envs[channel.id] == envs[web.id] == {}
    assert "memory" not in prompts[channel.id].lower()

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


@pytest.mark.acceptance(
    spec="chat", scenario="an unmanaged agent type is not offered and runs no turn"
)
@pytest.mark.asyncio
async def test_an_unmanaged_type_is_not_available_and_runs_no_turn(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from coffer.domain.chat.errors import AgentConfigRejected

    repo, engine = await _repo(tmp_path)
    managed = False

    async def _is_managed() -> bool:
        return managed

    provider = ClaudeSdkProvider(
        conversations=repo, which=lambda _b: "/usr/bin/claude", is_managed=_is_managed
    )
    conv = await repo.create(_conv())
    await provider.init_conversation(conv.id, {})

    # The binary is there, but no enabled agent of the type is registered.
    assert await provider.availability() is False
    with pytest.raises(AgentConfigRejected) as refused:
        await provider.build_adapter(conv.id)
    assert refused.value.reason == "agent_not_managed"

    managed = True
    assert await provider.availability() is True
    await provider.build_adapter(conv.id)
    await engine.dispose()


@pytest.mark.acceptance(
    spec="channels", scenario="an edited system prompt applies from the next turn"
)
@pytest.mark.asyncio
async def test_a_resumed_session_carries_the_owner_prompt_as_it_is_now(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The system prompt is not part of Claude Code's stored session: each turn
    resumes the session with the append composed for that turn, so a prompt the
    owner edited between two turns reaches the very next one."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv(channel_uid=_TELEGRAM_UID))
    prompt = ["Answer in Chinese."]

    async def _note(uid: str, conversation_id: str) -> ChannelNote | None:
        return ChannelNote(
            name="tg", platform="Telegram", chat_kind="direct", owner_prompt=prompt[0]
        )

    factory, captured = _make_factory(_simple_messages("sess-1"))
    provider = ClaudeSdkProvider(conversations=repo, session_factory=factory, resolve_channel=_note)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    await _collect(await provider.build_adapter(conv.id), _user_turn("hi", conv.id))
    first = captured[0].system_prompt["append"]  # type: ignore[index]
    assert "Instructions from the channel's owner:\nAnswer in Chinese." in first

    prompt[0] = "Answer in English."
    factory2, captured2 = _make_factory(_simple_messages("sess-1"))
    provider2 = ClaudeSdkProvider(
        conversations=repo, session_factory=factory2, resolve_channel=_note
    )
    await _collect(await provider2.build_adapter(conv.id), _user_turn("again", conv.id))

    assert captured2[0].resume == "sess-1"
    second = captured2[0].system_prompt["append"]  # type: ignore[index]
    assert "Instructions from the channel's owner:\nAnswer in English." in second
    assert "Answer in Chinese." not in second
    # The owner's text follows Coffer's note and comes before the model note.
    assert second.index("You are replying in") < second.index("Instructions from the channel")
    assert second.index("Instructions from the channel") < second.index("Coffer set no model")

    await engine.dispose()
