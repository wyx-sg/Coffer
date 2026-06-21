"""Unit: scanning the journal lane into indexable documents (recall slice)."""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

from coffer.infrastructure.knowledge.paths import journal_dir, journal_path
from coffer.infrastructure.memory.journal_files import (
    append_entry,
    journal_doc_id,
    scan_journal_dir,
)


def test_journal_doc_id_is_period_prefixed() -> None:
    assert journal_doc_id("2026-06") == "journal-2026-06"


def test_scan_empty_store_returns_empty(tmp_path: pathlib.Path) -> None:
    assert scan_journal_dir(tmp_path) == {}


def test_scan_indexes_one_doc_per_period_file(tmp_path: pathlib.Path) -> None:
    path = journal_path(tmp_path, "2026-06")
    append_entry(
        path,
        timestamp=datetime(2026, 6, 21, 9, tzinfo=UTC),
        body="deployed auth service to staging",
    )
    append_entry(path, timestamp=datetime(2026, 6, 21, 10, tzinfo=UTC), body="fixed the login bug")
    scan = scan_journal_dir(tmp_path)
    assert set(scan) == {journal_doc_id("2026-06")}
    doc = scan[journal_doc_id("2026-06")]
    assert doc.period == "2026-06"
    assert doc.title == "Journal 2026-06"
    # Both entry bodies are present in the chunkable body, markers excluded.
    assert "deployed auth service to staging" in doc.body
    assert "fixed the login bug" in doc.body
    assert "coffer:journal" not in doc.body
    # created/updated span the oldest→newest entry timestamps.
    assert doc.created_at == datetime(2026, 6, 21, 9, tzinfo=UTC)
    assert doc.updated_at == datetime(2026, 6, 21, 10, tzinfo=UTC)
    assert doc.path == journal_path(tmp_path, "2026-06")


def test_scan_covers_multiple_period_files(tmp_path: pathlib.Path) -> None:
    append_entry(
        journal_path(tmp_path, "2026-05"), timestamp=datetime(2026, 5, 1, tzinfo=UTC), body="may"
    )
    append_entry(
        journal_path(tmp_path, "2026-06"), timestamp=datetime(2026, 6, 1, tzinfo=UTC), body="june"
    )
    assert set(scan_journal_dir(tmp_path)) == {journal_doc_id("2026-05"), journal_doc_id("2026-06")}


def test_scan_sha_changes_on_append(tmp_path: pathlib.Path) -> None:
    path = journal_path(tmp_path, "2026-06")
    append_entry(path, timestamp=datetime(2026, 6, 21, 9, tzinfo=UTC), body="first")
    sha1 = scan_journal_dir(tmp_path)[journal_doc_id("2026-06")].content_sha256
    append_entry(path, timestamp=datetime(2026, 6, 21, 10, tzinfo=UTC), body="second")
    sha2 = scan_journal_dir(tmp_path)[journal_doc_id("2026-06")].content_sha256
    assert sha1 != sha2


def test_scan_skips_empty_file(tmp_path: pathlib.Path) -> None:
    d = journal_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07.md").write_text("", encoding="utf-8")
    assert scan_journal_dir(tmp_path) == {}
