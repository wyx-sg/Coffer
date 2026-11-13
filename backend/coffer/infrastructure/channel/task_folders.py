"""Each scheduled task's own folder: ``~/.coffer/content/workspace/scheduled-tasks/<uid>/``
(ADR automation-is-a-scheduled-prompt).

It holds the task's ``PROMPT.md`` and is where its runs work unless the task
names another folder, so what they write is there to read. It sits in Coffer's
workspace, which is ``content``: the user's only copy, not synced. The path is
resolved from ``HOME`` on every call, so a test's throwaway home moves it.
"""

from __future__ import annotations

from pathlib import Path

from coffer.domain.channel.scheduled_task import PROMPT_FILE
from coffer.infrastructure.vault.home import content_root

__all__ = ["TaskFolders"]


class TaskFolders:
    def _dir(self, task_uid: str) -> Path:
        if not task_uid or "/" in task_uid or task_uid.startswith("."):
            raise ValueError(f"not a task uid: {task_uid!r}")
        return content_root() / "workspace" / "scheduled-tasks" / task_uid

    def path(self, task_uid: str) -> str:
        folder = self._dir(task_uid)
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)

    def exists(self, path: str) -> bool:
        return Path(path).is_dir()

    def read_prompt(self, task_uid: str) -> str | None:
        try:
            return (self._dir(task_uid) / PROMPT_FILE).read_text(encoding="utf-8")
        except (FileNotFoundError, IsADirectoryError):
            return None

    def write_prompt(self, task_uid: str, text: str) -> None:
        target = Path(self.path(task_uid)) / PROMPT_FILE
        tmp = target.with_name(f".{PROMPT_FILE}.tmp")
        tmp.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        tmp.replace(target)
