"""SkillService end-to-end integration (DB + filesystem + sync engine).

Covers import / fetch / enable / disable / update / verify / remove +
the cross-kind cleanup hooks. Git fetch is exercised through a stubbed
SourceFetcher that yields a prepared folder so we don't reach the network.
"""

from __future__ import annotations

import os
import pathlib
import textwrap
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
    SkillNameMismatch,
    SkillValidationError,
    SSRFBlocked,
    TargetConflict,
    UpdateNotSupported,
)
from coffer.domain.skill.drift import DriftKind
from coffer.infrastructure.agent.persistence import SuppressedAgentTypeRepo
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


class _FakeFetcher:
    """Stub for GitSourceFetcher — serves prepared folders by URL."""

    def __init__(self, content_by_url: dict[str, pathlib.Path]) -> None:
        self._content = content_by_url

    @asynccontextmanager
    async def fetched(
        self,
        *,
        git_url: str,
        git_ref: str,
        git_subpath: str = "",
    ) -> AsyncIterator[pathlib.Path]:
        # Honor SSRF guard via the real check_url to ensure tests can
        # also exercise rejection paths.
        from coffer.infrastructure.skill.ssrf_guard import check_url

        try:
            check_url(git_url)
        except ValueError as e:
            host = git_url.split("//", 1)[-1].split("/", 1)[0]
            raise SSRFBlocked(host) from e
        if git_url not in self._content:
            raise FileNotFoundError(f"no fake content registered for {git_url}")
        yield self._content[git_url]


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


async def _setup(tmp_path: pathlib.Path, fake_fetch: dict[str, pathlib.Path] | None = None):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))

    binding_repo = SkillBindingRepo(sm)
    master_store = MasterStore(root=tmp_path / "coffer-skills")

    fetcher = _FakeFetcher(fake_fetch or {})

    # Cross-kind resolver — tests are outside the contract scope so we can
    # import both kinds here without violating Contract 5.
    from coffer.domain.agent.config import AgentConfig
    from coffer.domain.resource import Resource

    def _agent_skill_dir(r: Resource):
        return AgentConfig.model_validate(r.config).resolved_skill_dir()

    # Order: create services first, then kinds (with cross-kind hooks).
    placeholder_kinds: dict = {}
    rs = ResourceService(kinds=placeholder_kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit)
    from coffer.infrastructure.skill.sync_engine import SyncEngine

    skill_svc = SkillService(
        resource_service=rs,
        audit=audit,
        binding_repo=binding_repo,
        master_store=master_store,
        source_fetcher=fetcher,  # type: ignore[arg-type]
        sync_engine=SyncEngine(),
        agent_skill_dir_resolver=_agent_skill_dir,
    )

    suppression = SuppressedAgentTypeRepo(sm)
    agent_svc = AgentService(resource_service=rs, audit=audit, suppression_repo=suppression)

    # CODE21-001 made the agent on_delete hook awaited (not fire-and-forget)
    # so cleanup happens BEFORE the agent row vanishes; mirror that here so
    # the test wiring matches the composition root.
    async def _agent_on_delete(ref):
        await skill_svc.cleanup_bindings_for_agent(ref)

    placeholder_kinds["agent"] = make_agent_kind(on_delete=_agent_on_delete)
    placeholder_kinds["skill"] = make_skill_kind(skill_svc.cleanup_bindings_for_skill)

    return skill_svc, agent_svc, audit, master_store, engine


async def _register_agent(agent_svc: AgentService, tmp_path: pathlib.Path, *, name: str):
    skill_dir = tmp_path / f"{name}-skills"
    skill_dir.mkdir()
    return await agent_svc.register(
        agent_type=AgentType.CURSOR,
        name=name,
        skill_dir=str(skill_dir),
        actor="cli",
    )


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


# ----- fetch -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="fetch a public Git skill repo")
async def test_fetch_git_with_stub_fetcher(tmp_path):
    upstream = tmp_path / "upstream"
    _write_skill_folder(upstream, name="from-git")
    skill_svc, _, audit, store, engine = await _setup(
        tmp_path,
        fake_fetch={"https://github.com/x/y": upstream},
    )
    r = await skill_svc.fetch_git(git_url="https://github.com/x/y", git_ref="main", actor="cli")
    assert r.name == "from-git"
    assert store.paths_for("from-git").folder.is_dir()
    audited = await audit.query(event_type=AuditEventType.SKILL_FETCHED.value)
    assert len(audited) == 1
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="reject SSRF in fetch")
async def test_fetch_rejects_loopback(tmp_path):
    skill_svc, _, _, _, engine = await _setup(tmp_path)
    with pytest.raises(SSRFBlocked):
        await skill_svc.fetch_git(git_url="http://127.0.0.1/repo.git", git_ref="main", actor="cli")
    await engine.dispose()


