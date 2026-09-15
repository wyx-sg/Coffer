"""One spawn path, one PID record, one termination ladder for daemon children.

The daemon keeps several long-lived children alive on the user's behalf — a
``cloudflared`` tunnel per channel, the callback listener, a ``codex
app-server`` per Codex chat. Each of them used to spawn, record and tear down
its child on its own, and the copies drifted: the Codex session spawned without
recording its PID at all, so a daemon crash left ``codex app-server`` running
with nothing to point the next startup at it. The startup orphan sweep
(:mod:`coffer.infrastructure.daemon.orphan_sweep`) can only reap what was
recorded, so recording must be inseparable from spawning — which is what
:meth:`ChildProcess.spawn` makes true.

:meth:`ChildProcess.terminate` is the single termination ladder: SIGTERM, a
bounded wait, SIGKILL, a bounded wait, then the PID record is dropped *because
we reaped the child ourselves* — a record that lingers would send the next
startup sweep chasing a PID that may by then belong to a stranger (the sweep
guards against recycling by command line, but it should not have to).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from coffer.infrastructure.daemon.orphan_sweep import record_spawn

_logger = logging.getLogger(__name__)


async def _create_subprocess(argv: Sequence[str], **kwargs: Any) -> asyncio.subprocess.Process:
    """The one call that touches the OS. Tests that must not run a real binary
    (the cloudflared tunnel) monkeypatch this function and nothing else, so the
    recording and termination logic above it stays under test."""
    return await asyncio.create_subprocess_exec(*argv, **kwargs)


class ChildProcess:
    """A child the daemon owns: spawned, recorded for the orphan sweep, and torn
    down through one escalation ladder."""

    def __init__(self, name: str, process: asyncio.subprocess.Process, pidfile: Path) -> None:
        self._name = name
        self._process = process
        self._pidfile = pidfile

    @classmethod
    async def spawn(
        cls,
        name: str,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
        stdout: int | None = None,
        stderr: int | None = None,
    ) -> ChildProcess:
        """Spawn ``argv`` and record its PID under ``~/.coffer/upstream-pids``
        as ``<name>-<pid>.json`` (honours ``HOME``, like the sweep that reads it).

        ``name`` is the pidfile prefix; keep it stable per child kind so the
        sweep's records stay recognisable. ``stdin``/``stdout``/``stderr`` take
        the ``asyncio.subprocess`` constants (``PIPE``, ``DEVNULL``) or ``None``
        to inherit.
        """
        command = list(argv)
        process = await _create_subprocess(
            command, cwd=cwd, env=env, stdin=stdin, stdout=stdout, stderr=stderr
        )
        pidfile = record_spawn(name, process.pid, command)
        return cls(name, process, pidfile)

    @property
    def name(self) -> str:
        return self._name

    @property
    def pid(self) -> int:
        return self._process.pid

    @property
    def returncode(self) -> int | None:
        return self._process.returncode

    @property
    def running(self) -> bool:
        return self._process.returncode is None

    @property
    def process(self) -> asyncio.subprocess.Process:
        """The underlying process, for callers that own its stdio pipes."""
        return self._process

    @property
    def pidfile(self) -> Path:
        return self._pidfile

    async def wait(self) -> int:
        return await self._process.wait()

    async def terminate(self, *, timeout: float = 3.0, kill_timeout: float = 2.0) -> None:
        """SIGTERM, wait ``timeout``; SIGKILL, wait ``kill_timeout``; drop the
        PID record.

        Idempotent: a child that already exited only has its record dropped.
        The record is kept (and a warning logged) in the one case where the
        child is still alive after SIGKILL — it was not reaped by us, so the
        next startup sweep must still get its chance at it.
        """
        proc = self._process
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(proc.wait(), timeout=kill_timeout)
        if proc.returncode is None:
            _logger.warning(
                "child_process.survived_kill", extra={"name": self._name, "pid": proc.pid}
            )
            return
        self._pidfile.unlink(missing_ok=True)


__all__ = ["ChildProcess"]
