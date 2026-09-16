"""Shared networking helpers for tests.

One definition of "find me a port to start a server on", so a fix to the
bind-and-release dance lands everywhere at once instead of in one copy. Every
test module that needs a port imports from here; there are no local copies.
Use via::

    from tests.fixtures.net import free_port

    port = free_port()
"""

from __future__ import annotations

import socket


def free_port() -> int:
    """Bind a socket to an ephemeral loopback port, then release it.

    Returns the port number so the caller can hand it to a server it is about
    to start.  There is an inherent (small) race between releasing the socket
    here and the caller re-binding the port, identical to the local copies this
    replaced.
    """
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p
