"""Check a command a skill requires where the agent runs it.

``CommandProbe`` finds the command on the agent's real ``PATH`` (``UserPath``,
the login shell's merged with the inherited one), reads ``<path> --version``
and runs the declared login check. Every run is argv with no shell, ``stdin``
closed and a timeout. The login check's stdout and stderr go to
``subprocess.DEVNULL``: a login check may print a token or an account name,
and none of it is read, kept, logged or returned — only the exit status is.
"""

from __future__ import annotations

import contextlib
import logging
import os
import pathlib
import shutil
import subprocess
import threading
from collections.abc import Callable, Sequence

from coffer.domain.versions import parse_version
from coffer.infrastructure.platform.process import executable_name

_log = logging.getLogger(__name__)

VERSION_TIMEOUT_SECONDS = 5.0
LOGIN_TIMEOUT_SECONDS = 10.0
#: The most of a ``--version`` answer that is read.
MAX_VERSION_OUTPUT = 64 * 1024


class CommandProbe:
    """``CommandProbePort`` over the machine."""

    def __init__(
        self,
        *,
        user_path: Callable[[], str],
        version_timeout: float = VERSION_TIMEOUT_SECONDS,
        login_timeout: float = LOGIN_TIMEOUT_SECONDS,
    ) -> None:
        self._user_path = user_path
        self._version_timeout = version_timeout
        self._login_timeout = login_timeout

    def locate(self, command: str) -> str | None:
        """The command as the agent's ``PATH`` resolves it, symlinks followed."""
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

    def login_ok(self, argv: Sequence[str]) -> bool | None:
        """``True`` when the login check exits 0, ``False`` on any other exit,
        ``None`` when it could not run or ran past its timeout. Its output is
        discarded unread."""
        try:
            result = subprocess.run(
                list(argv),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self._login_timeout,
                env=self._env(),
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            # Only the program is named: the arguments are the skill's, and
            # nothing the check printed was ever read.
            _log.debug("skill.command_probe.login_check_failed program=%s", argv[0])
            return None
        return result.returncode == 0

    def _env(self) -> dict[str, str]:
        return {**os.environ, "PATH": self._user_path()}


__all__ = ["LOGIN_TIMEOUT_SECONDS", "MAX_VERSION_OUTPUT", "VERSION_TIMEOUT_SECONDS", "CommandProbe"]
