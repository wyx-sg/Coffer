"""Which agent answers for a type (spec chat "Ship Claude Code and Codex
subprocess providers on the type's one agent", spec agent-registry "Serve each
agent type's model catalogue from its one agent").

A conversation names a TYPE, and a type has one agent. That agent answers while
it is enabled; once disabled, a turn on the type runs as if no agent of it were
registered. Everything is real here: SQLite registry, agent service, the
answering lookup and the per-turn environment resolver the chat wiring hands
the providers.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.agent.answering import answering_agent_config
from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.types import AgentType
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.platform import HostPlatform
from coffer.surfaces.http.chat_provider_wiring import agent_home_env_resolver
from tests.support.vault_stores import make_resource_repo


@pytest.mark.acceptance(spec="chat", scenario="a disabled agent does not answer for its type")
async def test_a_disabled_agent_does_not_answer_for_its_type(tmp_path: pathlib.Path) -> None:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        sm = session_maker(engine)
        audit = AuditService(SqlAlchemyAuditRepo(sm))
        rs = ResourceService(
            kinds={"agent": make_agent_kind(on_delete=None)},
            repo=make_resource_repo(),
            audit=audit,
        )
        svc = AgentService(
            platform=HostPlatform(),
            resource_service=rs,
            audit=audit,
            config_file_store=ConfigFileStore(),
        )
        turn_env = agent_home_env_resolver(AgentType.CLAUDE_CODE, lambda: svc)
        # No agent of the type registered: the daemon's own environment.
        assert await turn_env() == {}

        work_dir = tmp_path / "work-cfg"
        work_dir.mkdir()
        agent = await svc.register(agent_type=AgentType.CLAUDE_CODE, config_dir=str(work_dir))

        # Enabled, it answers — the catalogue and the turn read the same one.
        answering = await answering_agent_config(svc, "claude_code")
        assert answering is not None
        assert answering.config_dir == str(work_dir)
        assert (await turn_env())["CLAUDE_CONFIG_DIR"] == str(work_dir)

        await rs.set_enabled(agent.uid, False, actor="cli")

        # Disabled, it no longer answers: exactly as when none is registered.
        assert await answering_agent_config(svc, "claude_code") is None
        assert "CLAUDE_CONFIG_DIR" not in await turn_env()
        assert await turn_env() == {}
    finally:
        await engine.dispose()
