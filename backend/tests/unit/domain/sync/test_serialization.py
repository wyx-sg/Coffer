"""Unit tests for deterministic resource <-> sync-document projection."""

from __future__ import annotations

import pytest

from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.serialization import parse_resource_doc, resource_to_doc


def test_doc_excludes_machine_local_fields() -> None:
    doc = resource_to_doc(
        kind="mcp_server",
        name="confluence",
        description="wiki",
        enabled=True,
        config={"transport": {"kind": "stdio"}},
        scope=None,
    )
    assert set(doc) == {"kind", "name", "description", "enabled", "config", "scope"}
    # No id / created_at / updated_at leak into the synced form.
    assert "id" not in doc
    assert "created_at" not in doc
    assert "updated_at" not in doc


def test_round_trip_preserves_fields() -> None:
    doc = resource_to_doc(
        kind="channel",
        name="tg",
        description=None,
        enabled=False,
        config={"channel_type": "telegram", "token_ref": "x"},
        scope=None,
    )
    parsed = parse_resource_doc(doc)
    assert parsed.kind == "channel"
    assert parsed.name == "tg"
    assert parsed.description is None
    assert parsed.enabled is False
    assert parsed.config == {"channel_type": "telegram", "token_ref": "x"}
    assert parsed.scope is None


def test_round_trip_preserves_scope() -> None:
    matrix = {"machine-1": ["agent-a", "agent-b"], "machine-2": "*"}
    doc = resource_to_doc(
        kind="agent",
        name="coder",
        description=None,
        enabled=True,
        config={},
        scope=matrix,
    )
    assert doc["scope"] == matrix
    parsed = parse_resource_doc(doc)
    assert parsed.scope == matrix


def test_parse_tolerates_missing_scope_key() -> None:
    # Backward tolerance: a v3 workspace doc has no "scope" key at all — it
    # must still parse cleanly, with scope defaulting to None AND
    # scope_present False (distinct from an explicit `scope: null`, which
    # is also None but scope_present True — the importer relies on telling
    # these apart).
    parsed = parse_resource_doc(
        {
            "kind": "mcp_server",
            "name": "x",
            "description": None,
            "enabled": True,
            "config": {},
        }
    )
    assert parsed.scope is None
    assert parsed.scope_present is False


def test_parse_marks_scope_present_for_explicit_null() -> None:
    # An explicit `scope: null` is an OPINION (unscoped) — unlike the
    # missing-key case above, scope_present must be True here.
    parsed = parse_resource_doc(
        {
            "kind": "channel",
            "name": "x",
            "description": None,
            "enabled": True,
            "config": {},
            "scope": None,
        }
    )
    assert parsed.scope is None
    assert parsed.scope_present is True


def test_resource_to_doc_output_always_parses_scope_present() -> None:
    # v4+ writers always emit the "scope" key (resource_to_doc's contract),
    # so anything round-tripped through it must parse as scope_present=True.
    doc = resource_to_doc(
        kind="channel", name="tg", description=None, enabled=True, config={}, scope=None
    )
    assert parse_resource_doc(doc).scope_present is True


def test_config_is_copied_not_aliased() -> None:
    config = {"a": 1}
    doc = resource_to_doc(
        kind="mcp_server", name="x", description=None, enabled=True, config=config, scope=None
    )
    config["a"] = 2
    assert doc["config"]["a"] == 1


def test_scope_is_copied_not_aliased() -> None:
    scope = {"machine-1": ["agent-a"]}
    doc = resource_to_doc(
        kind="agent", name="x", description=None, enabled=True, config={}, scope=scope
    )
    scope["machine-1"] = ["agent-b"]
    assert doc["scope"]["machine-1"] == ["agent-a"]


def test_parse_rejects_missing_fields() -> None:
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"kind": "mcp_server", "name": "x"})


def test_parse_rejects_unexpected_fields() -> None:
    with pytest.raises(SyncSerializationError):
        parse_resource_doc(
            {
                "kind": "mcp_server",
                "name": "x",
                "description": None,
                "enabled": True,
                "config": {},
                "scope": None,
                "id": 7,
            }
        )


def test_parse_rejects_wrong_types() -> None:
    with pytest.raises(SyncSerializationError):
        parse_resource_doc(
            {"kind": "", "name": "x", "description": None, "enabled": True, "config": {}}
        )
    with pytest.raises(SyncSerializationError):
        parse_resource_doc(
            {"kind": "k", "name": "x", "description": None, "enabled": "yes", "config": {}}
        )
    with pytest.raises(SyncSerializationError):
        parse_resource_doc(
            {"kind": "k", "name": "x", "description": None, "enabled": True, "config": []}
        )
    with pytest.raises(SyncSerializationError):
        parse_resource_doc(
            {
                "kind": "k",
                "name": "x",
                "description": None,
                "enabled": True,
                "config": {},
                "scope": "not-a-mapping",
            }
        )
