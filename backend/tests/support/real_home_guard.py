"""The real-home guard: no test may touch the developer's real ``~/.coffer``.

Two layers, because either one alone has a known way to fail.

1. **Redirection** (:func:`isolate_process_env`). Every path Coffer derives
   comes from ``$HOME`` (``Path.home()``, ``expanduser``, or
   ``os.environ["HOME"]``) or from a ``COFFER_*`` override. At import time the
   root conftest points ``HOME`` at a throwaway directory, strips every
   ``COFFER_*`` variable inherited from the developer's shell, and drops the
   agent-home variables (``CLAUDE_CONFIG_DIR``, ``CODEX_HOME``) and the
   ``XDG_*`` roots, so a forgotten fixture resolves into the throwaway tree
   instead of the live one. Subprocesses inherit ``os.environ``, so the daemon,
   shim and CLI a test spawns land there too.

2. **Tripwire** (:class:`RealHomeGuard`). Redirection is defeated by the one
   thing tests do all the time: rewrite ``HOME``. A test that deletes it makes
   ``expanduser`` fall back to the password database — the real home — and a
   subprocess spawned with a hand-built ``env`` that omits ``HOME`` does the
   same. So an audit hook (:func:`sys.addaudithook`, PEP 578) watches every
   ``open``, directory, rename/remove, ``shutil`` tree, ``sqlite3.connect`` and
   spawn event in the interpreter and refuses any whose path lies under a
   protected directory of the real home. It raises before the syscall runs —
   the guarded write never happens — and it records the violation, because a
   raised ``PermissionError`` can be swallowed by code that tolerates an
   unreadable file; the root conftest fails the test from the record.

Why an audit hook rather than monkeypatching ``Path.home``: the code reads the
home through three different routes (and ``sqlite3``/``shutil``/``subprocess``
never consult ``Path.home`` at all), a monkeypatch covers one route and can be
undone by the next ``monkeypatch.undo``, whereas the hook sees the path at the
point of use whichever way it was computed and cannot be uninstalled. The cost
is one string-prefix check per event; the realpath fallback only runs for paths under
the real home, where a symlinked subtree could lead into a protected root.
"""

from __future__ import annotations

import contextlib
import os
import pwd
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

#: Directories (and one file) under the real home that a test must never
#: touch: Coffer's own vault, and the agent config trees Coffer writes into.
PROTECTED_NAMES: tuple[str, ...] = (".coffer", ".claude", ".claude.json", ".codex", ".agents")

#: Carries the real home into nested pytest processes, whose ``HOME`` is
#: already the throwaway one by the time their conftest runs.
REAL_HOME_ENV = "COFFER_TEST_REAL_HOME"

#: ``COFFER_*`` variables that steer the test run itself rather than the code
#: under test, and so survive the strip.
_KEPT_COFFER_PREFIXES: tuple[str, ...] = ("COFFER_RUN_", "COFFER_SMOKE_", "COFFER_TEST_")

#: Variables that would send an agent, git or an XDG-aware library to a
#: directory other than the one ``HOME`` implies.
_DROPPED_VARS: tuple[str, ...] = (
    "CLAUDE_CONFIG_DIR",
    "CODEX_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_STATE_HOME",
    "GIT_CONFIG_GLOBAL",
)

#: Audit event -> positions of its path arguments (CPython 3.12 event table).
_PATH_EVENTS: dict[str, tuple[int, ...]] = {
    "open": (0,),
    "os.listdir": (0,),
    "os.scandir": (0,),
    "os.mkdir": (0,),
    "os.rename": (0, 1),
    "os.remove": (0,),
    "os.rmdir": (0,),
    "os.symlink": (0, 1),
    "os.link": (0, 1),
    "os.chmod": (0,),
    "os.chown": (0,),
    "os.chflags": (0,),
    "os.truncate": (0,),
    "os.utime": (0,),
    "os.chdir": (0,),
    "os.mkfifo": (0,),
    "os.mknod": (0,),
    "os.setxattr": (0,),
    "os.removexattr": (0,),
    "os.exec": (0,),
    "os.posix_spawn": (0,),
    "os.spawn": (1,),
    "glob.glob": (0,),
    "shutil.rmtree": (0,),
    "shutil.copyfile": (0, 1),
    "shutil.copytree": (0, 1),
    "shutil.copymode": (0, 1),
    "shutil.copystat": (0, 1),
    "shutil.move": (0, 1),
    "shutil.chown": (0,),
    "sqlite3.connect": (0,),
    "subprocess.Popen": (0, 2),
}

