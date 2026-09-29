"""SkillService end-to-end integration (DB + filesystem + sync engine).

Covers import / delivery / reclaim / verify / repair / remove + the
cross-kind cleanup hooks. Delivery is the ``skill_link`` reconcile target,
driven the way the composition root drives it (``tests/support/skills``).
"""

from __future__ import annotations

import os
import pathlib
import textwrap

import pytest

from coffer.application.agent.service import AgentService
from coffer.application.skill import drift_view
from coffer.application.skill.service import SkillService
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import SkillValidationError
from coffer.domain.reconcile import Disposition, Outcome, Trigger
from coffer.domain.resource import Resource
from coffer.domain.skill.drift import DriftKind, DriftReport
from coffer.infrastructure.skill.master_store import MasterStore
from tests.support.skills import SkillGraph, build_skill_graph


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
    """The skill + agent graph wired like the composition root, with the
    ``skill_link`` reconcile target every front door asks for a pass."""
    graph = await build_skill_graph(tmp_path)
    return graph.skills, graph.agents, graph.audit, graph.store, graph


async def _verify(graph: SkillGraph) -> DriftReport:
    return await drift_view.verify(graph.skills, graph.reconciler)


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
    skill_svc, _, audit, store, graph = await _setup(tmp_path)
    src = tmp_path / "src"
    _write_skill_folder(src, name="hello-world")
    r = await skill_svc.import_local(path=str(src), actor="cli")
    assert r.kind == "skill"
    assert r.name == "hello-world"
    assert store.paths_for("hello-world").skill_md.is_file()
    audited = await audit.query(event_type=AuditEventType.SKILL_IMPORTED.value)
    assert len(audited) == 1
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="reject import of an invalid skill folder")
async def test_import_rejects_invalid_frontmatter(tmp_path):
    skill_svc, _, _, store, graph = await _setup(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text("no frontmatter")
    with pytest.raises(SkillValidationError):
        await skill_svc.import_local(path=str(src), actor="cli")
    assert not store.root.exists() or not any(store.root.iterdir())
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="reject import containing path-escape symlinks"
)
async def test_import_rejects_path_escape_symlink(tmp_path):
    skill_svc, _, _, _, graph = await _setup(tmp_path)
    src = tmp_path / "src"
    _write_skill_folder(src, name="x")
    outside = tmp_path / "secret"
    outside.write_text("secret")
    os.symlink(outside, src / "ev")
    with pytest.raises(SkillValidationError):
        await skill_svc.import_local(path=str(src), actor="cli")
    await graph.dispose()


# ----- delivery / reclaim -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="deliver a skill to a registered agent")
async def test_enable_creates_link(tmp_path):
    skill_svc, agent_svc, _, _, graph = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    # import auto-binds; verify the link exists at the agent's skill_dir.
    target = skill_dir / "my-skill"
    assert target.exists()
    assert (target / "SKILL.md").is_file()
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="reclaim a skill from an agent")
async def test_disable_removes_link_keeps_master(tmp_path):
    skill_svc, agent_svc, audit, store, graph = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    target = skill_dir / "my-skill"
    assert target.exists()
    # Switching the skill off is what stops delivering it; the pass reclaims.
    await skill_svc._rs.set_enabled(await _uid(skill_svc, "skill", "my-skill"), False, actor="cli")
    assert not target.exists()
    assert store.paths_for("my-skill").folder.is_dir()
    [unbound] = await audit.query(event_type=AuditEventType.SKILL_UNBOUND.value)
    assert (unbound.resource_name, unbound.details["agent"]) == ("my-skill", "cur")
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="deliver one skill to multiple agents")
async def test_enable_for_two_agents(tmp_path):
    skill_svc, agent_svc, _, _, graph = await _setup(tmp_path)
    _, sd1 = await _register_agent(agent_svc, tmp_path, name="cur1")
    _, sd2 = await _register_agent(agent_svc, tmp_path, name="cur2", agent_type=AgentType.CODEX)
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    t1 = sd1 / "my-skill"
    t2 = sd2 / "my-skill"
    assert t1.is_dir() and t2.is_dir()
    assert (t1 / "SKILL.md").read_bytes() == (t2 / "SKILL.md").read_bytes()
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="refuse to overwrite a non-Coffer target")
async def test_refuse_to_overwrite_non_coffer_target(tmp_path):
    skill_svc, agent_svc, _, _, graph = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    # Pre-place a foreign directory at the would-be link path.
    link = skill_dir / "my-skill"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.mkdir()
    (link / "stub").write_text("foreign")
    # The delivery pass the import asks for leaves the foreign dir alone.
    await skill_svc.import_local(path=str(src), actor="cli")
    assert (link / "stub").read_text() == "foreign"
    # It is a BLOCKED item, and even a person applying it by hand (MANUAL)
    # does not make the policy clobber it.
    [result] = (await graph.plan()).results
    assert result.change.decision.disposition is Disposition.BLOCKED
    assert result.change.decision.reason_code == "foreign_content"
    applied = await graph.reconciler.apply([result.change.id], actor="cli")
    assert [r.outcome for r in applied.results] == [Outcome.PLANNED]
    assert (link / "stub").read_text() == "foreign"
    assert not list(skill_dir.glob("my-skill.coffer-backup-*"))
    await graph.dispose()


