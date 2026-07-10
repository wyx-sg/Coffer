"""Unit tests for the sync manifest and config/state value objects."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.manifest import SCHEMA_VERSION, Manifest
from coffer.domain.sync.models import SyncConfig, SyncState, SyncStatus


def test_manifest_defaults_to_current_schema_version() -> None:
    assert Manifest().schema_version == SCHEMA_VERSION


def test_manifest_is_machine_independent() -> None:
    # Byte-identical on every machine so it never becomes a merge conflict.
    assert Manifest().to_dict() == {"schema_version": SCHEMA_VERSION}


def test_manifest_round_trip() -> None:
    m = Manifest(schema_version=SCHEMA_VERSION)
    assert Manifest.from_dict(m.to_dict()) == m


def test_manifest_from_dict_rejects_malformed() -> None:
    with pytest.raises(SyncSerializationError):
        Manifest.from_dict({})
    with pytest.raises(SyncSerializationError):
        Manifest.from_dict({"schema_version": "not-an-int"})


def test_schema_version_is_4_for_scoped_resource_docs() -> None:
    # Bumped for Task 6 (scope rides resource docs) — an older build must
    # refuse a workspace whose resource docs carry a scope key.
    assert SCHEMA_VERSION == 4


def test_sync_config_is_operational() -> None:
    now = datetime.now(tz=UTC)
    assert not SyncConfig(None, True, False, 300, "main", now).is_operational()
    assert not SyncConfig("git@x", False, False, 300, "main", now).is_operational()
    assert SyncConfig("git@x", True, False, 300, "main", now).is_operational()


def test_sync_state_defaults() -> None:
    s = SyncState(status=SyncStatus.CLEAN, last_sync_at=None, last_error=None)
    assert s.conflict_paths == []
    assert s.locked_refs == []


def test_sync_status_values() -> None:
    assert SyncStatus.CREDENTIALS_LOCKED.value == "credentials_locked"
    assert SyncStatus.CONFLICTED.value == "conflicted"