#: Spawn events -> position of their ``env`` argument.
_ENV_EVENTS: dict[str, int] = {"subprocess.Popen": 3, "os.exec": 2, "os.posix_spawn": 2}

#: System tools that never read ``$HOME`` — they answer from the OS alone — so
#: spawning one with a scrubbed env cannot reach the real home. Library code
#: does exactly that on Linux: ``ctypes.util.find_library`` runs
#: ``/sbin/ldconfig -p`` with ``env={"LC_ALL": "C", "LANG": "C"}``, the first
#: time anything in the process looks a shared library up.
_HOME_BLIND_PROGRAMS: frozenset[str] = frozenset({"ldconfig"})

#: Variables a CI runner or a developer's terminal sets that change how the CLI
#: renders, and so what a test reads back: ``FORCE_COLOR`` / ``PY_COLORS`` /
#: ``TTY_COMPATIBLE`` make rich (and typer, which also reads
#: ``GITHUB_ACTIONS``) treat a captured stream as a terminal — wrapping every
#: token of an error panel in ANSI codes, and under ``TERM=dumb`` ignoring
#: ``COLUMNS`` for a fixed 80-column table. ``COLUMNS`` / ``LINES`` are dropped
#: because a rich ``Console`` built at import freezes the width it finds then.
_TERMINAL_VARS: tuple[str, ...] = (
    "FORCE_COLOR",
    "PY_COLORS",
    "TTY_COMPATIBLE",
    "COLUMNS",
    "LINES",
)

_GITCONFIG = "[user]\n\tname = Coffer Tests\n\temail = tests@coffer.invalid\n"


class RealHomeAccessError(PermissionError):
    """Raised, in place of the syscall, when a test touches the real home."""


@dataclass(frozen=True)
class Violation:
    event: str
    detail: str

    def __str__(self) -> str:
        return f"{self.event}: {self.detail}"


def real_homes() -> tuple[str, ...]:
    """Every spelling of the real home: the password database's, plus the
    ``HOME`` this process started with — or, in a nested pytest run whose
    ``HOME`` is already a throwaway one, the real home its parent recorded."""
    homes = {pwd.getpwuid(os.getuid()).pw_dir}
    recorded = os.environ.get(REAL_HOME_ENV)
    started = recorded if recorded else os.environ.get("HOME")
    if started:
        homes.update(part for part in started.split(os.pathsep) if part)
    return tuple(sorted(homes))


def write_home_skeleton(home: Path) -> Path:
    """Make ``home`` usable as ``$HOME``: exists, and git can commit in it."""
    home.mkdir(parents=True, exist_ok=True)
    gitconfig = home / ".gitconfig"
    if not gitconfig.exists():
        gitconfig.write_text(_GITCONFIG, encoding="utf-8")
    return home


def isolate_process_env(fake_home: Path, real: tuple[str, ...]) -> None:
    """Point this process (and everything it spawns) at ``fake_home``."""
    os.environ.setdefault(REAL_HOME_ENV, os.pathsep.join(real))
    for name in list(os.environ):
        if name.startswith("COFFER_") and not name.startswith(_KEPT_COFFER_PREFIXES):
            del os.environ[name]
    for name in _DROPPED_VARS:
        os.environ.pop(name, None)
    for name in _TERMINAL_VARS:
        os.environ.pop(name, None)
    # No colour, and never a terminal: typer forces one under GITHUB_ACTIONS
    # unless told not to.
    os.environ["NO_COLOR"] = "1"
    os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"
    os.environ["HOME"] = str(write_home_skeleton(fake_home))


