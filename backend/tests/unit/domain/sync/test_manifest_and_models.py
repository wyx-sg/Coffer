"""Unit tests for the manifest, its version gate, and the serialization summary."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from coffer.domain.sync.errors import SyncBundleTooNew, SyncSerializationError
from coffer.domain.sync.manifest import (
    MANIFEST_PATH,
    SCHEMA_VERSION,
    Manifest,
    refuse_if_too_new,
)
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


# --- the version gate -------------------------------------------------------
#
# The whole point of writing a version into every round's tree: a build that
# does not know a newer layout must refuse it rather than half-apply it and
# publish over the rest (spec vault-sync; ``SYNC_BUNDLE_TOO_NEW``).


def test_the_manifest_is_always_read_from_the_same_path() -> None:
    # The writer and the gate must name one path, or the gate guards nothing.
    assert MANIFEST_PATH == "manifest.json"


def test_a_newer_layout_is_refused() -> None:
    raw = json.dumps({"schema_version": SCHEMA_VERSION + 1}).encode("utf-8")
    with pytest.raises(SyncBundleTooNew) as caught:
        refuse_if_too_new(raw)
    assert caught.value.found == SCHEMA_VERSION + 1
    assert caught.value.supported == SCHEMA_VERSION
    assert caught.value.code == "SYNC_BUNDLE_TOO_NEW"


def test_this_layout_and_an_older_one_are_accepted() -> None:
    refuse_if_too_new(json.dumps({"schema_version": SCHEMA_VERSION}).encode("utf-8"))
    refuse_if_too_new(json.dumps({"schema_version": SCHEMA_VERSION - 1}).encode("utf-8"))


def test_a_manifest_the_gate_cannot_read_is_not_a_refusal() -> None:
    # None of these can be written by a newer Coffer — it writes the file the
    # way the contract freezes it — so they are a virgin remote, a hand-edit or
    # corruption. Refusing them would wedge sync over a file the user cannot
    # find from the error, so the gate lets the round proceed as every build
    # has until now.
    refuse_if_too_new(None)
    refuse_if_too_new(b"")
    refuse_if_too_new(b"not json at all")
    refuse_if_too_new(b'["a list, not a mapping"]')
    refuse_if_too_new(b"{}")
    refuse_if_too_new(b'{"schema_version": "not-a-version"}')
    refuse_if_too_new(b'{"schema_version": null}')
    refuse_if_too_new(b"\xff\xfe not utf-8")
    # An unreadable ``created_at`` is not the gate's question either.
    refuse_if_too_new(b'{"schema_version": 1, "created_at": "yesterday"}')


def test_a_hand_written_version_is_still_a_version() -> None:
    # The gate reads the manifest the same way everything else does, so a
    # number written as a string says what it says.
    with pytest.raises(SyncBundleTooNew):
        refuse_if_too_new(f'{{"schema_version": "{SCHEMA_VERSION + 1}"}}'.encode())


# --- summaries --------------------------------------------------------------


def test_export_summary_starts_empty() -> None:
    exported = ExportSummary(path="/tmp/b")
    assert exported.areas == [] and exported.failures == []
    assert exported.credentials_included is False


def test_area_count_is_a_value_object() -> None:
    assert AreaCount("resources", 3) == AreaCount("resources", 3)
