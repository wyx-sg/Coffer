"""Unit tests for the sync manifest and config/state value objects."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.manifest import SCHEMA_VERSION, Manifest
from coffer.domain.sync.models import SyncConfig, SyncState, SyncStatus


def test_manifest_create_uses_current_schema_version() -> None:
    m = Manifest.create(machine_id="m1", coffer_version="0.4.0", kinds=["mcp_server", "channel"])
    assert m.schema_version == SCHEMA_VERSION


def test_manifest_to_dict_sorts_kinds_deterministically() -> None:
    a = Manifest.create(machine_id="m", coffer_version="v", kinds=["channel", "agent"])
    b = Manifest.create(machine_id="m", coffer_version="v", kinds=["agent", "channel"])
    assert a.to_dict() == b.to_dict()
    assert a.to_dict()["kinds"] == ["agent", "channel"]


def test_manifest_round_trip() -> None:
    m = Manifest.create(machine_id="m1", coffer_version="0.4.0", kinds=["skill"])
    assert Manifest.from_dict(m.to_dict()) == m


def test_manifest_from_dict_rejects_malformed() -> None:
    with pytest.raises(SyncSerializationError):
        Manifest.from_dict({"schema_version": 1, "machine_id": "m"})
    with pytest.raises(SyncSerializationError):
        Manifest.from_dict(
            {"schema_version": 1, "machine_id": "m", "coffer_version": "v", "kinds": "skill"}
        )


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
