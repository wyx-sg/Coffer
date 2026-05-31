"""Wiring for chat application-layer tests: a ChatService over real SQLite with
a FakeRuntimeFactory, plus a seeded built-in agent and a registered external
agent."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from coffer.application.audit_service import AuditService
from coffer.application.builtin_agent.kind import (
    ensure_default_builtin_agent,
    make_builtin_agent_kind,
)
from coffer.application.chat.service import ChatService
from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Kind
from coffer.infrastructure.chat.persistence import (
    SqlAlchemyConversationRepo,
    SqlAlchemyMessageRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from tests.integration.chat.fakes import FakeRuntimeFactory, FakeTitleGenerator


def _agent_kind() -> Kind:
    # Minimal external `agent` kind for chat-target tests. We don't exercise the
    # real agent service here (its config_dir I/O is out of scope for chat).
    from coffer.application.agent.kind import make_agent_kind

    return make_agent_kind(on_delete=None)


@dataclass
class ChatEnv:
    chat: ChatService
    resources: ResourceService
    factory: FakeRuntimeFactory
    titler: FakeTitleGenerator
    audit: AuditService
    engine: AsyncEngine
    db_url: str
    sm: object


@pytest_asyncio.fixture
async def chat_env(tmp_path: pathlib.Path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'c.db'}"
    engine = create_async_engine_with_pragmas(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    kinds: dict[str, Kind] = {
        "builtin_agent": make_builtin_agent_kind(on_delete=None),
        "agent": _agent_kind(),
    }
    resources = ResourceService(kinds=kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit)
    await ensure_default_builtin_agent(resources)
    # A registered external agent target (no real config_dir I/O).
    await resources.register(
        kind="agent",
        name="claude-code",
        config={"type": "claude_code"},
        actor="test",
    )
    factory = FakeRuntimeFactory()
    titler = FakeTitleGenerator()
    chat = ChatService(
        conversations=SqlAlchemyConversationRepo(sm),
        messages=SqlAlchemyMessageRepo(sm),
        resources=resources,
        runtime_factory=factory,
        audit=audit,
        title_generator=titler,
    )
    try:
        yield ChatEnv(
            chat=chat,
            resources=resources,
            factory=factory,
            titler=titler,
            audit=audit,
            engine=engine,
            db_url=db_url,
            sm=sm,
        )
    finally:
        await engine.dispose()
