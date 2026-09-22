"""A template is a Resource and nothing else (FR-001, FR-008, FR-040).

Every other workflow test starts from a template the engine was handed. This
one starts a step earlier — at the generic resource framework — because that is
where FR-001's claim lives: the developer writes a template through the same
path as every other resource, is addressed by the uid it gets back, and leaves a
trail. Real rows, real audit table: the point is that the framework does this
for the workflow kind without the kind doing anything of its own.

The second test carries that claim one machine further: the workflow reaches
the developer's other machine over the same bundle every resource travels in,
with no path of its own (FR-008).
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.sync.appliers_resource import ResourceApplier
from coffer.application.sync.exporter import SyncExporter
from coffer.application.workflow.kind import KIND_WORKFLOW, make_workflow_kind
from coffer.domain.audit import AuditEventType
from coffer.domain.workflow.template import parse_template
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.infrastructure.sync.bundle import Bundle
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
        description="Two stages, two tasks",
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


class _NoCredentials:
    """The exporter's credential port, which this test never exercises: a
    template cites no secret, and exporting without credentials never reads
    from it."""

    def list_refs(self) -> list[str]:
        return []

    def read_ciphertext(self, ref: str) -> bytes | None:
        return None


async def _resource_service(db: pathlib.Path) -> tuple[ResourceService, object]:
    """One machine's resource registry, over its own database."""
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    service = ResourceService(
        kinds={KIND_WORKFLOW: make_workflow_kind()},
        repo=SqlAlchemyResourceRepo(sm),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )
    return service, engine


@pytest.mark.acceptance(
    spec="workflow", scenario="a workflow defined on one machine is there on the other"
)
async def test_a_template_registered_here_arrives_on_the_other_machine(
    tmp_path: pathlib.Path,
) -> None:
    """FR-008: the workflow travels the ordinary resource path and nothing else.

    Two registries over two databases, the production exporter writing one
    bundle and the production applier reading it back into the other. Asserted
    end to end rather than by reading ``Kind.converges``, because that flag is
    only half the claim: a kind can declare itself converging and still fail to
    arrive — its document has to serialize, and the receiving machine has to be
    able to register it at the identity it came with, or the second machine
    ends up with a workflow it cannot run or a second copy of the first one.
    """
    here, here_engine = await _resource_service(tmp_path / "here.db")
    there, there_engine = await _resource_service(tmp_path / "there.db")
    bundle_root = tmp_path / "bundle"

    registered = await here.register(
        kind=KIND_WORKFLOW,
        name="ship-a-feature",
        config=TEMPLATE,
        actor="user",
    )

    summary = await SyncExporter(here, _NoCredentials(), home=str(tmp_path)).export(
        Bundle(bundle_root, trees=[], excluded=frozenset())
    )
    assert not summary.failures, summary.failures

    applier = ResourceApplier(there, worktree=bundle_root, gates=[], home=str(tmp_path))
    await applier.upsert(f"resources/{KIND_WORKFLOW}/{registered.uid}.yaml")

    # The same workflow, not a copy of it: same identity, same definition.
    arrived = await there.get(registered.uid)
    assert (arrived.uid, arrived.name) == (registered.uid, "ship-a-feature")
    assert arrived.config == TEMPLATE
    # And it is there to RUN from: the definition still parses into the shape
    # the engine executes, which is what a document that travelled as opaque
    # bytes would not guarantee.
    assert [s.key for s in parse_template(arrived.config).stages] == ["design", "coding"]

    await here_engine.dispose()
    await there_engine.dispose()
