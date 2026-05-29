"""Unit tests for the daemon entry module.

TEST-011 — FR-012 requires the daemon to bind only to 127.0.0.1. Since
CODE-041 the daemon binds the socket itself (via ``bind_free_socket``, which
always binds ``127.0.0.1``) and hands uvicorn the fd, so the loopback
guarantee is structural rather than a uvicorn ``host`` kwarg. These tests pin
that entry.main passes a pre-bound socket fd (never a host/port that could be
overridden); the companion integration test ``test_port_alloc`` pins that
``bind_free_socket`` actually binds loopback (asserting the bound address
needs the ``socket`` module, which is banned in the pure unit tier).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.infrastructure.daemon import entry


def _setup_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59700")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59799")


def test_uvicorn_run_is_called_with_prebound_loopback_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_home(tmp_path, monkeypatch)

    captured: dict[str, object] = {}

    def _fake_run(*args: object, **kwargs: object) -> None:
        captured.update(kwargs)
        captured["args"] = args

    monkeypatch.setattr(entry.uvicorn, "run", _fake_run)
    # Avoid actually installing real signal handlers — they require a main
    # thread in some environments.
    monkeypatch.setattr(entry, "_install_signal_handlers", lambda: None)

    entry.main()

    assert isinstance(captured.get("fd"), int), "entry.main must hand uvicorn a pre-bound socket fd"
    # No host/port kwargs — binding is owned by bind_free_socket (loopback),
    # not by an overridable uvicorn host. (Loopback bind asserted in test_port_alloc.)
    assert "host" not in captured
    assert "port" not in captured


def test_no_host_override_path_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with COFFER_HOST=0.0.0.0 set, nothing widens the bind.

    entry.main has no host kwarg at all (it passes a pre-bound loopback fd),
    so a stray COFFER_HOST cannot move the daemon off loopback. This pins the
    absence of any such override path.
    """
    _setup_home(tmp_path, monkeypatch)
    monkeypatch.setenv("COFFER_HOST", "0.0.0.0")

    captured: dict[str, object] = {}

    def _fake_run(*args: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(entry.uvicorn, "run", _fake_run)
    monkeypatch.setattr(entry, "_install_signal_handlers", lambda: None)

    entry.main()

    assert "host" not in captured
    assert isinstance(captured.get("fd"), int)
