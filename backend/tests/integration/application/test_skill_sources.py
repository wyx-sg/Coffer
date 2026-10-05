"""SkillSourceService over real git, a real SQLite file and a real master store.

Spec skill-manager "Add skills from a Git repository" and "Hand a
Git-imported skill's update to an agent". Every repository is a bare one under
``tmp_path`` reached over ``file://`` (``tests/support/skill_sources``).
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.skill import update_ops
from coffer.application.skill.source_service import SkillSourceService
from coffer.application.skill.staging import StagingRegistry
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.content_hash import folder_content_hash
from coffer.domain.skill.source import GitImportSource
from coffer.domain.skill_source_errors import (
    SkillNotFromGit,
    SkillSourceUnreachable,
    SkillUpdateNotPending,
)
from coffer.infrastructure.daemon.skill_update_setting import DaemonConfigUpdateCheck
from coffer.infrastructure.skill.archive_reader import ZipArchiveReader
from coffer.infrastructure.skill.git_source import GitSource
from coffer.infrastructure.skill.source_status_repo import SkillSourceStatusRepo
from tests.support.skill_sources import Upstream, make_upstream, skill_md
from tests.support.skills import SkillGraph, build_skill_graph


@dataclass
class Env:
    graph: SkillGraph
    svc: SkillSourceService
    staging_root: pathlib.Path
    tmp: pathlib.Path

    def master(self, name: str) -> pathlib.Path:
        return pathlib.Path(self.graph.skills.master_path(name))

    def stages_left(self) -> list[str]:
        root = self.staging_root
        return sorted(p.name for p in root.iterdir()) if root.exists() else []

    async def source(self, uid: str) -> GitImportSource:
        skill = await self.graph.skills.get_skill(uid)
        src = SkillConfig.model_validate(skill.config).source
        assert isinstance(src, GitImportSource)
        return src

    async def add(self, up: Upstream, *, ref: str | None = None, path: str = "skills") -> Resource:
        stage = await self.svc.stage_git(up.url, ref, path)
        names = [s.name for s in stage.skills if s.name]
        [skill] = await self.svc.confirm(stage.id, names=names, replace=[], actor="cli")
        return skill


@pytest.fixture
async def env(tmp_path: pathlib.Path) -> AsyncIterator[Env]:
    graph = await build_skill_graph(tmp_path)
    staging_root = tmp_path / "staging"
    svc = SkillSourceService(
        skills=graph.skills,
        git=GitSource(timeout_s=60),
        archives=ZipArchiveReader(),
        status_repo=SkillSourceStatusRepo(),
        update_check=DaemonConfigUpdateCheck(),
        staging=StagingRegistry(root=staging_root),
    )
    yield Env(graph, svc, staging_root, tmp_path)
    svc.close()
    await graph.dispose()


def _upstream(tmp: pathlib.Path, *, tag: str | None = None) -> Upstream:
    return make_upstream(
        tmp / "upstream",
        {
            "README.md": "repo\n",
            "skills/review/SKILL.md": skill_md("review", "v1"),
            "skills/review/old.txt": "old\n",
            "skills/review/notes.txt": "one\n",
        },
        tag=tag,
    )


def _upstream_moves(up: Upstream) -> str:
    """One commit outside the skill's folder, then one that adds, removes and changes."""
    up.write("README.md", "repo v2\n")
    up.commit("docs only")
    up.write("skills/review/new.txt", "new\n")
    up.remove("skills/review/old.txt")
    up.write("skills/review/notes.txt", "two\n")
    return up.commit("rework review")


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a git-imported skill records the commit it was pinned to"
)
async def test_a_skill_found_one_folder_down_is_pinned_to_its_own_subpath(env: Env) -> None:
    up = _upstream(env.tmp)
    skill = await env.add(up, ref="main", path="skills")
    source = await env.source(skill.uid)
    assert source.url == up.url
    assert source.ref == "main"
    assert source.subpath == "skills/review"
    assert source.commit == up.head() and len(source.commit) == 40
    assert source.content_hash == folder_content_hash(env.master("review"))
    assert env.stages_left() == []


@pytest.mark.acceptance(
    spec="skill-manager", scenario="add a skill from a repository subpath at a ref"
)
async def test_a_tag_and_subpath_pin_and_a_later_commit_changes_nothing(env: Env) -> None:
    up = _upstream(env.tmp, tag="v1.2")
    tagged = up.head()
    stage = await env.svc.stage_git(up.url, "v1.2", "skills/review")
    assert (stage.commit, stage.ref, stage.subpath) == (tagged, "v1.2", "skills/review")
    assert [s.folder for s in stage.skills] == ["."]
    assert not env.master("review").exists(), "staging writes nothing"
    [skill] = await env.svc.confirm(stage.id, names=["review"], replace=[], actor="cli")
    source = await env.source(skill.uid)
    assert (source.ref, source.subpath, source.commit) == ("v1.2", "skills/review", tagged)
    assert (env.master("review") / "old.txt").read_text() == "old\n"

    _upstream_moves(up)
    assert (env.master("review") / "old.txt").read_text() == "old\n"
    assert not (env.master("review") / "new.txt").exists()
    assert (await env.source(skill.uid)).commit == tagged


