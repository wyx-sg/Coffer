"""Skill-delivery semantics (FR-012a / FR-025, User Story 11).

One rule decides delivery and nothing else does::

    delivered(skill, agent) == skill.enabled and agent_in_scope(skill.scope, agent)

Same construction style as ``test_skill_unmanaged.py`` (real sqlite + real
MasterStore / SyncEngine over tmp_path); the reconciliation hooks are wired the
way the composition root wires them.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.skill.kind import make_skill_kind
from coffer.application.skill.service import SkillService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ScopeInvalidError
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.workspace_errors import SkillOutOfScope
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.infrastructure.skill.master_store import MasterStore
from coffer.infrastructure.skill.persistence import SkillBindingRepo
from coffer.infrastructure.skill.sync_engine import SyncEngine


def _write_skill_folder(folder: pathlib.Path, *, name: str) -> pathlib.Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {name}
            description: A test skill named {name}.
            ---

            hello from {name}
            """
        ),
        encoding="utf-8",
    )
    return folder


async def _setup(tmp_path: pathlib.Path, *, reconcile_hooks: bool = True):
    """Build the real service graph over a real sqlite file.

    ``reconcile_hooks=False`` omits the skill kind's ``on_scope_changed`` /
    ``on_enabled_changed`` hooks, so a test can edit a skill's state WITHOUT
    triggering reconciliation and then drive ``apply_scope_for_agent`` by hand.
    """
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    binding_repo = SkillBindingRepo(sm)
    master_store = MasterStore(root=tmp_path / "coffer-skills")

    def _agent_skill_dir(r: Resource) -> pathlib.Path:
        return AgentConfig.model_validate(r.config).resolved_skill_dir()

    placeholder_kinds: dict = {}
    rs = ResourceService(kinds=placeholder_kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit)
    skill_svc = SkillService(
        resource_service=rs,
        audit=audit,
        binding_repo=binding_repo,
        master_store=master_store,
        sync_engine=SyncEngine(),
        agent_skill_dir_resolver=_agent_skill_dir,
    )

    async def _reconcile(agent_name: str) -> None:
        await skill_svc.apply_scope_for_agent(agent_name, actor="system")

    async def _skill_delivery_changed(ref: ResourceRef) -> None:
        for row in await rs.list(kind="agent"):
            await _reconcile(row.name)

    agent_svc = AgentService(
        resource_service=rs,
        audit=audit,
        on_config_dir_changed=skill_svc.relink_for_agent,
        reconcile_skill_delivery=_reconcile,
    )

    async def _agent_on_delete(ref):
        await skill_svc.cleanup_bindings_for_agent(ref)

    placeholder_kinds["agent"] = make_agent_kind(on_delete=_agent_on_delete)
    placeholder_kinds["skill"] = make_skill_kind(
        skill_svc.cleanup_bindings_for_skill,
        on_scope_changed=_skill_delivery_changed if reconcile_hooks else None,
        on_enabled_changed=_skill_delivery_changed if reconcile_hooks else None,
    )
    return skill_svc, agent_svc, audit, engine


async def _register_agent(
    agent_svc: AgentService, tmp_path: pathlib.Path, *, name: str
) -> tuple[Resource, pathlib.Path]:
    config_dir = tmp_path / f"{name}-cfg"
    config_dir.mkdir()
    agent = await agent_svc.register(
        agent_type=AgentType.CLAUDE_CODE,
        name=name,
        config_dir=str(config_dir),
        actor="cli",
    )
    return agent, config_dir / "skills"


async def _import_skill(skill_svc: SkillService, tmp_path: pathlib.Path, name: str) -> Resource:
    src = _write_skill_folder(tmp_path / "srcs" / name, name=name)
    return await skill_svc.import_local(path=str(src), actor="cli")


async def _delivered_names(skill_svc: SkillService, agent: Resource) -> set[str]:
    names_by_id = {s.id: s.name for s in await skill_svc.list_skills()}
    return {
        names_by_id[b.skill_resource_id]
        for b in await skill_svc._bindings.list_for_agent(agent.id)
        if b.enabled and b.skill_resource_id in names_by_id
    }


