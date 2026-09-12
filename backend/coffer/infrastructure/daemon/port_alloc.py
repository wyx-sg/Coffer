"""Loopback port binding: the user's fixed port, or a bounded free-port scan."""

from __future__ import annotations

import errno
import socket
import time
from dataclasses import dataclass

import psutil

from coffer.infrastructure.daemon.pid_lock import pid_is_coffer_daemon


class NoFreePort(Exception):  # noqa: N818
    """Raised when every port in the requested range is busy."""


@dataclass(frozen=True)
class PortHolder:
    """The process found listening on a port we wanted."""

    pid: int
    command: str

    @property
    def is_coffer_daemon(self) -> bool:
        return pid_is_coffer_daemon(self.pid)


class PortInUse(Exception):  # noqa: N818
    """Raised when the user's FIXED port is held by something else.

    Carries the port and, when it could be identified, the process holding it,
    so every surface can print the same actionable message instead of each
    inventing its own wording.
    """

    def __init__(self, port: int, holder: PortHolder | None, *, note: str | None = None) -> None:
        self.port = port
        self.holder = holder
        super().__init__(fixed_port_conflict_message(port, holder, note=note))


def find_port_holder(port: int) -> PortHolder | None:
    """The process listening on ``port``, or ``None`` when it can't be found.

    Best-effort by construction. macOS refuses a system-wide socket enumeration
    to an unprivileged process, so this walks processes and asks each one for
    its own sockets: that succeeds for the user's own processes — which is the
    case that matters, since the squatter is nearly always another of the
    user's dev servers or a stray Coffer daemon — and quietly skips the rest.
    Only ever called on the failure path, so its cost is irrelevant.
    """
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            connections = proc.net_connections(kind="tcp")
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        for conn in connections:
            if conn.status != psutil.CONN_LISTEN or not conn.laddr:
                continue
            if conn.laddr.port != port:
                continue
            try:
                command = " ".join(proc.cmdline()) or proc.name()
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                command = str(proc.info.get("name") or "?")
            return PortHolder(pid=proc.pid, command=command)
    return None


def fixed_port_conflict_message(
    port: int, holder: PortHolder | None, *, note: str | None = None
) -> str:
    """What the user is told when their fixed port cannot be bound.

    One text, shared by the daemon's own refusal and by the CLI's pre-flight
    check, because the user may meet either one first. It names the holder and
    every way out: a fixed port that fails without saying what to do next is
    worse than the drift it replaced.

    A Coffer daemon found squatting the port gets its own line. It is never
    killed automatically — it belongs to another vault (a live test under a
    throwaway ``HOME`` is the usual source) and reaping someone else's daemon
    without being asked is not a decision a failed bind earns — but the user
    should not have to work out what that process is, so the message says.
    """
    if note is not None:
        held_by = note
    elif holder is not None:
        held_by = f"pid {holder.pid}  {holder.command}"
    else:
        held_by = "could not identify the process — it belongs to another user"
    lines = [
        f"port {port} is configured as Coffer's fixed daemon port, but something "
        f"else is already using it.",
        f"  held by: {held_by}",
    ]
    if holder is not None and holder.is_coffer_daemon:
        lines.append(
            f"           that is a Coffer daemon this vault does not know about "
            f"(most often a test run under a throwaway HOME) — stop it with: kill {holder.pid}"
        )
    lines += [
        "  fix one of:",
        "    stop that process, then    coffer daemon start",
        "    use a different port       coffer daemon port set <port>",
        "    go back to automatic       coffer daemon port clear",
    ]
    return "\n".join(lines)


def _new_socket() -> socket.socket:
    """A loopback TCP socket with ``SO_REUSEADDR`` set.

    Without it, a ``coffer daemon stop`` immediately followed by a start could
    fail to rebind a port still in ``TIME_WAIT`` — and in the scan path that
    failure is invisible: it simply drifts to the next port, which is exactly
    what breaks the user's bookmark. On macOS/BSD (and Linux) ``SO_REUSEADDR``
    admits only a port in ``TIME_WAIT``, never one with a live ``LISTEN``, so
    CODE-041's guarantee that nothing can bind out from under us is untouched
    — stealing a live listener needs ``SO_REUSEPORT``, which we never set.
    """
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return sock


def allocate(start: int = 8000, end: int = 8009) -> int:
    """Return the first available 127.0.0.1 port in [start, end] inclusive.

    Note: this probe-and-close form has an inherent TOCTOU window — the port
    can be taken between the close here and a later bind. The daemon path uses
    :func:`bind_free_socket` instead, which keeps ownership of the port.
    """
    sock = bind_free_socket(start, end)
    try:
        return sock.getsockname()[1]  # type: ignore[no-any-return]
    finally:
        sock.close()


def bind_free_socket(start: int = 8000, end: int = 8009) -> socket.socket:
    """Bind the first free 127.0.0.1 port in [start, end] and RETURN the socket.

    CODE-041: the caller keeps the bound socket open and hands its fd to the
    server (uvicorn ``fd=``), so there is no close-then-rebind gap in which
    another process could steal the port — which would otherwise leave
    ``daemon.json`` (already published with the live token) pointing at a port
    owned by an unrelated process, leaking the management token to it.

    This is the path taken when the user has NOT fixed the daemon's port. It
    moves to the next port whenever one is taken, so the port the user's
    browser bookmark names is not guaranteed; :func:`bind_fixed_socket` is the
    path that guarantees it.
    """
    for port in range(start, end + 1):
        s = _new_socket()
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            s.close()
            continue
        return s
    raise NoFreePort(
        f"no free port in {start}-{end} — every port in the daemon's range is "
        "taken. Most often these are orphaned Coffer daemons a previous spawn "
        "could not see (check for other 'coffer.infrastructure.daemon.entry' "
        "processes); a live daemon now evicts itself once another takes over "
        "daemon.json, so this should not accumulate."
    )


def bind_fixed_socket(port: int, *, attempts: int = 4, delay: float = 0.3) -> socket.socket:
    """Bind exactly ``127.0.0.1:port`` and RETURN the socket, or raise :class:`PortInUse`.

    No fallback: a fixed port that quietly becomes a different port is the
    behaviour the setting exists to end, so the daemon refuses to start instead
    and the user is told what holds the port.

    The bounded retry is for one specific, benign case — a restart, where the
    outgoing daemon may still be releasing the socket as the incoming one binds.
    A second of patience there is the difference between "restart works" and
    "restart fails and the user must run it twice"; it is far too short to mask
    a port that is genuinely someone else's.
    """
    last_error: OSError | None = None
    for attempt in range(attempts):
        s = _new_socket()
        try:
            s.bind(("127.0.0.1", port))
        except OSError as exc:
            s.close()
            if exc.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(delay)
            continue
        return s
    if last_error is not None and last_error.errno == errno.EACCES:
        raise PortInUse(port, None, note="the operating system refused it (a privileged port)")
    raise PortInUse(port, find_port_holder(port))