@pytest.mark.parametrize(
    ("ref", "path", "needle"),
    [("no-such-ref", "skills/review", "no-such-ref"), ("main", "skills/absent", "skills/absent")],
)
async def test_a_ref_or_subpath_the_repository_lacks_writes_nothing(
    env: Env, ref: str, path: str, needle: str
) -> None:
    up = _upstream(env.tmp)
    with pytest.raises(SkillSourceUnreachable) as info:
        await env.svc.stage_git(up.url, ref, path)
    assert needle in info.value.git_message
    assert env.stages_left() == []
    assert [s.name for s in await env.graph.skills.list_skills()] == []


@pytest.mark.acceptance(spec="skill-manager", scenario="a newer commit shows update available")
async def test_check_counts_only_commits_that_change_the_folder(env: Env) -> None:
    up = _upstream(env.tmp)
    skill = await env.add(up)
    before = (env.master("review") / "notes.txt").read_text()

    status = await env.svc.check(skill.uid)
    assert (status.commits_ahead, status.update_available(up.head())) == (0, False)

    up.write("README.md", "unrelated\n")
    up.commit("docs only")
    status = await env.svc.check(skill.uid)
    assert status.commits_ahead == 0 and not status.update_available(
        (await env.source(skill.uid)).commit
    )

    new = _upstream_moves(up)
    status = await env.svc.check(skill.uid)
    pinned = (await env.source(skill.uid)).commit
    assert status.latest_commit == new
    assert status.commits_ahead == 1
    assert status.files_changed == 3
    assert status.update_available(pinned) is True
    assert status.error is None and status.last_success_at is not None
    assert (env.master("review") / "notes.txt").read_text() == before
    assert env.stages_left() == []


async def test_check_due_waits_the_chosen_interval_between_checks(env: Env) -> None:
    up = _upstream(env.tmp)
    skill = await env.add(up)
    await env.graph.import_skill(env.tmp, "local-one")  # not from git: never checked
    now = datetime.now(tz=UTC)
    day = timedelta(days=1)
    assert await update_ops.check_due(env.svc, day, now=now) == 1
    assert await update_ops.check_due(env.svc, day, now=now + timedelta(hours=7)) == 0
    new = _upstream_moves(up)
    assert await update_ops.check_due(env.svc, day, now=now + timedelta(hours=25)) == 1
    status = await env.svc.status(skill)
    assert status is not None and status.latest_commit == new


@pytest.mark.acceptance(
    spec="skill-manager", scenario="the update check follows this machine's setting"
)
async def test_the_update_check_follows_this_machines_setting(env: Env) -> None:
    config = pathlib.Path(os.environ["HOME"]) / ".coffer" / "daemon-config.json"
    up = _upstream(env.tmp)
    skill = await env.add(up)
    vault_before = _tree(env.master("review"))

    assert env.svc.update_check_choice() == "6h"
    assert env.svc.set_update_check_choice("1d") == "1d"
    assert json.loads(config.read_text())["skill_update_check"] == "1d"
    day_checks = await env.svc.check_due()
    assert day_checks == 1  # never checked: due now, then not again within a day
    assert await env.svc.check_due() == 0
    status = await env.svc.status(skill)
    assert status is not None and status.checked_at is not None
    later = status.checked_at + timedelta(hours=25)
    assert await update_ops.check_due(env.svc, timedelta(days=1), now=later) == 1

    assert env.svc.set_update_check_choice("manual") == "manual"
    assert json.loads(config.read_text())["skill_update_check"] == "manual"
    new = _upstream_moves(up)
    assert await env.svc.check_due() == 0  # no background check runs
    assert (await env.svc.status(skill)).latest_commit != new  # type: ignore[union-attr]
    # Check for updates on the skill still checks it.
    checked = await env.svc.check(skill.uid)
    assert checked.latest_commit == new
    assert _tree(env.master("review")) == vault_before