# ----- enable / disable -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="enable a skill for a registered agent")
async def test_enable_creates_link(tmp_path):
    skill_svc, agent_svc, _, _, engine = await _setup(tmp_path)
    agent = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    # import auto-binds; verify the link exists at the agent's skill_dir.
    target = pathlib.Path(agent.config["skill_dir"]) / "my-skill"
    assert target.exists()
    assert (target / "SKILL.md").is_file()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="disable a skill for an agent")
async def test_disable_removes_link_keeps_master(tmp_path):
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    agent = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    target = pathlib.Path(agent.config["skill_dir"]) / "my-skill"
    assert target.exists()
    await skill_svc.disable_for(skill_name="my-skill", agent_name="cur", actor="cli")
    assert not target.exists()
    assert store.paths_for("my-skill").folder.is_dir()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="enable for multiple agents")
async def test_enable_for_two_agents(tmp_path):
    skill_svc, agent_svc, _, _, engine = await _setup(tmp_path)
    a1 = await _register_agent(agent_svc, tmp_path, name="cur1")
    a2 = await _register_agent(agent_svc, tmp_path, name="cur2")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    t1 = pathlib.Path(a1.config["skill_dir"]) / "my-skill"
    t2 = pathlib.Path(a2.config["skill_dir"]) / "my-skill"
    assert t1.is_dir() and t2.is_dir()
    assert (t1 / "SKILL.md").read_bytes() == (t2 / "SKILL.md").read_bytes()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="005-skill-manager", scenario="refuse to overwrite a non-Coffer target"
)
async def test_refuse_to_overwrite_non_coffer_target(tmp_path):
    skill_svc, agent_svc, _, _, engine = await _setup(tmp_path)
    agent = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    # Pre-place a foreign directory at the would-be link path.
    link = pathlib.Path(agent.config["skill_dir"]) / "my-skill"
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
    backups = list(pathlib.Path(agent.config["skill_dir"]).glob("my-skill.coffer-backup-*"))
    assert backups
    # TEST21-005: pin the backup-name format so the spec's `<path>.coffer-
    # backup-<ts>` shape (integer unix timestamp suffix) doesn't regress.
    import re

    assert re.match(r".*\.coffer-backup-\d{10,}$", backups[0].name)
    await engine.dispose()


# ----- update -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="update a Git-sourced skill")
async def test_update_replaces_master(tmp_path):
    upstream_v1 = tmp_path / "upstream-v1"
    _write_skill_folder(upstream_v1, name="upd", body="v1 body")
    skill_svc, agent_svc, _, store, engine = await _setup(
        tmp_path, fake_fetch={"https://example.org/repo": upstream_v1}
    )
    agent = await _register_agent(agent_svc, tmp_path, name="cur")
    await skill_svc.fetch_git(git_url="https://example.org/repo", git_ref="main", actor="cli")
    # Replace upstream content.
    (upstream_v1 / "SKILL.md").write_text(
        "---\nname: upd\ndescription: v2 description.\n---\n\nv2 body"
    )
    outcome = await skill_svc.update(name="upd", actor="cli")
    assert outcome.changed
    assert "v2 body" in store.paths_for("upd").skill_md.read_text()
    # Symlink continues to point at master; verify the agent-side view updated.
    link = pathlib.Path(agent.config["skill_dir"]) / "upd"
    assert "v2 body" in (link / "SKILL.md").read_text()
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="005-skill-manager", scenario="detect frontmatter name change on update"
)
async def test_update_detects_name_change(tmp_path):
    upstream = tmp_path / "upstream"
    _write_skill_folder(upstream, name="orig")
    skill_svc, agent_svc, _, _, engine = await _setup(
        tmp_path, fake_fetch={"https://example.org/repo": upstream}
    )
    await _register_agent(agent_svc, tmp_path, name="cur")
    await skill_svc.fetch_git(git_url="https://example.org/repo", git_ref="main", actor="cli")
    (upstream / "SKILL.md").write_text("---\nname: renamed\ndescription: now renamed.\n---\nbody")
    with pytest.raises(SkillNameMismatch):
        await skill_svc.update(name="orig", actor="cli")
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_rejects_local_import(tmp_path):
    skill_svc, _, _, _, engine = await _setup(tmp_path)
    src = tmp_path / "src"
    _write_skill_folder(src, name="loc")
    await skill_svc.import_local(path=str(src), actor="cli")
    with pytest.raises(UpdateNotSupported):
        await skill_svc.update(name="loc", actor="cli")
    await engine.dispose()


# ----- verify -----


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="005-skill-manager", scenario="detect drift in agent skill directories"
)
async def test_verify_detects_missing_link(tmp_path):
    skill_svc, agent_svc, _, _, engine = await _setup(tmp_path)
    agent = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    link = pathlib.Path(agent.config["skill_dir"]) / "my-skill"
    link.unlink()
    report = await skill_svc.verify()
    assert any(e.kind is DriftKind.MISSING_LINK for e in report.entries)
    await engine.dispose()


