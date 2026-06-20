"""SkillService end-to-end integration (DB + filesystem + sync engine).

Covers import / enable / disable / verify / remove +
the cross-kind cleanup hooks.
"""

from __future__ import annotations

import os
import pathlib
import textwrap

import pytest

from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.skill.kind import make_skill_kind
from coffer.application.skill.service import SkillService
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import (
    SkillValidationError,
    TargetConflict,
)
from coffer.domain.resource import Resource
from coffer.domain.skill.drift import DriftKind
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


def _write_skill_folder(folder: pathlib.Path, *, name: str, body: str = "hello") -> pathlib.Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        textwrap.dedent(
            f"""\
            ---
            name: {name}
            description: A test skill named {name}.
            ---

            {body}
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

    # Cross-kind resolver — tests are outside the contract scope so we can
    # import both kinds here without violating Contract 5.
    from coffer.domain.agent.config import AgentConfig
    from coffer.domain.agent.descriptor import descriptor_for

    def _agent_skill_dir(r: Resource):
        cfg = AgentConfig.model_validate(r.config)
        return cfg.resolved_skill_dir()

    def _agent_skill_delivery(r: Resource) -> str:
        return descriptor_for(AgentConfig.model_validate(r.config).type).skill_delivery_mode.value

    # Order: create services first, then kinds (with cross-kind hooks).
    placeholder_kinds: dict = {}
    rs = ResourceService(kinds=placeholder_kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit)
    from coffer.infrastructure.skill.sync_engine import SyncEngine

    skill_svc = SkillService(
        resource_service=rs,
        audit=audit,
        binding_repo=binding_repo,
        master_store=master_store,
        sync_engine=SyncEngine(),
        agent_skill_dir_resolver=_agent_skill_dir,
        agent_skill_delivery_resolver=_agent_skill_delivery,
    )

    agent_svc = AgentService(
        resource_service=rs,
        audit=audit,
        on_config_dir_changed=skill_svc.relink_for_agent,
    )

    # CODE21-001 made the agent on_delete hook awaited (not fire-and-forget)
    # so cleanup happens BEFORE the agent row vanishes; mirror that here so
    # the test wiring matches the composition root.
    async def _agent_on_delete(ref):
        await skill_svc.cleanup_bindings_for_agent(ref)

    placeholder_kinds["agent"] = make_agent_kind(on_delete=_agent_on_delete)
    placeholder_kinds["skill"] = make_skill_kind(skill_svc.cleanup_bindings_for_skill)

    return skill_svc, agent_svc, audit, master_store, engine


async def _register_agent(
    agent_svc: AgentService,
    tmp_path: pathlib.Path,
    *,
    name: str,
    agent_type: AgentType = AgentType.CLAUDE_CODE,
) -> tuple[Resource, pathlib.Path]:
    # One agent per config dir (= per type), so tests that need two agents
    # pass distinct types — a skill bound to a claude_code AND a codex agent.
    config_dir = tmp_path / f"{name}-cfg"
    config_dir.mkdir()
    agent = await agent_svc.register(
        agent_type=agent_type,
        name=name,
        config_dir=str(config_dir),
        actor="cli",
    )
    # Registration auto-creates <config_dir>/skills; that's where this agent's
    # enabled skills are symlinked, so return it for link-location assertions.
    return agent, config_dir / "skills"


# ----- import -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="import a valid local skill folder")
async def test_import_valid_skill(tmp_path):
    skill_svc, _, audit, store, engine = await _setup(tmp_path)
    src = tmp_path / "src"
    _write_skill_folder(src, name="hello-world")
    r = await skill_svc.import_local(path=str(src), actor="cli")
    assert r.kind == "skill"
    assert r.name == "hello-world"
    assert store.paths_for("hello-world").skill_md.is_file()
    audited = await audit.query(event_type=AuditEventType.SKILL_IMPORTED.value)
    assert len(audited) == 1
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="005-skill-manager", scenario="reject import of an invalid skill folder"
)
async def test_import_rejects_invalid_frontmatter(tmp_path):
    skill_svc, _, _, store, engine = await _setup(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text("no frontmatter")
    with pytest.raises(SkillValidationError):
        await skill_svc.import_local(path=str(src), actor="cli")
    assert store.list_names() == []
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="005-skill-manager", scenario="reject import containing path-escape symlinks"
)
async def test_import_rejects_path_escape_symlink(tmp_path):
    skill_svc, _, _, _, engine = await _setup(tmp_path)
    src = tmp_path / "src"
    _write_skill_folder(src, name="x")
    outside = tmp_path / "secret"
    outside.write_text("secret")
    os.symlink(outside, src / "ev")
    with pytest.raises(SkillValidationError):
        await skill_svc.import_local(path=str(src), actor="cli")
    await engine.dispose()


# ----- enable / disable -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="enable a skill for a registered agent")
async def test_enable_creates_link(tmp_path):
    skill_svc, agent_svc, _, _, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    # import auto-binds; verify the link exists at the agent's skill_dir.
    target = skill_dir / "my-skill"
    assert target.exists()
    assert (target / "SKILL.md").is_file()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="disable a skill for an agent")
async def test_disable_removes_link_keeps_master(tmp_path):
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    target = skill_dir / "my-skill"
    assert target.exists()
    await skill_svc.disable_for(skill_name="my-skill", agent_name="cur", actor="cli")
    assert not target.exists()
    assert store.paths_for("my-skill").folder.is_dir()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="enable for multiple agents")
async def test_enable_for_two_agents(tmp_path):
    skill_svc, agent_svc, _, _, engine = await _setup(tmp_path)
    _, sd1 = await _register_agent(agent_svc, tmp_path, name="cur1")
    _, sd2 = await _register_agent(agent_svc, tmp_path, name="cur2", agent_type=AgentType.CODEX)
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    t1 = sd1 / "my-skill"
    t2 = sd2 / "my-skill"
    assert t1.is_dir() and t2.is_dir()
    assert (t1 / "SKILL.md").read_bytes() == (t2 / "SKILL.md").read_bytes()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="005-skill-manager", scenario="refuse to overwrite a non-Coffer target"
)
async def test_refuse_to_overwrite_non_coffer_target(tmp_path):
    skill_svc, agent_svc, _, _, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    # Pre-place a foreign directory at the would-be link path.
    link = skill_dir / "my-skill"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.mkdir()
    (link / "stub").write_text("foreign")
    # import auto-binds; it must skip this agent due to target conflict (no exception).
    await skill_svc.import_local(path=str(src), actor="cli")
    # Now try to enable explicitly without force — should raise TargetConflict.
    with pytest.raises(TargetConflict):
        await skill_svc.enable_for(
            skill_name="my-skill", agent_name="cur", force=False, actor="cli"
        )
    # With force, the foreign target is backed up and link is created.
    binding = await skill_svc.enable_for(
        skill_name="my-skill", agent_name="cur", force=True, actor="cli"
    )
    assert binding.enabled
    backups = list(skill_dir.glob("my-skill.coffer-backup-*"))
    assert backups
    # TEST21-005: pin the backup-name format so the spec's `<path>.coffer-
    # backup-<ts>` shape (integer unix timestamp suffix) doesn't regress.
    import re

    assert re.match(r".*\.coffer-backup-\d{10,}$", backups[0].name)
    await engine.dispose()


# ----- verify -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="005-skill-manager", scenario="detect drift in agent skill directories"
)
async def test_verify_detects_missing_link(tmp_path):
    skill_svc, agent_svc, _, _, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    link = skill_dir / "my-skill"
    link.unlink()
    report = await skill_svc.verify()
    assert any(e.kind is DriftKind.MISSING_LINK for e in report.entries)
    await engine.dispose()


# ----- removal -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="remove a skill cleans up all bindings")
async def test_remove_skill_cleans_everything(tmp_path):
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    _, sd1 = await _register_agent(agent_svc, tmp_path, name="cur1")
    _, sd2 = await _register_agent(agent_svc, tmp_path, name="cur2", agent_type=AgentType.CODEX)
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    t1 = sd1 / "my-skill"
    t2 = sd2 / "my-skill"
    assert t1.exists() and t2.exists()
    await skill_svc.remove(name="my-skill", actor="cli")
    assert not t1.exists() and not t2.exists()
    assert not store.paths_for("my-skill").folder.exists()
    assert (await skill_svc.list_skills()) == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_kind_agnostic_delete_skill_cleans_everything(tmp_path):
    """CODE21-001 fix-validation: going through ResourceService.delete
    (the kind-agnostic ``DELETE /api/v1/resources/skill/{name}`` path)
    must trigger the awaited on_delete hook BEFORE the row is removed,
    so symlinks AND the master folder are both gone — not orphaned."""
    from coffer.domain.resource import ResourceRef

    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    _, sd1 = await _register_agent(agent_svc, tmp_path, name="cur1")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    t1 = sd1 / "my-skill"
    assert t1.exists()
    assert store.paths_for("my-skill").folder.exists()
    # Bypass SkillService.remove — hit ResourceService.delete directly so
    # we exercise the same path the kind-agnostic HTTP route uses.
    await skill_svc._rs.delete(ResourceRef("skill", "my-skill"), actor="cli")
    # Symlink AND master folder must be gone before the row was deleted.
    assert not t1.exists()
    assert not store.paths_for("my-skill").folder.exists()
    assert (await skill_svc.list_skills()) == []
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="005-skill-manager",
    scenario="removing an agent (per spec 004) cleans up its skill bindings",
)
async def test_remove_agent_cleans_its_bindings(tmp_path):
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    a1, sd1 = await _register_agent(agent_svc, tmp_path, name="cur1")
    _, sd2 = await _register_agent(agent_svc, tmp_path, name="cur2", agent_type=AgentType.CODEX)
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    t1 = sd1 / "my-skill"
    t2 = sd2 / "my-skill"
    await skill_svc.cleanup_bindings_for_agent(a1.ref)
    assert not t1.exists()
    assert t2.exists()
    assert store.paths_for("my-skill").folder.exists()
    await engine.dispose()


# ----- TEST21-008: agent delete cascade through ResourceService.delete -----


@pytest.mark.asyncio
async def test_agent_delete_via_resource_service_triggers_skill_cleanup(tmp_path):
    """End-to-end on_delete hook coverage (not a direct cleanup call).

    Going through ``ResourceService.delete`` (which is what the agent HTTP
    surface and ``AgentService.remove`` both call) must run the awaited
    on_delete hook BEFORE the agent row vanishes, so per-agent symlinks
    are torn down and binding rows are removed without orphaning.
    """
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    _, sd1 = await _register_agent(agent_svc, tmp_path, name="cur1")
    _, sd2 = await _register_agent(agent_svc, tmp_path, name="cur2", agent_type=AgentType.CODEX)
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    t1 = sd1 / "my-skill"
    t2 = sd2 / "my-skill"
    assert t1.exists() and t2.exists()

    # Remove via AgentService — which calls ResourceService.delete, which
    # awaits the on_delete hook, which runs cleanup_bindings_for_agent.
    await agent_svc.remove(name="cur1", actor="cli")

    # Symlink for cur1 must be gone; the other agent's link is untouched.
    assert not t1.exists()
    assert t2.exists()
    # Master folder is untouched (only the binding cascades on agent delete).
    assert store.paths_for("my-skill").folder.exists()
    await engine.dispose()


# ----- TEST21-010: drift kinds besides MISSING_LINK -----


@pytest.mark.asyncio
async def test_verify_detects_replaced_with_regular(tmp_path):
    """Drift kind REPLACED_WITH_REGULAR: link path is a plain dir, not a symlink."""
    skill_svc, agent_svc, _, _, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    link = skill_dir / "my-skill"
    # Replace the symlink with a regular directory.
    link.unlink()
    link.mkdir()
    (link / "foo").write_text("not from coffer")
    report = await skill_svc.verify()
    assert any(e.kind is DriftKind.REPLACED_WITH_REGULAR for e in report.entries)
    await engine.dispose()


@pytest.mark.asyncio
async def test_verify_detects_tampered_link(tmp_path):
    """Drift kind TAMPERED_LINK: symlink points somewhere other than master."""
    skill_svc, agent_svc, _, _, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    link = skill_dir / "my-skill"
    # Repoint the symlink at an unrelated folder.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link.unlink()
    link.symlink_to(elsewhere, target_is_directory=True)
    report = await skill_svc.verify()
    assert any(e.kind is DriftKind.TAMPERED_LINK for e in report.entries)
    await engine.dispose()


@pytest.mark.asyncio
async def test_verify_detects_missing_master(tmp_path):
    """Drift kind MISSING_MASTER: master folder has been deleted."""
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    # Verify the link exists, then nuke the master folder out from under it.
    link = skill_dir / "my-skill"
    assert link.exists()
    import shutil

    shutil.rmtree(store.paths_for("my-skill").folder)
    report = await skill_svc.verify()
    assert any(e.kind is DriftKind.MISSING_MASTER for e in report.entries)
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="audit skill lifecycle")
async def test_audit_skill_lifecycle(tmp_path):
    skill_svc, _, audit, _, engine = await _setup(tmp_path)
    src = tmp_path / "src"
    _write_skill_folder(src, name="aud")
    await skill_svc.import_local(path=str(src), actor="cli")
    await skill_svc.remove(name="aud", actor="cli")
    imported = await audit.query(event_type=AuditEventType.SKILL_IMPORTED.value)
    deleted = await audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert len(imported) == 1 and len(deleted) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_disable_for_unbound_agent_is_noop(tmp_path):
    """disable_for an agent that was never bound must not write a phantom
    disabled binding row or a spurious SKILL_UNBOUND audit event."""
    skill_svc, agent_svc, audit, _, engine = await _setup(tmp_path)
    await _register_agent(agent_svc, tmp_path, name="bound")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    # A second agent registered AFTER import is never auto-bound to the skill.
    await _register_agent(agent_svc, tmp_path, name="never", agent_type=AgentType.CODEX)

    binding = await skill_svc.disable_for(skill_name="my-skill", agent_name="never", actor="cli")
    assert binding.enabled is False
    # No SKILL_UNBOUND event was recorded (nothing was ever bound).
    unbound = await audit.query(event_type=AuditEventType.SKILL_UNBOUND.value)
    assert unbound == []
    # No phantom binding row for the never-bound agent.
    bindings = await skill_svc.bindings_for("my-skill")
    never = await agent_svc.get("never")
    assert all(b.agent_resource_id != never.id for b in bindings)
    await engine.dispose()


@pytest.mark.asyncio
async def test_config_dir_change_relinks_skills(tmp_path):
    """Changing an agent's config_dir re-delivers its skills: the old link is
    removed and a new one is created under <new_config_dir>/skills, with the
    binding repointed — so verify reports no drift (not a false clean)."""
    skill_svc, agent_svc, _, _, engine = await _setup(tmp_path)
    _, old_skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    old_link = old_skill_dir / "my-skill"
    assert old_link.exists()

    new_config_dir = tmp_path / "moved-cfg"
    new_config_dir.mkdir()
    await agent_svc.update_config_dir(name="cur", new_config_dir=str(new_config_dir), actor="cli")

    new_link = new_config_dir / "skills" / "my-skill"
    assert not old_link.exists(), "old link should be torn down"
    assert new_link.exists() and (new_link / "SKILL.md").is_file()
    # Binding repointed to the new path → verify finds no drift.
    report = await skill_svc.verify()
    assert report.entries == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_config_dir_change_repoints_binding_even_if_new_target_exists(tmp_path):
    """Regression: when something already sits at the new <config_dir>/skills/
    <name> (e.g. a prior partial run), relink must still repoint the binding row
    to the new path instead of dropping it — a dropped row would dangle at the
    deleted old path and verify would report a false MISSING_LINK forever."""
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    _, old_skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    old_link = old_skill_dir / "my-skill"
    assert old_link.exists()

    new_config_dir = tmp_path / "moved-cfg"
    new_config_dir.mkdir()
    new_skills = new_config_dir / "skills"
    new_skills.mkdir()
    # Pre-create a correct link at the new target via the same engine the app uses.
    skill_svc._sync.make_directory_link(
        target=store.paths_for("my-skill").folder, link=new_skills / "my-skill"
    )

    await agent_svc.update_config_dir(name="cur", new_config_dir=str(new_config_dir), actor="cli")

    bindings = await skill_svc.bindings_for("my-skill")
    assert len(bindings) == 1
    # Row repointed to the new path (not dangling at the removed old path).
    assert bindings[0].last_link_path == str(new_skills / "my-skill")
    assert not old_link.exists()
    # Repointed to a correct link → no drift.
    report = await skill_svc.verify()
    assert report.entries == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_config_dir_change_does_not_clobber_foreign_content_at_new_target(tmp_path):
    """Data-loss guard: if FOREIGN content (not a Coffer link) already occupies
    the new <config_dir>/skills/<name>, relink must NOT claim it as the link
    (no copy_fallback mislabel) and a later teardown must NOT delete it."""
    skill_svc, agent_svc, _, _, engine = await _setup(tmp_path)
    await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")

    new_config_dir = tmp_path / "moved-cfg"
    new_config_dir.mkdir()
    new_skills = new_config_dir / "skills"
    new_skills.mkdir()
    foreign = new_skills / "my-skill"
    foreign.mkdir()
    (foreign / "important.txt").write_text("precious user data")

    await agent_svc.update_config_dir(name="cur", new_config_dir=str(new_config_dir), actor="cli")

    # Foreign content untouched and NOT mislabeled as a Coffer copy-fallback.
    assert (foreign / "important.txt").read_text() == "precious user data"
    bindings = await skill_svc.bindings_for("my-skill")
    assert len(bindings) == 1
    assert bindings[0].link_mode is None
    # verify surfaces the conflict rather than reporting a false clean.
    report = await skill_svc.verify()
    assert report.entries
    # Disabling must NOT delete the user's directory (the data-loss path).
    await skill_svc.disable_for(skill_name="my-skill", agent_name="cur", actor="cli")
    assert (foreign / "important.txt").read_text() == "precious user data"
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="005-skill-manager",
    scenario="re-import a skill with overwrite replaces it",
)
async def test_reimport_overwrite_replaces_and_preserves_bindings(tmp_path):
    """Re-importing with overwrite=True replaces master content + refreshes
    version_hash while preserving the Resource row, per-agent binding, and
    the delivered symlink; re-importing without overwrite still raises
    ResourceAlreadyExists."""
    from coffer.domain.errors import ResourceAlreadyExists

    skill_svc, agent_svc, audit, store, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")

    # --- initial import ---
    src_v1 = tmp_path / "src_v1"
    _write_skill_folder(src_v1, name="my-skill", body="version one")
    r1 = await skill_svc.import_local(path=str(src_v1), actor="cli")
    original_id = r1.id

    # import auto-binds — symlink must exist
    link = skill_dir / "my-skill"
    assert link.exists(), "symlink should be delivered on initial import"

    # sanity: re-import WITHOUT overwrite raises ResourceAlreadyExists
    with pytest.raises(ResourceAlreadyExists):
        await skill_svc.import_local(path=str(src_v1), actor="cli")

    # --- re-import with different content and overwrite=True ---
    src_v2 = tmp_path / "src_v2"
    _write_skill_folder(src_v2, name="my-skill", body="version two")
    r2 = await skill_svc.import_local(path=str(src_v2), actor="cli", overwrite=True)

    # (a) master folder content is the new content
    master_skill_md = store.paths_for("my-skill").skill_md
    assert "version two" in master_skill_md.read_text(encoding="utf-8")

    # (b) version_hash changed
    assert r2.config["version_hash"] != r1.config["version_hash"]

    # (c) per-agent binding still exists (Resource row preserved — same id)
    assert r2.id == original_id
    bindings = await skill_svc.bindings_for("my-skill")
    agent_resource = await agent_svc.get("cur")
    assert any(b.agent_resource_id == agent_resource.id for b in bindings)

    # (d) delivered symlink still resolves to the master (content updated in place)
    assert link.exists(), "symlink must still exist after overwrite"
    assert (link / "SKILL.md").is_file()
    assert "version two" in (link / "SKILL.md").read_text(encoding="utf-8")

    # (e) SKILL_UPDATED audit row was recorded
    updated_events = await audit.query(event_type=AuditEventType.SKILL_UPDATED.value)
    assert len(updated_events) == 1

    await engine.dispose()
