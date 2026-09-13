"""The two ways Coffer takes a loopback port.

:func:`bind_fixed_socket` is the one a user's daemon uses: exactly one port,
and a refusal naming its holder when that port is not to be had.
:func:`bind_free_socket` / :func:`allocate` are the scan, which survives only
for the ``COFFER_PORT_RANGE_*`` override the test suite pins so its own daemons
do not queue up for 8000 — so the tests below are the last thing keeping that
path honest.
"""

import socket

import pytest

from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.daemon import port_alloc
from coffer.infrastructure.daemon.port_alloc import (
    NoFreePort,
    PortHolder,
    PortInUse,
    allocate,
    bind_fixed_socket,
    bind_free_socket,
    fixed_port_conflict_message,
)


def test_picks_default_when_free():
    port = allocate(start=58000, end=58009)
    assert 58000 <= port <= 58009


def test_bind_free_socket_returns_loopback_bound_socket():
    """CODE-041 / FR-012: bind_free_socket hands back an OPEN socket bound to
    a loopback port in range — a daemon started under the range override keeps
    it and passes its fd to uvicorn, so the port is never released between
    publishing daemon.json and binding."""
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


def test_bind_fixed_socket_binds_exactly_that_port():
    s = bind_fixed_socket(58050)
    try:
        assert s.getsockname() == ("127.0.0.1", 58050)
    finally:
        s.close()


def test_bind_fixed_socket_never_falls_back():
    """The whole value of a fixed port is that it does not move — so a taken
    port is an error, not a cue to try 58061."""
    holder = socket.socket()
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", 58060))
    holder.listen(1)
    try:
        with pytest.raises(PortInUse) as raised:
            bind_fixed_socket(58060, attempts=1)
    finally:
        holder.close()
    assert raised.value.port == 58060


def test_fixed_bind_sets_so_reuseaddr_and_the_scan_does_not():
    """The option belongs to the one-port path only, and the split is load-bearing.

    A restart must be able to rebind a port whose old connections are still in
    TIME_WAIT, so the fixed path sets it. The scan path must not: on Linux
    SO_REUSEADDR also permits two sockets to bind the same port while neither
    is LISTENing, which is the whole of a daemon's boot window — setting it
    there let a second acquire() bind the port the first was still holding,
    dissolving CODE-041. macOS/BSD refuse that bind, so only CI caught it.
    """
    scanned = bind_free_socket(start=58070, end=58079)
    try:
        assert scanned.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0
    finally:
        scanned.close()

    fixed = bind_fixed_socket(58080)
    try:
        assert fixed.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) != 0
    finally:
        fixed.close()


def test_a_held_scan_port_cannot_be_bound_again():
    """CODE-041, pinned at the socket level: while acquire() holds a port taken
    under the range override, nothing else may take it — not even another
    socket of ours setting SO_REUSEADDR, which is exactly what Linux would
    otherwise allow."""
    held = bind_free_socket(start=58090, end=58099)
    try:
        port = held.getsockname()[1]
        other = socket.socket()
        other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            with pytest.raises(OSError):
                other.bind(("127.0.0.1", port))
        finally:
            other.close()
    finally:
        held.close()


def test_conflict_message_names_a_coffer_daemon_squatter(monkeypatch):
    """Another Coffer daemon is never killed for us, so the message has to say
    what that process is — otherwise the user stares at an opaque pid.

    It must lead with "probably your own, still starting up". Now that every
    start binds one port, the likeliest holder is the user's own healthy daemon
    that the liveness probe missed mid-warm-up, and a start that reached this
    message will find it serving moments later. Killing on that advice drops
    every MCP client attached to it. `kill` stays in the message, but as the
    second reading and explicitly conditioned on the daemon being another
    vault's."""
    monkeypatch.setattr(port_alloc, "pid_is_coffer_daemon", lambda pid: True)
    message = fixed_port_conflict_message(8000, PortHolder(pid=4321, command="/x/coffer-daemon"))
    assert "pid 4321" in message
    assert "still starting up" in message
    assert "coffer daemon status" in message
    assert "kill 4321" in message
    assert "coffer daemon port set" in message

    # Ordering is the whole point: the wait-and-see reading must reach the eye
    # before the kill does.
    assert message.index("still starting up") < message.index("kill 4321")
    # And the kill must stay tied to its precondition rather than floating free.
    kill_line = next(ln for ln in message.splitlines() if "kill 4321" in ln)
    assert "different vault" in kill_line, kill_line


def test_conflict_message_stays_quiet_about_an_unrelated_squatter(monkeypatch):
    """No kill advice for someone else's dev server — it is not ours to stop."""
    monkeypatch.setattr(port_alloc, "pid_is_coffer_daemon", lambda pid: False)
    message = fixed_port_conflict_message(8000, PortHolder(pid=4321, command="node vite"))
    assert "pid 4321" in message
    assert "kill 4321" not in message


def test_conflict_message_survives_an_unidentifiable_holder():
    """macOS will not let an unprivileged process inspect another user's
    sockets, so "who holds it" can legitimately be unknown — the way out must
    still be spelled out."""
    message = fixed_port_conflict_message(daemon_config.DEFAULT_PORT, None)
    assert "could not identify" in message
    assert "coffer daemon port set" in message


def test_conflict_message_offers_clear_only_where_it_would_do_something():
    """Clearing the setting means "go back to the default", not "go back to
    picking a port", so it is a way out of a squatted 9000 and no way out at
    all of a squatted 8000 — and a message that offered it anyway would send
    the user to a command that changes nothing."""
    holder = PortHolder(pid=4321, command="node vite")

    on_a_chosen_port = fixed_port_conflict_message(9000, holder)
    assert "coffer daemon port clear" in on_a_chosen_port
    assert str(daemon_config.DEFAULT_PORT) in on_a_chosen_port

    on_the_default = fixed_port_conflict_message(daemon_config.DEFAULT_PORT, holder)
    assert "coffer daemon port clear" not in on_the_default
