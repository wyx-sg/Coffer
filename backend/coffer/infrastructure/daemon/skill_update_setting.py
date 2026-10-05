"""The skill update check's setting, kept in ``~/.coffer/daemon-config.json``."""

from __future__ import annotations

from coffer.domain.skill.update_check import CHOICES, DEFAULT_CHOICE, UpdateCheckChoice
from coffer.infrastructure.daemon import config as daemon_config


class DaemonConfigUpdateCheck:
    """``UpdateCheckSettingPort`` over the daemon config's ``skill_update_check``."""

    def read(self) -> UpdateCheckChoice:
        stored = daemon_config.read_skill_update_check()
        return stored if stored in CHOICES else DEFAULT_CHOICE  # type: ignore[return-value]

    def write(self, choice: UpdateCheckChoice) -> None:
        daemon_config.write_skill_update_check(choice)
