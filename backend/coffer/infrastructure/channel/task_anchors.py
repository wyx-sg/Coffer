"""Where each switched-on scheduled task's slots are counted from:
``~/.coffer/local/scheduled-task-anchors.json`` (ADR
a-missed-run-is-caught-up-within-seven-days).

Machine-local state, like the tasks themselves. Losing the file costs at most
one catch-up: every task then counts from the scheduler's next pass. The path
is resolved from ``HOME`` on every call, so a test's throwaway home moves it.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from coffer.application.channel.schedule.ports import Anchor
from coffer.infrastructure.vault.atomic import atomic_write
from coffer.infrastructure.vault.home import local_root

__all__ = ["TaskAnchors"]


class TaskAnchors:
    def _path(self) -> Path:
        return local_root() / "scheduled-task-anchors.json"

    def all(self) -> dict[str, Anchor]:
        try:
            raw = json.loads(self._path().read_text(encoding="utf-8"))
            return {
                uid: Anchor(schedule=str(a["schedule"]), at=datetime.fromisoformat(a["at"]))
                for uid, a in raw.items()
            }
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return {}

    def replace(self, anchors: dict[str, Anchor]) -> None:
        data = {uid: {"schedule": a.schedule, "at": a.at.isoformat()} for uid, a in anchors.items()}
        atomic_write(self._path(), json.dumps(data, indent=2, sort_keys=True).encode("utf-8"))
