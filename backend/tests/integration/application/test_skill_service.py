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

    def _agent_skill_dir(r: Resource):
        cfg = AgentConfig.model_validate(r.config)
        return cfg.resolved_skill_dir()

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
    )

    agent_svc = AgentService(
        resource_service=rs,
        audit=audit,
        on_config_dir_changed=skill_svc.relink_for_agent,
    )

    # CODE21-001 made the agent on_delete hook awaited (not fire-and-forget)
    # so cleanup happens BEFORE the agent row vanishes; mirror that here so
    # the test wiring matches the composition root.
    async def _agent_on_delete(agent: Resource):
        await skill_svc.cleanup_bindings_for_agent(agent)

    placeholder_kinds["agent"] = make_agent_kind(on_delete=_agent_on_delete)
    placeholder_kinds["skill"] = make_skill_kind(
        skill_svc.cleanup_bindings_for_skill,
        skill_svc.move_master_folder,
    )

    return skill_svc, agent_svc, audit, master_store, engine


async def _uid(skill_svc: SkillService, kind: str, name: str) -> str:
    """Resolve a LABEL to the uid everything inside the daemon addresses by.

    The same one-shot resolution the CLI does at its front door
    (ADR resource-identity-is-an-immutable-uid): a test states what it means in
    the names a person would type, and converts once.
    """
    return (await skill_svc._rs.get_by_name(kind, name)).uid


