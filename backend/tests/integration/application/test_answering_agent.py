"""Which agent answers for a type when two of that type are registered
(spec chat "Ship Claude Code and Codex subprocess providers", spec
agent-registry "Serve each agent type's model catalogue").

A conversation names a TYPE, and two agents of one type can be registered as
long as their config directories differ. The one that answers is the first
enabled agent of the type in NAME order — the order the registry lists agents
in — so the rule is visible to the user and a rename changes it. Everything is
real here: SQLite registry, agent service, the answering lookup and the
per-turn environment resolver the chat wiring hands the providers.
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
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.surfaces.http.chat_provider_wiring import agent_home_env_resolver


@pytest.mark.acceptance(
    spec="chat", scenario="two agents of one type — the one first by name answers"
)
@pytest.mark.acceptance(
    spec="agent-registry", scenario="two agents of one type — the one first by name answers"
)
async def test_the_agent_first_by_name_answers_and_a_rename_moves_it(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        sm = session_maker(engine)
        audit = AuditService(SqlAlchemyAuditRepo(sm))
        rs = ResourceService(
            kinds={"agent": make_agent_kind(on_delete=None)},
            repo=SqlAlchemyResourceRepo(sm),
            audit=audit,
        )
        svc = AgentService(resource_service=rs, audit=audit, config_file_store=ConfigFileStore())
        work_dir = tmp_path / "work-cfg"
        home_dir = tmp_path / "home-cfg"
        work_dir.mkdir()
        home_dir.mkdir()
        # Registered in the order that would win if creation order decided.
        work = await svc.register(
            agent_type=AgentType.CLAUDE_CODE, name="zeta-work", config_dir=str(work_dir)
        )
        await svc.register(
            agent_type=AgentType.CLAUDE_CODE, name="alpha-home", config_dir=str(home_dir)
        )
        turn_env = agent_home_env_resolver(AgentType.CLAUDE_CODE, lambda: svc)

        first = await answering_agent_config(svc, "claude_code")
        assert first is not None
        assert first.config_dir == str(home_dir)
        assert (await turn_env())["CLAUDE_CONFIG_DIR"] == str(home_dir)

        await rs.rename(work.uid, "aardvark-work", actor="cli")

        after = await answering_agent_config(svc, "claude_code")
        assert after is not None
        assert after.config_dir == str(work_dir)
        assert (await turn_env())["CLAUDE_CONFIG_DIR"] == str(work_dir)
    finally:
        await engine.dispose()
