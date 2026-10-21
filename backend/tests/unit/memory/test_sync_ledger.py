"""A ledger written under another reader revision re-reads every source once."""

from __future__ import annotations

import pathlib

from coffer.infrastructure.memory.sync_ledger import (
    Ledger,
    LedgerStore,
    SourceRecord,
)
from coffer.infrastructure.vault.json_store import JsonStore


def test_sources_survive_a_round_trip_under_the_same_revision(tmp_path: pathlib.Path) -> None:
    store = LedgerStore(lambda: tmp_path / "ledger.json")
    ledger = Ledger(previewed=True)
    ledger.sources["/a/MEMORY.md"] = SourceRecord(digest="d1", entries=["e1"])
    store.save(ledger)

    loaded = store.load()

    assert loaded.sources["/a/MEMORY.md"].digest == "d1"


def test_a_ledger_from_an_older_reader_revision_forgets_its_source_digests(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "ledger.json"
    store = LedgerStore(lambda: path)
    ledger = Ledger(previewed=True)
    ledger.sources["/a/MEMORY.md"] = SourceRecord(digest="d1", entries=["e1"])
    store.save(ledger)
    raw = JsonStore(lambda: path).read()
    raw["reader_revision"] = 1
    JsonStore(lambda: path).write(raw)

    loaded = store.load()

    assert loaded.sources == {}
    assert loaded.previewed is True