async def _by_name(skill_svc: SkillService, name: str) -> Resource:
    """Resolve a skill LABEL to its row.

    The one-shot resolution a surface does at its front door
    (ADR resource-identity-is-an-immutable-uid): a test states what it means in
    the name a person would type, and converts once.
    """
    return await skill_svc._rs.get_by_name("skill", name)


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
@pytest.mark.acceptance(spec="skill-manager", scenario="import a valid local skill folder")
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
@pytest.mark.acceptance(spec="skill-manager", scenario="reject import of an invalid skill folder")
async def test_import_rejects_invalid_frontmatter(tmp_path):
    skill_svc, _, _, store, engine = await _setup(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text("no frontmatter")
    with pytest.raises(SkillValidationError):
        await skill_svc.import_local(path=str(src), actor="cli")
    assert not store.root.exists() or not any(store.root.iterdir())
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="reject import containing path-escape symlinks"
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


# ----- delivery / reclaim -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="deliver a skill to a registered agent")
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
@pytest.mark.acceptance(spec="skill-manager", scenario="reclaim a skill from an agent")
async def test_disable_removes_link_keeps_master(tmp_path):
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    target = skill_dir / "my-skill"
    assert target.exists()
    await skill_svc.disable_for(
        skill_uid=await _uid(skill_svc, "skill", "my-skill"),
        agent_uid=await _uid(skill_svc, "agent", "cur"),
        actor="cli",
    )
    assert not target.exists()
    assert store.paths_for("my-skill").folder.is_dir()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="deliver one skill to multiple agents")
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
@pytest.mark.acceptance(spec="skill-manager", scenario="refuse to overwrite a non-Coffer target")
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
    skill_uid = await _uid(skill_svc, "skill", "my-skill")
    agent_uid = await _uid(skill_svc, "agent", "cur")
    with pytest.raises(TargetConflict):
        await skill_svc.enable_for(
            skill_uid=skill_uid, agent_uid=agent_uid, force=False, actor="cli"
        )
    # With force, the foreign target is backed up and link is created.
    binding = await skill_svc.enable_for(
        skill_uid=skill_uid, agent_uid=agent_uid, force=True, actor="cli"
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
@pytest.mark.acceptance(spec="skill-manager", scenario="detect drift in agent skill directories")
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
@pytest.mark.acceptance(spec="skill-manager", scenario="remove a skill cleans up all bindings")
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
    await skill_svc.remove(uid=await _uid(skill_svc, "skill", "my-skill"), actor="cli")
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
    await skill_svc._rs.delete(await _uid(skill_svc, "skill", "my-skill"), actor="cli")
    # Symlink AND master folder must be gone before the row was deleted.
    assert not t1.exists()
    assert not store.paths_for("my-skill").folder.exists()
    assert (await skill_svc.list_skills()) == []
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="removing an agent (per spec agent-registry) cleans up its skill bindings",
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
    await skill_svc.cleanup_bindings_for_agent(a1)
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
    await agent_svc.remove(uid=(await skill_svc._rs.get_by_name("agent", "cur1")).uid, actor="cli")

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
@pytest.mark.acceptance(spec="skill-manager", scenario="audit skill lifecycle")
async def test_audit_skill_lifecycle(tmp_path):
    skill_svc, _, audit, _, engine = await _setup(tmp_path)
    src = tmp_path / "src"
    _write_skill_folder(src, name="aud")
    await skill_svc.import_local(path=str(src), actor="cli")
    await skill_svc.remove(uid=await _uid(skill_svc, "skill", "aud"), actor="cli")
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

    binding = await skill_svc.disable_for(
        skill_uid=await _uid(skill_svc, "skill", "my-skill"),
        agent_uid=await _uid(skill_svc, "agent", "never"),
        actor="cli",
    )
    assert binding.enabled is False
    # No SKILL_UNBOUND event was recorded (nothing was ever bound).
    unbound = await audit.query(event_type=AuditEventType.SKILL_UNBOUND.value)
    assert unbound == []
    # No phantom binding row for the never-bound agent.
    bindings = await skill_svc.bindings_for(await _uid(skill_svc, "skill", "my-skill"))
    never = await skill_svc._rs.get_by_name("agent", "never")
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
    await agent_svc.update_config_dir(
        uid=await _uid(skill_svc, "agent", "cur"),
        new_config_dir=str(new_config_dir),
        actor="cli",
    )

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

    await agent_svc.update_config_dir(
        uid=await _uid(skill_svc, "agent", "cur"),
        new_config_dir=str(new_config_dir),
        actor="cli",
    )

    bindings = await skill_svc.bindings_for(await _uid(skill_svc, "skill", "my-skill"))
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

    await agent_svc.update_config_dir(
        uid=await _uid(skill_svc, "agent", "cur"),
        new_config_dir=str(new_config_dir),
        actor="cli",
    )

    # Foreign content untouched and NOT mislabeled as a Coffer copy-fallback.
    assert (foreign / "important.txt").read_text() == "precious user data"
    bindings = await skill_svc.bindings_for(await _uid(skill_svc, "skill", "my-skill"))
    assert len(bindings) == 1
    assert bindings[0].link_mode is None
    # verify surfaces the conflict rather than reporting a false clean.
    report = await skill_svc.verify()
    assert report.entries
    # Disabling must NOT delete the user's directory (the data-loss path).
    await skill_svc.disable_for(
        skill_uid=await _uid(skill_svc, "skill", "my-skill"),
        agent_uid=await _uid(skill_svc, "agent", "cur"),
        actor="cli",
    )
    assert (foreign / "important.txt").read_text() == "precious user data"
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
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
    # ...and so is its identity: a re-import is an update of the same resource.
    assert r2.uid == r1.uid
    bindings = await skill_svc.bindings_for(r2.uid)
    agent_resource = await skill_svc._rs.get_by_name("agent", "cur")
    assert any(b.agent_resource_id == agent_resource.id for b in bindings)

    # (d) delivered symlink still resolves to the master (content updated in place)
    assert link.exists(), "symlink must still exist after overwrite"
    assert (link / "SKILL.md").is_file()
    assert "version two" in (link / "SKILL.md").read_text(encoding="utf-8")

    # (e) SKILL_UPDATED audit row was recorded
    updated_events = await audit.query(event_type=AuditEventType.SKILL_UPDATED.value)
    assert len(updated_events) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_reimport_overwrite_registers_orphan_master(tmp_path):
    """An orphan master folder (content on disk, no Resource row —
    DriftKind.ORPHAN_MASTER) plus overwrite must REGISTER the row rather than
    crash on update_config's missing-row lookup."""
    skill_svc, _agent_svc, audit, store, engine = await _setup(tmp_path)

    # Create an orphan master folder directly: content on disk, no row.
    orphan_src = tmp_path / "orphan_src"
    _write_skill_folder(orphan_src, name="orphan-skill", body="stale")
    store.copy_in(src=orphan_src, name="orphan-skill", meta={"name": "orphan-skill"})
    assert store.exists("orphan-skill")
    rows = await skill_svc._rs.list(kind="skill")
    assert all(r.name != "orphan-skill" for r in rows), "no row yet — orphan state"

    # Re-import the same name with overwrite -> registers the row + swaps content.
    new_src = tmp_path / "new_src"
    _write_skill_folder(new_src, name="orphan-skill", body="fresh")
    r = await skill_svc.import_local(path=str(new_src), actor="cli", overwrite=True)

    assert r.name == "orphan-skill"
    rows2 = await skill_svc._rs.list(kind="skill")
    assert any(r2.name == "orphan-skill" for r2 in rows2), "row registered"
    assert "fresh" in store.paths_for("orphan-skill").skill_md.read_text(encoding="utf-8")
    # The orphan adoption audits as a fresh import (the passed event).
    imported = await audit.query(event_type=AuditEventType.SKILL_IMPORTED.value)
    assert len(imported) == 1

    await engine.dispose()


# ----- repair_drift (FR-015) -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="opt-in repair re-delivers repairable drift from master",
)
async def test_repair_redelivers_repairable_drift_and_leaves_foreign(tmp_path):
    """repair_drift re-delivers MISSING_LINK + TAMPERED_LINK, leaves
    REPLACED_WITH_REGULAR + MISSING_MASTER in the residual report, and records
    a SKILL_DRIFT_REMEDIATED audit row for each repaired entry."""
    import shutil

    skill_svc, agent_svc, audit, store, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")

    # Import four skills so we can induce one drift kind each.
    for skill_name in ("s-missing-link", "s-tampered", "s-foreign-dir", "s-missing-master"):
        src = tmp_path / f"src-{skill_name}"
        _write_skill_folder(src, name=skill_name)
        await skill_svc.import_local(path=str(src), actor="cli")

    # --- induce MISSING_LINK: delete the delivered symlink ---
    link_missing = skill_dir / "s-missing-link"
    assert link_missing.is_symlink()
    link_missing.unlink()

    # --- induce TAMPERED_LINK: repoint the symlink elsewhere ---
    link_tampered = skill_dir / "s-tampered"
    assert link_tampered.is_symlink()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link_tampered.unlink()
    link_tampered.symlink_to(elsewhere, target_is_directory=True)

    # --- induce REPLACED_WITH_REGULAR: swap symlink for a foreign plain dir ---
    link_foreign = skill_dir / "s-foreign-dir"
    assert link_foreign.is_symlink()
    link_foreign.unlink()
    link_foreign.mkdir()
    foreign_sentinel = link_foreign / "precious.txt"
    foreign_sentinel.write_text("user data — must not be touched")

    # --- induce MISSING_MASTER: remove the master folder ---
    link_missing_master = skill_dir / "s-missing-master"
    assert link_missing_master.exists()
    shutil.rmtree(store.paths_for("s-missing-master").folder)

    # Confirm verify sees all four drift kinds before repair.
    pre_report = await skill_svc.verify()
    pre_kinds = {e.kind for e in pre_report.entries}
    from coffer.domain.skill.drift import DriftKind

    assert DriftKind.MISSING_LINK in pre_kinds
    assert DriftKind.TAMPERED_LINK in pre_kinds
    assert DriftKind.REPLACED_WITH_REGULAR in pre_kinds
    assert DriftKind.MISSING_MASTER in pre_kinds

    # --- run repair ---
    result = await skill_svc.repair_drift(actor="test")

    # Repaired: MISSING_LINK and TAMPERED_LINK only.
    remediated_kinds = {e.kind for e in result.remediated}
    assert DriftKind.MISSING_LINK in remediated_kinds
    assert DriftKind.TAMPERED_LINK in remediated_kinds
    assert DriftKind.REPLACED_WITH_REGULAR not in remediated_kinds
    assert DriftKind.MISSING_MASTER not in remediated_kinds

    # Repaired links resolve to master again.
    master_missing = store.paths_for("s-missing-link").folder
    master_tampered = store.paths_for("s-tampered").folder
    assert link_missing.exists(), "MISSING_LINK should be re-delivered"
    assert link_missing.resolve() == master_missing.resolve()
    assert link_tampered.exists(), "TAMPERED_LINK should be re-delivered"
    assert link_tampered.resolve() == master_tampered.resolve()

    # Foreign directory is completely untouched.
    assert link_foreign.is_dir() and not link_foreign.is_symlink(), "foreign dir must remain"
    assert foreign_sentinel.read_text() == "user data — must not be touched"

    # Residual report contains the two un-repairable kinds.
    residual_kinds = {e.kind for e in result.remaining.entries}
    assert DriftKind.REPLACED_WITH_REGULAR in residual_kinds
    assert DriftKind.MISSING_MASTER in residual_kinds
    # Repaired kinds must not appear in remaining.
    assert DriftKind.MISSING_LINK not in residual_kinds
    assert DriftKind.TAMPERED_LINK not in residual_kinds

    # A SKILL_DRIFT_REMEDIATED audit row was recorded for each repaired entry.
    remediated_events = await audit.query(event_type=AuditEventType.SKILL_DRIFT_REMEDIATED.value)
    assert len(remediated_events) == 2  # one per repaired skill
    remediated_skill_names = {ev.resource_name for ev in remediated_events}
    assert "s-missing-link" in remediated_skill_names
    assert "s-tampered" in remediated_skill_names

    await engine.dispose()


