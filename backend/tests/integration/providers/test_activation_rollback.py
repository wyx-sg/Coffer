"""A switch whose write fails leaves the agent's file and record as they were.

A switch projects the connection into the agent's native config file and then
records it on the agent. When the file is edited between Coffer's read and write
the switch is refused (spec provider-switching "Project into Claude Code
settings without clobbering them" / "Switch one agent at a time"); when the
record write is the one that fails, the file already written is put back, so no
agent is left pointed at the proxy with no connection behind it.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.provider import switch_ops
from coffer.application.provider.projector import ProviderProjector
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol, ProviderConfig
from coffer.domain.resource import Resource
from coffer.domain.workspace_errors import ConfigFileStale
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from tests.support.facets import agent_catalog

_NOW = datetime(2026, 10, 2, tzinfo=UTC)


class _EditCodexAfterRead(ConfigFileStore):
    def read_text(self, path: pathlib.Path) -> str | None:
        text = super().read_text(path)
        if path.name == "config.toml":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('model = "mine"\n', encoding="utf-8")
        return text


class _Audit:
    async def record(self, *_a: Any, **_k: Any) -> None:
        return None


def _agent(uid: str, name: str, kind: str, config_dir: pathlib.Path) -> Resource:
    return Resource(
        uid=uid,
        kind="agent",
        name=name,
        description=None,
        config={"type": kind, "config_dir": str(config_dir)},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


class _Agents:
    def __init__(self, rows: list[Resource], *, fail_record: bool = False) -> None:
        self._rows = rows
        self._fail = fail_record
        self.recorded: list[tuple[str, str | None]] = []

    async def list(self) -> list[Resource]:
        return self._rows

    async def set_connection(
        self, uid: str, connection_uid: str | None, *, actor: str = "api"
    ) -> Resource:
        if self._fail:
            raise RuntimeError("the agent record could not be written")
        self.recorded.append((uid, connection_uid))
        return self._rows[0]


class _Service:
    def __init__(self, store: ConfigFileStore, connection: Resource, agents: _Agents):
        self._projector = ProviderProjector(store, agents=agent_catalog())
        self._audit = _Audit()
        self._connection = connection
        self._agents = agents

    async def list(self) -> list[Resource]:
        return [self._connection]

    async def get(self, uid: str) -> Resource:
        return self._connection

    def _cfg(self, resource: Resource) -> ProviderConfig:
        return ProviderConfig.model_validate(resource.config)


def _connection() -> Resource:
    cfg = ProviderConfig(
        protocol=Protocol.ANTHROPIC, base_url="https://gw.example", secret_ref="provider/x/key"
    )
    return Resource(
        uid="3c9a7b15d0e24f6688aa1b2c3d4e5f60",
        kind="provider",
        name="x",
        description=None,
        config=cfg.model_dump(mode="json"),
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a switch whose write fails puts the file back",
)
@pytest.mark.asyncio
async def test_a_refused_file_write_leaves_the_user_edit_and_the_record_alone(
    tmp_path: pathlib.Path,
) -> None:
    codex_dir = tmp_path / "codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text('model = "gpt"\n', encoding="utf-8")
    connection = _connection()
    agents = _Agents([_agent("b" * 32, "cx", "codex", codex_dir)])
    service = _Service(_EditCodexAfterRead(), connection, agents)

    with pytest.raises(ConfigFileStale):
        await switch_ops.activate(
            service,  # type: ignore[arg-type]
            connection.uid,
            AgentType.CODEX,
            actor="cli",
        )

    assert (codex_dir / "config.toml").read_text(encoding="utf-8") == 'model = "mine"\n'
    assert agents.recorded == []


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a switch whose write fails puts the file back",
)
@pytest.mark.asyncio
async def test_a_failed_record_write_puts_the_projected_file_back(tmp_path: pathlib.Path) -> None:
    cc_dir = tmp_path / "cc"
    cc_dir.mkdir()
    (cc_dir / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
    connection = _connection()
    agents = _Agents([_agent("a" * 32, "cc", "claude_code", cc_dir)], fail_record=True)
    service = _Service(ConfigFileStore(), connection, agents)

    with pytest.raises(RuntimeError):
        await switch_ops.activate(
            service,  # type: ignore[arg-type]
            connection.uid,
            AgentType.CLAUDE_CODE,
            actor="cli",
        )

    assert (cc_dir / "settings.json").read_text(encoding="utf-8") == '{"theme": "dark"}'
