"""The dependency probe facet: is the agent's program on its real ``PATH``, and
which version (ADR agent-mechanisms-are-optional-facets-on-the-descriptor).

The daemon's own ``PATH`` is often the truncated one a GUI launch gets, so the
program is looked up on the user's login-shell ``PATH`` merged with the
inherited one — the ``PATH`` the agent itself runs with when the user starts
it from a terminal. The version comes from ``<program> --version`` under a
bounded timeout: a flag both shipped agents answer without a login, a network
call or a config directory.

Generic: one probe per agent, built from the descriptor's program name at the
composition root. The per-OS parts — the login-shell lookup and the
executable's file name — come from the platform package.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shutil
import subprocess
import threading
from collections.abc import Callable

from coffer.domain.agent.detection import ProgramInfo, parse_version
from coffer.infrastructure.platform.process import executable_name, login_shell_path

_log = logging.getLogger(__name__)

#: ``--version`` is expected back in well under a second; a program that takes
#: longer is reported installed with no version rather than holding a request.
VERSION_TIMEOUT_SECONDS = 5.0


#: The login shell's ``PATH``, per lookup function, shared across the process.
_SHELL_PATHS: dict[Callable[[], str], str] = {}
_SHELL_LOCK = threading.Lock()


class UserPath:
    """The agent's real ``PATH``: the login shell's entries, then any inherited
    entry the shell did not list. Asked of the shell once per process — the
    directories a user keeps tools in rarely move, and a program installed
    into one of them later is still found, because the lookup itself is made
    on every probe. The login shell's answer is shared by every instance in
    the process; the inherited ``PATH`` is read at each call."""

    def __init__(self, shell_path: Callable[[], str] = login_shell_path) -> None:
        self._shell_path = shell_path

    def __call__(self) -> str:
        with _SHELL_LOCK:
            shell = _SHELL_PATHS.get(self._shell_path)
            if shell is None:
                shell = self._shell_path()
                _SHELL_PATHS[self._shell_path] = shell
        return _merge(shell, os.environ.get("PATH", ""))


def _merge(first: str, second: str) -> str:
    seen: list[str] = []
    for entry in (*first.split(os.pathsep), *second.split(os.pathsep)):
        if entry and entry not in seen:
            seen.append(entry)
    return os.pathsep.join(seen)


#: (resolved path, mtime_ns, size) -> version, shared by every probe in the
#: process: a binary is asked once. An upgrade replaces the file, which moves
#: the key, so a stale version is never served.
_VERSIONS: dict[tuple[str, int, int], str | None] = {}
_VERSIONS_LOCK = threading.Lock()


class ProgramProbe:
    """``DependencyProbe`` for one program name."""

    def __init__(
        self,
        program: str,
        *,
        user_path: Callable[[], str],
        timeout: float = VERSION_TIMEOUT_SECONDS,
    ) -> None:
        self._program = program
        self._user_path = user_path
        self._timeout = timeout

    @property
    def program(self) -> str:
        return self._program

    def probe(self) -> ProgramInfo:
        path = self.locate()
        if path is None:
            return ProgramInfo()
        try:
            stat = path.stat()
        except OSError:
            return ProgramInfo()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        with _VERSIONS_LOCK:
            if key in _VERSIONS:
                return ProgramInfo(path=str(path), version=_VERSIONS[key])
        version = self._version(path)
        with _VERSIONS_LOCK:
            _VERSIONS[key] = version
        return ProgramInfo(path=str(path), version=version)

    def locate(self) -> pathlib.Path | None:
        """The program as the agent's ``PATH`` resolves it, symlinks followed."""
        found = shutil.which(executable_name(self._program), path=self._user_path())
        if found is None:
            return None
        try:
            return pathlib.Path(found).resolve()
        except OSError:
            return None

    def _version(self, path: pathlib.Path) -> str | None:
        env = {**os.environ, "PATH": self._user_path()}
        try:
            result = subprocess.run(
                [str(path), "--version"],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                stdin=subprocess.DEVNULL,
                env=env,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            _log.debug(
                "agent.program_probe.version_failed program=%s", self._program, exc_info=True
            )
            return None
        return parse_version(result.stdout) or parse_version(result.stderr)


__all__ = ["VERSION_TIMEOUT_SECONDS", "ProgramProbe", "UserPath"]
