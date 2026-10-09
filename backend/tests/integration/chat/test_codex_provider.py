"""CodexAppServerProvider integration tests (spec channels — app-server-backed Codex provider).

Mirrors ``test_sdk_provider.py`` but for ``CodexAppServerProvider``:
- ``init_conversation`` rejects a missing or non-directory cwd.
- ``build_adapter`` returns a ``CodexAppServerAdapter`` with the right cwd / resume
  and a working session sink.
- ``availability()`` reflects the injected ``which``.

A fake ``AppServerSessionFactory`` is injected throughout — no real ``codex`` binary
or subprocess is touched.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.channel_note import ChannelNote
from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.errors import AgentConfigRejected, ConversationNotFound
from coffer.infrastructure.chat.codex_agent import CodexAppServerAdapter
from coffer.infrastructure.chat.codex_provider import CodexAppServerProvider
from coffer.infrastructure.chat.persistence import ConversationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

# Re-use the FakeCodexAppServer + _FakeSession + _Factory fakes from the
# adapter-level integration tests.
from tests.integration.chat.test_codex_app_server_agent import (
    FakeCodexAppServer,
    _Factory,
    _Frame,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _repo(tmp_path: Any) -> tuple[ConversationRepo, Any]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return ConversationRepo(session_maker(engine)), engine


#: The channel a bridged conversation points at. The row stores the channel's
#: uid (ADR identity-is-the-uid-inside-the-file); its name reaches the prompt
#: only through the resolver the provider is handed.
_SEATALK_UID = "3c8a17d5e2f04b9188ac6d0f5e2b7a91"


async def _seatalk_name(uid: str, conversation_id: str) -> ChannelNote | None:
    assert uid == _SEATALK_UID
    return ChannelNote(name="st-ops", platform="SeaTalk", chat_kind="group", in_thread=True)


def _conv(agent_key: str = "codex", channel_uid: str | None = None) -> Conversation:
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


def _basic_frames() -> list[_Frame]:
    """Minimal scripted conversation: thread started + turn completed."""
    return [
        _Frame("thread/start", "thread/started", {"thread": {"id": "thread-99"}}),
        _Frame(
            "turn/start",
            "turn/completed",
            {"threadId": "thread-99", "turn": {"id": "turn-99", "status": "completed"}},
        ),
    ]


def _make_factory() -> tuple[_Factory, FakeCodexAppServer]:
    server = FakeCodexAppServer(frames=_basic_frames())
    return _Factory(server), server


async def _collect(adapter: CodexAppServerAdapter, prompt: str) -> list[Any]:
    stream = await adapter.run_turn(prompt)
    return [ev async for ev in stream]


# ---------------------------------------------------------------------------
# init_conversation — cwd validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_conversation_defaults_missing_cwd_to_workspace(
    tmp_path: Any, monkeypatch: Any
) -> None:
    # No cwd given falls back to the Coffer-managed workspace rather than
    # failing the turn (parity with the SDK provider).
    monkeypatch.setenv("HOME", str(tmp_path))
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = CodexAppServerProvider(conversations=repo)

    await provider.init_conversation(conv.id, {})
    stored = await repo.get_agent_config(conv.id)
    expected = str(tmp_path / ".coffer" / "content" / "workspace")
    assert stored.cwd == expected
    assert (tmp_path / ".coffer" / "content" / "workspace").is_dir()

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_rejects_non_directory_cwd(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = CodexAppServerProvider(conversations=repo)

    with pytest.raises(AgentConfigRejected) as exc:
        await provider.init_conversation(conv.id, {"cwd": "/no/such/dir/xyz"})
    assert exc.value.reason == "cwd_not_a_directory"

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_stores_cwd(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = CodexAppServerProvider(conversations=repo)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    stored = await repo.get_agent_config(conv.id)
    assert stored.cwd == str(tmp_path)

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_stores_model_when_present(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = CodexAppServerProvider(conversations=repo)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path), "model": "o4-mini"})
    stored = await repo.get_agent_config(conv.id)
    assert stored.cwd == str(tmp_path)
    assert stored.model == "o4-mini"

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_omits_model_when_absent(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = CodexAppServerProvider(conversations=repo)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    stored = await repo.get_agent_config(conv.id)
    assert stored.cwd == str(tmp_path)
    assert stored.model is None

    await engine.dispose()


# ---------------------------------------------------------------------------
# build_adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_adapter_returns_codex_adapter_with_correct_cwd(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, _server = _make_factory()
    provider = CodexAppServerProvider(conversations=repo, session_factory=factory)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)

    assert isinstance(adapter, CodexAppServerAdapter)
    # Drive one turn so the session is started and cwd confirmed.
    import asyncio

    await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)
    assert factory.last_cwd == str(tmp_path)

    await engine.dispose()


@pytest.mark.asyncio
async def test_build_adapter_resumes_stored_session(tmp_path: Any) -> None:
    """Session id (thread id) written by the first turn is passed as resume_session on next."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())

    # First turn — thread/started notification gives thread id "thread-99".
    factory1, _ = _make_factory()
    provider1 = CodexAppServerProvider(conversations=repo, session_factory=factory1)
    await provider1.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter1 = await provider1.build_adapter(conv.id)

    import asyncio

    await asyncio.wait_for(_collect(adapter1, _user_turn("hi", conv.id)), timeout=5)

    # Thread id must have been written back.
    cfg = await repo.get_agent_config(conv.id)
    assert cfg.session_id == "thread-99"

    # Second provider+adapter should pass resume_session="thread-99".
    factory2, server2 = _make_factory()
    # For the resume case, the fake needs thread/resume not thread/start.
    server2._frames = [
        _Frame("thread/resume", "thread/started", {"thread": {"id": "thread-99"}}),
        _Frame(
            "turn/start",
            "turn/completed",
            {"threadId": "thread-99", "turn": {"id": "turn-99", "status": "completed"}},
        ),
    ]
    provider2 = CodexAppServerProvider(conversations=repo, session_factory=factory2)
    adapter2 = await provider2.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter2, _user_turn("hello again", conv.id)), timeout=5)

    # The second turn must have used thread/resume.
    methods = [m for m, _ in server2.requests]
    assert "thread/resume" in methods
    assert "thread/start" not in methods

    await engine.dispose()


