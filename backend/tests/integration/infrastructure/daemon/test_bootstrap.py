"""Tests for bootstrap.acquire() — daemon.json writing + permissions."""

from __future__ import annotations

import json
import socket
import stat
from pathlib import Path

import pytest


def test_acquire_writes_daemon_json_with_0600(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """bootstrap.acquire() must write daemon.json with 0600 perms, a valid free port,
    a non-empty token, and a started_at timestamp."""
    # Redirect HOME so acquire() writes to tmp_path
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    # Use a free port range that won't conflict with anything real
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59400")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59499")

    from coffer.infrastructure.daemon import bootstrap

    info, sock = bootstrap.acquire()
    self_addr = sock.getsockname()
    try:
        # CODE-041: acquire holds the bound socket open (no probe-and-close
        # TOCTOU); it is bound to the loopback port recorded in daemon.json.
        assert self_addr[0] == "127.0.0.1"

        daemon_json = home / ".coffer" / "daemon.json"
        assert daemon_json.exists(), "daemon.json was not created"

        # Verify file mode is exactly 0600 (owner read+write only)
        file_mode = stat.S_IMODE(daemon_json.stat().st_mode)
        assert file_mode == 0o600, f"Expected 0o600, got {oct(file_mode)}"

        # Verify content round-trips
        raw = json.loads(daemon_json.read_text())
        assert isinstance(raw["port"], int)
        assert 59400 <= raw["port"] <= 59499, f"Port {raw['port']} outside expected range"
        assert isinstance(raw["token"], str) and len(raw["token"]) >= 32, "Token missing/short"
        assert raw.get("started_at"), "started_at missing"

        # DaemonInfo returned by acquire() must match the file
        assert info.port == raw["port"]
        assert info.token == raw["token"]
        # The held socket is bound to exactly the published port.
        assert self_addr[1] == raw["port"]
    finally:
        sock.close()


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="daemon port conflict falls back to the next free port"
)
def test_second_daemon_picks_free_port_and_clients_discover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TEST-009: with the lowest port in the configured range held by an
    unrelated socket, bootstrap.acquire() skips it and picks the next free
    one.  Each acquire() writes a daemon.json that records the chosen port,
    so a discoverer reading the file gets the right answer.

    This pins the spec edge case "Daemon port conflict": the daemon must
    fall back to the next port in its bounded range without crashing, and
    `daemon.json` must always reflect the live port.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59500")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59599")

    from coffer.infrastructure.daemon import bootstrap

    # Hold one port in the range so bind_free_socket() must move on.
    holder = socket.socket()
    holder.bind(("127.0.0.1", 59500))
    holder.listen(1)
    try:
        info_a, sock_a = bootstrap.acquire()
        path_a = home / ".coffer" / "daemon.json"
        try:
            recorded_a = json.loads(path_a.read_text())
            assert info_a.port != 59500, "first daemon must skip the busy port"
            assert recorded_a["port"] == info_a.port

            # CODE-041: acquire() now HOLDS info_a.port (no probe-and-release),
            # so a second acquire must naturally skip it and pick another free
            # port; daemon.json must update to the live port.
            info_b, sock_b = bootstrap.acquire()
            try:
                recorded_b = json.loads(path_a.read_text())
                assert info_b.port != info_a.port
                assert info_b.port != 59500
                assert recorded_b["port"] == info_b.port
            finally:
                sock_b.close()
        finally:
            sock_a.close()
    finally:
        holder.close()