# ----- acceptance scenarios -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="a skill with no scope reaches every registered agent"
)
async def test_unscoped_skill_reaches_every_agent(tmp_path):
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    a1, dir1 = await _register_agent(agent_svc, tmp_path, name="a1")
    a2, dir2 = await _register_agent(agent_svc, tmp_path, name="a2")

    skill = await _import_skill(skill_svc, tmp_path, "shared")
    assert skill.scope is None  # a fresh skill names no agent → every agent

    assert (dir1 / "shared").is_symlink()
    assert (dir2 / "shared").is_symlink()
    assert await _delivered_names(skill_svc, a1) == {"shared"}
    assert await _delivered_names(skill_svc, a2) == {"shared"}
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="a skill scoped to no agent reaches nobody")
async def test_dormant_skill_reaches_nobody(tmp_path):
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    a1, dir1 = await _register_agent(agent_svc, tmp_path, name="a1")
    await _import_skill(skill_svc, tmp_path, "dormant")
    assert (dir1 / "dormant").is_symlink()

    # scope == [] is dormant: no agent is in scope.
    await skill_svc._rs.update_scope(ResourceRef("skill", "dormant"), [], actor="cli")
    assert not (dir1 / "dormant").exists()
    assert await _delivered_names(skill_svc, a1) == set()

    # And a later agent gets nothing either.
    a2, dir2 = await _register_agent(agent_svc, tmp_path, name="a2")
    assert not (dir2 / "dormant").exists()
    assert await _delivered_names(skill_svc, a2) == set()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="import delivers a skill only where its scope grants it"
)
async def test_import_delivers_only_where_scope_grants(tmp_path):
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    a1, dir1 = await _register_agent(agent_svc, tmp_path, name="a1")
    a2, dir2 = await _register_agent(agent_svc, tmp_path, name="a2")

    # Import, then narrow the scope to a1 only.
    await _import_skill(skill_svc, tmp_path, "only-a1")
    await skill_svc._rs.update_scope(ResourceRef("skill", "only-a1"), ["a1"], actor="cli")
    assert (dir1 / "only-a1").is_symlink()
    assert not (dir2 / "only-a1").exists()

    # A re-import of the SAME name (overwrite) must not widen delivery.
    src = _write_skill_folder(tmp_path / "srcs2" / "only-a1", name="only-a1")
    await skill_svc.import_local(path=str(src), actor="cli", overwrite=True)
    assert (dir1 / "only-a1").is_symlink()
    assert not (dir2 / "only-a1").exists()
    assert await _delivered_names(skill_svc, a1) == {"only-a1"}
    assert await _delivered_names(skill_svc, a2) == set()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="disabling a skill reclaims every delivered copy"
)
async def test_disabling_a_skill_reclaims_every_copy(tmp_path):
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    a1, dir1 = await _register_agent(agent_svc, tmp_path, name="a1")
    a2, dir2 = await _register_agent(agent_svc, tmp_path, name="a2")
    await _import_skill(skill_svc, tmp_path, "everywhere")
    assert (dir1 / "everywhere").is_symlink() and (dir2 / "everywhere").is_symlink()

    await skill_svc._rs.set_enabled(ResourceRef("skill", "everywhere"), False, actor="cli")

    assert not (dir1 / "everywhere").exists()
    assert not (dir2 / "everywhere").exists()
    assert await _delivered_names(skill_svc, a1) == set()
    assert await _delivered_names(skill_svc, a2) == set()
    # The master folder is untouched — a disable is not a removal.
    assert (skill_svc._store.paths_for("everywhere").folder / "SKILL.md").exists()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="re-enabling a skill redelivers it")