# ----- boot heal (spec-boot-heal) -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="skill drift self-heals at daemon boot")
@pytest.mark.acceptance(
    spec="skill-manager", scenario="boot heal leaves unsafe drift for a human to find"
)
async def test_boot_heal_repairs_missing_link_and_leaves_foreign_dir(tmp_path):
    """The boot heal is ``repair_drift`` run from a different trigger (daemon
    startup instead of a person clicking "repair"): it must re-deliver a
    missing link, leave foreign content untouched, and audit the repair with
    an actor that names the boot heal rather than a person."""
    from coffer.application.skill.boot_reconcile import BOOT_ACTOR, SkillDriftBootHeal

    skill_svc, agent_svc, audit, store, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")

    for skill_name in ("s-missing", "s-foreign"):
        src = tmp_path / f"src-{skill_name}"
        _write_skill_folder(src, name=skill_name)
        await skill_svc.import_local(path=str(src), actor="cli")

    # --- induce MISSING_LINK while the daemon is "down" ---
    link_missing = skill_dir / "s-missing"
    assert link_missing.is_symlink()
    link_missing.unlink()

    # --- induce REPLACED_WITH_REGULAR: unsafe, must be left alone ---
    link_foreign = skill_dir / "s-foreign"
    assert link_foreign.is_symlink()
    link_foreign.unlink()
    link_foreign.mkdir()
    foreign_sentinel = link_foreign / "precious.txt"
    foreign_sentinel.write_text("user data — must not be touched")

    heal = SkillDriftBootHeal(skill_service=skill_svc)
    notes = await heal.heal()

    # The missing link is repaired, pointing back at master.
    master_missing = store.paths_for("s-missing").folder
    assert link_missing.exists(), "MISSING_LINK must self-heal at boot"
    assert link_missing.resolve() == master_missing.resolve()
    assert any("s-missing" in n and "missing_link" in n for n in notes)

    # The foreign directory is completely untouched — never auto-repaired.
    assert link_foreign.is_dir() and not link_foreign.is_symlink()
    assert foreign_sentinel.read_text() == "user data — must not be touched"
    assert any("s-foreign" in n and "replaced_with_regular" in n for n in notes), (
        "residual drift must be logged clearly enough for a human to find, now that "
        "the only other surface (the UI button) is gone"
    )

    # A second verify pass confirms the residual drift is exactly the foreign one.
    residual = await skill_svc.verify()
    residual_kinds = {e.kind for e in residual.entries}
    assert DriftKind.REPLACED_WITH_REGULAR in residual_kinds
    assert DriftKind.MISSING_LINK not in residual_kinds

    # The repair is audited with the boot heal's own actor, not a person's.
    remediated_events = await audit.query(event_type=AuditEventType.SKILL_DRIFT_REMEDIATED.value)
    assert len(remediated_events) == 1
    assert remediated_events[0].resource_name == "s-missing"
    assert remediated_events[0].actor == BOOT_ACTOR == "system"

    await engine.dispose()


