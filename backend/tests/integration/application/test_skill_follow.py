"""Follow-master-library delivery semantics (FR-025, User Story 11).

Same construction style as ``test_skill_unmanaged.py`` (real sqlite + real
MasterStore / SyncEngine over tmp_path); the follow-policy resolver and the
on-skill-policy-changed hook are wired the way the composition root does:
AgentConfig fields read at the seam (tests sit outside Contract 5c).
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


async def _setup(tmp_path: pathlib.Path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    binding_repo = SkillBindingRepo(sm)
    master_store = MasterStore(root=tmp_path / "coffer-skills")

    def _agent_skill_dir(r: Resource) -> pathlib.Path:
        return AgentConfig.model_validate(r.config).resolved_skill_dir()

    def _agent_skill_policy(r: Resource) -> tuple[bool, list[str]]:
        cfg = AgentConfig.model_validate(r.config)
        return (cfg.follow_all_skills, cfg.skill_exclusions)

    placeholder_kinds: dict = {}
    rs = ResourceService(kinds=placeholder_kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit)
    skill_svc = SkillService(
        resource_service=rs,
        audit=audit,
        binding_repo=binding_repo,
        master_store=master_store,
        sync_engine=SyncEngine(),
        agent_skill_dir_resolver=_agent_skill_dir,
        agent_skill_policy_resolver=_agent_skill_policy,
    )

    async def _on_skill_policy_changed(agent_name: str) -> None:
        await skill_svc.apply_follow_for_agent(agent_name, actor="system")

    agent_svc = AgentService(
        resource_service=rs,
        audit=audit,
        on_config_dir_changed=skill_svc.relink_for_agent,
        on_skill_policy_changed=_on_skill_policy_changed,
    )

    async def _agent_on_delete(ref):
        await skill_svc.cleanup_bindings_for_agent(ref)

    placeholder_kinds["agent"] = make_agent_kind(on_delete=_agent_on_delete)
    placeholder_kinds["skill"] = make_skill_kind(skill_svc.cleanup_bindings_for_skill)
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


async def _enabled_bound_names(skill_svc: SkillService, agent: Resource) -> set[str]:
    names_by_id = {s.id: s.name for s in await skill_svc.list_skills()}
    return {
        names_by_id[b.skill_resource_id]
        for b in await skill_svc._bindings.list_for_agent(agent.id)
        if b.enabled and b.skill_resource_id in names_by_id
    }


# ----- acceptance scenarios -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="enable follow-all and deliver every master skill"
)
async def test_enable_follow_delivers_every_master_skill(tmp_path):
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await agent_svc.update_skill_policy(name="a1", follow_all_skills=False, actor="cli")
    for n in ("s1", "s2", "s3"):
        await _import_skill(skill_svc, tmp_path, n)
    # Not following — imports were not delivered.
    assert not any((skill_dir / n).exists() for n in ("s1", "s2", "s3"))

    await agent_svc.update_skill_policy(name="a1", follow_all_skills=True, actor="cli")
    for n in ("s1", "s2", "s3"):
        assert (skill_dir / n).is_symlink()
    assert await _enabled_bound_names(skill_svc, agent) == {"s1", "s2", "s3"}
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="auto-deliver new skills to following agents"
)
async def test_new_skill_auto_delivered_to_following_agent(tmp_path):
    skill_svc, agent_svc, _, engine = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await _import_skill(skill_svc, tmp_path, "fresh")
    # Delivered on registration, with no further calls.
    assert (skill_dir / "fresh").is_symlink()
    assert await _enabled_bound_names(skill_svc, agent) == {"fresh"}
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="auto-remove deleted skills from following agents"
)
async def test_master_removal_cleans_up_following_agent(tmp_path):
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
@pytest.mark.acceptance(spec="skill-manager", scenario="exclude a skill from a following agent")
async def test_exclude_removes_link_and_never_redelivers(tmp_path):
    skill_svc, agent_svc, _, engine = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await _import_skill(skill_svc, tmp_path, "keep")
    await _import_skill(skill_svc, tmp_path, "drop")
    assert (skill_dir / "keep").is_symlink() and (skill_dir / "drop").is_symlink()

    await agent_svc.update_skill_policy(name="a1", skill_exclusions=["drop"], actor="cli")
    assert (skill_dir / "keep").is_symlink()  # others remain
    assert not (skill_dir / "drop").exists()
    assert await _enabled_bound_names(skill_svc, agent) == {"keep"}

    # Re-applying follow never redelivers an excluded skill …
    await skill_svc.apply_follow_for_agent("a1", actor="system")
    assert not (skill_dir / "drop").exists()
    # … and neither does removing + re-importing it into the master store.
    await skill_svc.remove(name="drop", actor="cli")
    await _import_skill(skill_svc, tmp_path, "drop")
    assert not (skill_dir / "drop").exists()
    assert await _enabled_bound_names(skill_svc, agent) == {"keep"}
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="disable follow-all preserving current bindings"
)
async def test_disable_follow_preserves_bindings(tmp_path):
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await _import_skill(skill_svc, tmp_path, "s1")
    await _import_skill(skill_svc, tmp_path, "s2")

    await agent_svc.update_skill_policy(name="a1", follow_all_skills=False, actor="cli")
    # Existing deliveries are untouched.
    assert (skill_dir / "s1").is_symlink() and (skill_dir / "s2").is_symlink()
    assert await _enabled_bound_names(skill_svc, agent) == {"s1", "s2"}

    # A later import is no longer auto-delivered to this agent.
    await _import_skill(skill_svc, tmp_path, "s3")
    assert not (skill_dir / "s3").exists()
    assert await _enabled_bound_names(skill_svc, agent) == {"s1", "s2"}
    await engine.dispose()


# ----- non-acceptance coverage -----


@pytest.mark.asyncio
async def test_autobind_skips_excluded_skill_on_import(tmp_path):
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await agent_svc.update_skill_policy(name="a1", skill_exclusions=["banned"], actor="cli")

    await _import_skill(skill_svc, tmp_path, "banned")
    await _import_skill(skill_svc, tmp_path, "welcome")
    assert not (skill_dir / "banned").exists()
    assert (skill_dir / "welcome").is_symlink()
    await engine.dispose()


@pytest.mark.asyncio
async def test_apply_follow_tolerates_target_conflict(tmp_path):
    """An occupied target path skips that one skill — the rest of the
    reconciliation still delivers."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await agent_svc.update_skill_policy(name="a1", follow_all_skills=False, actor="cli")
    await _import_skill(skill_svc, tmp_path, "blocked")
    await _import_skill(skill_svc, tmp_path, "smooth")
    # Foreign content occupies the would-be link path for "blocked".
    foreign = skill_dir / "blocked"
    foreign.mkdir(parents=True)
    (foreign / "mine.txt").write_text("user data", encoding="utf-8")

    await agent_svc.update_skill_policy(name="a1", follow_all_skills=True, actor="cli")
    assert (skill_dir / "smooth").is_symlink()
    assert (foreign / "mine.txt").read_text(encoding="utf-8") == "user data"  # never clobbered
    assert await _enabled_bound_names(skill_svc, agent) == {"smooth"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_unwired_policy_resolver_defaults_to_trust_mode(tmp_path):
    """Without a wired resolver the policy is (True, []) — today's auto-bind
    behavior is preserved even if the agent's config says otherwise."""
    skill_svc, agent_svc, _, engine = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await agent_svc.update_skill_policy(name="a1", follow_all_skills=False, actor="cli")
    skill_svc._agent_skill_policy_resolver = None

    assert skill_svc._resolve_agent_skill_policy(agent) == (True, [])
    await _import_skill(skill_svc, tmp_path, "anyway")
    assert (skill_dir / "anyway").is_symlink()
    await engine.dispose()


@pytest.mark.asyncio
async def test_config_dir_move_preserves_follow_policy(tmp_path):
    """Regression: a config-dir PATCH once rebuilt AgentConfig from type+dir
    only, silently resetting follow_all_skills/skill_exclusions to defaults."""
    _skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    await _register_agent(agent_svc, tmp_path, name="cc")
    await agent_svc.update_skill_policy(
        name="cc", follow_all_skills=False, skill_exclusions=["x"], actor="cli"
    )
    new_dir = tmp_path / "moved-claude"
    new_dir.mkdir()
    moved = await agent_svc.update_config_dir(name="cc", new_config_dir=str(new_dir), actor="cli")
    cfg = AgentConfig.model_validate(moved.config)
    assert cfg.follow_all_skills is False
    assert cfg.skill_exclusions == ["x"]
    await engine.dispose()


async def _setup_with_scope_reconcile(tmp_path: pathlib.Path):
    """Same wiring as ``_setup``, plus the skill kind's ``on_scope_changed``
    hook the composition root wires in ``agent_skill_wiring.py``: a skill's
    scope edit re-reconciles every registered agent's follow delivery. Kept
    separate from ``_setup`` so the many existing tests above (and the relink
    test) keep exercising a scope edit that does NOT itself trigger
    reconciliation."""
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    binding_repo = SkillBindingRepo(sm)
    master_store = MasterStore(root=tmp_path / "coffer-skills")

    def _agent_skill_dir(r: Resource) -> pathlib.Path:
        return AgentConfig.model_validate(r.config).resolved_skill_dir()

    def _agent_skill_policy(r: Resource) -> tuple[bool, list[str]]:
        cfg = AgentConfig.model_validate(r.config)
        return (cfg.follow_all_skills, cfg.skill_exclusions)

    placeholder_kinds: dict = {}
    rs = ResourceService(kinds=placeholder_kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit)
    skill_svc = SkillService(
        resource_service=rs,
        audit=audit,
        binding_repo=binding_repo,
        master_store=master_store,
        sync_engine=SyncEngine(),
        agent_skill_dir_resolver=_agent_skill_dir,
        agent_skill_policy_resolver=_agent_skill_policy,
    )

    async def _on_skill_policy_changed(agent_name: str) -> None:
        await skill_svc.apply_follow_for_agent(agent_name, actor="system")

    async def _skill_on_scope_changed(ref: ResourceRef) -> None:
        for row in await rs.list(kind="agent"):
            await _on_skill_policy_changed(row.name)

    agent_svc = AgentService(
        resource_service=rs,
        audit=audit,
        on_config_dir_changed=skill_svc.relink_for_agent,
        on_skill_policy_changed=_on_skill_policy_changed,
    )

    async def _agent_on_delete(ref):
        await skill_svc.cleanup_bindings_for_agent(ref)

    placeholder_kinds["agent"] = make_agent_kind(on_delete=_agent_on_delete)
    placeholder_kinds["skill"] = make_skill_kind(
        skill_svc.cleanup_bindings_for_skill, on_scope_changed=_skill_on_scope_changed
    )
    return skill_svc, agent_svc, audit, engine


# ----- scope intersection + reclaim -----


@pytest.mark.asyncio
async def test_scoped_out_skill_not_delivered_under_follow(tmp_path):
    """A skill scoped to another agent is excluded from `wanted` and never
    delivered, even though this agent is following (delivery = scope ∩ follow
    policy)."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    # Import before any agent exists — nothing to auto-bind yet.
    await _import_skill(skill_svc, tmp_path, "elsewhere")
    await skill_svc._rs.update_scope(ResourceRef("skill", "elsewhere"), ["other"], actor="test")

    # Registration triggers apply_follow_for_agent (follow_all_skills=True default).
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    assert not (skill_dir / "elsewhere").exists()
    assert await _enabled_bound_names(skill_svc, agent) == set()
    await engine.dispose()


@pytest.mark.asyncio
async def test_dormant_skill_not_delivered_to_any_agent(tmp_path):
    """``scope == []`` is dormant — no agent is in scope, so nothing is
    delivered even under follow-all."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    await _import_skill(skill_svc, tmp_path, "dormant")
    await skill_svc._rs.update_scope(ResourceRef("skill", "dormant"), [], actor="test")

    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    assert not (skill_dir / "dormant").exists()
    assert await _enabled_bound_names(skill_svc, agent) == set()
    await engine.dispose()


@pytest.mark.asyncio
async def test_skill_scoped_to_this_agent_is_delivered(tmp_path):
    """The converse of the exclusion tests: a skill naming this agent is
    delivered under follow — the gate must not be overly restrictive."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    await _import_skill(skill_svc, tmp_path, "mine")
    await skill_svc._rs.update_scope(ResourceRef("skill", "mine"), ["a1"], actor="test")

    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    assert (skill_dir / "mine").is_symlink()
    assert await _enabled_bound_names(skill_svc, agent) == {"mine"}
    await engine.dispose()


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario=(
        "delivery is the intersection of scope and follow policy; an out-of-scope copy is reclaimed"
    ),
)
@pytest.mark.asyncio
async def test_previously_delivered_copy_reclaimed_once_scope_excludes_it(tmp_path):
    """Scope is a hard grant: once a bound skill falls out of scope, the next
    follow run reclaims the delivered copy — even though nothing about the
    follow policy itself changed."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await _import_skill(skill_svc, tmp_path, "shared")
    assert (skill_dir / "shared").is_symlink()
    assert await _enabled_bound_names(skill_svc, agent) == {"shared"}

    await skill_svc._rs.update_scope(ResourceRef("skill", "shared"), ["other"], actor="test")
    await skill_svc.apply_follow_for_agent("a1", actor="system")

    assert not (skill_dir / "shared").exists()
    assert await _enabled_bound_names(skill_svc, agent) == set()
    await engine.dispose()


@pytest.mark.asyncio
async def test_manual_enable_refused_out_of_scope(tmp_path):
    """A manual `enable_for` call must not be able to override an
    out-of-scope agent — scope is a hard grant."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    await _import_skill(skill_svc, tmp_path, "denied")
    await skill_svc._rs.update_scope(ResourceRef("skill", "denied"), ["other"], actor="test")
    await _register_agent(agent_svc, tmp_path, name="a1")

    with pytest.raises(SkillOutOfScope):
        await skill_svc.enable_for(skill_name="denied", agent_name="a1", actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_unscoped_skill_is_never_filtered(tmp_path):
    """``scope is None`` is the pre-scope default: every agent is in scope,
    for both follow delivery and manual binds."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    await _import_skill(skill_svc, tmp_path, "anywhere")
    assert (await skill_svc._rs.get(ResourceRef("skill", "anywhere"))).scope is None

    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    assert (skill_dir / "anywhere").is_symlink()
    assert await _enabled_bound_names(skill_svc, agent) == {"anywhere"}

    # Manual bind is not gated either.
    await skill_svc.disable_for(skill_name="anywhere", agent_name="a1", actor="cli")
    await skill_svc.enable_for(skill_name="anywhere", agent_name="a1", actor="cli")
    assert (skill_dir / "anywhere").is_symlink()
    await engine.dispose()


@pytest.mark.asyncio
async def test_config_dir_change_does_not_resurrect_out_of_scope_link(tmp_path):
    """Regression: relink_agent_skills must not recreate a binding's link at
    the new config_dir once its skill has fallen out of this agent's scope.
    Before the fix, a config_dir change blindly re-created every enabled
    binding's link — resurrecting a link the scope hard grant had already
    excluded."""
    skill_svc, agent_svc, _audit, engine = await _setup(tmp_path)
    _agent, old_skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await _import_skill(skill_svc, tmp_path, "shared")
    old_link = old_skill_dir / "shared"
    assert old_link.is_symlink()

    # Scope the skill away from this agent WITHOUT running a follow
    # reconciliation — isolates the config-dir-change relink path from
    # apply_follow_for_agent's own reclaim.
    await skill_svc._rs.update_scope(ResourceRef("skill", "shared"), ["other"], actor="test")

    new_config_dir = tmp_path / "moved-cfg"
    new_config_dir.mkdir()
    await agent_svc.update_config_dir(name="a1", new_config_dir=str(new_config_dir), actor="cli")

    new_link = new_config_dir / "skills" / "shared"
    assert not old_link.exists(), "stale old link should still be torn down"
    assert not new_link.exists(), "out-of-scope link must not be resurrected at the new config_dir"
    # The binding row itself is left untouched (not deleted) — reclaim is
    # apply_follow_for_agent's job, not relink's.
    bindings = await skill_svc.bindings_for("shared")
    assert len(bindings) == 1
    await engine.dispose()


# ----- scope-edit reconciliation hook -----


@pytest.mark.asyncio
async def test_update_scope_on_skill_immediately_reclaims_delivered_copy(tmp_path):
    """Editing a skill's scope through ResourceService.update_scope must
    immediately reclaim a previously delivered copy — no unrelated trigger
    (another import, a policy flip) required."""
    skill_svc, agent_svc, _audit, engine = await _setup_with_scope_reconcile(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    await _import_skill(skill_svc, tmp_path, "shared")
    assert (skill_dir / "shared").is_symlink()
    assert await _enabled_bound_names(skill_svc, agent) == {"shared"}

    # No manual apply_follow_for_agent call — the scope edit alone must
    # trigger the reclaim via the skill kind's on_scope_changed hook.
    await skill_svc._rs.update_scope(ResourceRef("skill", "shared"), ["other"], actor="cli")

    assert not (skill_dir / "shared").exists()
    assert await _enabled_bound_names(skill_svc, agent) == set()
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_scope_on_skill_immediately_delivers_newly_in_scope(tmp_path):
    """The converse of reclaim: scoping a previously out-of-scope skill IN
    immediately delivers it to a following agent — again with no unrelated
    trigger."""
    skill_svc, agent_svc, _audit, engine = await _setup_with_scope_reconcile(tmp_path)
    await _import_skill(skill_svc, tmp_path, "elsewhere")
    await skill_svc._rs.update_scope(ResourceRef("skill", "elsewhere"), ["other"], actor="cli")
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    assert not (skill_dir / "elsewhere").exists()

    # No manual apply_follow_for_agent call — scoping the skill back in
    # alone must deliver it.
    await skill_svc._rs.update_scope(ResourceRef("skill", "elsewhere"), ["a1"], actor="cli")

    assert (skill_dir / "elsewhere").is_symlink()
    assert await _enabled_bound_names(skill_svc, agent) == {"elsewhere"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_scope_on_agent_kind_is_rejected(tmp_path):
    """The `agent` kind declares no scope (ADR per-agent-resource-scope) — scope names the agents a
    resource is active for, so an agent scoping itself is meaningless."""
    skill_svc, agent_svc, _audit, engine = await _setup_with_scope_reconcile(tmp_path)
    await _register_agent(agent_svc, tmp_path, name="a1")
    with pytest.raises(ScopeInvalidError):
        await skill_svc._rs.update_scope(ResourceRef("agent", "a1"), ["a1"], actor="cli")
    await engine.dispose()
