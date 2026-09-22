"""A template is a Resource and nothing else (FR-001), and writing one is audited (FR-040).

Every other workflow test starts from a template the engine was handed. This
one starts a step earlier — at the generic resource framework — because that is
where FR-001's claim lives: the developer writes a template through the same
path as every other resource, is addressed by the uid it gets back, and leaves a
trail. Real rows, real audit table: the point is that the framework does this
for the workflow kind without the kind doing anything of its own.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.workflow.kind import KIND_WORKFLOW, make_workflow_kind
from coffer.domain.audit import AuditEventType
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from tests.unit.application.workflow.conftest import TEMPLATE


@pytest.mark.acceptance(spec="workflow", scenario="a template is registered as a resource")
async def test_a_registered_template_is_a_workflow_resource_with_an_audit_entry(
    tmp_path: pathlib.Path,
) -> None:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'resources.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    service = ResourceService(
        kinds={KIND_WORKFLOW: make_workflow_kind()},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )

    created = await service.register(
        kind=KIND_WORKFLOW,
        name="ship-a-feature",
        config=TEMPLATE,
        actor="user",
        description="Two stages, one edge",
    )

    # FR-001: it is an ordinary resource of kind `workflow`, and the document
    # is stored as written.
    assert (created.kind, created.name) == (KIND_WORKFLOW, "ship-a-feature")
    assert created.uid
    assert created.config == TEMPLATE
    # The framework's own lifecycle, nothing kind-specific: enabled on creation,
    # readable back by the identity it was given.
    assert created.enabled is True
    assert (await service.get(created.uid)).config == TEMPLATE
    assert [r.name for r in await service.list(kind=KIND_WORKFLOW)] == ["ship-a-feature"]

    # FR-040: the write left a trail.
    # By the resource, not by its label: the trail belongs to the row.
    entries = await audit.query(resource=created)
    assert [e.event_type for e in entries] == [AuditEventType.RESOURCE_CREATED.value]
    assert entries[0].actor == "user"

    await engine.dispose()
