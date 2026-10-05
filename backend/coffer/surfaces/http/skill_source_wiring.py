"""Wire skill sources (spec skill-manager "Add skills from an archive", "Add
skills from a Git repository", "Hand a Git-imported skill's update to an agent").

Called from ``agent_skill_wiring`` once the skill service exists: builds the
source service over the machine's ``git``, the archive reader and the
machine-local check record (``local/skill-source-status.json``), publishes it
to the routes, and starts the update worker, which follows this machine's
schedule. ``stop`` is the shutdown half.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.application.skill.service import SkillService
from coffer.application.skill.source_service import SkillSourceService, SkillUpdateWorker
from coffer.infrastructure.daemon.skill_update_setting import DaemonConfigUpdateCheck
from coffer.infrastructure.skill.archive_reader import ZipArchiveReader
from coffer.infrastructure.skill.git_source import GitSource
from coffer.infrastructure.skill.source_status_repo import SkillSourceStatusRepo
from coffer.surfaces.http.skill_dependencies import set_skill_source_service


@dataclass
class SkillSources:
    service: SkillSourceService
    worker: SkillUpdateWorker

    async def stop(self) -> None:
        await self.worker.stop()
        self.service.close()


def wire_skill_sources(skill_svc: SkillService) -> SkillSources:
    service = SkillSourceService(
        skills=skill_svc,
        git=GitSource(),
        archives=ZipArchiveReader(),
        status_repo=SkillSourceStatusRepo(),
        update_check=DaemonConfigUpdateCheck(),
    )
    set_skill_source_service(service)
    worker = SkillUpdateWorker(service)
    worker.start()
    return SkillSources(service=service, worker=worker)


__all__ = ["SkillSources", "wire_skill_sources"]