# ----- rename (ADR resource-identity-is-an-immutable-uid) -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="renaming a skill carries its master folder, links and frontmatter name",
)
async def test_rename_moves_master_and_redelivers_under_the_new_name(tmp_path):
    """A skill's name is a label, but it is also two directories on disk.

    Renaming must carry both: the master folder under ~/.coffer/skills/ and
    the copy delivered into the agent's own skills dir. The binding row is
    NOT carried, because it never held the name — it joins on
    ``resources.id`` — and proving that is half the point of the change.
    """
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="before", body="the body")
    skill = await skill_svc.import_local(path=str(src), actor="cli")

    old_master = store.paths_for("before").folder
    old_link = skill_dir / "before"
    assert old_master.is_dir() and old_link.exists()
    binding_before = (await skill_svc.bindings_for(skill.uid))[0]

    renamed = await skill_svc._rs.rename(skill.uid, "after", actor="cli")

    # The identity did not move; only the label did.
    assert renamed.uid == skill.uid
    assert renamed.id == skill.id
    assert renamed.name == "after"

    # Master folder followed the label, with its content.
    assert not old_master.exists()
    new_master = store.paths_for("after").folder
    assert new_master.is_dir()
    assert "the body" in (new_master / "SKILL.md").read_text(encoding="utf-8")

    # So did the delivered copy.
    new_link = skill_dir / "after"
    assert not old_link.exists()
    assert new_link.exists()
    assert new_link.resolve() == new_master.resolve()
    assert (new_link / "SKILL.md").is_file()

    # The binding survived untouched apart from the path it records: same
    # row, same two integer ids, still a live delivery.
    bindings = await skill_svc.bindings_for(renamed.uid)
    assert len(bindings) == 1
    assert bindings[0].skill_resource_id == binding_before.skill_resource_id
    assert bindings[0].agent_resource_id == agent.id
    assert bindings[0].enabled
    assert bindings[0].last_link_path == str(new_link)

    # The SKILL.md the agent reads follows too, and the two config fields that
    # describe that file follow it.
    assert "name: after" in (new_master / "SKILL.md").read_text(encoding="utf-8")
    assert renamed.config["version_hash"] != skill.config["version_hash"]
    # The name is recorded in exactly one place on the row. A config field
    # mirroring it is what migration 0098 removed.
    assert "skill_md_name" not in renamed.config

    # And nothing about the move reads as drift.
    assert (await skill_svc.verify()).entries == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_rename_keeps_the_audit_trail_as_one_history(tmp_path):
    """The trail is keyed on the resource, not on what it was called."""
    skill_svc, _, audit, _, engine = await _setup(tmp_path)
    src = tmp_path / "src"
    _write_skill_folder(src, name="before")
    skill = await skill_svc.import_local(path=str(src), actor="cli")

    renamed = await skill_svc._rs.rename(skill.uid, "after", actor="cli")

    trail = await audit.query(resource=renamed)
    events = [e.event_type for e in trail]
    assert AuditEventType.SKILL_IMPORTED.value in events, (
        "the import happened under the old name and must still be in this resource's history"
    )
    imported = next(e for e in trail if e.event_type == AuditEventType.SKILL_IMPORTED.value)
    assert imported.resource_name == "before", "each row says what it was called at the time"
    await engine.dispose()


