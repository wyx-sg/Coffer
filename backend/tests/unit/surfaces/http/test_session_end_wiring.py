"""Unit tests for session_end_wiring (FR-035 opt-in wiring)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from coffer.surfaces.http.session_end_wiring import (
    AUTO_ORGANIZE_ENV,
    auto_organize_enabled,
    start_auto_organize,
    stop_auto_organize,
)


class _MemStub:
    def __init__(self) -> None:
        self.set_on_change_calls: list[Any] = []

    def set_on_change(self, hook: Any) -> None:
        self.set_on_change_calls.append(hook)


class _OrganizerStub:
    async def organize(self, *, store_name: str) -> None:
        pass


def _make_app() -> Any:
    app = SimpleNamespace()
    app.state = SimpleNamespace()
    return app


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "TRUE", "YES", "ON"])
def test_auto_organize_enabled_truthy(monkeypatch: pytest.MonkeyPatch, val: str) -> None:
    monkeypatch.setenv(AUTO_ORGANIZE_ENV, val)
    assert auto_organize_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "maybe"])
def test_auto_organize_enabled_falsy(monkeypatch: pytest.MonkeyPatch, val: str) -> None:
    monkeypatch.setenv(AUTO_ORGANIZE_ENV, val)
    assert auto_organize_enabled() is False


def test_auto_organize_enabled_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(AUTO_ORGANIZE_ENV, raising=False)
    assert auto_organize_enabled() is False


def test_start_auto_organize_env_off_does_not_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(AUTO_ORGANIZE_ENV, raising=False)
    app = _make_app()
    mem = _MemStub()
    organizer = _OrganizerStub()
    start_auto_organize(app, mem, organizer)
    assert mem.set_on_change_calls == []
    assert not hasattr(app.state, "auto_organizer")


def test_start_auto_organize_env_on_wires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTO_ORGANIZE_ENV, "1")
    app = _make_app()
    mem = _MemStub()
    organizer = _OrganizerStub()
    start_auto_organize(app, mem, organizer)
    assert len(mem.set_on_change_calls) == 1
    assert hasattr(app.state, "auto_organizer")


@pytest.mark.asyncio
async def test_stop_auto_organize_calls_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTO_ORGANIZE_ENV, "1")
    app = _make_app()
    mem = _MemStub()
    organizer = _OrganizerStub()
    start_auto_organize(app, mem, organizer)
    await stop_auto_organize(app)
    # No exception and state is accessible
    assert hasattr(app.state, "auto_organizer")


@pytest.mark.asyncio
async def test_stop_auto_organize_noop_when_not_set() -> None:
    app = _make_app()
    await stop_auto_organize(app)  # should not raise
