"""Unit tests for the bundle manifest and the export/import summaries."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.manifest import SCHEMA_VERSION, Manifest
from coffer.domain.sync.models import AreaCount, ExportSummary


def test_manifest_defaults_to_current_schema_version() -> None:
    assert Manifest().schema_version == SCHEMA_VERSION


def test_manifest_carries_version_and_creation_time() -> None:
    created = datetime(2026, 7, 11, 9, 30, tzinfo=UTC)
    assert Manifest(created_at=created).to_dict() == {
        "schema_version": SCHEMA_VERSION,
        "created_at": created.isoformat(),
    }


def test_manifest_omits_a_creation_time_nobody_supplied() -> None:
    # The manifest a converge export writes must be byte-identical on every
    # machine and on every round: it lives in the working tree git three-way
    # merges, so a stamped-per-export timestamp would make an unchanged vault
    # commit and would conflict two machines on their first contact before they
    # had disagreed about anything real (spec vault-sync "Determinism").
    assert Manifest().to_dict() == {"schema_version": SCHEMA_VERSION}


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


def test_export_summary_starts_empty() -> None:
    exported = ExportSummary(path="/tmp/b")
    assert exported.areas == [] and exported.failures == []
    assert exported.credentials_included is False


def test_area_count_is_a_value_object() -> None:
    assert AreaCount("resources", 3) == AreaCount("resources", 3)
