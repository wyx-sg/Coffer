import logging
from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo


def _resource(
    row_id: int, name: str, *, kind: str = "mcp_server", uid: str | None = None
) -> Resource:
    """A resource to attribute an event to.

    Built in memory rather than registered: ``AuditService`` is handed the row
    by the caller performing the mutation, so what it needs is a ``Resource``,
    not a lookup — which is the whole of what replaced the resolver it used to
    be constructed with.
    """
    now = datetime.now(tz=UTC)
    return Resource(
        id=row_id,
        uid=uid or f"uid-{row_id}",
        kind=kind,
        name=name,
        description=None,
        config={},
        enabled=True,
        created_at=now,
        updated_at=now,
    )


async def _service(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    return AuditService(SqlAlchemyAuditRepo(sm)), engine


@pytest.mark.asyncio
async def test_record_decomposes_the_resource(tmp_path):
    svc, engine = await _service(tmp_path)
    await svc.record(
        AuditEventType.RESOURCE_CREATED.value,
        resource=_resource(1, "filesystem"),
        actor="cli",
        details={"config": {"transport": "stdio"}},
    )
    entries = await svc.query()
    assert len(entries) == 1
    e = entries[0]
    assert e.event_type == "resource_created"
    # Two different things, kept on purpose: the id ties the event to the
    # resource, and kind/name record the LABEL it carried at that moment.
    assert e.resource_id == 1
    assert e.resource_kind == "mcp_server"
    assert e.resource_name == "filesystem"
    assert e.actor == "cli"
    assert e.details == {"config": {"transport": "stdio"}}
    assert e.timestamp is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_record_without_a_resource_uses_system_actor_default(tmp_path):
    """Resource-less events default to actor='system' and name no resource."""
    svc, engine = await _service(tmp_path)
    await svc.record(AuditEventType.TOKEN_ROTATED.value, details={"port": 8000})
    entries = await svc.query()
    assert entries[0].resource_id is None
    assert entries[0].resource_kind is None
    assert entries[0].resource_name is None
    assert entries[0].actor == "system"
    assert entries[0].details == {"port": 8000}
    await engine.dispose()


@pytest.mark.asyncio
async def test_record_empty_details_default(tmp_path):
    svc, engine = await _service(tmp_path)
    await svc.record("resource_enabled", resource=_resource(1, "x"), actor="api")
    entries = await svc.query()
    assert entries[0].details == {}
    await engine.dispose()


@pytest.mark.asyncio
async def test_query_filters(tmp_path):
    svc, engine = await _service(tmp_path)
    a = _resource(1, "a")
    b = _resource(2, "b")
    await svc.record("resource_created", resource=a, actor="cli")
    await svc.record("resource_created", resource=b, actor="cli")
    await svc.record("resource_updated", resource=a, actor="api")

    # Was ``query(name="a")``. One resource's trail is asked for by handing
    # over the resource itself; the filter is its id, not its current label.
    only_a = await svc.query(resource=a)
    assert len(only_a) == 2

    only_created = await svc.query(event_type="resource_created")
    assert len(only_created) == 2

    only_a_created = await svc.query(resource=a, event_type="resource_created")
    assert len(only_a_created) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_renamed_resource_keeps_one_trail(tmp_path):
    """The trail follows the resource, not the label it carried at the time.

    Each row still records the name of the moment — that is what makes the
    history read as "a thing that was called different names at different
    times" — but the filter is the resource, so a rename neither splits the
    trail nor requires rewriting a single row.
    """
    svc, engine = await _service(tmp_path)
    before = _resource(1, "before")
    after = _resource(1, "after")  # same resource, same id/uid, new label
    await svc.record("resource_created", resource=before, actor="cli")
    await svc.record(AuditEventType.RESOURCE_RENAMED.value, resource=after, actor="cli")

    trail = await svc.query(resource=after)
    assert [e.event_type for e in trail] == ["resource_renamed", "resource_created"]
    assert [e.resource_name for e in trail] == ["after", "before"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_two_resources_sharing_a_label_keep_separate_trails(tmp_path):
    """Replaces the old "find the trail by (kind, name)" behaviour.

    Querying by label used to fall back to matching ``resource_kind`` +
    ``resource_name``, which cannot tell a deleted resource from a later one
    that took its name: the two objects' histories rendered as one. Addressing
    the trail by the resource is what makes that impossible, so this asserts
    the outcome that fallback got wrong.
    """
    svc, engine = await _service(tmp_path)
    old = _resource(1, "fs", uid="the-deleted-one")
    new = _resource(2, "fs", uid="the-one-that-took-the-name")
    await svc.record("resource_created", resource=old, actor="cli")
    await svc.record(AuditEventType.RESOURCE_DELETED.value, resource=old, actor="cli")
    await svc.record("resource_created", resource=new, actor="cli")

    assert len(await svc.query(resource=old)) == 2
    assert len(await svc.query(resource=new)) == 1
    # The coarse filter still sees everything of that kind — that is the slice
    # the activity page renders, and it is a different question.
    assert len(await svc.query(kind="mcp_server")) == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_query_since(tmp_path):
    svc, engine = await _service(tmp_path)
    await svc.record("resource_created", resource=_resource(1, "old"), actor="cli")
    # All entries arrive ~now; querying since `now + 1 hour` should yield none
    recent = await svc.query(since=datetime.now(tz=UTC) + timedelta(hours=1))
    assert recent == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_every_audited_event_is_also_logged(tmp_path, caplog) -> None:
    """Coffer used to log only its failures. A live daemon.log held 4,277 lines
    of which 62 were Coffer's own — all one error type — and a search across two
    months for `credential_read`, `provider_switched`, `resource_deleted` and
    four other key operations returned nothing at all.

    The audit table already decides what is worth recording, so mirroring it is
    the cheapest way to make that decision legible to whoever is tailing a log.
    """
    svc, _engine = await _service(tmp_path)
    jira = _resource(7, "jira", uid="9f2c1a7b4e8d4c1fa0b3d5e6f7081920")
    with caplog.at_level(logging.INFO, logger="coffer.application.audit_service"):
        await svc.record(
            AuditEventType.CREDENTIAL_READ.value,
            resource=jira,
            actor="cli",
            details={"ref": "jira.TOKEN"},
        )

    [record] = [r for r in caplog.records if r.name == "coffer.application.audit_service"]
    assert record.event == "credential_read"
    # Was the single `mcp_server:jira` identifier. The line carries three
    # separate fields now, because there is no identifier that is the two
    # halves glued together: the label for a human reading the log, the kind,
    # and the uid for anyone correlating the line with a resource.
    assert record.resource == "jira"
    assert record.resource_kind == "mcp_server"
    assert record.resource_uid == "9f2c1a7b4e8d4c1fa0b3d5e6f7081920"
    assert record.actor == "cli"
    # `details` stays out: the audit table applies each kind's redactor before
    # storing it, and re-deriving that here would duplicate the one place that
    # knows which fields carry secrets.
    assert not hasattr(record, "details")
