"""Unit: on-disk handoff (working-state) file I/O + branch slug."""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

from coffer.infrastructure.memory.handoff_files import (
    HandoffFile,
    branch_slug,
    read_handoff,
    write_handoff,
)


def test_branch_slug_is_filesystem_safe() -> None:
    assert branch_slug("feature/007-memory") == "feature-007-memory"
    assert branch_slug("main") == "main"


def test_write_then_read_roundtrip(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "handoff" / "main.md"
    ts = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)
    write_handoff(path, branch="main", body="doing X\nnext: Y", updated_at=ts)
    got = read_handoff(path)
    assert got == HandoffFile(branch="main", body="doing X\nnext: Y", updated_at=ts)


def test_read_missing_returns_none(tmp_path: pathlib.Path) -> None:
    assert read_handoff(tmp_path / "nope.md") is None


def test_write_overwrites(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "h.md"
    ts1 = datetime(2026, 6, 20, 1, 0, tzinfo=UTC)
    ts2 = datetime(2026, 6, 20, 2, 0, tzinfo=UTC)
    write_handoff(path, branch="b", body="first", updated_at=ts1)
    write_handoff(path, branch="b", body="second", updated_at=ts2)
    got = read_handoff(path)
    assert got is not None
    assert got.body == "second"
    assert got.updated_at == ts2
