"""Skill-delivery semantics ("Deliver a skill only where it is enabled and in scope").

One rule decides delivery and nothing else does::

    delivered(skill, agent) == skill.enabled and scope.is_active(skill.scope, agent.uid)

``scope`` is the skill's single ``agents`` allow-list: activation is
machine-local, so the machine holding the scope is already the machine answer.

Same construction style as ``test_skill_unmanaged.py`` (real sqlite + real
MasterStore / SyncEngine over tmp_path); the reconciliation hooks are wired the
way the composition root wires them.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.agent.service import AgentService
from coffer.application.skill.service import SkillService
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ScopeInvalidError
from coffer.domain.reconcile import Disposition, Outcome
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope
from tests.support.skills import build_skill_graph, write_skill_folder


async def _setup(tmp_path: pathlib.Path, *, reconcile_hooks: bool = True):
    """The real service graph over a real sqlite file, wired like the
    composition root (``tests/support/skills``). ``reconcile_hooks=False``
    leaves the kind hooks out, so a test can edit a skill's state WITHOUT a
    delivery pass and then run one by hand."""
    graph = await build_skill_graph(tmp_path, hooks=reconcile_hooks)
    return graph.skills, graph.agents, graph.audit, graph


async def _register_agent(
    agent_svc: AgentService,
    tmp_path: pathlib.Path,
    *,
    name: str,
    agent_type: AgentType = AgentType.CLAUDE_CODE,
) -> tuple[Resource, pathlib.Path]:
    # ``name`` labels the config dir only: an agent is named by its type, and
    # one agent per type, so a test needing two agents registers one of each.
    config_dir = tmp_path / f"{name}-cfg"
    config_dir.mkdir()
    agent = await agent_svc.register(
        agent_type=agent_type,
        config_dir=str(config_dir),
        actor="cli",
    )
    return agent, config_dir / "skills"


async def _by_name(skill_svc: SkillService, name: str) -> Resource:
    """Resolve a skill LABEL to its row.

    The one-shot resolution a surface does at its front door
    (ADR identity-is-the-uid-inside-the-file): a test states what it means in
    the name a person would type, and converts once.
    """
    return await skill_svc._rs.get_by_name("skill", name)


async def _import_skill(skill_svc: SkillService, tmp_path: pathlib.Path, name: str) -> Resource:
    src = write_skill_folder(tmp_path / "srcs" / name, name=name)
    return await skill_svc.import_local(path=str(src), actor="cli")


async def _delivered_names(skill_svc: SkillService, agent: Resource) -> set[str]:
    names_by_id = {s.uid: s.name for s in await skill_svc.list_skills()}
    return {
        names_by_id[b.skill_uid]
        for b in await skill_svc._bindings.list_for_agent(agent.uid)
        if b.enabled and b.skill_uid in names_by_id
    }


# ----- acceptance scenarios -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="a skill with no scope reaches every registered agent"
)
async def test_unscoped_skill_reaches_every_agent(tmp_path):
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path)
    a1, dir1 = await _register_agent(agent_svc, tmp_path, name="a1")
    a2, dir2 = await _register_agent(agent_svc, tmp_path, name="a2", agent_type=AgentType.CODEX)

    skill = await _import_skill(skill_svc, tmp_path, "shared")
    assert skill.scope is None  # a fresh skill names no agent → every agent

    assert (dir1 / "shared").is_symlink()
    assert (dir2 / "shared").is_symlink()
    assert await _delivered_names(skill_svc, a1) == {"shared"}
    assert await _delivered_names(skill_svc, a2) == {"shared"}
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="a skill scoped to no agent reaches nobody")
async def test_dormant_skill_reaches_nobody(tmp_path):
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path)
    a1, dir1 = await _register_agent(agent_svc, tmp_path, name="a1")
    await _import_skill(skill_svc, tmp_path, "dormant")
    assert (dir1 / "dormant").is_symlink()

    # An empty agents axis is dormant: no agent is in scope.
    dormant = await _by_name(skill_svc, "dormant")
    await skill_svc._rs.update_scope(dormant.uid, Scope(agents=[]), actor="cli")
    assert not (dir1 / "dormant").exists()
    assert await _delivered_names(skill_svc, a1) == set()

    # And a later agent gets nothing either.
    a2, dir2 = await _register_agent(agent_svc, tmp_path, name="a2", agent_type=AgentType.CODEX)
    assert not (dir2 / "dormant").exists()
    assert await _delivered_names(skill_svc, a2) == set()
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="import delivers a skill only where its scope grants it"
)
async def test_import_delivers_only_where_scope_grants(tmp_path):
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path)
    a1, dir1 = await _register_agent(agent_svc, tmp_path, name="a1")
    a2, dir2 = await _register_agent(agent_svc, tmp_path, name="a2", agent_type=AgentType.CODEX)

    # Import, then narrow the scope to a1 only.
    only_a1 = await _import_skill(skill_svc, tmp_path, "only-a1")
    # A scope names agents by UID: the identity a rename cannot move out from
    # under the reference (ADR identity-is-the-uid-inside-the-file).
    await skill_svc._rs.update_scope(only_a1.uid, Scope(agents=[a1.uid]), actor="cli")
    assert (dir1 / "only-a1").is_symlink()
    assert not (dir2 / "only-a1").exists()

    # A re-import of the SAME name (overwrite) must not widen delivery.
    src = write_skill_folder(tmp_path / "srcs2" / "only-a1", name="only-a1")
    await skill_svc.import_local(path=str(src), actor="cli", overwrite=True)
    assert (dir1 / "only-a1").is_symlink()
    assert not (dir2 / "only-a1").exists()
    assert await _delivered_names(skill_svc, a1) == {"only-a1"}
    assert await _delivered_names(skill_svc, a2) == set()
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager", scenario="disabling a skill reclaims every delivered copy"
)
async def test_disabling_a_skill_reclaims_every_copy(tmp_path):
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path)
    a1, dir1 = await _register_agent(agent_svc, tmp_path, name="a1")
    a2, dir2 = await _register_agent(agent_svc, tmp_path, name="a2", agent_type=AgentType.CODEX)
    await _import_skill(skill_svc, tmp_path, "everywhere")
    assert (dir1 / "everywhere").is_symlink() and (dir2 / "everywhere").is_symlink()

    everywhere = await _by_name(skill_svc, "everywhere")
    await skill_svc._rs.set_enabled(everywhere.uid, False, actor="cli")

    assert not (dir1 / "everywhere").exists()
    assert not (dir2 / "everywhere").exists()
    assert await _delivered_names(skill_svc, a1) == set()
    assert await _delivered_names(skill_svc, a2) == set()
    # The master folder is untouched — a disable is not a removal.
    assert (skill_svc._store.paths_for("everywhere").folder / "SKILL.md").exists()
    await graph.dispose()


@pytest.mark.asyncio
async def test_a_disabled_agent_is_never_written_into(tmp_path):
    """An agent the user switched off is one Coffer does not deliver into.

    The delivery predicate decides which agents a skill is FOR; the agent's own
    enabled flag decides whether Coffer touches its config dir at all. Both a
    fresh import and a reconciliation run must respect it, and the reclaim must
    be reversible — otherwise disabling an agent would be a one-way door.
    """
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path)
    live, live_dir = await _register_agent(agent_svc, tmp_path, name="live")
    off, off_dir = await _register_agent(
        agent_svc, tmp_path, name="off", agent_type=AgentType.CODEX
    )
    await skill_svc._rs.set_enabled(off.uid, False, actor="cli")

    # Import after the agent was switched off: only the live agent gets it.
    await _import_skill(skill_svc, tmp_path, "fresh")
    assert (live_dir / "fresh").is_symlink()
    assert not (off_dir / "fresh").exists()
    assert await _delivered_names(skill_svc, off) == set()

    # Re-enabling the agent reconciles it back.
    await skill_svc._rs.set_enabled(off.uid, True, actor="cli")
    assert (off_dir / "fresh").is_symlink()
    assert await _delivered_names(skill_svc, off) == {"fresh"}

    # And switching it off again reclaims what it holds.
    await skill_svc._rs.set_enabled(off.uid, False, actor="cli")
    assert not (off_dir / "fresh").exists()
    assert await _delivered_names(skill_svc, off) == set()
    assert (live_dir / "fresh").is_symlink()  # the live agent is untouched throughout
    assert await _delivered_names(skill_svc, live) == {"fresh"}
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="disabling an agent reclaims its skills and drops it from the catalogue",
)
async def test_disabling_an_agent_reclaims_skills_and_leaves_the_catalogue(tmp_path):
    """The agent's own ``enabled`` flag, toggled through the kind-agnostic
    resource route, is the one switch that stops Coffer writing into it: the
    skills it holds are reclaimed, its config dir stops feeding the model
    catalogue, and the toggle is audited as ``resource_disabled``."""
    from coffer.application.agent.model_catalogue import AgentModelCatalogueService
    from coffer.domain.agent.model_catalogue import AgentModel
    from coffer.domain.audit import AuditEventType

    skill_svc, agent_svc, audit, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="solo")
    await _import_skill(skill_svc, tmp_path, "held")
    assert (skill_dir / "held").is_symlink()

    seen: list = []

    class _Discovery:
        async def discover(self, *, agent_key, config_dir):
            seen.append(config_dir)
            return [AgentModel("m-1")]

    class _Agents:
        async def list(self):
            return await skill_svc._rs.list(kind="agent")

    catalogue = AgentModelCatalogueService(agents=_Agents(), discovery=_Discovery())
    await catalogue.catalogue("claude_code")
    assert seen == [tmp_path / "solo-cfg"]

    await skill_svc._rs.set_enabled(agent.uid, False, actor="cli")

    assert not (skill_dir / "held").exists()
    assert await _delivered_names(skill_svc, agent) == set()
    seen.clear()
    await catalogue.catalogue("claude_code")
    assert seen == [None]  # no enabled agent answers for the type any more
    disabled = await audit.query(event_type=AuditEventType.RESOURCE_DISABLED.value)
    assert [(e.resource_kind, e.resource_name, e.actor) for e in disabled] == [
        ("agent", "claude-code", "cli")
    ]
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="skill-manager", scenario="re-enabling a skill redelivers it")
async def test_re_enabling_a_skill_redelivers_it(tmp_path):
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path)
    a1, dir1 = await _register_agent(agent_svc, tmp_path, name="a1")
    back_again = await _import_skill(skill_svc, tmp_path, "back-again")

    await skill_svc._rs.set_enabled(back_again.uid, False, actor="cli")
    assert not (dir1 / "back-again").exists()

    await skill_svc._rs.set_enabled(back_again.uid, True, actor="cli")
    assert (dir1 / "back-again").is_symlink()
    assert await _delivered_names(skill_svc, a1) == {"back-again"}
    await graph.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="scoping a skill away from an agent reclaims the delivered copy",
)
async def test_scoping_away_reclaims_the_delivered_copy(tmp_path):
    """Scope is a hard grant: once a delivered skill stops naming this agent,
    the copy is reclaimed — no other trigger required."""
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    shared = await _import_skill(skill_svc, tmp_path, "shared")
    assert (skill_dir / "shared").is_symlink()
    assert await _delivered_names(skill_svc, agent) == {"shared"}

    # A uid that matches no registered agent is legal and simply never
    # matches — the scope now names somebody who is not this agent.
    await skill_svc._rs.update_scope(shared.uid, Scope(agents=["no-such-agent"]), actor="cli")

    assert not (skill_dir / "shared").exists()
    assert await _delivered_names(skill_svc, agent) == set()
    await graph.dispose()


# ----- non-acceptance coverage -----


@pytest.mark.asyncio
async def test_disabled_skill_is_not_delivered_to_a_new_agent(tmp_path):
    """A disabled skill is invisible to delivery, including to an agent that
    registers later."""
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path)
    switched_off = await _import_skill(skill_svc, tmp_path, "switched-off")
    await skill_svc._rs.set_enabled(switched_off.uid, False, actor="cli")

    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    assert not (skill_dir / "switched-off").exists()
    assert await _delivered_names(skill_svc, agent) == set()
    await graph.dispose()


@pytest.mark.asyncio
async def test_scoping_back_in_redelivers(tmp_path):
    """The converse of the reclaim scenario: naming the agent again delivers
    the copy back, with no unrelated trigger."""
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path)
    elsewhere = await _import_skill(skill_svc, tmp_path, "elsewhere")
    await skill_svc._rs.update_scope(elsewhere.uid, Scope(agents=["no-such-agent"]), actor="cli")
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    assert not (skill_dir / "elsewhere").exists()

    await skill_svc._rs.update_scope(elsewhere.uid, Scope(agents=[agent.uid]), actor="cli")

    assert (skill_dir / "elsewhere").is_symlink()
    assert await _delivered_names(skill_svc, agent) == {"elsewhere"}
    await graph.dispose()


@pytest.mark.asyncio
async def test_master_removal_cleans_up_delivered_copies(tmp_path):
    skill_svc, agent_svc, _, graph = await _setup(tmp_path)
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    doomed = await _import_skill(skill_svc, tmp_path, "doomed")
    assert (skill_dir / "doomed").is_symlink()

    await skill_svc.remove(uid=doomed.uid, actor="cli")
    assert not (skill_dir / "doomed").exists()
    assert not (skill_dir / "doomed").is_symlink()
    assert await skill_svc._bindings.list_for_agent(agent.uid) == []
    await graph.dispose()


@pytest.mark.asyncio
async def test_reconcile_tolerates_target_conflict(tmp_path):
    """An occupied target path skips that one skill — the rest of the
    reconciliation still delivers."""
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path)
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
        agent_type=AgentType.CLAUDE_CODE, config_dir=str(config_dir), actor="cli"
    )
    assert (config_dir / "skills" / "smooth").is_symlink()
    assert (foreign / "mine.txt").read_text(encoding="utf-8") == "user data"  # never clobbered
    assert await _delivered_names(skill_svc, agent) == {"smooth"}
    await graph.dispose()


@pytest.mark.asyncio
async def test_an_occupied_path_is_reported_blocked_not_failed(tmp_path):
    """Foreign content where a link would go is a blocked item the pass reports
    (and the sync round shows), never a failed write and never a clobber."""
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path, reconcile_hooks=False)
    await _import_skill(skill_svc, tmp_path, "blocked")

    config_dir = tmp_path / "a1-cfg"
    (config_dir / "skills").mkdir(parents=True)
    foreign = config_dir / "skills" / "blocked"
    foreign.mkdir()
    (foreign / "mine.txt").write_text("user data", encoding="utf-8")
    await agent_svc.register(
        agent_type=AgentType.CLAUDE_CODE, config_dir=str(config_dir), actor="cli"
    )

    report = await graph.run()
    [result] = report.results
    assert result.outcome is Outcome.PLANNED
    assert result.change.decision.disposition is Disposition.BLOCKED
    assert result.change.decision.reason_code == "foreign_content"
    assert (foreign / "mine.txt").read_text(encoding="utf-8") == "user data"
    await graph.dispose()


@pytest.mark.asyncio
async def test_config_dir_move_preserves_delivery(tmp_path):
    _skill_svc, agent_svc, _audit, graph = await _setup(tmp_path)
    _agent, old_dir = await _register_agent(agent_svc, tmp_path, name="cc")
    await _import_skill(_skill_svc, tmp_path, "travels")
    assert (old_dir / "travels").is_symlink()

    new_dir = tmp_path / "moved-claude"
    new_dir.mkdir()
    await agent_svc.update_config_dir(uid=_agent.uid, new_config_dir=str(new_dir), actor="cli")
    assert not (old_dir / "travels").exists()
    assert (new_dir / "skills" / "travels").is_symlink()
    await graph.dispose()


@pytest.mark.asyncio
async def test_an_out_of_scope_agent_is_never_planned(tmp_path):
    """Scope is a hard grant by construction: a delivery the rule does not
    grant is not in the plan at all, so no trigger can make it."""
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path, reconcile_hooks=False)
    denied = await _import_skill(skill_svc, tmp_path, "denied")
    await skill_svc._rs.update_scope(denied.uid, Scope(agents=["no-such-agent"]), actor="test")
    agent, skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")

    assert (await graph.plan()).results == ()
    await graph.run()
    assert not (skill_dir / "denied").exists()
    assert await _delivered_names(skill_svc, agent) == set()
    await graph.dispose()


@pytest.mark.asyncio
async def test_config_dir_change_does_not_resurrect_ungranted_link(tmp_path):
    """A config-dir move of an agent whose delivery the rule no longer grants
    reclaims the old link and makes no new one: the pass judges the move and
    the grant together."""
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path, reconcile_hooks=False)
    agent, old_skill_dir = await _register_agent(agent_svc, tmp_path, name="a1")
    shared = await _import_skill(skill_svc, tmp_path, "shared")
    old_link = old_skill_dir / "shared"
    assert old_link.is_symlink()

    # Disable and move with no pass in between (hooks omitted).
    await skill_svc._rs.set_enabled(shared.uid, False, actor="test")
    new_config_dir = tmp_path / "moved-cfg"
    new_config_dir.mkdir()
    await agent_svc.update_config_dir(
        uid=agent.uid, new_config_dir=str(new_config_dir), actor="cli"
    )
    await graph.run()

    new_link = new_config_dir / "skills" / "shared"
    assert not old_link.exists(), "the stale old link is torn down"
    assert not new_link.exists(), "an ungranted link is not made at the new config_dir"
    [binding] = await skill_svc.bindings_for(shared.uid)
    assert (binding.enabled, binding.last_link_path) == (False, None)
    await graph.dispose()


@pytest.mark.asyncio
async def test_update_scope_on_agent_kind_is_rejected(tmp_path):
    """The `agent` kind declares no scope (ADR per-agent-resource-scope) — scope names the agents a
    resource is active for, so an agent scoping itself is meaningless."""
    skill_svc, agent_svc, _audit, graph = await _setup(tmp_path)
    agent, _ = await _register_agent(agent_svc, tmp_path, name="a1")
    with pytest.raises(ScopeInvalidError):
        await skill_svc._rs.update_scope(agent.uid, Scope(agents=[agent.uid]), actor="cli")
    await graph.dispose()
