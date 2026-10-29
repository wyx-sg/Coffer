"""Free a Codex thread another Codex process holds, so a Coffer turn can continue it.

Spec chat "Take over a session open elsewhere"; ADR "A Coffer Turn Takes Over a
Session Open Elsewhere". Codex lets one process write a thread at a time: the
writer holds ``$CODEX_HOME/thread-writer-locks/<thread>.lock``, and any other
app-server answers ``thread/resume`` with ``-32600`` "already has an active
writer". Two holders are freed here:

- **Codex's shared background app-server** (``codex app-server
  --managed-daemon``). A terminal ``codex`` attaches to it, so the thread stays
  loaded there after the terminal closes. Coffer connects to its control socket
  (``$CODEX_HOME/app-server-control/app-server-control.sock``, JSON-RPC over a
  WebSocket), joins the thread, interrupts a turn left running (one waiting on an
  approval nobody can give never ends), unsubscribes, and waits for the server
  to unload it: it does so ``thread_unload_delay_secs`` (60 by default) after
  the thread has no subscriber and nothing running.
- **A terminal ``codex`` running its own embedded app-server**: found by the
  lock file among its open files and ended like a terminal in
  ``session_takeover``.

Anything else holding the lock — the Codex app's or an editor's own
``codex app-server`` — is left alone, and the turn is refused.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import pathlib
import time
from collections.abc import Callable, Iterable
from typing import Any

import psutil
from websockets.asyncio.client import ClientConnection, unix_connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from coffer.infrastructure.chat.codex_jsonrpc import CodexRpcClient
from coffer.infrastructure.chat.session_takeover import end_processes, own_tree, snapshot

_logger = logging.getLogger(__name__)

_CLIENT_INFO = {"name": "coffer", "title": None, "version": "0"}
_SOCKET = pathlib.Path("app-server-control") / "app-server-control.sock"
_LOCKS = "thread-writer-locks"

#: Codex unloads an idle thread 60 s after its last subscriber leaves; this
#: leaves room for that plus the interrupt.
UNLOAD_TIMEOUT_SECONDS = 90.0
_POLL_SECONDS = 1.0
_REQUEST_TIMEOUT_SECONDS = 15.0


def codex_home(env: dict[str, str] | None) -> pathlib.Path:
    """The ``CODEX_HOME`` the turn's app-server runs under."""
    configured = (env or os.environ).get("CODEX_HOME")
    return pathlib.Path(configured) if configured else pathlib.Path.home() / ".codex"


class _WebSocketLines:
    """Reader and writer for ``CodexRpcClient`` over a WebSocket: one JSON-RPC
    message per WebSocket text message instead of per line."""

    def __init__(self, ws: ClientConnection) -> None:
        self._ws = ws
        self._out: list[bytes] = []

    async def readline(self) -> bytes:
        try:
            message = await self._ws.recv()
        except ConnectionClosed:
            return b""
        raw = message.encode("utf-8") if isinstance(message, str) else message
        return raw + b"\n"

    def write(self, data: bytes) -> None:
        self._out.append(data)

    async def drain(self) -> None:
        out, self._out = self._out, []
        for data in out:
            await self._ws.send(data.decode("utf-8").rstrip("\n"))


async def _loaded(rpc: CodexRpcClient) -> set[str]:
    ids: set[str] = set()
    cursor: str | None = None
    while True:
        page = await _ask(rpc, "thread/loaded/list", {"cursor": cursor})
        ids.update(i for i in page.get("data") or () if isinstance(i, str))
        cursor = page.get("nextCursor")
        if not cursor:
            return ids


