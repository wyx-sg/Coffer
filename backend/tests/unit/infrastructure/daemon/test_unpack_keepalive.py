from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from coffer.infrastructure.daemon import unpack_keepalive as uk


def _age(path: Path, seconds: float = 10 * 86400) -> float:
    old = path.stat().st_mtime - seconds
    os.utime(path, (old, old))
    return old


def test_touch_tree_refreshes_files_and_directories(tmp_path: Path) -> None:
    sub = tmp_path / "certifi"
    sub.mkdir()
    pem = sub / "cacert.pem"
    pem.write_text("x")
    old = _age(pem)
    _age(sub)

    assert uk.touch_tree(tmp_path) == 2
    assert pem.stat().st_atime > old + 86400
    assert sub.stat().st_atime > old + 86400


def test_touch_tree_skips_broken_symlinks(tmp_path: Path) -> None:
    (tmp_path / "dangling").symlink_to(tmp_path / "missing")
    assert uk.touch_tree(tmp_path) >= 0


def test_unpack_dir_is_none_when_not_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert uk.unpack_dir() is None
    asyncio.run(uk.keep_unpack_dir_alive())  # returns at once


def test_keepalive_touches_frozen_dir_repeatedly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    pem = tmp_path / "cacert.pem"
    pem.write_text("x")
    old = _age(pem)

    async def run() -> None:
        task = asyncio.create_task(uk.keep_unpack_dir_alive(interval=0.01))
        await asyncio.sleep(0.2)
        task.cancel()

    asyncio.run(run())
    assert pem.stat().st_atime > old + 86400


def _unpacked(root: Path, name: str, pid: int | None) -> Path:
    directory = root / name
    directory.mkdir()
    (directory / "base_library.zip").write_text("x")
    if pid is not None:
        (directory / uk.OWNER_MARKER).write_text(str(pid))
    return directory


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a frozen daemon deletes the unpack directories of exited Coffer binaries",
)
def test_sweep_removes_only_marked_dirs_whose_process_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    dead = _unpacked(tmp_path, "_MEIdead", 111)
    alive = _unpacked(tmp_path, "_MEIalive", 222)
    unmarked = _unpacked(tmp_path, "_MEIother", None)  # another program's, or not yet marked
    garbled = _unpacked(tmp_path, "_MEIgarbled", None)
    (garbled / uk.OWNER_MARKER).write_text("not a pid")
    unrelated = _unpacked(tmp_path, "cache", 111)

    removed = uk.sweep_dead_unpack_dirs(tmp_path, is_alive=lambda pid: pid == 222)

    assert removed == ["_MEIdead"]
    assert not dead.exists()
    assert alive.exists() and unmarked.exists() and garbled.exists() and unrelated.exists()


def test_sweep_never_removes_the_running_binarys_own_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    own = _unpacked(tmp_path, "_MEIown", 111)
    monkeypatch.setattr(sys, "_MEIPASS", str(own), raising=False)

    assert uk.sweep_dead_unpack_dirs(tmp_path, is_alive=lambda pid: False) == []
    assert own.exists()


def test_sweep_of_a_missing_temp_dir_removes_nothing(tmp_path: Path) -> None:
    assert uk.sweep_dead_unpack_dirs(tmp_path / "gone", is_alive=lambda pid: False) == []