@pytest.mark.asyncio
async def test_build_adapter_raises_conversation_not_found(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    factory, _ = _make_factory()
    provider = CodexAppServerProvider(conversations=repo, session_factory=factory)

    with pytest.raises(ConversationNotFound):
        await provider.build_adapter("nonexistent-conv-id")

    await engine.dispose()


@pytest.mark.asyncio
async def test_build_adapter_session_sink_writes_back(tmp_path: Any) -> None:
    """The on_session sink wired by build_adapter persists the session_id (thread id)."""
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, _ = _make_factory()
    provider = CodexAppServerProvider(conversations=repo, session_factory=factory)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)

    import asyncio

    await asyncio.wait_for(_collect(adapter, _user_turn("go", conv.id)), timeout=5)

    cfg = await repo.get_agent_config(conv.id)
    assert cfg.session_id == "thread-99"

    await engine.dispose()


# ---------------------------------------------------------------------------
# build_adapter — no provider key in the spawn environment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_adapter_puts_no_provider_key_in_codex_env(tmp_path: Any) -> None:
    """No key rides Codex's environment: an API-key connection is reached through
    Coffer's model proxy, which injects the real key upstream. With no config-dir
    override the env stays None, so the codex subprocess inherits the daemon env
    as-is."""
    import asyncio

    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, _ = _make_factory()

    provider = CodexAppServerProvider(conversations=repo, session_factory=factory)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)

    assert factory.last_env is None

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a channel turn carries no memory from Coffer")
async def test_a_channel_turn_spawns_the_app_server_as_any_other_turn(tmp_path: Any) -> None:
    """Coffer puts no memory into a turn: a channel turn's ``codex app-server``
    starts with the same environment as one the developer drives, and its
    memory is whatever Codex reads from its own memory directory."""
    import asyncio

    repo, engine = await _repo(tmp_path)
    channel = await repo.create(_conv(channel_uid=_SEATALK_UID))
    web = await repo.create(_conv())
    envs: dict[str, dict[str, str] | None] = {}
    for conv in (channel, web):
        factory, _ = _make_factory()
        provider = CodexAppServerProvider(conversations=repo, session_factory=factory)
        await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
        adapter = await provider.build_adapter(conv.id)
        await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)
        envs[conv.id] = factory.last_env

    assert envs[channel.id] is None
    assert envs[web.id] is None

    await engine.dispose()


# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_availability_reflects_injected_which(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)

    present = CodexAppServerProvider(conversations=repo, which=lambda _b: "/usr/bin/codex")
    absent = CodexAppServerProvider(conversations=repo, which=lambda _b: None)

    assert await present.availability() is True
    assert await absent.availability() is False
    assert present.agent_key == "codex"

    await engine.dispose()


# ---------------------------------------------------------------------------
# on_conversation_deleted — no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_conversation_deleted_is_noop(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    provider = CodexAppServerProvider(conversations=repo)
    await provider.on_conversation_deleted("any-id")
    await engine.dispose()


# ---------------------------------------------------------------------------
# system-prompt appends — the notes Codex went without until now
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="channels", scenario="an edited system prompt applies from the next turn"
)
@pytest.mark.asyncio
async def test_a_resumed_thread_carries_the_owner_prompt_as_it_is_now(tmp_path: Any) -> None:
    """Codex is told Coffer's context in ``developerInstructions`` on every
    ``thread/resume`` too, composed for that turn — so the group prompt the owner
    just edited rides on the resumed thread's next turn."""
    import asyncio

    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv(channel_uid=_SEATALK_UID))
    await repo.set_agent_config(conv.id, AgentConfig(cwd=str(tmp_path), session_id="thread-99"))

    async def _note(uid: str, conversation_id: str) -> ChannelNote | None:
        return ChannelNote(
            name="st-ops", platform="SeaTalk", chat_kind="group", owner_prompt="Be brief."
        )

    factory, server = _make_factory()
    server._frames = [
        _Frame("thread/resume", "thread/started", {"thread": {"id": "thread-99"}}),
        _Frame(
            "turn/start",
            "turn/completed",
            {"threadId": "thread-99", "turn": {"id": "turn-99", "status": "completed"}},
        ),
    ]
    provider = CodexAppServerProvider(
        conversations=repo, session_factory=factory, resolve_channel=_note
    )
    adapter = await provider.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)

    resume = next(p for m, p in server.requests if m == "thread/resume")
    assert resume["threadId"] == "thread-99"
    assert resume["developerInstructions"].count("Instructions from the channel's owner:") == 1
    assert "Instructions from the channel's owner:\nBe brief." in resume["developerInstructions"]

    await engine.dispose()