# ----- verify -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="detect drift in agent skill directories")
async def test_verify_detects_missing_link(tmp_path):
    skill_svc, agent_svc, _, _, graph = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    link = skill_dir / "my-skill"
    link.unlink()
    report = await _verify(graph)
    assert any(e.kind is DriftKind.MISSING_LINK for e in report.entries)
    await graph.dispose()


# ----- removal -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="remove a skill cleans up all bindings")
async def test_remove_skill_cleans_everything(tmp_path):
    skill_svc, agent_svc, _, store, graph = await _setup(tmp_path)
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
    await graph.dispose()


@pytest.mark.asyncio
async def test_kind_agnostic_delete_skill_cleans_everything(tmp_path):
    """CODE21-001 fix-validation: going through ResourceService.delete
    (the kind-agnostic ``DELETE /api/v1/resources/skill/{name}`` path)
    must trigger the awaited on_delete hook BEFORE the row is removed,
    so symlinks AND the master folder are both gone — not orphaned."""
    skill_svc, agent_svc, _, store, graph = await _setup(tmp_path)
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
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="removing an agent (per spec agent-registry) cleans up its skill bindings",
)
async def test_remove_agent_cleans_its_bindings(tmp_path):
    skill_svc, agent_svc, _, store, graph = await _setup(tmp_path)
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
    await graph.dispose()


# ----- TEST21-008: agent delete cascade through ResourceService.delete -----


@pytest.mark.asyncio
async def test_agent_delete_via_resource_service_triggers_skill_cleanup(tmp_path):
    """End-to-end on_delete hook coverage (not a direct cleanup call).

    Going through ``ResourceService.delete`` (which is what the agent HTTP
    surface and ``AgentService.remove`` both call) must run the awaited
    on_delete hook BEFORE the agent row vanishes, so per-agent symlinks
    are torn down and binding rows are removed without orphaning.
    """
    skill_svc, agent_svc, _, store, graph = await _setup(tmp_path)
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
    await graph.dispose()


# ----- TEST21-010: drift kinds besides MISSING_LINK -----


@pytest.mark.asyncio
async def test_verify_detects_replaced_with_regular(tmp_path):
    """Drift kind REPLACED_WITH_REGULAR: link path is a plain dir, not a symlink."""
    skill_svc, agent_svc, _, _, graph = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    link = skill_dir / "my-skill"
    # Replace the symlink with a regular directory.
    link.unlink()
    link.mkdir()
    (link / "foo").write_text("not from coffer")
    report = await _verify(graph)
    assert any(e.kind is DriftKind.REPLACED_WITH_REGULAR for e in report.entries)
    await graph.dispose()


@pytest.mark.asyncio
async def test_verify_detects_tampered_link(tmp_path):
    """Drift kind TAMPERED_LINK: symlink points somewhere other than master."""
    skill_svc, agent_svc, _, _, graph = await _setup(tmp_path)
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
    report = await _verify(graph)
    assert any(e.kind is DriftKind.TAMPERED_LINK for e in report.entries)
    await graph.dispose()


