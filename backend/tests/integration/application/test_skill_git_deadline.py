"""One operation on a skill's Git source is held to one deadline.

Spec skill-manager "Fetch a Git skill's folder in one request, within one
deadline". The git here is a script that never finishes, so the deadline, not
git's own per-command timeout, is what ends the stage.
"""

from __future__ import annotations

import os
import pathlib
import stat

import pytest

from coffer.application.skill.source_service import SkillSourceService
from coffer.application.skill.staging import StagingRegistry
from coffer.domain.skill_source_errors import SkillSourceUnreachable
from coffer.infrastructure.skill.archive_reader import ZipArchiveReader
from coffer.infrastructure.skill.git_source import GitSource
from coffer.infrastructure.skill.source_status_repo import SkillSourceStatusRepo
from tests.support.skill_sources import stage_dirs
from tests.support.skills import build_skill_graph


@pytest.mark.acceptance(
    spec="skill-manager", scenario="a Git source operation past its deadline is refused"
)
async def test_a_stage_past_the_deadline_is_refused_and_leaves_nothing(
    tmp_path: pathlib.Path,
) -> None:
    pid_file = tmp_path / "pid"
    hanging = tmp_path / "git"
    hanging.write_text(f'#!/bin/sh\necho $$ > "{pid_file}"\nexec sleep 60\n')
    hanging.chmod(hanging.stat().st_mode | stat.S_IEXEC)
    graph = await build_skill_graph(tmp_path)
    svc = SkillSourceService(
        skills=graph.skills,
        git=GitSource(git=str(hanging), timeout_s=60),
        archives=ZipArchiveReader(),
        status_repo=SkillSourceStatusRepo(),
        staging=StagingRegistry(root=tmp_path / "staging"),
        deadline_s=0.5,
    )
    try:
        with pytest.raises(SkillSourceUnreachable) as refused:
            await svc.stage_git("https://example.com/skills.git", None, None)

        assert str(refused.value) == "reading the Git repository did not finish within 0.5 s"
        assert stage_dirs(svc) == []
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)
    finally:
        svc.close()
        await graph.dispose()
