"""Unit coverage for FsOpenService validation + spawn (spec daemon "Open and
reveal existing absolute paths", ADR: daemon-proxies-os-file-actions).

The per-OS launcher argv is the platform adapter's answer and is covered in
``tests/unit/infrastructure/platform/test_desktop.py``; here the port is a fake,
so these tests say only what the use case does with its answer.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.fs import open_service
from coffer.application.fs.open_service import FsOpenService
from coffer.domain.errors import FsPathNotOpenable

from ._fake_platform import FakePlatform


@pytest.fixture
def captured(monkeypatch) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(open_service.subprocess, "Popen", lambda cmd, **_: calls.append(cmd))
    return calls


def _svc() -> FsOpenService:
    return FsOpenService(FakePlatform())


def _file(tmp_path: pathlib.Path) -> str:
    f = tmp_path / "doc.md"
    f.write_text("x", encoding="utf-8")
    return str(f)


def test_open_spawns_the_platform_argv(tmp_path, captured):
    path = _file(tmp_path)
    _svc().open(path, with_app="Cursor")
    assert captured == [["open-with", "Cursor", path]]


def test_open_without_editor_asks_for_the_default(tmp_path, captured):
    path = _file(tmp_path)
    _svc().open(path)
    assert captured == [["open-with", "<default>", path]]


def test_reveal_spawns_the_platform_argv(tmp_path, captured):
    path = _file(tmp_path)
    _svc().reveal(path)
    assert captured == [["reveal", path]]


# --- validation: nothing is spawned for a bad path -----------------------------


def test_open_rejects_relative_path(tmp_path, captured):
    with pytest.raises(FsPathNotOpenable) as exc:
        _svc().open("relative/doc.md")
    assert exc.value.reason == "not_absolute"
    assert captured == []


def test_open_rejects_empty_path(captured):
    with pytest.raises(FsPathNotOpenable):
        _svc().open("")
    assert captured == []


def test_open_rejects_missing_path(tmp_path, captured):
    with pytest.raises(FsPathNotOpenable) as exc:
        _svc().open(str(tmp_path / "nope.md"))
    assert exc.value.reason == "not_found"
    assert captured == []


def test_reveal_rejects_missing_path(tmp_path, captured):
    with pytest.raises(FsPathNotOpenable):
        _svc().reveal(str(tmp_path / "gone"))
    assert captured == []


def test_launch_failure_becomes_fs_path_not_openable(tmp_path, monkeypatch):
    path = _file(tmp_path)

    def boom(cmd, **_):
        raise OSError("no launcher")

    monkeypatch.setattr(open_service.subprocess, "Popen", boom)
    with pytest.raises(FsPathNotOpenable) as exc:
        _svc().open(path)
    assert exc.value.reason == "launch_failed"


def test_spawn_detaches_and_silences_output(tmp_path, monkeypatch):
    """The launcher is detached (start_new_session) with stdout/stderr discarded,
    so a long-lived editor never holds the daemon nor leaks into its streams."""
    path = _file(tmp_path)
    seen: dict[str, object] = {}
    monkeypatch.setattr(open_service.subprocess, "Popen", lambda cmd, **kw: seen.update(kw))
    _svc().open(path)
    assert seen["start_new_session"] is True
    assert seen["stdout"] == open_service.subprocess.DEVNULL
    assert seen["stderr"] == open_service.subprocess.DEVNULL