@pytest.mark.asyncio
async def test_rename_onto_a_taken_name_moves_nothing(tmp_path):
    """A collision is refused before the hook runs — nothing on disk moves."""
    from coffer.domain.errors import ResourceAlreadyExists

    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    for name in ("mine", "theirs"):
        src = tmp_path / f"src-{name}"
        _write_skill_folder(src, name=name)
        await skill_svc.import_local(path=str(src), actor="cli")
    mine = await _by_name(skill_svc, "mine")

    with pytest.raises(ResourceAlreadyExists):
        await skill_svc._rs.rename(mine.uid, "theirs", actor="cli")

    assert (await skill_svc.get_skill(mine.uid)).name == "mine"
    assert store.paths_for("mine").folder.is_dir()
    assert store.paths_for("theirs").folder.is_dir()
    assert (skill_dir / "mine").exists() and (skill_dir / "theirs").exists()
    assert (await skill_svc.verify()).entries == []
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="renaming a skill carries its master folder, links and frontmatter name",
)
async def test_rename_aborts_when_the_master_folder_cannot_move(tmp_path):
    """An orphan master folder occupies the destination: no row answers to
    that name, so the framework's collision check passes and the hook is the
    only thing standing between the rename and a clobbered directory.

    Raising there must abort the rename with NOTHING moved — the row keeps
    its old name and both folders are where they were.
    """
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="mine")
    skill = await skill_svc.import_local(path=str(src), actor="cli")

    # A master folder on disk with no resource row behind it (the
    # ORPHAN_MASTER drift kind), sitting exactly where the rename would land.
    orphan_src = tmp_path / "orphan"
    _write_skill_folder(orphan_src, name="squatter", body="not mine to delete")
    store.copy_in(src=orphan_src, name="squatter", meta={"name": "squatter"})

    with pytest.raises(FileExistsError):
        await skill_svc._rs.rename(skill.uid, "squatter", actor="cli")

    assert (await skill_svc.get_skill(skill.uid)).name == "mine"
    assert store.paths_for("mine").folder.is_dir()
    assert (skill_dir / "mine").exists()
    assert "not mine to delete" in store.paths_for("squatter").skill_md.read_text(encoding="utf-8")
    await engine.dispose()