async def _ask(rpc: CodexRpcClient, method: str, params: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.wait_for(rpc.request(method, params), _REQUEST_TIMEOUT_SECONDS)


async def release_in_daemon(
    socket_path: pathlib.Path, thread_id: str, *, unload_timeout: float = UNLOAD_TIMEOUT_SECONDS
) -> bool | None:
    """Have the shared background app-server let go of ``thread_id``.

    ``None`` when there is no such server or it does not have the thread loaded
    (someone else holds the lock), ``True`` once it has unloaded the thread,
    ``False`` when it still has it after ``unload_timeout`` (another client,
    such as an open terminal or the Codex app, is still on it) or failed midway.
    """
    if not socket_path.exists():
        return None
    try:
        ws = await unix_connect(str(socket_path), "ws://localhost/", max_size=None, open_timeout=5)
    except (OSError, WebSocketException, TimeoutError):
        _logger.info("codex_thread_release.daemon_unreachable", exc_info=True)
        return None
    lines = _WebSocketLines(ws)
    rpc = CodexRpcClient(lines, lines)
    rpc.start()
    held = False
    try:
        await _ask(rpc, "initialize", {"clientInfo": _CLIENT_INFO, "capabilities": None})
        await rpc.notify("initialized")
        if thread_id not in await _loaded(rpc):
            return None
        held = True
        joined = await _ask(rpc, "thread/resume", {"threadId": thread_id})
        for turn in (joined.get("thread") or {}).get("turns") or ():
            if isinstance(turn, dict) and turn.get("status") == "inProgress":
                await _ask(rpc, "turn/interrupt", {"threadId": thread_id, "turnId": turn["id"]})
        await _ask(rpc, "thread/unsubscribe", {"threadId": thread_id})
        deadline = time.monotonic() + unload_timeout
        while thread_id in await _loaded(rpc):
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(_POLL_SECONDS)
        return True
    except Exception:
        _logger.warning("codex_thread_release.daemon_release_failed", exc_info=True)
        return False if held else None
    finally:
        await rpc.close()
        with contextlib.suppress(Exception):
            await ws.close()


def _is_codex(cmdline: tuple[str, ...]) -> bool:
    """The program is Codex: ``codex``, its platform binary (``codex-aarch64-…``),
    or the npm launcher run by ``node``."""
    args = cmdline[1:2] if cmdline and pathlib.Path(cmdline[0]).name == "node" else cmdline[:1]
    return any(
        (name := pathlib.Path(a).name.lower()) == "codex" or name.startswith("codex-") for a in args
    )


def is_terminal_codex(cmdline: tuple[str, ...]) -> bool:
    """A ``codex`` someone runs in a terminal, not an app-server another app
    started (the Codex app, an editor, the shared background server)."""
    return _is_codex(cmdline) and "app-server" not in cmdline


def _open_paths(pid: int) -> set[str]:
    with contextlib.suppress(psutil.Error):
        return {f.path for f in psutil.Process(pid).open_files()}
    return set()


def lock_holders(
    lock: pathlib.Path,
    *,
    processes: Iterable[Any],
    own_pid: int,
    open_paths: Callable[[int], set[str]] = _open_paths,
) -> list[tuple[int, tuple[str, ...]]]:
    """The processes outside the daemon's tree with ``lock`` open."""
    listing = list(processes)
    own = own_tree(listing, own_pid)
    wanted = {str(lock), os.path.realpath(lock)}
    return [
        (p.pid, p.cmdline)
        for p in listing
        if p.pid not in own and _is_codex(p.cmdline) and open_paths(p.pid) & wanted
    ]


def end_terminal_holder(lock: pathlib.Path) -> bool:
    """End a terminal ``codex`` holding ``lock``; False when the holder is
    something else, or none could be found or ended."""
    holders = lock_holders(lock, processes=snapshot(), own_pid=os.getpid())
    terminals = [pid for pid, cmdline in holders if is_terminal_codex(cmdline)]
    if not terminals or len(terminals) != len(holders):
        _logger.info("codex_thread_release.holder_left_alone", extra={"holders": holders})
        return False
    return not end_processes(terminals)


class CodexThreadRelease:
    """Frees a Codex thread held elsewhere; ``True`` when the turn may retry."""

    def __init__(
        self, home: pathlib.Path, *, unload_timeout: float = UNLOAD_TIMEOUT_SECONDS
    ) -> None:
        self._home = home
        self._unload_timeout = unload_timeout

    async def __call__(self, thread_id: str) -> bool:
        released = await release_in_daemon(
            self._home / _SOCKET, thread_id, unload_timeout=self._unload_timeout
        )
        if released is not None:
            _logger.info(
                "codex_thread_release.daemon",
                extra={"thread_id": thread_id, "released": released},
            )
            return released
        lock = self._home / _LOCKS / f"{thread_id}.lock"
        return await asyncio.to_thread(end_terminal_holder, lock)


__all__ = ["CodexThreadRelease", "codex_home", "release_in_daemon"]
