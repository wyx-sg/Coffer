"""Whether this machine has a git the vault can run on (spec daemon "Wait in a
setup state when git is missing or too old").

The vault is a git repository and every sync round's merge needs git 2.40
(``merge-tree --write-tree --merge-base``; ADR
sync-applies-clean-merges-and-stops-on-any-conflict), so the daemon asks this
before it opens the vault, and again each time the person presses Check again.

git is looked for on two ``PATH`` values, in order:

1. the daemon's own — what every vault call runs with;
2. the person's login shell's (``login_shell_path``) — a daemon started from
   the Dock or by a GUI editor's MCP shim gets the truncated ``PATH`` macOS
   hands a GUI launch, while the git the person installed sits in Homebrew or
   ``~/.local/bin``, which only the login shell lists.

A git good enough only on the login shell's ``PATH`` is still a git Coffer can
use: :func:`use_git_dir` puts its directory first on this process's ``PATH``, so
every later vault call — and a restarted successor, which inherits this
environment — runs it. The answer is never cached: a git installed a moment ago
is found on the next check.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from coffer.infrastructure.platform.process import executable_name, login_shell_path

_log = logging.getLogger(__name__)

#: ``merge-tree --write-tree`` needs git 2.38; ``--merge-base`` needs 2.40.
MIN_GIT = (2, 40)
_VERSION_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class FoundGit:
    """One ``git`` on one ``PATH``: where it is and the version it reports."""

    path: str
    version: tuple[int, int]


@dataclass(frozen=True)
class GitCheck:
    """What a check found. ``usable`` is a git of :data:`MIN_GIT` or later;
    ``found`` is the best git seen when none is (``None``: no git at all)."""

    usable: FoundGit | None
    found: FoundGit | None
    #: The usable git sits only on the login shell's ``PATH``.
    from_login_path: bool = False

    @property
    def ok(self) -> bool:
        return self.usable is not None

    @property
    def found_version(self) -> str | None:
        return None if self.found is None else version_text(self.found.version)


def version_text(version: tuple[int, int]) -> str:
    return f"{version[0]}.{version[1]}"


def parse_version(output: str) -> tuple[int, int] | None:
    """``git version 2.39.5 (Apple Git-154)`` → ``(2, 39)``; ``None`` when unreadable."""
    words = output.split()
    try:
        major, minor = words[2].split(".")[:2]
        return int(major), int(minor)
    except (IndexError, ValueError):
        return None


def find_git(search_path: str) -> FoundGit | None:
    """The ``git`` on ``search_path`` and its version; ``None`` when there is
    none, or it does not answer ``--version`` with a version."""
    located = shutil.which(executable_name("git"), path=search_path)
    if located is None:
        return None
    try:
        done = subprocess.run(
            [located, "--version"],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=_VERSION_TIMEOUT_S,
            check=False,
            env={**os.environ, "PATH": search_path},
        )
    except (OSError, subprocess.TimeoutExpired):
        _log.warning("git.version_probe_failed", extra={"path": located}, exc_info=True)
        return None
    version = parse_version(done.stdout.decode("utf-8", "replace"))
    if done.returncode != 0 or version is None:
        return None
    return FoundGit(path=located, version=version)


def check_git(
    *,
    daemon_path: str | None = None,
    login_path: Callable[[], str] = login_shell_path,
    finder: Callable[[str], FoundGit | None] = find_git,
) -> GitCheck:
    """Look for a usable git on the daemon's ``PATH``, then the login shell's."""
    own = finder(os.environ.get("PATH", "") if daemon_path is None else daemon_path)
    if own is not None and own.version >= MIN_GIT:
        return GitCheck(usable=own, found=own)
    login = finder(login_path())
    if login is not None and login.version >= MIN_GIT:
        return GitCheck(usable=login, found=login, from_login_path=True)
    seen = [g for g in (own, login) if g is not None]
    best = max(seen, key=lambda g: g.version) if seen else None
    return GitCheck(usable=None, found=best)


def use_git_dir(check: GitCheck) -> None:
    """Put the usable git's directory first on this process's ``PATH`` when it
    was found only on the login shell's, so every vault call runs it."""
    if check.usable is None or not check.from_login_path:
        return
    directory = str(Path(check.usable.path).parent)
    entries = [e for e in os.environ.get("PATH", "").split(os.pathsep) if e and e != directory]
    os.environ["PATH"] = os.pathsep.join([directory, *entries])
    _log.warning(
        "git.using_login_shell_git",
        extra={"path": check.usable.path, "version": version_text(check.usable.version)},
    )


__all__ = [
    "MIN_GIT",
    "FoundGit",
    "GitCheck",
    "check_git",
    "find_git",
    "parse_version",
    "use_git_dir",
    "version_text",
]
