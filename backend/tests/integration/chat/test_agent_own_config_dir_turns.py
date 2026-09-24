"""A turn on an agent with its own config directory runs against that directory
(spec chat "Ship Claude Code and Codex subprocess providers").

Coffer delivers skills, installs its MCP entry and edits config files in the
agent's ``config_dir``. The process it spawns to run a turn must read that same
directory, which for a custom one means ``CLAUDE_CONFIG_DIR`` (Claude Code) or
``CODEX_HOME`` (Codex) in its environment; for the default directory the
environment is left exactly as it was.

The SDK session and the app-server session are fakes that capture what the
adapter would hand the real subprocess — no binary is spawned.
"""

from __future__ import annotations

import asyncio
import dataclasses
import pathlib
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.domain.agent.types import AgentType
from coffer.domain.resource import Resource
from coffer.infrastructure.chat.claude_sdk_provider import ClaudeSdkProvider
from coffer.infrastructure.chat.codex_provider import CodexAppServerProvider
from coffer.surfaces.http.chat_provider_wiring import agent_home_env_resolver
from tests.integration.chat.test_codex_provider import _make_factory as _codex_factory
from tests.integration.chat.test_sdk_provider import (
    _conv,
    _repo,
    _simple_messages,
    _user_turn,
)
from tests.integration.chat.test_sdk_provider import _make_factory as _sdk_factory

_NOW = datetime(2026, 9, 24, tzinfo=UTC)


def _agent(agent_type: AgentType, config_dir: pathlib.Path | None, *, uid: str) -> Resource:
    config: dict[str, Any] = {"type": agent_type.value}
    if config_dir is not None:
        config["config_dir"] = str(config_dir)
    return Resource(
        id=1,
        uid=uid,
        kind="agent",
        name=agent_type.default_name(),
        description=None,
        config=config,
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


class _Agents:
    def __init__(self, rows: list[Resource]) -> None:
        self._rows = rows

    async def list(self) -> list[Resource]:
        return list(self._rows)


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


async def _claude_turn_env(tmp_path: pathlib.Path, agents: _Agents) -> dict[str, str]:
    repo, engine = await _repo(tmp_path)
    try:
        conv = await repo.create(_conv())
        factory, captured = _sdk_factory(_simple_messages())
        provider = ClaudeSdkProvider(
            conversations=repo,
            session_factory=factory,
            resolve_home_env=agent_home_env_resolver(AgentType.CLAUDE_CODE, lambda: agents),
        )
        await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
        adapter = await provider.build_adapter(conv.id)
        stream = await adapter.run_turn(history=_user_turn("hi", conv.id))
        _ = [ev async for ev in stream]
        assert len(captured) == 1
        return dict(captured[0].env)
    finally:
        await engine.dispose()


async def _codex_turn_env(
    tmp_path: pathlib.Path, agents: _Agents, *, key: str | None = None
) -> dict[str, str] | None:
    repo, engine = await _repo(tmp_path)
    try:
        conv = await repo.create(_conv("codex"))
        factory, _server = _codex_factory()

        async def resolve_key() -> str | None:
            return key

        provider = CodexAppServerProvider(
            conversations=repo,
            session_factory=factory,
            resolve_key=resolve_key,
            resolve_home_env=agent_home_env_resolver(AgentType.CODEX, lambda: agents),
        )
        await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
        adapter = await provider.build_adapter(conv.id)
        stream = await adapter.run_turn(history=_user_turn("hi", conv.id))
        await asyncio.wait_for(_drain(stream), timeout=5)
        return factory.last_env
    finally:
        await engine.dispose()


async def _drain(stream: Any) -> None:
    async for _ in stream:
        pass


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="chat",
    scenario="a turn on an agent with its own config directory runs against that directory",
)
async def test_claude_turn_runs_against_the_agents_own_config_dir(
    tmp_path: pathlib.Path, home: pathlib.Path
) -> None:
    custom = tmp_path / "work-claude"
    custom.mkdir()
    agents = _Agents([_agent(AgentType.CLAUDE_CODE, custom, uid="a" * 32)])

    env = await _claude_turn_env(tmp_path, agents)

    assert env == {"CLAUDE_CONFIG_DIR": str(custom)}


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="chat",
    scenario="a turn on an agent with its own config directory runs against that directory",
)
async def test_claude_turn_on_the_default_dir_leaves_the_env_untouched(
    tmp_path: pathlib.Path, home: pathlib.Path
) -> None:
    agents = _Agents([_agent(AgentType.CLAUDE_CODE, None, uid="b" * 32)])

    env = await _claude_turn_env(tmp_path, agents)

    assert env == {}


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="chat",
    scenario="a turn on an agent with its own config directory runs against that directory",
)
async def test_codex_turn_runs_against_the_agents_own_codex_home(
    tmp_path: pathlib.Path, home: pathlib.Path
) -> None:
    custom = tmp_path / "work-codex"
    custom.mkdir()
    agents = _Agents([_agent(AgentType.CODEX, custom, uid="c" * 32)])

    env = await _codex_turn_env(tmp_path, agents, key="sk-codex")

    assert env is not None
    assert env["CODEX_HOME"] == str(custom)
    # Merged with the daemon env and the projected key, never replacing them.
    assert env["COFFER_PROVIDER_KEY"] == "sk-codex"
    assert "PATH" in env


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="chat",
    scenario="a turn on an agent with its own config directory runs against that directory",
)
async def test_codex_turn_on_the_default_dir_leaves_the_env_untouched(
    tmp_path: pathlib.Path, home: pathlib.Path
) -> None:
    agents = _Agents([_agent(AgentType.CODEX, home / ".codex", uid="d" * 32)])

    env = await _codex_turn_env(tmp_path, agents)

    # No key, no custom home: the subprocess inherits the daemon env as-is.
    assert env is None


@pytest.mark.asyncio
async def test_the_resolver_reads_the_agent_answering_for_the_type(home: pathlib.Path) -> None:
    """Disabled agents and agents of the other type do not answer — the same
    agent the model catalogue reads is the one a turn runs against."""
    off = _agent(AgentType.CLAUDE_CODE, home / "off", uid="e" * 32)
    off = dataclasses.replace(off, enabled=False)
    agents = _Agents(
        [
            off,
            _agent(AgentType.CODEX, home / "cx", uid="f" * 32),
            _agent(AgentType.CLAUDE_CODE, home / "on", uid="0" * 32),
        ]
    )

    resolve = agent_home_env_resolver(AgentType.CLAUDE_CODE, lambda: agents)

    assert await resolve() == {"CLAUDE_CONFIG_DIR": str(home / "on")}
    assert await agent_home_env_resolver(AgentType.CLAUDE_CODE, lambda: _Agents([]))() == {}
