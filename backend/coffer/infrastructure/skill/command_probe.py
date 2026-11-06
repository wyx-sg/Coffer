"""Find a command a skill requires where the agent runs it.

``CommandProbe`` looks the command up on the agent's real ``PATH``
(``UserPath``, the login shell's merged with the inherited one). It runs
nothing: whether a tool is new enough or logged in is the agent's to find out
when it uses it (ADR agents-check-cli-logins-themselves).
"""

from __future__ import annotations

import os
import pathlib
import shutil
from collections.abc import Callable

from coffer.infrastructure.platform.process import executable_name


class CommandProbe:
    """``CommandProbePort`` over the machine."""

    def __init__(self, *, user_path: Callable[[], str]) -> None:
        self._user_path = user_path

    def locate(self, command: str) -> str | None:
        """The command as the agent's ``PATH`` resolves it, symlinks followed.
        An absolute path is the file itself, when it can be run."""
        if os.path.isabs(command):
            file = pathlib.Path(command)
            return str(file.resolve()) if file.is_file() and os.access(file, os.X_OK) else None
        found = shutil.which(executable_name(command), path=self._user_path())
        if found is None:
            return None
        try:
            return str(pathlib.Path(found).resolve())
        except OSError:
            return None


__all__ = ["CommandProbe"]
