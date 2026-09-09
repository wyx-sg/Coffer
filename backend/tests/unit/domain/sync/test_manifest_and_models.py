"""Unit tests for the bundle manifest and the export/import summaries."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.manifest import SCHEMA_VERSION, Manifest
from coffer.domain.sync.models import AreaCount, ExportSummary, ImportSummary


def test_manifest_defaults_to_current_schema_version() -> None:
    assert Manifest().schema_version == SCHEMA_VERSION


def test_manifest_carries_version_and_creation_time() -> None:
    created = datetime(2026, 7, 11, 9, 30, tzinfo=UTC)
    assert Manifest(created_at=created).to_dict() == {
        "schema_version": SCHEMA_VERSION,
        "created_at": created.isoformat(),
    }


def test_manifest_stamps_a_creation_time_when_none_is_given() -> None:
    # created_at is the one field that legitimately differs between two
    # exports of an unchanged vault.
    assert "created_at" in Manifest().to_dict()


def test_manifest_round_trip() -> None:
    m = Manifest(schema_version=SCHEMA_VERSION, created_at=datetime.now(tz=UTC))
    assert Manifest.from_dict(m.to_dict()) == m


def test_manifest_from_dict_rejects_malformed() -> None:
    with pytest.raises(SyncSerializationError):
        Manifest.from_dict({})
    with pytest.raises(SyncSerializationError):
        Manifest.from_dict({"schema_version": "not-an-int"})
    with pytest.raises(SyncSerializationError):
        Manifest.from_dict({"schema_version": 1, "created_at": "not-a-time"})


def test_manifest_tolerates_a_missing_creation_time() -> None:
    # Only the version is load-bearing; a hand-written manifest still reads.
    assert Manifest.from_dict({"schema_version": 1}).created_at is None


def test_summaries_start_empty() -> None:
    exported = ExportSummary(path="/tmp/b")
    assert exported.areas == [] and exported.failures == []
    assert exported.credentials_included is False
    imported = ImportSummary(path="/tmp/b")
    assert imported.areas == [] and imported.failures == [] and imported.locked_refs == []


def test_area_count_is_a_value_object() -> None:
    assert AreaCount("resources", 3) == AreaCount("resources", 3)
