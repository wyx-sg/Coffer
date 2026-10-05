"""SkillSourceService — where a skill comes from, and what is newer there.

The front door for spec skill-manager "Add skills from an archive", "Add
skills from a Git repository" and "Hand a Git-imported skill's update to an
agent". It owns the staging registry and the three adapters those need (the
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

from coffer.application.runtime.supervisor import spawn
from coffer.application.skill import (
    source_change_ops,
    source_stage_ops,
    update_merge,
    update_ops,
)
from coffer.application.skill.ports import (
    ArchiveReaderPort,
    GitSourcePort,
    SourceStatusRepoPort,
    UpdateCheckSettingPort,
)
from coffer.application.skill.service import SkillService
from coffer.application.skill.staging import ImportStage, StagingRegistry
from coffer.application.upkeep_schedule import SLICE_S
from coffer.domain.resource import Resource
from coffer.domain.skill.source_status import SourceStatus
from coffer.domain.skill.update_check import DEFAULT_CHOICE, UpdateCheckChoice, interval_of

logger = logging.getLogger(__name__)


class SkillSourceService:
    def __init__(
        self,
        *,
        skills: SkillService,
        git: GitSourcePort,
        archives: ArchiveReaderPort,
        status_repo: SourceStatusRepoPort,
        update_check: UpdateCheckSettingPort | None = None,
        staging: StagingRegistry | None = None,
        size_limit_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self.skills = skills
        self.git = git
        self.archives = archives
        self.status_repo = status_repo
        self.update_check = update_check
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

    async def statuses(self) -> dict[str, SourceStatus]:
        return await self.status_repo.list_all()

    async def status(self, skill: Resource) -> SourceStatus | None:
        return await self.status_repo.get(skill.uid)

    async def check(self, uid: str) -> SourceStatus:
        return await update_ops.check(self, await self.skills.get_skill(uid))

    async def check_due(self) -> int:
        """Check the skills due under this machine's setting; none for **Only when I ask**."""
        interval = interval_of(self.update_check_choice())
        return 0 if interval is None else await update_ops.check_due(self, interval)

    def update_check_choice(self) -> UpdateCheckChoice:
        return self.update_check.read() if self.update_check else DEFAULT_CHOICE

    def set_update_check_choice(self, choice: UpdateCheckChoice) -> UpdateCheckChoice:
        """Keep the choice on this machine; the worker reads it again on its next slice."""
        if self.update_check is not None:
            self.update_check.write(choice)
        return self.update_check_choice()

    async def handoff(self, uid: str) -> update_ops.UpdateHandoff:
        return await update_ops.handoff(self, await self.skills.get_skill(uid))

    async def change_source(
        self, uid: str, url: str, ref: str | None, path: str | None
    ) -> source_change_ops.SourceChangePreview:
        return await source_change_ops.preview_change(
            self, await self.skills.get_skill(uid), url, ref, path
        )

    async def apply_change(self, uid: str, stage_id: str, *, actor: str) -> Resource:
        return await source_change_ops.apply_change(
            self, await self.skills.get_skill(uid), stage_id, actor=actor
        )

    async def mark_merged(self, uid: str, commit: str, *, actor: str) -> Resource:
        return await update_merge.mark_merged(
            self, await self.skills.get_skill(uid), commit, actor=actor
        )

    def close(self) -> None:
        self.staging.close()


class SkillUpdateWorker:
    """Checks Git-imported skills in the background on this machine's schedule
    (spec skill-manager "Hand a Git-imported skill's update to an agent").

    The setting is read again every slice (``upkeep_schedule.SLICE_S``), so a
    change of **Check skills for updates** takes effect within one slice and
    **Only when I ask** stops the background checks. Each round checks only the
    skills not checked within the chosen interval, so a daemon restarted often
    does not fetch every repository on every start. The first round waits
    ``first_delay_s`` so startup never waits on the network. A failure is
    logged and the loop goes on.
    """

    def __init__(
        self,
        service: SkillSourceService,
        *,
        slice_s: float = SLICE_S,
        first_delay_s: float = 60.0,
    ) -> None:
        self._svc = service
        self._slice = slice_s
        self._first_delay = first_delay_s
        self._task: asyncio.Task[None] | None = None

    async def run(self) -> None:
        await asyncio.sleep(self._first_delay)
        while True:
            try:
                await self._svc.check_due()
            except Exception:
                logger.warning("skill.update_check.failed", exc_info=True)
            await asyncio.sleep(self._slice)

    def start(self) -> asyncio.Task[None]:
        self._task = spawn(self.run(), name="skill-source-updates")
        return self._task

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task
        self._task = None


__all__ = ["SkillSourceService", "SkillUpdateWorker"]