@pytest.mark.asyncio
async def test_verify_detects_missing_master(tmp_path):
    """Drift kind MISSING_MASTER: master folder has been deleted."""
    skill_svc, agent_svc, _, store, graph = await _setup(tmp_path)
    _, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    # Verify the link exists, then nuke the master folder out from under it.
    link = skill_dir / "my-skill"
    assert link.exists()
    import shutil

    shutil.rmtree(store.paths_for("my-skill").folder)
    report = await _verify(graph)
    assert any(e.kind is DriftKind.MISSING_MASTER for e in report.entries)
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="audit skill lifecycle")
async def test_audit_skill_lifecycle(tmp_path):
    skill_svc, _, audit, _, graph = await _setup(tmp_path)
    src = tmp_path / "src"
    _write_skill_folder(src, name="aud")
    await skill_svc.import_local(path=str(src), actor="cli")
    await skill_svc.remove(uid=await _uid(skill_svc, "skill", "aud"), actor="cli")
    imported = await audit.query(event_type=AuditEventType.SKILL_IMPORTED.value)
    deleted = await audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
    assert len(imported) == 1 and len(deleted) == 1
    await graph.dispose()


@pytest.mark.asyncio
async def test_config_dir_change_relinks_skills(tmp_path):
    """Changing an agent's config_dir re-delivers its skills: the old link is
    removed and a new one is created under <new_config_dir>/skills, with the
    binding repointed — so verify reports no drift (not a false clean)."""
    skill_svc, agent_svc, _, _, graph = await _setup(tmp_path)
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
    report = await _verify(graph)
    assert report.entries == []
    await graph.dispose()


@pytest.mark.asyncio
async def test_config_dir_change_repoints_binding_even_if_new_target_exists(tmp_path):
    """Regression: when something already sits at the new <config_dir>/skills/
    <name> (e.g. a prior partial run), relink must still repoint the binding row
    to the new path instead of dropping it — a dropped row would dangle at the
    deleted old path and verify would report a false MISSING_LINK forever."""
    skill_svc, agent_svc, _, store, graph = await _setup(tmp_path)
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
    report = await _verify(graph)
    assert report.entries == []
    await graph.dispose()


@pytest.mark.asyncio
async def test_config_dir_change_does_not_clobber_foreign_content_at_new_target(tmp_path):
    """Data-loss guard: if FOREIGN content (not a Coffer link) already occupies
    the new <config_dir>/skills/<name>, relink must NOT claim it as the link
    (the move is blocked) and a later reclaim must NOT delete it."""
    skill_svc, agent_svc, _, _, graph = await _setup(tmp_path)
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

    # Foreign content untouched: the move is blocked, not forced.
    assert (foreign / "important.txt").read_text() == "precious user data"
    [result] = (await graph.plan()).results
    assert result.change.decision.reason_code == "foreign_content"
    # verify surfaces the conflict rather than reporting a false clean.
    report = await _verify(graph)
    assert [e.kind for e in report.entries] == [DriftKind.REPLACED_WITH_REGULAR]
    # Disabling must NOT delete the user's directory (the data-loss path).
    await skill_svc._rs.set_enabled(await _uid(skill_svc, "skill", "my-skill"), False, actor="cli")
    assert (foreign / "important.txt").read_text() == "precious user data"
    await graph.dispose()


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

    skill_svc, agent_svc, audit, store, graph = await _setup(tmp_path)
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

    await graph.dispose()


@pytest.mark.asyncio
async def test_reimport_overwrite_registers_orphan_master(tmp_path):
    """An orphan master folder (content on disk, no Resource row —
    DriftKind.ORPHAN_MASTER) plus overwrite must REGISTER the row rather than
    crash on update_config's missing-row lookup."""
    skill_svc, _agent_svc, audit, store, graph = await _setup(tmp_path)

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

    await graph.dispose()


