"""Unmanaged-skill scan / adopt / delete integration coverage.

See "List unmanaged skills in an agent's skill locations".

The graph is ``tests/support/skills`` (real sqlite + real MasterStore /
SyncEngine / WorkspaceScan over tmp_path, and the ``skill_link`` reconcile
target); the agent scan-location resolver is built the way the composition
root builds it, over a fake home for Codex's secondary location.
"""

from __future__ import annotations

import os
import pathlib
import textwrap

import pytest

from coffer.application.agent.service import AgentService
from coffer.application.skill.service import SkillService
from coffer.domain.agent.types import AgentType
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceAlreadyExists, ResourceNotFound
from coffer.domain.resource import Resource
from coffer.domain.workspace_errors import UnmanagedSkillInvalid, UnmanagedSkillNotFound
from tests.support.skills import build_skill_graph


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
    fake_home = tmp_path / "home"  # codex secondary location lives under here
    graph = await build_skill_graph(tmp_path, scan_home=fake_home)
    return graph.skills, graph.agents, graph.audit, graph.store, fake_home, graph


async def _by_name(skill_svc: SkillService, name: str) -> Resource:
    """Resolve a skill LABEL to its row.

    The one-shot resolution a surface does at its front door
    (ADR identity-is-the-uid-inside-the-file): a test states what it means in
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
    config_dir = tmp_path / f"{name}-cfg"
    config_dir.mkdir()
    agent = await agent_svc.register(
        agent_type=agent_type,
        config_dir=str(config_dir),
        actor="cli",
    )
    return agent, config_dir / "skills"


# ----- list -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="exclude managed links and system entries from the unmanaged scan",
)
async def test_list_unmanaged_valid_invalid_and_exclusions(tmp_path):
    skill_svc, agent_svc, _, _, _, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    # Managed link: import a skill — the delivery pass links it into master.
    src = tmp_path / "src"
    _write_skill_folder(src, name="managed-one")
    await skill_svc.import_local(path=str(src), actor="cli")
    assert (skill_dir / "managed-one").is_symlink()
    # Hand-placed valid folder, invalid folder (no SKILL.md), and .system.
    _write_skill_folder(skill_dir / "hand-made", name="hand-made")
    (skill_dir / "broken-skill").mkdir()
    (skill_dir / ".system").mkdir()

    views = await skill_svc.list_unmanaged(agent.uid)
    by_name = {v.name: v for v in views}
    assert set(by_name) == {"hand-made", "broken-skill"}  # managed + .system excluded
    assert by_name["hand-made"].valid is True
    assert by_name["hand-made"].reason is None
    assert by_name["hand-made"].location == "skills"
    assert by_name["hand-made"].foreign_link is False
    assert by_name["broken-skill"].valid is False
    assert by_name["broken-skill"].reason == "skill_md_missing"
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="list unmanaged skills across an agent's skill locations"
)
async def test_list_unmanaged_labels_codex_second_location(tmp_path):
    skill_svc, agent_svc, _, _, fake_home, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(
        agent_svc, tmp_path, name="cdx", agent_type=AgentType.CODEX
    )
    _write_skill_folder(skill_dir / "primary-one", name="primary-one")
    agents_dir = fake_home / ".agents" / "skills"
    _write_skill_folder(agents_dir / "secondary-one", name="secondary-one")

    views = await skill_svc.list_unmanaged(agent.uid)
    by_name = {v.name: v for v in views}
    assert by_name["primary-one"].location == "skills"
    assert by_name["secondary-one"].location == "agents_dir"
    assert by_name["secondary-one"].path == str(agents_dir / "secondary-one")
    await graph.dispose()


@pytest.mark.asyncio
async def test_list_unmanaged_flags_foreign_link(tmp_path):
    skill_svc, agent_svc, _, _, _, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    skill_dir.mkdir(parents=True, exist_ok=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, skill_dir / "foreign")

    views = await skill_svc.list_unmanaged(agent.uid)
    assert len(views) == 1
    v = views[0]
    assert v.foreign_link is True
    assert v.valid is False
    assert v.reason == "symlink points outside the master store"
    await graph.dispose()


@pytest.mark.asyncio
async def test_list_unmanaged_unknown_agent_raises(tmp_path):
    skill_svc, _, _, _, _, graph = await _setup(tmp_path)
    with pytest.raises(ResourceNotFound):
        await skill_svc.list_unmanaged("no-such-uid")
    await graph.dispose()


# ----- adopt -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="adopt an unmanaged skill into the master store"
)
async def test_adopt_happy_path(tmp_path):
    skill_svc, agent_svc, audit, store, _, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    original = skill_dir / "hand-made"
    _write_skill_folder(original, name="hand-made", body="adopt me")

    r = await skill_svc.adopt_unmanaged(
        agent_uid=agent.uid, skill_name="hand-made", location="skills", actor="cli"
    )
    assert r.kind == "skill" and r.name == "hand-made"
    # Master copy exists with the original content.
    assert "adopt me" in store.paths_for("hand-made").skill_md.read_text()
    # Original path is now a Coffer-managed symlink into master.
    assert original.is_symlink()
    assert original.resolve() == store.paths_for("hand-made").folder.resolve()
    # Binding enabled for this agent.
    bindings = await skill_svc.bindings_for(r.uid)
    assert any(b.agent_uid == agent.uid and b.enabled for b in bindings)
    # Audit trail.
    adopted = await audit.query(event_type=AuditEventType.SKILL_ADOPTED.value)
    assert len(adopted) == 1
    # And it no longer shows up as unmanaged.
    assert await skill_svc.list_unmanaged(agent.uid) == []
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="reject adopting an invalid or conflicting unmanaged skill"
)
async def test_adopt_name_conflict_leaves_original_untouched(tmp_path):
    skill_svc, agent_svc, _, _, _, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    # Register a master skill named "dup" first.
    src = tmp_path / "src"
    _write_skill_folder(src, name="dup")
    await skill_svc.import_local(path=str(src), actor="cli")
    # Hand-placed folder under a DIFFERENT folder name whose frontmatter
    # name collides with the registered skill.
    original = skill_dir / "dup-copy"
    _write_skill_folder(original, name="dup", body="local copy")

    with pytest.raises(ResourceAlreadyExists):
        await skill_svc.adopt_unmanaged(
            agent_uid=agent.uid, skill_name="dup-copy", location="skills", actor="cli"
        )
    assert original.is_dir() and not original.is_symlink()
    assert "local copy" in (original / "SKILL.md").read_text()
    await graph.dispose()


@pytest.mark.asyncio
async def test_adopt_invalid_folder_raises_and_registers_nothing(tmp_path):
    skill_svc, agent_svc, _, store, _, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    original = skill_dir / "no-md"
    original.mkdir(parents=True)
    (original / "notes.txt").write_text("not a skill")

    with pytest.raises(UnmanagedSkillInvalid) as exc:
        await skill_svc.adopt_unmanaged(
            agent_uid=agent.uid, skill_name="no-md", location="skills", actor="cli"
        )
    assert exc.value.reason == "skill_md_missing"
    assert await skill_svc.list_skills() == []
    assert not store.root.exists() or not any(store.root.iterdir())
    assert (original / "notes.txt").is_file()  # untouched
    await graph.dispose()


@pytest.mark.asyncio
async def test_adopt_foreign_link_raises(tmp_path):
    skill_svc, agent_svc, _, _, _, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    skill_dir.mkdir(parents=True, exist_ok=True)
    elsewhere = tmp_path / "elsewhere"
    _write_skill_folder(elsewhere, name="foreign")
    os.symlink(elsewhere, skill_dir / "foreign")

    with pytest.raises(UnmanagedSkillInvalid) as exc:
        await skill_svc.adopt_unmanaged(
            agent_uid=agent.uid, skill_name="foreign", location="skills", actor="cli"
        )
    assert "outside the master store" in exc.value.reason
    assert (skill_dir / "foreign").is_symlink()  # untouched
    await graph.dispose()


@pytest.mark.asyncio
async def test_adopt_from_codex_agents_dir(tmp_path):
    """Adopting from the secondary location: the original is removed there
    and the managed link is delivered to <config_dir>/skills (the delivery pass
    already succeeded for the free primary path; adoption's link is idempotent)."""
    skill_svc, agent_svc, _, store, fake_home, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(
        agent_svc, tmp_path, name="cdx", agent_type=AgentType.CODEX
    )
    agents_dir = fake_home / ".agents" / "skills"
    original = agents_dir / "side-skill"
    _write_skill_folder(original, name="side-skill")

    await skill_svc.adopt_unmanaged(
        agent_uid=agent.uid, skill_name="side-skill", location="agents_dir", actor="cli"
    )
    assert not original.exists()
    delivered = skill_dir / "side-skill"
    assert delivered.is_symlink()
    assert delivered.resolve() == store.paths_for("side-skill").folder.resolve()
    bindings = await skill_svc.bindings_for((await _by_name(skill_svc, "side-skill")).uid)
    assert any(b.agent_uid == agent.uid and b.enabled for b in bindings)
    await graph.dispose()


@pytest.mark.asyncio
async def test_adopt_unknown_raises_not_found(tmp_path):
    skill_svc, agent_svc, _, _, _, graph = await _setup(tmp_path)
    agent, _ = await _register_agent(agent_svc, tmp_path, name="cur")
    with pytest.raises(UnmanagedSkillNotFound):
        await skill_svc.adopt_unmanaged(
            agent_uid=agent.uid, skill_name="ghost", location="skills", actor="cli"
        )
    await graph.dispose()


# ----- delete -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="adopting from a disabled agent links the skill in place"
)
async def test_adopt_from_a_disabled_agent_links_in_place(tmp_path):
    """Adoption is the one write into a disabled agent: the folder was already
    there, so replacing it with the managed link changes nothing the agent sees."""
    skill_svc, agent_svc, audit, store, _, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="off")
    await skill_svc._rs.set_enabled(agent.uid, False, actor="cli")
    original = skill_dir / "kept-here"
    _write_skill_folder(original, name="kept-here", body="still mine")

    r = await skill_svc.adopt_unmanaged(
        agent_uid=agent.uid, skill_name="kept-here", location="skills", actor="cli"
    )

    assert original.is_symlink()
    assert original.resolve() == store.paths_for("kept-here").folder.resolve()
    assert "still mine" in (original / "SKILL.md").read_text()
    bindings = await skill_svc.bindings_for(r.uid)
    assert [(b.agent_uid, b.enabled) for b in bindings] == [(agent.uid, True)]
    adopted = await audit.query(event_type=AuditEventType.SKILL_ADOPTED.value)
    assert [e.resource_name for e in adopted] == ["kept-here"]
    await graph.dispose()