@pytest.mark.asyncio
async def test_rename_does_not_clobber_foreign_content_at_the_new_link_path(tmp_path):
    """Data-loss guard on the delivery half of a rename.

    Something that is not Coffer's already occupies ``<skill_dir>/<new name>``.
    The master folder still moves — the rename is about the row and its
    canonical folder — but the delivered copy is dropped rather than written
    over, and the drift is reported instead of hidden.
    """
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="before")
    skill = await skill_svc.import_local(path=str(src), actor="cli")

    foreign = skill_dir / "after"
    foreign.mkdir()
    (foreign / "important.txt").write_text("precious user data")

    renamed = await skill_svc._rs.rename(skill.uid, "after", actor="cli")

    assert renamed.name == "after"
    assert store.paths_for("after").folder.is_dir()
    # The user's directory is exactly as they left it.
    assert not foreign.is_symlink()
    assert (foreign / "important.txt").read_text() == "precious user data"
    # The binding admits it holds nothing, so verify names the real conflict
    # at the real path rather than reporting a clean delivery.
    bindings = await skill_svc.bindings_for(renamed.uid)
    assert len(bindings) == 1
    assert bindings[0].last_link_path is None
    assert bindings[0].link_mode is None
    report = await skill_svc.verify()
    assert [e.kind for e in report.entries] == [DriftKind.REPLACED_WITH_REGULAR]
    assert report.entries[0].target_path == str(foreign)
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="renaming a skill carries its master folder, links and frontmatter name",
)
async def test_rename_rewrites_only_the_frontmatter_name(tmp_path):
    """The agent product reads SKILL.md's ``name:``, so a rename must move it.

    Exactly that one line: the rest of the file — the user's comments, their
    key order, fields Coffer does not model, and the body — survives
    byte-for-byte. Re-serialising the frontmatter would have been shorter and
    would have quietly reflowed a document the user writes by hand.
    """
    skill_svc, _, _, store, engine = await _setup(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text(
        "---\n"
        "# why this skill exists\n"
        "description: A test skill named before.\n"
        "name: before\n"
        "allowed-tools: [Bash]\n"
        "license: MIT\n"
        "---\n"
        "\n"
        "Body mentioning name: before, which is prose and must not move.\n",
        encoding="utf-8",
    )
    (src / "reference.md").write_text("untouched\n", encoding="utf-8")
    skill = await skill_svc.import_local(path=str(src), actor="cli")
    before_bytes = store.paths_for("before").skill_md.read_bytes()

    renamed = await skill_svc._rs.rename(skill.uid, "after", actor="cli")

    after_bytes = store.paths_for("after").skill_md.read_bytes()
    assert after_bytes == before_bytes.replace(b"name: before\n", b"name: after\n")
    assert b"Body mentioning name: before" in after_bytes  # prose untouched
    assert (store.paths_for("after").folder / "reference.md").read_text() == "untouched\n"

    # The one config field that describes that file moved with it.
    assert "skill_md_name" not in renamed.config
    import hashlib

    assert renamed.config["version_hash"] == hashlib.sha256(after_bytes).hexdigest()
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_renamed_skill_still_validates_as_a_skill(tmp_path):
    """The round trip that matters: what Coffer wrote, Coffer can re-import.

    A rename is the one path that makes Coffer the AUTHOR of a SKILL.md rather
    than its reader, so the file it produces has to satisfy the same validator
    the importer runs.
    """
    from coffer.domain.skill.validator import ValidationOk, validate_skill_folder

    skill_svc, _, _, store, engine = await _setup(tmp_path)
    src = tmp_path / "src"
    _write_skill_folder(src, name="before")
    skill = await skill_svc.import_local(path=str(src), actor="cli")

    await skill_svc._rs.rename(skill.uid, "after", actor="cli")

    result = validate_skill_folder(store.paths_for("after").folder)
    assert isinstance(result, ValidationOk)
    assert result.frontmatter.name == "after"
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="refuse a skill name its own SKILL.md could not carry",
)
async def test_rename_to_a_framework_legal_but_frontmatter_illegal_name_is_refused(tmp_path):
    """The framework's name rule is a superset of the frontmatter's.

    ``My.Skill`` matches ``^[a-zA-Z0-9_.-]{1,64}$`` and is a fine directory
    name, so nothing outside the kind would stop it — and Coffer would then
    have written a SKILL.md its own importer rejects. The kind's
    ``validate_name`` refuses it before anything moves.
    """
    from coffer.domain.errors import ConfigValidationError

    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="before")
    skill = await skill_svc.import_local(path=str(src), actor="cli")

    for illegal in ("My.Skill", "MySkill", "-leading"):
        with pytest.raises(ConfigValidationError):
            await skill_svc._rs.rename(skill.uid, illegal, actor="cli")
        assert not store.paths_for("before").folder.parent.joinpath(illegal).exists()

    # Nothing moved: row, master folder, SKILL.md and the delivered copy.
    assert (await skill_svc.get_skill(skill.uid)).name == "before"
    assert store.paths_for("before").folder.is_dir()
    assert "name: before" in store.paths_for("before").skill_md.read_text(encoding="utf-8")
    assert (skill_dir / "before").exists()
    assert (await skill_svc.verify()).entries == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_rename_is_refused_when_the_master_has_no_frontmatter_name(tmp_path):
    """A master hand-edited into a shape the importer would reject.

    There is no ``name:`` to carry, so the rename cannot leave the row and the
    file agreeing. It refuses before anything moves rather than renaming the
    folder and leaving the file naming the old skill.
    """
    from coffer.domain.errors import SkillValidationError

    skill_svc, _, _, store, engine = await _setup(tmp_path)
    src = tmp_path / "src"
    _write_skill_folder(src, name="before")
    skill = await skill_svc.import_local(path=str(src), actor="cli")

    # Strip the frontmatter after import, the way a user editing the master
    # folder in their own editor could.
    store.paths_for("before").skill_md.write_text("no frontmatter here\n", encoding="utf-8")

    with pytest.raises(SkillValidationError):
        await skill_svc._rs.rename(skill.uid, "after", actor="cli")

    assert (await skill_svc.get_skill(skill.uid)).name == "before"
    assert store.paths_for("before").folder.is_dir()
    assert not store.paths_for("after").folder.exists()
    await engine.dispose()