# ----- repair ("Repair repairable drift from master") -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="opt-in repair re-delivers repairable drift from master",
)
async def test_repair_redelivers_repairable_drift_and_leaves_foreign(tmp_path):
    """Repair (``verify --fix``) re-delivers MISSING_LINK + TAMPERED_LINK, leaves
    REPLACED_WITH_REGULAR + MISSING_MASTER in the residual report, and records
    a SKILL_DRIFT_REMEDIATED audit row for each repaired entry."""
    import shutil

    skill_svc, agent_svc, audit, store, graph = await _setup(tmp_path)
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
    pre_report = await _verify(graph)
    pre_kinds = {e.kind for e in pre_report.entries}
    from coffer.domain.skill.drift import DriftKind

    assert DriftKind.MISSING_LINK in pre_kinds
    assert DriftKind.TAMPERED_LINK in pre_kinds
    assert DriftKind.REPLACED_WITH_REGULAR in pre_kinds
    assert DriftKind.MISSING_MASTER in pre_kinds

    # --- run repair ---
    result = await drift_view.repair(skill_svc, graph.reconciler, actor="test")

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

    # A SKILL_DRIFT_REMEDIATED audit row was recorded for each repaired entry,
    # under the person who asked.
    remediated_events = await audit.query(event_type=AuditEventType.SKILL_DRIFT_REMEDIATED.value)
    assert len(remediated_events) == 2  # one per repaired skill
    assert {ev.actor for ev in remediated_events} == {"test"}
    remediated_skill_names = {ev.resource_name for ev in remediated_events}
    assert "s-missing-link" in remediated_skill_names
    assert "s-tampered" in remediated_skill_names

    await graph.dispose()


# ----- boot pass (spec-boot-heal) -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="skill drift self-heals at daemon boot")
@pytest.mark.acceptance(
    spec="skill-manager", scenario="boot heal leaves unsafe drift for a human to find"
)
async def test_boot_heal_repairs_missing_link_and_leaves_foreign_dir(tmp_path):
    """The boot pass is the same ``skill_link`` target run from a different
    trigger (daemon startup instead of a person asking): it re-delivers a
    missing link, leaves foreign content untouched and reported, and audits
    the repair as the system rather than a person."""
    skill_svc, agent_svc, audit, store, graph = await _setup(tmp_path)
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

    report = await graph.run(Trigger.BOOT)
    by_code = {r.change.decision.reason_code: r for r in report.results}

    # The missing link is repaired, pointing back at master.
    master_missing = store.paths_for("s-missing").folder
    assert link_missing.exists(), "MISSING_LINK must self-heal at boot"
    assert link_missing.resolve() == master_missing.resolve()
    assert by_code["missing_link"].outcome is Outcome.APPLIED

    # The foreign directory is completely untouched — never auto-repaired, and
    # reported with a sentence a person can act on.
    assert link_foreign.is_dir() and not link_foreign.is_symlink()
    assert foreign_sentinel.read_text() == "user data — must not be touched"
    blocked = by_code["foreign_content"]
    assert blocked.outcome is Outcome.PLANNED
    assert str(link_foreign) in blocked.change.decision.reason

    # A second verify pass confirms the residual drift is exactly the foreign one.
    residual = await _verify(graph)
    residual_kinds = {e.kind for e in residual.entries}
    assert DriftKind.REPLACED_WITH_REGULAR in residual_kinds
    assert DriftKind.MISSING_LINK not in residual_kinds

    # The repair is audited once, as the system, not a person.
    remediated_events = await audit.query(event_type=AuditEventType.SKILL_DRIFT_REMEDIATED.value)
    assert len(remediated_events) == 1
    assert remediated_events[0].resource_name == "s-missing"
    assert remediated_events[0].actor == "system"

    await graph.dispose()


# ----- a fixed name, and a title (ADR names-visible-to-agents-are-fixed) -----