@pytest.mark.asyncio
async def test_a_skill_adopted_from_a_disabled_agent_is_reclaimed_then_restored(tmp_path):
    """The exception adoption makes (spec agent-registry "Switch an agent off
    with the kind-agnostic enabled flag") ends at the agent's next reconcile,
    and enabling the agent puts the skill back."""
    skill_svc, agent_svc, _, store, _, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="off")
    await skill_svc._rs.set_enabled(agent.uid, False, actor="cli")
    original = skill_dir / "kept-here"
    _write_skill_folder(original, name="kept-here", body="still mine")
    r = await skill_svc.adopt_unmanaged(
        agent_uid=agent.uid, skill_name="kept-here", location="skills", actor="cli"
    )

    await graph.run()

    assert not original.exists() and not original.is_symlink()
    bindings = await skill_svc.bindings_for(r.uid)
    assert [(b.agent_uid, b.enabled) for b in bindings] == [(agent.uid, False)]

    await skill_svc._rs.set_enabled(agent.uid, True, actor="cli")
    await graph.run()

    assert original.resolve() == store.paths_for("kept-here").folder.resolve()
    bindings = await skill_svc.bindings_for(r.uid)
    assert [(b.agent_uid, b.enabled) for b in bindings] == [(agent.uid, True)]
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="delete an unmanaged skill")
async def test_delete_unmanaged_dir(tmp_path):
    skill_svc, agent_svc, audit, _, _, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    original = skill_dir / "junk"
    _write_skill_folder(original, name="junk")

    await skill_svc.delete_unmanaged(
        agent_uid=agent.uid, skill_name="junk", location="skills", actor="cli"
    )
    assert not original.exists()
    deleted = await audit.query(event_type=AuditEventType.SKILL_UNMANAGED_DELETED.value)
    assert len(deleted) == 1
    assert deleted[0].details["agent"] == "claude-code"
    assert deleted[0].details["path"] == str(original)
    assert deleted[0].details["location"] == "skills"
    await graph.dispose()


@pytest.mark.asyncio
async def test_delete_foreign_link_unlinks_without_touching_target(tmp_path):
    skill_svc, agent_svc, _, _, _, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="cur")
    skill_dir.mkdir(parents=True, exist_ok=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "precious.txt").write_text("keep me")
    link = skill_dir / "foreign"
    os.symlink(elsewhere, link)

    await skill_svc.delete_unmanaged(
        agent_uid=agent.uid, skill_name="foreign", location="skills", actor="cli"
    )
    assert not link.is_symlink() and not link.exists()
    assert (elsewhere / "precious.txt").read_text() == "keep me"
    await graph.dispose()


@pytest.mark.asyncio
async def test_delete_unknown_raises_not_found(tmp_path):
    skill_svc, agent_svc, _, _, _, graph = await _setup(tmp_path)
    agent, _ = await _register_agent(agent_svc, tmp_path, name="cur")
    with pytest.raises(UnmanagedSkillNotFound):
        await skill_svc.delete_unmanaged(
            agent_uid=agent.uid, skill_name="ghost", location="skills", actor="cli"
        )
    await graph.dispose()


# ----- guard -----
