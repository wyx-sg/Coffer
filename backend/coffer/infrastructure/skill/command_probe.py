"""Check a command a skill requires where the agent runs it.

``CommandProbe`` finds the command on the agent's real ``PATH`` (``UserPath``,
the login shell's merged with the inherited one) and reads ``<path> --version``,
as argv with no shell, ``stdin`` closed and a timeout. That is the only program
it runs.
"""

from __future__ import annotations

import contextlib
import logging
import os
import pathlib
import shutil
import subprocess
import threading
from collections.abc import Callable

from coffer.domain.versions import parse_version
from coffer.infrastructure.platform.process import executable_name

_log = logging.getLogger(__name__)

VERSION_TIMEOUT_SECONDS = 5.0
#: The most of a ``--version`` answer that is read.
MAX_VERSION_OUTPUT = 64 * 1024


class CommandProbe:
    """``CommandProbePort`` over the machine."""

    def __init__(
        self,
        *,
        user_path: Callable[[], str],
        version_timeout: float = VERSION_TIMEOUT_SECONDS,
    ) -> None:
        self._user_path = user_path
        self._version_timeout = version_timeout

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

    def version(self, path: str) -> str | None:
        """What ``<path> --version`` prints, read up to ``MAX_VERSION_OUTPUT``
        bytes: a command that never stops printing cannot fill the daemon's memory."""
        try:
            proc = subprocess.Popen(
                [path, "--version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=self._env(),
            )
        except OSError:
            _log.debug("skill.command_probe.version_failed path=%s", path, exc_info=True)
            return None
        timer = threading.Timer(self._version_timeout, proc.kill)
        timer.start()
        try:
            assert proc.stdout is not None
            raw = proc.stdout.read(MAX_VERSION_OUTPUT)
        except (OSError, ValueError):
            return None
        finally:
            timer.cancel()
            proc.kill()
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                proc.wait(timeout=2)
            if proc.stdout is not None:
                proc.stdout.close()
        return parse_version(raw.decode("utf-8", errors="replace"))

    def _env(self) -> dict[str, str]:
        return {**os.environ, "PATH": self._user_path()}


__all__ = ["MAX_VERSION_OUTPUT", "VERSION_TIMEOUT_SECONDS", "CommandProbe"]
