"""The agent's real ``PATH``: what a program a user runs from a terminal sees.

The daemon's own ``PATH`` is often the truncated one a GUI launch gets, so a
program is looked up on the user's login-shell ``PATH`` merged with the
inherited one. Kind-agnostic: agent detection finds an agent's program on it,
and the skill kind finds the commands a skill requires on it.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable

from coffer.infrastructure.platform.process import login_shell_path

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


__all__ = ["UserPath"]
