"""Unit tests for the atomic file-write helpers
(``coffer.infrastructure.knowledge.fs``).

These guard the KB19 invariant: a persisted source-of-truth file is written via
a same-dir temp file → fsync → ``os.replace``, so a crash mid-write leaves either
the complete old file or the complete new file, never a truncated mix.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from coffer.infrastructure.knowledge.fs import atomic_write_bytes, atomic_write_text


def test_write_text_round_trips(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    atomic_write_text(target, "héllo 世界\n")
    assert target.read_text(encoding="utf-8") == "héllo 世界\n"


def test_write_bytes_round_trips(tmp_path: Path) -> None:
    target = tmp_path / "raw.bin"
    payload = b"\x00\x01\x02binary\xff"
    atomic_write_bytes(target, payload)
    assert target.read_bytes() == payload


def test_overwrites_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    target.write_text("old", encoding="utf-8")
    atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"


def test_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "doc.md"
    atomic_write_text(target, "content")
    assert target.read_text(encoding="utf-8") == "content"


def test_no_temp_files_left_after_success(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    atomic_write_text(target, "content")
    # Only the target remains — no ``.<name>.<pid>.tmp`` sidecar.
    assert [p.name for p in tmp_path.iterdir()] == ["doc.md"]


def test_failure_leaves_original_intact_and_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If ``os.replace`` fails mid-write, the ORIGINAL file is untouched and no
    leftover ``.tmp`` file remains — the core atomicity guarantee."""
    target = tmp_path / "doc.md"
    target.write_text("original", encoding="utf-8")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated crash before rename completes")

    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError, match="simulated crash"):
        atomic_write_text(target, "new content that must NOT land")

    # Old content is fully intact — a reader never saw a partial file.
    assert target.read_text(encoding="utf-8") == "original"
    # The temp file was cleaned up on failure.
    assert [p.name for p in tmp_path.iterdir()] == ["doc.md"]


def test_concurrent_same_path_writes_never_collide(tmp_path: Path) -> None:
    """Many threads writing the SAME path concurrently must all succeed (no
    spurious failure from a shared temp name) and leave a complete file — the
    per-call temp uniquifier guards a fact-update racing an organizer rewrite."""
    target = tmp_path / "doc.md"
    payloads = [f"version-{i}\n".encode() for i in range(64)]

    errors: list[BaseException] = []

    def _write(data: bytes) -> None:
        try:
            atomic_write_bytes(target, data)
        except BaseException as exc:
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(_write, payloads))

    # No writer failed on a temp-name collision...
    assert errors == []
    # ...the target is one COMPLETE version (never torn), and no temp leaked.
    assert target.read_bytes() in payloads
    assert [p.name for p in tmp_path.iterdir()] == ["doc.md"]