@pytest.mark.asyncio
async def test_rename_puts_the_master_back_when_the_config_write_fails(tmp_path):
    """The folder moves before the config does, so the config write owns the undo.

    If it fails, the rename must still mean "nothing moved" — otherwise the row
    would keep a name no folder answers to.
    """
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="before")
    skill = await skill_svc.import_local(path=str(src), actor="cli")
    original_bytes = store.paths_for("before").skill_md.read_bytes()

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("the database said no")

    skill_svc._rs.update_config = _boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="the database said no"):
        await skill_svc._rs.rename(skill.uid, "after", actor="cli")

    # Folder back, file bytes back, row untouched, delivery intact.
    assert store.paths_for("before").folder.is_dir()
    assert not store.paths_for("after").folder.exists()
    assert store.paths_for("before").skill_md.read_bytes() == original_bytes
    assert (await skill_svc.get_skill(skill.uid)).name == "before"
    assert (skill_dir / "before").exists()
    await engine.dispose()


# ----- config schema -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="store a skill's config without restating its name"
)
async def test_skill_config_holds_provenance_and_never_the_name(tmp_path):
    """The config carries source + metadata; the name lives only on the row."""
    from pydantic import ValidationError

    from coffer.domain.errors import ConfigValidationError
    from coffer.domain.skill.config import SkillConfig

    skill_svc, _, _, _, engine = await _setup(tmp_path)
    src = tmp_path / "src"
    _write_skill_folder(src, name="provenance")
    skill = await skill_svc.import_local(path=str(src), actor="cli")

    stored = (await skill_svc.get_skill(skill.uid)).config
    assert set(stored) == {
        "source",
        "skill_md_description",
        "version_hash",
        "last_synced_from_source_at",
    }
    assert stored["source"]["type"] == "local_import"
    assert stored["source"]["original_path"] == str(src)
    assert stored["skill_md_description"] == "A test skill named provenance."
    assert stored["version_hash"]
    assert "provenance" not in {str(v) for v in stored.values() if not isinstance(v, dict)}

    # A field that restates the name is not in the schema, so it is refused —
    # both by the schema itself and by the resource write path that runs it.
    with pytest.raises(ValidationError):
        SkillConfig.model_validate({**stored, "skill_md_name": "provenance"})
    with pytest.raises(ConfigValidationError):
        await skill_svc._rs.update_config(
            skill.uid,
            {**stored, "skill_md_name": "provenance"},
            actor="cli",
            allow_lifecycle_kind=True,
        )
    # The builtin variant carries nothing but its name: even handed a path, the
    # validated config holds none.
    for source in ({"type": "builtin"}, {"type": "builtin", "original_path": "/somewhere"}):
        validated = SkillConfig.model_validate({**stored, "source": source})
        assert validated.model_dump(mode="json")["source"] == {"type": "builtin"}
    assert "skill_md_name" not in (await skill_svc.get_skill(skill.uid)).config
    await engine.dispose()