def _tree(root: pathlib.Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.mark.acceptance(
    spec="skill-manager", scenario="an unreachable source is reported and changes nothing"
)
async def test_an_unreachable_source_keeps_the_last_success(env: Env) -> None:
    up = _upstream(env.tmp)
    skill = await env.add(up)
    pinned = (await env.source(skill.uid)).commit
    ok = await env.svc.check(skill.uid)
    assert ok.last_success_at is not None
    shutil.rmtree(up.bare)

    status = await env.svc.check(skill.uid)
    assert status.error is not None and status.error.startswith("git clone failed:")
    assert status.last_success_at == ok.last_success_at
    assert status.checked_at is not None and status.checked_at >= ok.last_success_at
    assert (await env.source(skill.uid)).commit == pinned
    assert (env.master("review") / "notes.txt").read_text() == "one\n"
    stored = await env.svc.status(skill)
    assert stored is not None and stored.error == status.error
    with pytest.raises(SkillSourceUnreachable):
        await env.svc.handoff(skill.uid)
    assert env.stages_left() == []


async def test_update_operations_refuse_a_skill_not_from_git(env: Env) -> None:
    local = await env.graph.import_skill(env.tmp, "local-one")
    with pytest.raises(SkillNotFromGit):
        await env.svc.check(local.uid)
    with pytest.raises(SkillNotFromGit):
        await env.svc.handoff(local.uid)


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="the update hand-off names the commits, the local edits and the read-only source",
)
async def test_the_update_hand_off_names_the_commits_the_edits_and_the_source(env: Env) -> None:
    up = _upstream(env.tmp)
    skill = await env.add(up)
    first = (await env.source(skill.uid)).commit
    new = _upstream_moves(up)

    # No local edit: the prompt says there are none.
    plain = await env.svc.handoff(skill.uid)
    assert plain.commit == new
    assert "I have not edited the skill since the pin." in plain.prompt
    assert "Files I edited" not in plain.prompt

    (env.master("review") / "notes.txt").write_text("mine\n")
    before = _tree(env.master("review"))
    result = await env.svc.handoff(skill.uid)
    prompt = result.prompt
    assert result.commit == new
    assert str(env.master("review")) in prompt
    assert first in prompt and new in prompt
    assert "Files I edited since the pin: notes.txt" in prompt
    assert "rework review" in prompt  # the upstream commit's subject
    assert up.url in prompt and "(read-only)" in prompt
    assert "only read it — never push" in prompt
    assert "keeping my local edits" in prompt
    assert "Show me the diff" in prompt
    assert "do not call Coffer to record it" in prompt
    # Nothing was written by building it.
    assert _tree(env.master("review")) == before
    assert (await env.source(skill.uid)).commit == first
    assert env.stages_left() == []


@pytest.mark.acceptance(
    spec="skill-manager",
    scenario="the update is offered only as a hand-off while an update is available",
)
async def test_the_update_hand_off_is_refused_while_up_to_date(env: Env) -> None:
    up = _upstream(env.tmp)
    skill = await env.add(up)
    with pytest.raises(SkillUpdateNotPending):
        await env.svc.handoff(skill.uid)
    # A commit that does not touch the skill's folder is no update either.
    up.write("README.md", "unrelated\n")
    up.commit("docs only")
    with pytest.raises(SkillUpdateNotPending):
        await env.svc.handoff(skill.uid)
    assert env.stages_left() == []


@pytest.mark.acceptance(
    spec="skill-manager", scenario="recording a merge moves the pin and keeps the merged files"
)
async def test_recording_a_merge_moves_the_pin_and_keeps_the_files(env: Env) -> None:
    up = _upstream(env.tmp)
    skill = await env.add(up)
    first = (await env.source(skill.uid)).commit
    (env.master("review") / "notes.txt").write_text("mine\n")
    new = _upstream_moves(up)
    # The agent's merge: upstream's new file taken, the local edit kept.
    (env.master("review") / "new.txt").write_text("new\n")
    (env.master("review") / "old.txt").unlink()
    merged_hash = folder_content_hash(env.master("review"))

    await env.svc.mark_merged(skill.uid, new[:10], actor="cli")

    source = await env.source(skill.uid)
    assert source.commit == new
    # The master's files are exactly as the merge left them.
    assert (env.master("review") / "notes.txt").read_text() == "mine\n"
    assert folder_content_hash(env.master("review")) == merged_hash
    # The pin's hash is upstream's own content, so the merged edit still
    # reads as a local edit against the new base.
    assert source.content_hash != merged_hash
    status = await env.svc.status(skill)
    assert status is not None and status.update_available(new) is False
    [event] = await env.graph.audit.query(event_type=AuditEventType.SKILL_UPDATE_MERGED.value)
    assert event.actor == "cli"
    assert event.details == {"from_commit": first, "to_commit": new}

    # A later upstream change hands off listing only the carried edit.
    up.write("skills/review/SKILL.md", skill_md("review", "v3"))
    up.commit("v3")
    later = await env.svc.handoff(skill.uid)
    assert "Files I edited since the pin: notes.txt\n" in later.prompt + "\n"
    assert "new.txt" not in later.prompt.split("Files I edited since the pin:")[1].split("\n")[0]
    assert env.stages_left() == []


@pytest.mark.acceptance(
    spec="skill-manager", scenario="recording a merge refuses a commit that is not the update"
)
async def test_recording_a_merge_refuses_a_commit_not_waiting(env: Env) -> None:
    up = _upstream(env.tmp)
    skill = await env.add(up)
    first = (await env.source(skill.uid)).commit
    # Nothing newer upstream: there is no update to have merged.
    with pytest.raises(SkillUpdateNotPending):
        await env.svc.mark_merged(skill.uid, first, actor="cli")
    _upstream_moves(up)
    # The pinned commit itself, and a commit that is not on the ref, are refused.
    for commit in (first, "0" * 40):
        with pytest.raises(SkillUpdateNotPending):
            await env.svc.mark_merged(skill.uid, commit, actor="cli")
    assert (await env.source(skill.uid)).commit == first
    assert await env.graph.audit.query(event_type=AuditEventType.SKILL_UPDATE_MERGED.value) == []
    assert env.stages_left() == []
