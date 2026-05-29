import socket

import pytest

from coffer.infrastructure.daemon.port_alloc import NoFreePort, allocate


def test_picks_default_when_free():
    port = allocate(start=58000, end=58009)
    assert 58000 <= port <= 58009


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