async def test_re_enabling_a_skill_redelivers_it(tmp_path):
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    a1, dir1 = await _register_agent(agent_svc, tmp_path, name="a1")
    await _import_skill(skill_svc, tmp_path, "back-again")
    ref = ResourceRef("skill", "back-again")

    await skill_svc._rs.set_enabled(ref, False, actor="cli")
    assert not (dir1 / "back-again").exists()

    await skill_svc._rs.set_enabled(ref, True, actor="cli")
    assert (dir1 / "back-again").is_symlink()
    assert await _delivered_names(skill_svc, a1) == {"back-again"}
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="scoping a skill away from an agent reclaims the delivered copy",
)
async def test_scoping_away_reclaims_the_delivered_copy(tmp_path):
    """Scope is a hard grant: once a delivered skill stops naming this agent,
    the copy is reclaimed — no other trigger required."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await _import_skill(skill_svc, tmp_path, "shared")
    assert (skill_dir / "shared").is_symlink()
    assert await _delivered_names(skill_svc, agent) == {"shared"}

    await skill_svc._rs.update_scope(ResourceRef("skill", "shared"), ["other"], actor="cli")

    assert not (skill_dir / "shared").exists()
    assert await _delivered_names(skill_svc, agent) == set()
    await engine.dispose()


# ----- non-acceptance coverage -----


@pytest.mark.asyncio
async def test_disabled_skill_is_not_delivered_to_a_new_agent(tmp_path):
    """A disabled skill is invisible to delivery, including to an agent that
    registers later."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    await _import_skill(skill_svc, tmp_path, "switched-off")
    await skill_svc._rs.set_enabled(ResourceRef("skill", "switched-off"), False, actor="cli")

    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    assert not (skill_dir / "switched-off").exists()
    assert await _delivered_names(skill_svc, agent) == set()
    await engine.dispose()


