"""SkillSourceService — where a skill comes from, and what is newer there.

The front door for spec skill-manager "Add skills from an archive", "Add
skills from a Git repository" and "Update a Git-imported skill from its
source". It owns the staging registry and the three adapters those need (the
machine's ``git``, the archive reader, the machine-local check results) and
hands every registration to the ``SkillService`` it was built over, so a
source never becomes a second way to write the master store. The operations
themselves live in ``source_stage_ops`` and ``update_ops``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import IO

from coffer.application.skill import source_change_ops, source_stage_ops, update_ops
from coffer.application.skill.ports import ArchiveReaderPort, GitSourcePort, SourceStatusRepoPort
from coffer.application.skill.service import SkillService
from coffer.application.skill.staging import ImportStage, StagingRegistry
from coffer.domain.resource import Resource
from coffer.domain.skill.source_status import SourceStatus

logger = logging.getLogger(__name__)


class SkillSourceService:
    def __init__(
        self,
        *,
        skills: SkillService,
        git: GitSourcePort,
        archives: ArchiveReaderPort,
        status_repo: SourceStatusRepoPort,
        staging: StagingRegistry | None = None,
        size_limit_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self.skills = skills
        self.git = git
        self.archives = archives
        self.status_repo = status_repo
        self.staging = staging or StagingRegistry()
        self.size_limit = size_limit_bytes

    # ---------- staging an import ----------

    async def stage_folder(self, path: str) -> ImportStage:
        return await source_stage_ops.stage_folder(self, path)

    async def stage_archive(self, stream: IO[bytes], filename: str) -> ImportStage:
        return await source_stage_ops.stage_archive(self, stream, filename)

    async def stage_git(self, url: str, ref: str | None, path: str | None) -> ImportStage:
        return await source_stage_ops.stage_git(self, url, ref, path)

    async def confirm(
        self, stage_id: str, *, names: list[str], replace: list[str], actor: str
    ) -> list[Resource]:
        return await source_stage_ops.confirm(
            self, stage_id, names=names, replace=replace, actor=actor
        )

    def cancel(self, stage_id: str) -> bool:
        return self.staging.discard(stage_id)

    # ---------- a Git-imported skill's updates ----------

    async def statuses(self) -> dict[int, SourceStatus]:
        return await self.status_repo.list_all()

    async def status(self, skill: Resource) -> SourceStatus | None:
        return await self.status_repo.get(skill.id)

    async def check(self, uid: str) -> SourceStatus:
        return await update_ops.check(self, await self.skills.get_skill(uid))

    async def check_due(self) -> int:
        return await update_ops.check_due(self)

    async def preview(self, uid: str) -> update_ops.UpdatePreview:
        return await update_ops.preview(self, await self.skills.get_skill(uid))

    async def change_source(
        self, uid: str, url: str, ref: str | None, path: str | None
    ) -> update_ops.UpdatePreview:
        return await source_change_ops.preview_change(
            self, await self.skills.get_skill(uid), url, ref, path
        )

    async def compare(self, uid: str, stage_id: str, path: str) -> update_ops.CompareView:
        return update_ops.compare(self, await self.skills.get_skill(uid), stage_id, path)

    async def apply(
        self, uid: str, stage_id: str, *, discard_local_edits: bool, actor: str
    ) -> Resource:
        return await update_ops.apply(
            self,
            await self.skills.get_skill(uid),
            stage_id,
            discard_local_edits=discard_local_edits,
            actor=actor,
        )

    async def keep_mine(self, uid: str, commit: str | None) -> SourceStatus:
        return await update_ops.keep_mine(self, await self.skills.get_skill(uid), commit)

    def close(self) -> None:
        self.staging.close()


class SkillUpdateWorker:
    """Checks every Git-imported skill every six hours (spec skill-manager
    "Update a Git-imported skill from its source").

    Each round checks only the skills not checked within the interval, so a
    daemon restarted often does not fetch every repository on every start. The
    first round waits ``first_delay_s`` so startup never waits on the network.
    A failure is logged and the loop goes on.
    """

    def __init__(
        self,
        service: SkillSourceService,
        *,
        interval_s: float = update_ops.CHECK_INTERVAL.total_seconds(),
        first_delay_s: float = 60.0,
    ) -> None:
        self._svc = service
        self._interval = interval_s
        self._first_delay = first_delay_s
        self._task: asyncio.Task[None] | None = None

    async def run(self) -> None:
        await asyncio.sleep(self._first_delay)
        while True:
            try:
                await self._svc.check_due()
            except Exception:
                logger.warning("skill.update_check.failed", exc_info=True)
            await asyncio.sleep(self._interval)

    def start(self) -> asyncio.Task[None]:
        self._task = asyncio.create_task(self.run())
        return self._task

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task
        self._task = None


__all__ = ["SkillSourceService", "SkillUpdateWorker"]
