"""The built-in template a fresh vault already has (FR-009), and its one rule.

Two claims, and the second is the one with teeth. A vault nobody has touched
ends up holding exactly one workflow, seeded through the ordinary resource
write path so it is an ordinary resource. And once the developer has had their
say about it — edited, renamed, disabled, deleted — the seed stops: booting
again must not argue with them.

Real SQLite and the real ``ResourceService``, because "it is an ordinary
resource" is a claim about the framework, not about the seed.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.workflow.builtin_seed import SEED_ACTOR, BuiltinWorkflowSeed
from coffer.application.workflow.kind import KIND_WORKFLOW, make_workflow_kind
from coffer.domain.audit import AuditEventType
from coffer.domain.workflow.builtin import BUILTIN_TEMPLATE_NAME, BUILTIN_TEMPLATE_UID
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
from coffer.surfaces.http.workflow_seed_wiring import SEED_MARKER, FileSeedRecord


class Vault:
    """One throwaway vault: its resource service, its audit, its seed record."""

    def __init__(self, resources: ResourceService, audit: AuditService, home: pathlib.Path) -> None:
        self.resources = resources
        self.audit = audit
        self.home = home

    def seed(self) -> BuiltinWorkflowSeed:
        """A seed over this vault, built fresh — a daemon restart holds no
        state from the boot before it, and neither does this."""
        return BuiltinWorkflowSeed(resources=self.resources, record=FileSeedRecord(self.home))

    async def workflows(self) -> list[str]:
        return [r.name for r in await self.resources.list(kind=KIND_WORKFLOW)]


@pytest.fixture
async def vault(tmp_path: pathlib.Path) -> AsyncIterator[Vault]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'resources.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds={KIND_WORKFLOW: make_workflow_kind()},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    home = tmp_path / "home"
    home.mkdir()
    yield Vault(resources, audit, home)
    await engine.dispose()


@pytest.mark.acceptance(
    spec="workflow", scenario="a vault that has never been touched already has a workflow"
)
async def test_an_untouched_vault_holds_one_built_in_workflow_it_owns(vault: Vault) -> None:
    assert await vault.workflows() == []

    assert await vault.seed().seed() is True

    rows = await vault.resources.list(kind=KIND_WORKFLOW)
    assert [r.name for r in rows] == [BUILTIN_TEMPLATE_NAME]
    seeded = rows[0]

    # It assumes nothing about what this vault has registered: no task names a
    # skill or an agent, and the document validates against a vault that has
    # neither. `known_skills=()` is the strict reading — an empty registry, not
    # an unchecked one — which is what a fresh install actually is.
    template = parse_template(seeded.config, known_skills=(), allowed_agents=())
    nodes = [node for _stage, node in template.ordered_nodes()]
    assert len(nodes) == 5
    assert [n.skill for n in nodes] == [None] * 5
    assert [n.agent for n in nodes] == [None] * 5
    # Every task owes something, so none of them can finish leaving the run
    # nothing (FR-072) — including the one that declares no artifact of its own.
    assert all(n.required_artifacts for n in nodes)
    implement = next(n for n in nodes if n.key == "implement")
    assert implement.artifacts == ()
    assert [a.name for a in implement.owed_artifacts] == ["report.md"]

    # FR-001: an ordinary resource. It has the framework's identity, it is
    # enabled, it left an audit trail, and every lifecycle operation the
    # developer has over any other resource works on it.
    assert seeded.uid == BUILTIN_TEMPLATE_UID
    assert seeded.enabled is True
    entries = await vault.audit.query(resource=seeded)
    assert [(e.event_type, e.actor) for e in entries] == [
        (AuditEventType.RESOURCE_CREATED.value, SEED_ACTOR)
    ]

    renamed = await vault.resources.rename(seeded.uid, "my-flow", actor="user")
    assert renamed.name == "my-flow"
    assert (await vault.resources.set_enabled(seeded.uid, False, actor="user")).enabled is False
    await vault.resources.delete(seeded.uid, actor="user")
    assert await vault.workflows() == []


async def test_seeding_twice_leaves_one_row(vault: Vault) -> None:
    assert await vault.seed().seed() is True
    assert await vault.seed().seed() is False

    assert await vault.workflows() == [BUILTIN_TEMPLATE_NAME]


async def test_a_deleted_built_in_is_not_seeded_again(vault: Vault) -> None:
    await vault.seed().seed()
    rows = await vault.resources.list(kind=KIND_WORKFLOW)
    await vault.resources.delete(rows[0].uid, actor="user")

    assert await vault.seed().seed() is False
    assert await vault.workflows() == []


async def test_a_renamed_built_in_is_not_seeded_again(vault: Vault) -> None:
    await vault.seed().seed()
    rows = await vault.resources.list(kind=KIND_WORKFLOW)
    await vault.resources.rename(rows[0].uid, "my-own-flow", actor="user")

    assert await vault.seed().seed() is False
    assert await vault.workflows() == ["my-own-flow"]


async def test_a_disabled_built_in_is_neither_re_seeded_nor_re_enabled(vault: Vault) -> None:
    await vault.seed().seed()
    rows = await vault.resources.list(kind=KIND_WORKFLOW)
    await vault.resources.set_enabled(rows[0].uid, False, actor="user")

    assert await vault.seed().seed() is False
    still = await vault.resources.list(kind=KIND_WORKFLOW)
    assert [(r.name, r.enabled) for r in still] == [(BUILTIN_TEMPLATE_NAME, False)]


async def test_a_machine_that_received_the_row_by_sync_records_it_without_writing(
    vault: Vault,
) -> None:
    """The second machine in a vault. It boots with the row already there —
    converge carried it — and must record that it has seen the built-in, or the
    developer deleting it from either machine gets it back from this one."""
    await vault.resources.register(
        kind=KIND_WORKFLOW,
        name=BUILTIN_TEMPLATE_NAME,
        config={
            "stages": [
                {"key": "s", "name": "S", "nodes": [{"key": "n", "name": "N", "type": "ai"}]}
            ]
        },
        actor="sync",
        uid=BUILTIN_TEMPLATE_UID,
    )

    assert await vault.seed().seed() is False
    assert (vault.home / SEED_MARKER).exists()
    assert await vault.workflows() == [BUILTIN_TEMPLATE_NAME]


async def test_a_seed_that_could_not_be_written_is_retried_rather_than_recorded(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The marker goes down after the row, not before: one failed write must
    not cost the vault its built-in permanently."""

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(vault.resources, "register", _boom)
    assert await vault.seed().seed() is False
    assert not (vault.home / SEED_MARKER).exists()

    monkeypatch.undo()
    assert await vault.seed().seed() is True
    assert await vault.workflows() == [BUILTIN_TEMPLATE_NAME]
