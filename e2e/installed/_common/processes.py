"""Processes a run starts itself, and the check that no fixture outlives its resource.

A fixture is found by exact pid or by a marker in its command line that only
this run uses (its ``--out`` directory), so nothing else on the machine is ever
matched, signalled or counted.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
from pathlib import Path
from typing import IO, Any

import psutil


class OwnedProcesses:
    def __init__(self) -> None:
        self._procs: list[tuple[subprocess.Popen[bytes], IO[bytes], str]] = []

    def spawn(
        self, command: list[str], name: str, log: Path, env: dict[str, str], cwd: Path
    ) -> subprocess.Popen[bytes]:
        out = log.open("ab")
        proc = subprocess.Popen(
            command, env=env, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, start_new_session=True
        )
        self._procs.append((proc, out, name))
        return proc

    async def stop_all(self) -> list[dict[str, Any]]:
        stopped = []
        for proc, out, name in reversed(self._procs):
            if proc.poll() is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()
                try:
                    await asyncio.to_thread(proc.wait, 10)
                except subprocess.TimeoutExpired:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(proc.pid, signal.SIGKILL)
                    await asyncio.to_thread(proc.wait, 5)
            out.close()
            stopped.append({"name": name, "pid": proc.pid, "returncode": proc.returncode})
        return stopped


def processes_with_marker(marker: str) -> list[dict[str, Any]]:
    """Live processes whose command line contains ``marker`` (never this one)."""
    found = []
    for proc in psutil.process_iter(["pid", "ppid", "cmdline"]):
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            if proc.pid == os.getpid() or proc.status() == psutil.STATUS_ZOMBIE:
                continue
            command = " ".join(proc.info["cmdline"] or [])
            if marker in command:
                found.append({"pid": proc.pid, "ppid": proc.info["ppid"], "command": command})
    return found


def alive(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


async def wait_gone(pids: set[int], timeout: float) -> list[int]:
    """Wait up to ``timeout`` seconds for every pid to exit; returns those still alive."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        living = sorted(p for p in pids if alive(p))
        if not living or asyncio.get_running_loop().time() >= deadline:
            return living
        await asyncio.sleep(0.2)
