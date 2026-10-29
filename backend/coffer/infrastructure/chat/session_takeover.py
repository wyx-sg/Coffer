"""End the terminal processes that have a native session open, so a turn can continue it.

Spec chat "Take over a session open elsewhere"; ADR "A Coffer Turn Takes Over a
Session Open Elsewhere". A session someone resumes in a terminal (``claude
--resume <id>``, ``codex resume <id>``) has its id among that process's
arguments. Such a process is ended (SIGTERM, then SIGKILL after a grace period)
before the turn resumes the session. A process the daemon itself started for a
turn — the Claude Agent SDK spawns ``claude ... --resume <id>`` — is part of the
daemon's own process tree and is never touched.

Only a session started with its id on the command line is seen here; one opened
by picking it inside the agent's own picker is not. For Codex, the writer lock
catches that case and ``codex_thread_release`` frees it.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import psutil

_logger = logging.getLogger(__name__)

#: How long an ended process gets to exit on SIGTERM before SIGKILL, and then
#: how long SIGKILL gets.
_TERM_GRACE_SECONDS = 5.0
_KILL_GRACE_SECONDS = 2.0


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    ppid: int
    cmdline: tuple[str, ...]


def snapshot() -> list[ProcessInfo]:
    """Every readable process now (a process that is gone or denied is skipped)."""
    found: list[ProcessInfo] = []
    for proc in psutil.process_iter(["pid", "ppid", "cmdline"]):
        info = proc.info
        found.append(ProcessInfo(info["pid"], info["ppid"] or 0, tuple(info["cmdline"] or ())))
    return found


def own_tree(processes: Iterable[ProcessInfo], root_pid: int) -> set[int]:
    """``root_pid`` and every process descended from it."""
    children: dict[int, list[int]] = {}
    for p in processes:
        children.setdefault(p.ppid, []).append(p.pid)
    tree = {root_pid}
    frontier = [root_pid]
    while frontier:
        for child in children.get(frontier.pop(), ()):
            if child not in tree:
                tree.add(child)
                frontier.append(child)
    return tree


def end_processes(pids: Iterable[int]) -> list[int]:
    """SIGTERM each process, SIGKILL whatever outlives the grace period; return
    the pids still alive after that (a process that is gone already counts as
    ended, one this user may not signal stays alive)."""
    procs: list[psutil.Process] = []
    alive: list[int] = []
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            procs.append(proc)
        except psutil.NoSuchProcess:
            continue
        except psutil.Error:
            alive.append(pid)
    _, left = psutil.wait_procs(procs, timeout=_TERM_GRACE_SECONDS)
    for proc in left:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            continue
        except psutil.Error:
            alive.append(proc.pid)
    _, left = psutil.wait_procs(left, timeout=_KILL_GRACE_SECONDS)
    return alive + [p.pid for p in left if p.pid not in alive]


def _names_session(cmdline: Iterable[str], session_id: str) -> bool:
    resume = f"--resume={session_id}"
    return any(arg in (session_id, resume) for arg in cmdline)


class ProcessSessionTakeover:
    """``SessionTakeoverPort`` over the host's process list."""

    def __init__(
        self,
        *,
        processes: Callable[[], Iterable[ProcessInfo]] = snapshot,
        own_pid: Callable[[], int] = os.getpid,
        end: Callable[[list[int]], list[int]] = end_processes,
    ) -> None:
        self._processes = processes
        self._own_pid = own_pid
        self._end = end

    def _release(self, session_id: str) -> bool:
        listing = list(self._processes())
        own = own_tree(listing, self._own_pid())
        holders = [
            p.pid for p in listing if p.pid not in own and _names_session(p.cmdline, session_id)
        ]
        if not holders:
            return True
        survivors = self._end(holders)
        _logger.info(
            "session_takeover.ended_terminals",
            extra={"session_id": session_id, "ended": holders, "survivors": survivors},
        )
        return not survivors

    async def release(self, session_id: str) -> bool:
        # The process list and the waits are blocking; keep them off the event loop.
        return await asyncio.to_thread(self._release, session_id)
