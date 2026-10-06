"""Running an installed binary as a person's terminal would, and keeping what it said.

``run`` keeps stdout and stderr apart, so a suite can tell "the error is one
JSON object on stderr" from "something else leaked onto either stream".
``run_pty`` gives the command a pseudo-terminal under a real parent shell:
macOS ``ps`` lists only processes with a controlling terminal, so anything
that finds its shell by walking the process tree (shell completion's
``shellingham``) sees nothing without one.
"""

from __future__ import annotations

import os
import pty
import shlex
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Ran:
    argv: list[str]
    exit: int
    stdout: str
    stderr: str
    duration_s: float

    def record(self) -> dict[str, object]:
        """What a case keeps as its ``actual``: everything, the output cut short."""
        return {
            "argv": self.argv,
            "exit": self.exit,
            "stdout": self.stdout[:2000],
            "stderr": self.stderr[:2000],
            "duration_s": round(self.duration_s, 2),
        }

    @property
    def crashed(self) -> bool:
        """An unhandled exception: a traceback, or PyInstaller's own failure line."""
        text = self.stdout + self.stderr
        return "Traceback (most recent call last)" in text or "[PYI-" in text


def isolated_env(home: Path, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """A minimal environment under ``home``: no inherited ``COFFER_*``, no PATH
    entry that could hold a ``coffer-daemon``."""
    env = {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "LANG": "en_US.UTF-8",
        "TERM": "dumb",
        "NO_COLOR": "1",
    }
    env.update(extra or {})
    return env


def run(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    stdin: bytes | None = None,
    timeout: float = 60,
    cwd: Path | None = None,
) -> Ran:
    started = time.monotonic()
    try:
        done = subprocess.run(
            list(argv),
            input=stdin if stdin is not None else b"",
            capture_output=True,
            env=dict(env),
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
        code, out, err = done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired as exc:
        code, out, err = -9, exc.stdout or b"", (exc.stderr or b"") + b"\n[timed out]"
    return Ran(
        list(argv),
        code,
        out.decode("utf-8", "replace"),
        err.decode("utf-8", "replace"),
        time.monotonic() - started,
    )


def run_pty(argv: Sequence[str], *, shell: str, env: Mapping[str, str], timeout: float = 60) -> Ran:
    """``argv`` in a pseudo-terminal, as a child of ``shell`` (not exec'd by it:
    ``; exit $?`` keeps the shell alive as the parent the command looks for).
    The terminal merges both streams; they come back as ``stdout``."""
    command = " ".join(shlex.quote(a) for a in argv) + "; exit $?"
    started = time.monotonic()
    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - the child execs at once
        os.execve(shell, [shell, "-c", command], {**env, "SHELL": shell})
    chunks: list[bytes] = []
    deadline = started + timeout
    while time.monotonic() < deadline:
        try:
            data = os.read(fd, 65536)
        except OSError:
            break
        if not data:
            break
        chunks.append(data)
    else:
        os.kill(pid, 9)
    _, status = os.waitpid(pid, 0)
    os.close(fd)
    return Ran(
        [shell, "-c", command],
        os.waitstatus_to_exitcode(status),
        b"".join(chunks).decode("utf-8", "replace").replace("\r\n", "\n"),
        "",
        time.monotonic() - started,
    )


__all__ = ["Ran", "isolated_env", "run", "run_pty"]