def _resource_client(skill_svc: SkillService):
    """The kind-agnostic resource routes, served by this test's ResourceService —
    the same PATCH a person's edit reaches through the CLI or the web UI."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from coffer.surfaces.http import errors as err_handlers
    from coffer.surfaces.http.auth import set_active_token
    from coffer.surfaces.http.dependencies import get_resource_service
    from coffer.surfaces.http.resource_routes import router as resource_router

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(resource_router)
    app.dependency_overrides[get_resource_service] = lambda: skill_svc._rs
    set_active_token("test-token")
    return AsyncClient(
        transport=ASGITransport(app),
        base_url="http://t",
        headers={"X-Coffer-Token": "test-token"},
    )


def _disk_state(store: MasterStore, skill_dir: pathlib.Path, name: str) -> dict[str, object]:
    """Everything on disk a skill's name is written into, byte for byte."""
    master = store.paths_for(name).folder
    link = skill_dir / name
    return {
        "files": {
            str(p.relative_to(master)): p.read_bytes()
            for p in sorted(master.rglob("*"))
            if p.is_file()
        },
        "link_is_symlink": link.is_symlink(),
        "link_resolves_to": link.resolve(),
    }


async def _deliver_before(tmp_path: pathlib.Path):
    """An imported skill ``before``, delivered to a registered agent, whose
    SKILL.md carries a comment, another frontmatter field and a body."""
    skill_svc, agent_svc, audit, store, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text(
        "---\n"
        "# a comment the user wrote\n"
        "name: before\n"
        "description: A test skill named before.\n"
        "license: MIT\n"
        "---\n\n"
        "the body\n",
        encoding="utf-8",
    )
    skill = await skill_svc.import_local(path=str(src), actor="cli")
    assert (skill_dir / "before").exists(), "precondition: the skill is delivered"
    return skill_svc, audit, store, graph, agent, skill_dir, skill


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="refuse changing a registered skill's name")
@pytest.mark.acceptance(spec="resource-framework", scenario="a fixed name refuses a rename")
async def test_a_skill_name_change_is_refused_and_moves_nothing(tmp_path):
    skill_svc, audit, store, graph, _agent, skill_dir, skill = await _deliver_before(tmp_path)
    disk_before = _disk_state(store, skill_dir, "before")
    trail_before = await audit.query(resource=skill)
    binding_before = (await skill_svc.bindings_for(skill.uid))[0]

    async with _resource_client(skill_svc) as c:
        r = await c.patch(f"/api/v1/resources/{skill.uid}", json={"name": "after"})

    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["code"] == "NAME_IMMUTABLE"
    # The message names the way to a new name and what it costs.
    assert "delete it and register it again" in error["message"]
    for reset in ("enabled flag", "scope", "deliveries"):
        assert reset in error["message"]

    # The service refuses it too, whatever surface calls it.
    from coffer.domain.errors import NameImmutable

    with pytest.raises(NameImmutable):
        await skill_svc._rs.rename(skill.uid, "after", actor="cli")

    # Row, master folder, SKILL.md `name: before` and the delivered link are
    # exactly as they were; nothing exists under the new name.
    assert (await skill_svc.get_skill(skill.uid)).name == "before"
    assert _disk_state(store, skill_dir, "before") == disk_before
    assert "name: before" in store.paths_for("before").skill_md.read_text(encoding="utf-8")
    assert not store.paths_for("after").folder.exists()
    assert not (skill_dir / "after").exists()
    binding_after = (await skill_svc.bindings_for(skill.uid))[0]
    assert binding_after == binding_before
    assert (await _verify(graph)).entries == []
    # Nothing was audited.
    assert await audit.query(resource=skill) == trail_before
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="a skill's title is edited without touching disk"
)
async def test_a_skill_title_is_edited_without_touching_disk(tmp_path):
    skill_svc, _audit, store, graph, _agent, skill_dir, skill = await _deliver_before(tmp_path)
    disk_before = _disk_state(store, skill_dir, "before")
    hash_before = skill.config["version_hash"]

    async with _resource_client(skill_svc) as c:
        r = await c.patch(f"/api/v1/resources/{skill.uid}", json={"title": "Release checklist"})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "before"
        assert r.json()["title"] == "Release checklist"
        listed = (await c.get("/api/v1/resources", params={"kind": "skill"})).json()
    assert [(row["name"], row["title"]) for row in listed["resources"]] == [
        ("before", "Release checklist")
    ]

    # The skill's own read carries both, and the title went nowhere near disk.
    row = await skill_svc.get_skill(skill.uid)
    assert (row.name, row.title) == ("before", "Release checklist")
    assert row.config["version_hash"] == hash_before
    assert _disk_state(store, skill_dir, "before") == disk_before
    assert "Release checklist" not in store.paths_for("before").skill_md.read_text(encoding="utf-8")
    assert (await _verify(graph)).entries == []
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="a refused name change leaves the master folder where it is",
)
async def test_a_refused_name_change_then_a_title_leaves_the_master_folder(tmp_path):
    skill_svc, _audit, store, graph, agent, skill_dir, skill = await _deliver_before(tmp_path)
    skill_md_before = store.paths_for("before").skill_md.read_bytes()
    binding_before = (await skill_svc.bindings_for(skill.uid))[0]

    async with _resource_client(skill_svc) as c:
        refused = await c.patch(f"/api/v1/resources/{skill.uid}", json={"name": "after"})
        titled = await c.patch(f"/api/v1/resources/{skill.uid}", json={"title": "After"})
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "NAME_IMMUTABLE"
    assert titled.status_code == 200, titled.text

    master = store.paths_for("before").folder
    link = skill_dir / "before"
    assert master.is_dir()
    assert link.exists() and link.resolve() == master.resolve()
    # The same binding row still records the delivery.
    binding_after = (await skill_svc.bindings_for(skill.uid))[0]
    assert binding_after.skill_resource_id == binding_before.skill_resource_id
    assert binding_after.agent_resource_id == agent.id
    assert binding_after.enabled
    assert binding_after.last_link_path == binding_before.last_link_path
    # SKILL.md — comments, other fields, body — and the hash are unchanged.
    assert store.paths_for("before").skill_md.read_bytes() == skill_md_before
    assert (await skill_svc.get_skill(skill.uid)).config["version_hash"] == skill.config[
        "version_hash"
    ]
    assert not store.paths_for("after").folder.exists()
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="refuse a skill name its own SKILL.md could not carry",
)
async def test_import_refuses_a_frontmatter_name_its_own_skill_md_could_not_carry(tmp_path):
    """The framework's name rule is a superset of the frontmatter's.

    ``My.Skill`` matches ``^[a-zA-Z0-9_.-]{1,64}$`` and is a fine directory
    name, so nothing outside the kind would stop it — and Coffer would then
    hold a skill its own importer rejects.
    """
    skill_svc, _agent_svc, _, store, graph = await _setup(tmp_path)

    for illegal in ("My.Skill", "MySkill", "-leading"):
        src = tmp_path / f"src-{illegal}"
        _write_skill_folder(src, name=illegal)
        with pytest.raises(SkillValidationError):
            await skill_svc.import_local(path=str(src), actor="cli")
        assert not store.paths_for("placeholder").folder.parent.joinpath(illegal).exists()

    assert await skill_svc._rs.list(kind="skill") == []
    await graph.dispose()


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

    skill_svc, _, _, _, graph = await _setup(tmp_path)
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
    await graph.dispose()


# ----- copy fallback -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="fall back to a copy where a directory link cannot be made"
)
async def test_delivery_falls_back_to_a_copy_without_links(tmp_path, monkeypatch):
    """No symlink and no junction on this filesystem: deliver a real copy.

    Drives the real ``make_directory_link`` down the platform's Windows branch with both
    link primitives failing — the FAT32 / network-share case — rather than
    faking the engine.
    """
    import subprocess
    import types

    from coffer.domain.skill.binding import LinkMode
    from coffer.infrastructure.platform import HostOs
    from coffer.infrastructure.platform import links as platform_links

    skill_svc, agent_svc, audit, store, graph = await _setup(tmp_path)
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
        m.setattr(platform_links, "host_os", lambda: HostOs.WINDOWS)
        m.setattr(platform_links, "os", _NoLinkOs())
        m.setattr(
            platform_links,
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
    assert (await _verify(graph)).entries == []
    await graph.dispose()