def _as_path(value: object) -> str | None:
    if isinstance(value, int) or value is None:
        return None  # a file descriptor, or an argument the call left unset
    try:
        raw = os.fspath(value)  # type: ignore[arg-type]
    except TypeError:
        return None
    return os.path.abspath(os.fsdecode(raw))


class RealHomeGuard:
    """The tripwire. One per process; :meth:`install` is idempotent."""

    def __init__(self, homes: tuple[str, ...]) -> None:
        expanded: set[str] = set()
        for home in homes:
            for part in home.split(os.pathsep):
                if part:
                    expanded.update({os.path.abspath(part), os.path.realpath(part)})
        self.homes = tuple(sorted(expanded))
        self.roots = tuple(
            os.path.join(home, name) for home in self.homes for name in PROTECTED_NAMES
        )
        self._violations: list[Violation] = []
        self._lock = threading.Lock()
        self._busy = threading.local()
        self._installed = False

    # --- matching -----------------------------------------------------------

    def protected_root(self, path: str) -> str | None:
        """The protected root ``path`` falls under, or ``None``."""
        for root in self.roots:
            if path == root or path.startswith(root + os.sep):
                return root
        return None

    def _check(self, path: str) -> str | None:
        hit = self.protected_root(path)
        if hit is None and any(path.startswith(home) for home in self.homes):
            hit = self.protected_root(os.path.realpath(path))
        return hit

    # --- the hook -----------------------------------------------------------

    def install(self) -> None:
        if not self._installed:
            sys.addaudithook(self._hook)
            self._installed = True

    def _hook(self, event: str, args: tuple[object, ...]) -> None:
        positions = _PATH_EVENTS.get(event)
        if positions is None or getattr(self._busy, "on", False):
            return
        self._busy.on = True
        try:
            detail = self._inspect(event, args, positions)
        finally:
            self._busy.on = False
        if detail is not None:
            violation = Violation(event, detail)
            with self._lock:
                self._violations.append(violation)
            raise RealHomeAccessError(f"test touched the real home — {violation}")

    def _inspect(
        self, event: str, args: tuple[object, ...], positions: tuple[int, ...]
    ) -> str | None:
        for index in positions:
            path = _as_path(args[index]) if index < len(args) else None
            if path is not None and self._check(path) is not None:
                return path
        env_index = _ENV_EVENTS.get(event)
        if env_index is None:
            return None
        env = args[env_index] if env_index < len(args) else None
        home = os.environ.get("HOME") if env is None else _env_home(env)
        if home is None:
            if os.path.basename(os.fsdecode(args[0])) in _HOME_BLIND_PROGRAMS:
                return None
            return f"spawned {args[0]!r} with no HOME in its env (it falls back to the real one)"
        if os.path.abspath(home) in self.homes:
            return f"spawned {args[0]!r} with HOME={home}, the real home"
        return None

    # --- the record ---------------------------------------------------------

    def drain(self) -> list[Violation]:
        with self._lock:
            taken, self._violations = self._violations, []
        return taken

    @contextlib.contextmanager
    def expect_violation(self) -> Iterator[list[Violation]]:
        """For the guard's own tests: collect what fired inside the block and
        keep it out of the per-test record, so the test can assert on it."""
        before = self.drain()
        caught: list[Violation] = []
        try:
            yield caught
        finally:
            caught.extend(self.drain())
            with self._lock:
                self._violations[:0] = before


def _env_home(env: object) -> str | None:
    getter = getattr(env, "get", None)
    if getter is None:
        return None
    value = getter("HOME")
    if value is None:
        value = getter(b"HOME")
    return os.fsdecode(value) if value is not None else None


#: The process-wide guard, created and installed by the root conftest.
GUARD: RealHomeGuard | None = None


def install(fake_home: Path) -> RealHomeGuard:
    """Redirect, then arm the tripwire. Called once, before ``coffer`` imports."""
    global GUARD
    if GUARD is None:
        real = real_homes()
        isolate_process_env(fake_home, real)
        GUARD = RealHomeGuard(real)
        GUARD.install()
    return GUARD
