"""The port this daemon serves on, set once by the composition root.

Its own module so a surface that only needs the address (the MCP servers
page's built-in ``coffer`` entry, the Host guard) does not import the daemon
routes and, through them, everything the status page reads.
"""

from __future__ import annotations

_PORT = 8000  # set by composition root


def set_port(port: int) -> None:
    global _PORT
    _PORT = port


def get_port() -> int:
    """The port the daemon is serving on (set by the composition root)."""
    return _PORT
