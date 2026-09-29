"""Directory links (symlink / junction / copy) and the OS checks behind them."""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.platform import links
from coffer.infrastructure.platform.links import DirLinkKind


def test_posix_links_with_a_symlink(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    target = tmp_path / "master"
    target.mkdir()
    link = tmp_path / "link"
    assert links.link_directory(target=target, link=link) is DirLinkKind.SYMLINK
    assert link.is_symlink() and link.resolve() == target.resolve()
    assert links.infer_dir_link_kind(link) is DirLinkKind.SYMLINK


def test_windows_falls_back_to_a_copy_when_nothing_links(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    target = tmp_path / "master"
    target.mkdir()
    (target / "SKILL.md").write_text("x", encoding="utf-8")
    link = tmp_path / "link"

    def no_symlink(*_a, **_k):
        raise OSError("no privilege")

    def no_mklink(*_a, **_k):
        raise FileNotFoundError("cmd")

    monkeypatch.setattr(links.os, "symlink", no_symlink)
    monkeypatch.setattr(links.subprocess, "run", no_mklink)
    assert links.link_directory(target=target, link=link) is DirLinkKind.COPY_FALLBACK
    assert (link / "SKILL.md").is_file() and not link.is_symlink()


def test_windows_uses_a_junction_when_symlink_is_refused(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    target = tmp_path / "master"
    target.mkdir()
    seen: list[list[str]] = []

    def no_symlink(*_a, **_k):
        raise OSError("no privilege")

    monkeypatch.setattr(links.os, "symlink", no_symlink)
    monkeypatch.setattr(links.subprocess, "run", lambda cmd, **_: seen.append(cmd))
    link = tmp_path / "link"
    assert links.link_directory(target=target, link=link) is DirLinkKind.JUNCTION
    assert seen == [["cmd", "/c", "mklink", "/J", str(link), str(target)]]


@pytest.mark.parametrize("host", ["darwin", "linux"])
def test_junction_checks_are_inert_off_windows(tmp_path: pathlib.Path, monkeypatch, host):
    monkeypatch.setattr("sys.platform", host)
    real = tmp_path / "real"
    real.mkdir()
    assert links.is_junction(real) is False
    assert links.remove_junction(real) is False
    assert real.is_dir()  # untouched
    assert links.infer_dir_link_kind(real) is DirLinkKind.COPY_FALLBACK


def test_windows_reads_the_reparse_point_attribute(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    d = tmp_path / "d"
    d.mkdir()

    class _St:
        st_file_attributes = 0x400

    monkeypatch.setattr(links.os, "lstat", lambda _p: _St())
    assert links.is_junction(d) is True
    assert links.infer_dir_link_kind(d) is DirLinkKind.JUNCTION


def test_windows_remove_junction_rmdirs_only_what_it_can(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    empty = tmp_path / "empty"
    empty.mkdir()
    assert links.remove_junction(empty) is True and not empty.exists()
    full = tmp_path / "full"
    full.mkdir()
    (full / "f").write_text("x", encoding="utf-8")
    assert links.remove_junction(full) is False and full.is_dir()