@pytest.mark.asyncio
async def test_scoping_back_in_redelivers(tmp_path):
    """The converse of the reclaim scenario: naming the agent again delivers
    the copy back, with no unrelated trigger."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    await _import_skill(skill_svc, tmp_path, "elsewhere")
    await skill_svc._rs.update_scope(ResourceRef("skill", "elsewhere"), ["other"], actor="cli")
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    assert not (skill_dir / "elsewhere").exists()

    await skill_svc._rs.update_scope(ResourceRef("skill", "elsewhere"), ["a1"], actor="cli")

    assert (skill_dir / "elsewhere").is_symlink()
    assert await _delivered_names(skill_svc, agent) == {"elsewhere"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_master_removal_cleans_up_delivered_copies(tmp_path):
    skill_svc, agent_svc, _, engine = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await _import_skill(skill_svc, tmp_path, "doomed")
    assert (skill_dir / "doomed").is_symlink()

    await skill_svc.remove(name="doomed", actor="cli")
    assert not (skill_dir / "doomed").exists()
    assert not (skill_dir / "doomed").is_symlink()
    assert await skill_svc._bindings.list_for_agent(agent.id) == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_reconcile_tolerates_target_conflict(tmp_path):
    """An occupied target path skips that one skill — the rest of the
    reconciliation still delivers."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    # Import before any agent exists so nothing is delivered yet.
    await _import_skill(skill_svc, tmp_path, "blocked")
    await _import_skill(skill_svc, tmp_path, "smooth")

    config_dir = tmp_path / "a1-cfg"
    (config_dir / "skills").mkdir(parents=True)
    # Foreign content occupies the would-be link path for "blocked".
    foreign = config_dir / "skills" / "blocked"
    foreign.mkdir()
    (foreign / "mine.txt").write_text("user data", encoding="utf-8")

    agent = await agent_svc.register(
        agent_type=AgentType.CLAUDE_CODE, name="a1", config_dir=str(config_dir), actor="cli"
    )
    assert (config_dir / "skills" / "smooth").is_symlink()
    assert (foreign / "mine.txt").read_text(encoding="utf-8") == "user data"  # never clobbered
    assert await _delivered_names(skill_svc, agent) == {"smooth"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_apply_scope_reports_per_skill_failures(tmp_path):
    """Per-skill failures come back as strings for the sync run's errors, and
    never abort the rest of the reconciliation."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path, reconcile_hooks=False)
    await _import_skill(skill_svc, tmp_path, "blocked")

    config_dir = tmp_path / "a1-cfg"
    (config_dir / "skills").mkdir(parents=True)
    foreign = config_dir / "skills" / "blocked"
    foreign.mkdir()
    (foreign / "mine.txt").write_text("user data", encoding="utf-8")
    await agent_svc.register(
        agent_type=AgentType.CLAUDE_CODE, name="a1", config_dir=str(config_dir), actor="cli"
    )

    failures = await skill_svc.apply_scope_for_agent("a1", actor="sync")
    assert len(failures) == 1
    assert "blocked" in failures[0]
    await engine.dispose()


@pytest.mark.asyncio
async def test_apply_scope_for_unknown_agent_is_a_noop(tmp_path):
    skill_svc, _agent_svc, _audit, engine = await _setup(tmp_path)
    assert await skill_svc.apply_scope_for_agent("ghost", actor="system") == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_config_dir_move_preserves_delivery(tmp_path):
    _skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    _agent, old_dir = await _register_agent(agent_svc, tmp_path, name="cc")
    await _import_skill(_skill_svc, tmp_path, "travels")
    assert (old_dir / "travels").is_symlink()

    new_dir = tmp_path / "moved-claude"
    new_dir.mkdir()
    await agent_svc.update_config_dir(name="cc", new_config_dir=str(new_dir), actor="cli")
    assert not (old_dir / "travels").exists()
    assert (new_dir / "skills" / "travels").is_symlink()
    await engine.dispose()


@pytest.mark.asyncio
async def test_manual_enable_refused_out_of_scope(tmp_path):
    """The internal ``enable_for`` primitive must not be able to override an
    out-of-scope agent — scope is a hard grant."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path, reconcile_hooks=False)
    await _import_skill(skill_svc, tmp_path, "denied")
    await skill_svc._rs.update_scope(ResourceRef("skill", "denied"), ["other"], actor="test")
    await _register_agent(agent_svc, tmp_path, name="a1")

    with pytest.raises(SkillOutOfScope):
        await skill_svc.enable_for(skill_name="denied", agent_name="a1", actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_config_dir_change_does_not_resurrect_ungranted_link(tmp_path):
    """Regression: relink_agent_skills must not recreate a binding's link at
    the new config_dir once the predicate no longer grants it. Before the fix,
    a config_dir change blindly re-created every enabled binding's link."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path, reconcile_hooks=False)
    _agent, old_skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await _import_skill(skill_svc, tmp_path, "shared")
    old_link = old_skill_dir / "shared"
    assert old_link.is_symlink()

    # Disable the skill WITHOUT reconciliation (hooks omitted) — isolates the
    # config-dir-change relink path from apply_scope_for_agent's own reclaim.
    await skill_svc._rs.set_enabled(ResourceRef("skill", "shared"), False, actor="test")

    new_config_dir = tmp_path / "moved-cfg"
    new_config_dir.mkdir()
    await agent_svc.update_config_dir(name="a1", new_config_dir=str(new_config_dir), actor="cli")

    new_link = new_config_dir / "skills" / "shared"
    assert not old_link.exists(), "stale old link should still be torn down"
    assert not new_link.exists(), "an ungranted link must not be resurrected at the new config_dir"
    # The binding row itself is left untouched (not deleted) — reclaim is
    # apply_scope_for_agent's job, not relink's.
    assert len(await skill_svc.bindings_for("shared")) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_scope_on_agent_kind_is_rejected(tmp_path):
    """The `agent` kind declares no scope (ADR per-agent-resource-scope) — scope names the agents a
    resource is active for, so an agent scoping itself is meaningless."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    await _register_agent(agent_svc, tmp_path, name="a1")
    with pytest.raises(ScopeInvalidError):
        await skill_svc._rs.update_scope(ResourceRef("agent", "a1"), ["a1"], actor="cli")
    await engine.dispose()
