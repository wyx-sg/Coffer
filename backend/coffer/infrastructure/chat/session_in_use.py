"""Is a native session open in a process outside the daemon?

Spec chat "Run a session in one place at a time". A session someone resumes in a
terminal (``claude --resume <id>``, ``codex resume <id>``) has its id among that
process's arguments. A process the daemon itself started for a turn — the Claude
Agent SDK spawns ``claude ... --resume <id>`` — is part of the daemon's own
process tree and never counts.

Only a session started with its id on the command line is seen; one opened by
picking it inside the agent's own picker is not.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import psutil


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


def _own_tree(processes: Iterable[ProcessInfo], root_pid: int) -> set[int]:
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


def _names_session(cmdline: Iterable[str], session_id: str) -> bool:
    resume = f"--resume={session_id}"
    return any(arg in (session_id, resume) for arg in cmdline)


class ProcessSessionInUse:
    """``SessionInUsePort`` over the host's process list."""

    def __init__(
        self,
        *,
        processes: Callable[[], Iterable[ProcessInfo]] = snapshot,
        own_pid: Callable[[], int] = os.getpid,
    ) -> None:
        self._processes = processes
        self._own_pid = own_pid

    def _check(self, session_id: str) -> bool:
        listing = list(self._processes())
        own = _own_tree(listing, self._own_pid())
        return any(p.pid not in own and _names_session(p.cmdline, session_id) for p in listing)

    async def in_use(self, session_id: str) -> bool:
        # The process list is blocking; keep it off the event loop.
        return await asyncio.to_thread(self._check, session_id)