# ----- copy fallback -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="fall back to a copy where a directory link cannot be made"
)
async def test_delivery_falls_back_to_a_copy_without_links(tmp_path, monkeypatch):
    """No symlink and no junction on this filesystem: deliver a real copy.

    Drives the real ``make_directory_link`` down its Windows branch with both
    link primitives failing — the FAT32 / network-share case — rather than
    faking the engine.
    """
    import subprocess
    import types

    from coffer.domain.skill.binding import LinkMode
    from coffer.infrastructure.skill import sync_engine

    skill_svc, agent_svc, audit, store, engine = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="fat32")

    class _NoLinkOs:
        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(os, item)

        @staticmethod
        def symlink(*_a, **_k):
            raise OSError("symlinks unsupported on this filesystem")

    def _no_junction(*_a, **_k):
        raise subprocess.CalledProcessError(1, "mklink")

    src = tmp_path / "src"
    _write_skill_folder(src, name="copied", body="copied body")
    with monkeypatch.context() as m:
        m.setattr(sync_engine, "sys", types.SimpleNamespace(platform="win32"))
        m.setattr(sync_engine, "os", _NoLinkOs())
        m.setattr(
            sync_engine,
            "subprocess",
            types.SimpleNamespace(
                run=_no_junction, CalledProcessError=subprocess.CalledProcessError
            ),
        )
        skill = await skill_svc.import_local(path=str(src), actor="cli")

    delivered = skill_dir / "copied"
    assert delivered.is_dir() and not delivered.is_symlink()
    assert (delivered / "SKILL.md").read_bytes() == store.paths_for("copied").skill_md.read_bytes()

    bindings = await skill_svc.bindings_for(skill.uid)
    assert len(bindings) == 1
    assert bindings[0].link_mode is LinkMode.COPY_FALLBACK

    bound = await audit.query(event_type=AuditEventType.SKILL_BOUND.value)
    assert [e.details["mode"] for e in bound] == ["copy_fallback"]

    # A copy is the expected shape of this delivery, not drift.
    assert (await skill_svc.verify()).entries == []
    await engine.dispose()
