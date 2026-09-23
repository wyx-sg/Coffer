"""Conversation retention (spec chat "Archive and delete idle conversations on a
retention schedule", "Register conversation retention in the framework
registry").

Uses the daemon's own composed retention registry
(``build_prunable_registry``), so what is tested is the two windows chat really
registers — not a copy of them written into the test. The media-dir sweep the
daemon also binds is left out: it walks a real directory and has nothing to do
with conversations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from coffer.application.audit_service import AuditService
from coffer.application.chat.service import ChatService
from coffer.application.retention_service import RetentionService
from coffer.domain.chat.message import Role
from coffer.infrastructure.chat.persistence import ConversationRepo, MessageRepo
from coffer.infrastructure.persistence import models as _models  # noqa: F401  (registers tables)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyRetentionRepo
from coffer.infrastructure.persistence.retention_repo import allowlist_from_registry
from coffer.surfaces.http.app_mcp_composition import build_prunable_registry
from tests.unit.chat.conftest import FakeAgentAdapter, make_registry

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 5, 20, tzinfo=UTC)
_CONV_SQL = (
    "INSERT INTO conversations (id, agent_key, title, created_at, updated_at, archived_at) "
    "VALUES (:id, 'agent', 't', :ts, :ts, :arch)"
)
_MSG_SQL = (
    "INSERT INTO chat_messages (id, conversation_id, seq, role, content, status, created_at) "
    "VALUES (:id, :conv, 0, 'user', '[]', 'complete', :ts)"
)


async def _db(tmp_path):  # type: ignore[no-untyped-def]
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, session_maker(engine)


def _retention(sm) -> RetentionService:  # type: ignore[no-untyped-def]
    registry = build_prunable_registry()
    return RetentionService(
        registry=registry,
        repo=SqlAlchemyRetentionRepo(sm, allowlist=allowlist_from_registry(registry.all())),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )


@pytest.mark.acceptance(
    spec="chat", scenario="an idle conversation is archived, then deleted with its messages"
)
async def test_idle_conversations_are_archived_then_deleted_with_their_messages(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine, sm = await _db(tmp_path)
    try:
        svc = _retention(sm)
        await svc.initialize_defaults()
        async with sm() as s:
            # Idle 8 days (past the 7-day default), never archived.
            await s.execute(
                text(_CONV_SQL), {"id": "idle", "ts": _NOW - timedelta(days=8), "arch": None}
            )
            # Active yesterday.
            await s.execute(
                text(_CONV_SQL), {"id": "fresh", "ts": _NOW - timedelta(days=1), "arch": None}
            )
            # Archived 31 days ago (past the 30-day default), with messages.
            await s.execute(
                text(_CONV_SQL),
                {"id": "old", "ts": _NOW - timedelta(days=60), "arch": _NOW - timedelta(days=31)},
            )
            await s.execute(
                text(_MSG_SQL), {"id": "m-old", "conv": "old", "ts": _NOW - timedelta(days=60)}
            )
            # The idle conversation's last message is as old as the conversation
            # itself: "idle" means no new message for the window, so a message
            # dated today would make it an active conversation, not an idle one.
            await s.execute(
                text(_MSG_SQL), {"id": "m-idle", "conv": "idle", "ts": _NOW - timedelta(days=8)}
            )
            await s.commit()

        await svc.prune(now=_NOW)

        async with sm() as s:
            rows = dict((await s.execute(text("SELECT id, archived_at FROM conversations"))).all())
            msgs = set((await s.execute(text("SELECT id FROM chat_messages"))).scalars().all())
        assert set(rows) == {"idle", "fresh"}  # the long-archived one is gone
        assert rows["idle"] is not None  # archived, not deleted
        assert rows["fresh"] is None
        assert msgs == {"m-idle"}  # the deleted conversation took its messages

        # Keep-forever disables the archive stage.
        await svc.set_retention("conversations_archive", None, actor="cli")
        async with sm() as s:
            await s.execute(
                text(_CONV_SQL), {"id": "idle2", "ts": _NOW - timedelta(days=99), "arch": None}
            )
            await s.commit()
        await svc.prune(now=_NOW)
        async with sm() as s:
            archived = (
                await s.execute(text("SELECT archived_at FROM conversations WHERE id='idle2'"))
            ).scalar_one()
        assert archived is None
    finally:
        await engine.dispose()


@pytest.mark.acceptance(
    spec="chat", scenario="chat's retention windows are tuned beside every other table"
)
async def test_chat_retention_windows_are_ordinary_registry_entries(tmp_path) -> None:  # type: ignore[no-untyped-def]
    registry = build_prunable_registry()
    by_name = {t.name: t for t in registry.all()}
    archive, delete = by_name["conversations_archive"], by_name["conversations"]
    assert (archive.default_retention_days, archive.action) == (7, "archive")
    assert archive.target_table == "conversations"
    assert archive.archive_set_column == "archived_at"
    assert delete.default_retention_days == 30
    assert delete.action != "archive"
    # They sit beside the log tables on the one surface.
    assert {"audit_log", "mcp_invocations"} <= set(by_name)

    engine, sm = await _db(tmp_path)
    try:
        svc = _retention(sm)
        await svc.initialize_defaults()
        policies = {p.table.name: p.retention_days for p in await svc.list_policies()}
        assert policies["conversations_archive"] == 7
        assert policies["conversations"] == 30

        # An owner delete takes the conversation's messages with it.
        chat_registry, _ = make_registry(FakeAgentAdapter([]), agent_key="agent")
        chat = ChatService(
            conversations=ConversationRepo(sm), messages=MessageRepo(sm), registry=chat_registry
        )
        conv = await chat.create_conversation(agent_key="agent")
        await chat.append_message(conv.id, role=Role.USER, content=[])
        assert len(await chat.list_messages(conv.id)) == 1
        await chat.delete_conversation(conv.id)
        async with sm() as s:
            left = (
                await s.execute(
                    text("SELECT COUNT(*) FROM chat_messages WHERE conversation_id = :c"),
                    {"c": conv.id},
                )
            ).scalar_one()
        assert left == 0
    finally:
        await engine.dispose()
