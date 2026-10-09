"""Starting a stdio upstream's child process, and learning its pid exactly.

``StdioUpstreamConnection`` owns the child in a lifetime task; this module is
the part of starting it that needs the child's pid, which the SDK's
``stdio_client`` does not expose: the pid files that let a leaked child be
reaped later are written under it. The pid is read from the process object the
SDK creates, never inferred from a before/after diff of the daemon's children —
any other child the daemon starts in that window (a codex, a git, a
skill-source clone) would be recorded as this server's process and killed with
it.
"""

from __future__ import annotations

import asyncio
import contextlib
import weakref
from collections.abc import Callable, Iterable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

import mcp.client.stdio as _sdk_stdio
import psutil
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

from coffer.infrastructure.daemon.orphan_sweep import record_spawn
from coffer.infrastructure.logging.files import (
    LineSink,
    open_upstream_errlog,
    write_coffer_line,
)
from coffer.infrastructure.mcp.stderr_mask import masked_sink


def leaf_exception(exc: BaseException) -> BaseException:
    """Unwrap single-member exception groups so the real error is named."""
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


# Serialise the window in which the SDK's process factory is wrapped, across
# the whole process: the wrapper records the pid of the NEXT process the SDK
# creates, so two concurrent spawns must not overlap. One lock per event loop:
# an ``asyncio.Lock`` binds to the loop of its first contended acquire, so a
# single module-level lock would refuse every later loop (a test's, or the
# daemon's after a restart in-process). The daemon runs one loop, so it has
# exactly one lock.
_SPAWN_LOCKS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


def _spawn_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _SPAWN_LOCKS.get(loop)
    if lock is None:
        lock = _SPAWN_LOCKS[loop] = asyncio.Lock()
    return lock


@dataclass
class StartedChild:
    """What opening the child produced besides its two streams."""

    read: Any
    write: Any
    errlog: LineSink | None = None
    pid_files: list[Path] = field(default_factory=list)
    child_pids: list[int] = field(default_factory=list)


async def open_child(
    exit_stack: AsyncExitStack,
    params: StdioServerParameters,
    *,
    server_name: str,
    server_uid: str,
    stderr_sink: TextIO | None,
    command_line: str,
    on_stop: Callable[[LineSink], None],
    mask_values: Iterable[str] = (),
    on_sink: Callable[[LineSink], None] | None = None,
) -> StartedChild:
    """Start the child inside ``exit_stack`` and record its pid file.

    ``mask_values`` are the secrets injected into the child's environment:
    none of them reaches its stderr destination. ``on_sink`` receives the
    line sink for Coffer's own lines as soon as it exists, so a start that
    fails can still be described in it.
    """
    async with _spawn_lock():
        # Give this upstream its own stderr file. The SDK's default is the
        # daemon's stderr, which lands in daemon.log and drowns Coffer's own
        # lines there (see logging/files.py).
        errlog = None if stderr_sink is not None else open_upstream_errlog(server_name)
        if errlog is not None:
            exit_stack.callback(errlog.close)
        # With a secret injected, the child's stderr is a pipe pumped through
        # a masker into the sink, never the file itself (see stderr_mask.py).
        masked = masked_sink(errlog if errlog is not None else stderr_sink, mask_values)
        lines: LineSink | None = None
        if errlog is not None:
            lines = masked if masked is not None else errlog
            # LIFO: this runs after the client's teardown, before close.
            exit_stack.callback(on_stop, lines)
            if on_sink is not None:
                on_sink(lines)
            write_coffer_line(lines, f"start {command_line}")
        pipe: TextIO | None = None
        sink = errlog if errlog is not None else stderr_sink
        if masked is not None:
            sink = pipe = masked.open_pipe()
            # LIFO again: the pump drains the stopped child's last bytes before
            # Coffer writes its stop line.
            exit_stack.push_async_callback(masked.aclose)
        client = stdio_client(params) if sink is None else stdio_client(params, errlog=sink)

        original = _sdk_stdio._create_platform_compatible_process
        pids: list[int] = []

        async def _recording(*args: Any, **kwargs: Any) -> Any:
            process = await original(*args, **kwargs)
            pids.append(process.pid)
            return process

        _sdk_stdio._create_platform_compatible_process = _recording
        try:
            read, write = await exit_stack.enter_async_context(client)
        finally:
            _sdk_stdio._create_platform_compatible_process = original
            # The child holds its own copy of the write end: closing ours is
            # what lets the pump see end of file once the child is gone.
            if pipe is not None:
                pipe.close()

    started = StartedChild(read, write, lines, child_pids=sorted(pids))
    # The SDK starts the child in a new session, so its pid is also its process
    # group's id. The pid file keeps the child's actual cmdline, so a later
    # sweep can still guard against PID recycling.
    for pid in pids:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            started.pid_files.append(record_spawn(server_uid, pid, psutil.Process(pid).cmdline()))
    return started
