"""The frozen daemon's sidecar deployment (spec mcp-gateway FR-026).

The desktop shell used to place these binaries in ``~/.coffer/bin``; the daemon
does it now. The staleness rules are the part worth pinning — each of the three
signals exists because the other two miss a real case.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from coffer.application.binary_deploy import (
    _atomic_deploy,
    _sentinel_for,
    deploy_frozen_sidecars,
    needs_copy,
)


def _write(path: Path, content: bytes, *, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_missing_target_needs_a_copy(tmp_path: Path) -> None:
    source = _write(tmp_path / "src" / "coffer-mcp-shim", b"binary")
    assert needs_copy(tmp_path / "bin" / "coffer-mcp-shim", source, "1.0.0") is True


def test_matching_target_is_left_alone(tmp_path: Path) -> None:
    """The steady state on every restart after the first: nothing to do."""
    source = _write(tmp_path / "src" / "shim", b"same-bytes", mtime=1000)
    target = _write(tmp_path / "bin" / "shim", b"same-bytes", mtime=2000)
    _sentinel_for(target).write_text("1.0.0\n")
    assert needs_copy(target, source, "1.0.0") is False


def test_size_change_forces_a_copy(tmp_path: Path) -> None:
    source = _write(tmp_path / "src" / "shim", b"longer-bytes", mtime=1000)
    target = _write(tmp_path / "bin" / "shim", b"short", mtime=2000)
    _sentinel_for(target).write_text("1.0.0\n")
    assert needs_copy(target, source, "1.0.0") is True


def test_newer_source_forces_a_copy_at_equal_size(tmp_path: Path) -> None:
    """A dev or PR build changes the binary without changing the version."""
    source = _write(tmp_path / "src" / "shim", b"aaaa", mtime=5000)
    target = _write(tmp_path / "bin" / "shim", b"bbbb", mtime=1000)
    _sentinel_for(target).write_text("1.0.0\n")
    assert needs_copy(target, source, "1.0.0") is True


def test_version_change_forces_a_copy_at_equal_size_and_mtime(tmp_path: Path) -> None:
    """Two releases can produce a same-size binary; size alone would miss it."""
    source = _write(tmp_path / "src" / "shim", b"aaaa", mtime=1000)
    target = _write(tmp_path / "bin" / "shim", b"bbbb", mtime=2000)
    _sentinel_for(target).write_text("1.0.0\n")
    assert needs_copy(target, source, "2.0.0") is True


def test_missing_sentinel_forces_a_copy(tmp_path: Path) -> None:
    source = _write(tmp_path / "src" / "shim", b"aaaa", mtime=1000)
    target = _write(tmp_path / "bin" / "shim", b"bbbb", mtime=2000)
    assert needs_copy(target, source, "1.0.0") is True


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a frozen daemon deploys its sibling binaries on start",
)
def test_deploy_is_atomic_and_executable(tmp_path: Path) -> None:
    source = _write(tmp_path / "src" / "shim", b"payload")
    target = tmp_path / "bin" / "shim"

    _atomic_deploy(source, target, "1.2.3")

    assert target.read_bytes() == b"payload"
    assert target.stat().st_mode & stat.S_IXUSR
    assert _sentinel_for(target).read_text().strip() == "1.2.3"
    # The temp sibling must not survive — a leftover would be mistaken for a
    # binary by anything globbing the directory.
    assert not (tmp_path / "bin" / ".shim.tmp").exists()


def test_deploy_replaces_an_existing_binary(tmp_path: Path) -> None:
    source = _write(tmp_path / "src" / "shim", b"new-payload")
    target = _write(tmp_path / "bin" / "shim", b"old")

    _atomic_deploy(source, target, "2.0.0")

    assert target.read_bytes() == b"new-payload"


def test_no_op_when_not_frozen() -> None:
    """A source install already has these on PATH via pip (FR-018)."""
    assert deploy_frozen_sidecars() == []
