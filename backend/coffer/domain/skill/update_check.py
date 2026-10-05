"""How often this machine looks for updates to Git-imported skills in the background.

Spec skill-manager "Hand a Git-imported skill's update to an agent": the
background ``git fetch`` is this machine's own choice (Settings > General,
**Check skills for updates**), kept in ``~/.coffer/daemon-config.json`` and
never synced. **Check for updates** on a skill works whatever it says.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal, get_args

UpdateCheckChoice = Literal["6h", "1d", "7d", "manual"]

CHOICES: tuple[str, ...] = get_args(UpdateCheckChoice)
DEFAULT_CHOICE: UpdateCheckChoice = "6h"

_INTERVALS: dict[str, timedelta] = {
    "6h": timedelta(hours=6),
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
}


def interval_of(choice: str) -> timedelta | None:
    """The gap between background checks of one skill; ``None`` for **Only when I ask**."""
    return _INTERVALS.get(choice)


__all__ = ["CHOICES", "DEFAULT_CHOICE", "UpdateCheckChoice", "interval_of"]
