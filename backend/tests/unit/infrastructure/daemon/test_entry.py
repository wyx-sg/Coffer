"""Unit tests for the daemon entry module.

TEST-011 — FR-012 requires the daemon to bind only to 127.0.0.1.  This test
monkeypatches uvicorn.run so it never actually opens a port, captures the
keyword arguments, and asserts host == "127.0.0.1" regardless of whether a
COFFER_HOST environment variable is set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.infrastructure.daemon import bootstrap, entry


def _setup_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59700")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59799")


def test_uvicorn_run_is_called_with_loopback_host(
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

    try:
        entry.main()
    finally:
        bootstrap.release()

    assert captured.get("host") == "127.0.0.1", (
        f"FR-012 violated: uvicorn host kwarg was {captured.get('host')!r}; "
        f"the daemon must NEVER bind to any non-loopback address."
    )
    # And the port is the one bootstrap allocated.
    assert isinstance(captured.get("port"), int)


def test_loopback_host_is_not_overridable_by_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even with COFFER_HOST=0.0.0.0 set, the daemon binds only to loopback.

    There is no `COFFER_HOST` env var honoured by entry.main today — this
    test pins that absence so a future regression that adds one won't slip
    past CI.  FR-012 explicitly forbids the daemon from listening on any
    non-loopback interface.
    """
    _setup_home(tmp_path, monkeypatch)
    monkeypatch.setenv("COFFER_HOST", "0.0.0.0")

    captured: dict[str, object] = {}

    def _fake_run(*args: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(entry.uvicorn, "run", _fake_run)
    monkeypatch.setattr(entry, "_install_signal_handlers", lambda: None)

    try:
        entry.main()
    finally:
        bootstrap.release()

    assert captured.get("host") == "127.0.0.1"
