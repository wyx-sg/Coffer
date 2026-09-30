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
