"""Shared fixtures for `backend/tests/integration/application/`.

Lifts the previously-duplicated `_setup()` helper out of `test_agent_service.py`
into a single typed fixture (TEST25-003 / TEST25-004).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.config_file_service import AgentConfigFileService
from coffer.application.agent.hook_service import AgentHookService
from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.mcp_service import AgentMcpService
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
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


@dataclass
class AgentTestBundle:
    """Typed grouping of the services + engine an agent-service test needs."""

    svc: AgentService
    detect: AutoDetectService
    config_files: AgentConfigFileService
    mcp: AgentMcpService
    hook: AgentHookService
    audit: AuditService
    engine: AsyncEngine
    db_path: pathlib.Path


@pytest_asyncio.fixture
async def agent_bundle(tmp_path: pathlib.Path):
    """Build a wired AgentService + AutoDetectService on a fresh in-tree SQLite.

    Yielded as an `AgentTestBundle` so callers spell the attributes by name
    (no positional 5-tuple unpacking).
    """
    db_path = tmp_path / "c.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    kinds = {"agent": make_agent_kind(on_delete=None)}
    rs = ResourceService(kinds=kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit)
    store = ConfigFileStore()
    svc = AgentService(resource_service=rs, audit=audit, config_file_store=store)
    detect = AutoDetectService(agent_service=svc)
    config_files = AgentConfigFileService(agent_service=svc, audit=audit, store=store)
    mcp = AgentMcpService(
        agent_service=svc,
        audit=audit,
        store=store,
        shim_resolver=lambda: "/opt/coffer/coffer-mcp-shim",
    )

    async def _session_context() -> str:
        # The FR-044 payload the INSTRUCTIONS_BLOCK mode renders; a static stub
        # stands in for MemoryService.assemble_session_context(cwd=None).
        return "RULES BUNDLE"

    hook = AgentHookService(
        agent_service=svc,
        audit=audit,
        store=store,
        hook_resolver=lambda: "/opt/coffer/coffer-hook",
        session_context=_session_context,
    )
    try:
        yield AgentTestBundle(
            svc=svc,
            detect=detect,
            config_files=config_files,
            mcp=mcp,
            hook=hook,
            audit=audit,
            engine=engine,
            db_path=db_path,
        )
    finally:
        await engine.dispose()
