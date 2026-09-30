"""Pin the daemon's port from the running daemon (spec daemon "Bind a fixed, settable port").

The settings page's twin of ``coffer config set daemon.port``: the same range
check, the same pre-bind file, written by :func:`config.write_fixed_port`. It
adds the one check a running daemon can make and the CLI cannot usefully make
— that no OTHER process holds the port — because the page is where a user
picks a new port, and a port that is taken would make the next start refuse.
The port this daemon itself answers on counts as free. Nothing is audited: the
setting is process configuration read before the database opens.
"""

from __future__ import annotations

import errno
import socket

import psutil

from coffer.domain.daemon_port_errors import PortInUse, PortOutOfRange
from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon.port_alloc import find_port_holder


def _holder_of(port: int) -> dict[str, object] | None:
    holder = find_port_holder(port)
    if holder is None:
        return None
    try:
        name = psutil.Process(holder.pid).name()
    except (psutil.Error, OSError):
        name = holder.command.split(" ", 1)[0].rsplit("/", 1)[-1] or "?"
    return {"pid": holder.pid, "name": name, "command": holder.command}


def _is_free(port: int) -> bool:
    """Whether ``127.0.0.1:port`` can be bound now, with the options a start uses."""
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError as exc:
        if exc.errno in (errno.EADDRINUSE, errno.EACCES):
            return False
        raise
    finally:
        sock.close()
    return True


def pin_port(port: int, *, bound_port: int) -> int:
    """Validate ``port`` and write it as the port of the next start; return it.

    Raises :class:`PortOutOfRange` or :class:`PortInUse` (naming the holder
    when it can be identified); on either nothing is written.
    """
    if not daemon_config.MIN_PORT <= port <= daemon_config.MAX_PORT:
        raise PortOutOfRange(port, daemon_config.MIN_PORT, daemon_config.MAX_PORT)
    if port != bound_port and not _is_free(port):
        raise PortInUse(port, _holder_of(port))
    daemon_config.write_fixed_port(port)
    return port


__all__ = ["pin_port"]
