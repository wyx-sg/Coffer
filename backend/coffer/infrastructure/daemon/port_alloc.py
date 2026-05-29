"""Loopback port allocator with bounded fallback range."""

from __future__ import annotations

import socket


class NoFreePort(Exception):  # noqa: N818
    """Raised when every port in the requested range is busy."""


def allocate(start: int = 8000, end: int = 8009) -> int:
    """Return the first available 127.0.0.1 port in [start, end] inclusive."""
    for port in range(start, end + 1):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise NoFreePort(f"no free port in {start}-{end}")
