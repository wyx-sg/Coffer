import socket

import pytest

from coffer.infrastructure.daemon.port_alloc import NoFreePort, allocate, bind_free_socket


def test_picks_default_when_free():
    port = allocate(start=58000, end=58009)
    assert 58000 <= port <= 58009


def test_bind_free_socket_returns_loopback_bound_socket():
    """CODE-041 / FR-012: bind_free_socket hands back an OPEN socket bound to
    a loopback port in range — the daemon keeps it and passes its fd to uvicorn
    so the port is never released between publishing daemon.json and binding."""
    s = bind_free_socket(start=58030, end=58039)
    try:
        host, port = s.getsockname()
        assert host == "127.0.0.1"
        assert 58030 <= port <= 58039
        # It is genuinely still held: a fresh bind to the same port must fail.
        other = socket.socket()
        try:
            with pytest.raises(OSError):
                other.bind(("127.0.0.1", port))
        finally:
            other.close()
    finally:
        s.close()


def test_bind_free_socket_raises_when_all_busy():
    sockets = []
    try:
        for p in range(58040, 58045):
            s = socket.socket()
            s.bind(("127.0.0.1", p))
            sockets.append(s)
        with pytest.raises(NoFreePort):
            bind_free_socket(start=58040, end=58044)
    finally:
        for s in sockets:
            s.close()


def test_falls_back_when_default_busy():
    s = socket.socket()
    s.bind(("127.0.0.1", 58010))
    s.listen()
    try:
        port = allocate(start=58010, end=58019)
        assert 58011 <= port <= 58019
    finally:
        s.close()


def test_raises_when_all_busy():
    sockets = []
    try:
        for p in range(58020, 58025):
            s = socket.socket()
            s.bind(("127.0.0.1", p))
            s.listen()
            sockets.append(s)
        with pytest.raises(NoFreePort):
            allocate(start=58020, end=58024)
    finally:
        for s in sockets:
            s.close()
