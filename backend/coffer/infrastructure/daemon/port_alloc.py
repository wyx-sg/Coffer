"""Loopback port allocator with bounded fallback range."""

from __future__ import annotations

import socket


class NoFreePort(Exception):  # noqa: N818
    """Raised when every port in the requested range is busy."""


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
    """
    for port in range(start, end + 1):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            s.close()
            continue
        return s
    raise NoFreePort(f"no free port in {start}-{end}")