# ----- removal -----


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="005-skill-manager", scenario="remove a skill cleans up all bindings")
async def test_remove_skill_cleans_everything(tmp_path):
    skill_svc, agent_svc, _, store, engine = await _setup(tmp_path)
    a1 = await _register_agent(agent_svc, tmp_path, name="cur1")
    a2 = await _register_agent(agent_svc, tmp_path, name="cur2")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    t1 = pathlib.Path(a1.config["skill_dir"]) / "my-skill"
    t2 = pathlib.Path(a2.config["skill_dir"]) / "my-skill"
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
    a1 = await _register_agent(agent_svc, tmp_path, name="cur1")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    t1 = pathlib.Path(a1.config["skill_dir"]) / "my-skill"
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
    a1 = await _register_agent(agent_svc, tmp_path, name="cur1")
    a2 = await _register_agent(agent_svc, tmp_path, name="cur2")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    t1 = pathlib.Path(a1.config["skill_dir"]) / "my-skill"
    t2 = pathlib.Path(a2.config["skill_dir"]) / "my-skill"
    await skill_svc.cleanup_bindings_for_agent(a1.ref)
    assert not t1.exists()
    assert t2.exists()
    assert store.paths_for("my-skill").folder.exists()
    await engine.dispose()


# ----- TEST21-012: update with allow_rename — master + bindings rewire -----


@pytest.mark.asyncio
async def test_update_with_allow_rename_renames_master_and_rewires_bindings(tmp_path):
    """Cover the `_rename_master_and_bindings` path of update_ops.

    Two agents are enabled on the original skill name, the upstream then
    changes the frontmatter ``name`` and the user runs update with
    ``allow_rename=True``. The master folder must be renamed, every binding
    rewired to the new resource_id, both agent-side links recreated under
    the new name, and a SKILL_RENAMED audit emitted.
    """
    upstream = tmp_path / "upstream"
    _write_skill_folder(upstream, name="orig")
    skill_svc, agent_svc, audit, store, engine = await _setup(
        tmp_path, fake_fetch={"https://example.org/repo": upstream}
    )
    a1 = await _register_agent(agent_svc, tmp_path, name="cur1")
    a2 = await _register_agent(agent_svc, tmp_path, name="cur2")
    await skill_svc.fetch_git(git_url="https://example.org/repo", git_ref="main", actor="cli")
    # Pre-rename: both agents have a link at <skill_dir>/orig.
    t1_old = pathlib.Path(a1.config["skill_dir"]) / "orig"
    t2_old = pathlib.Path(a2.config["skill_dir"]) / "orig"
    assert t1_old.exists() and t2_old.exists()

    # Upstream renames itself in the frontmatter.
    (upstream / "SKILL.md").write_text("---\nname: shiny\ndescription: renamed.\n---\nbody")
    outcome = await skill_svc.update(name="orig", allow_rename=True, actor="cli")
    assert outcome.changed
    assert outcome.renamed_from == "orig"
    assert outcome.skill.name == "shiny"

    # Master folder rename: old gone, new present.
    assert not store.paths_for("orig").folder.exists()
    assert store.paths_for("shiny").folder.is_dir()

    # Bindings rewired: agent-side links now live under the new name and the
    # old paths are gone.
    t1_new = pathlib.Path(a1.config["skill_dir"]) / "shiny"
    t2_new = pathlib.Path(a2.config["skill_dir"]) / "shiny"
    assert t1_new.exists() and t2_new.exists()
    assert not t1_old.exists() and not t2_old.exists()

    # SKILL_RENAMED audit emitted with the from→to pair.
    renamed = await audit.query(event_type=AuditEventType.SKILL_RENAMED.value)
    assert len(renamed) == 1
    details = renamed[0].details
    assert details.get("from") == "orig"
    assert details.get("to") == "shiny"
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
    a1 = await _register_agent(agent_svc, tmp_path, name="cur1")
    a2 = await _register_agent(agent_svc, tmp_path, name="cur2")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    t1 = pathlib.Path(a1.config["skill_dir"]) / "my-skill"
    t2 = pathlib.Path(a2.config["skill_dir"]) / "my-skill"
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
    agent = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    link = pathlib.Path(agent.config["skill_dir"]) / "my-skill"
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
    agent = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    link = pathlib.Path(agent.config["skill_dir"]) / "my-skill"
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
    agent = await _register_agent(agent_svc, tmp_path, name="cur")
    src = tmp_path / "src"
    _write_skill_folder(src, name="my-skill")
    await skill_svc.import_local(path=str(src), actor="cli")
    # Verify the link exists, then nuke the master folder out from under it.
    link = pathlib.Path(agent.config["skill_dir"]) / "my-skill"
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
