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
    )
    assert set(doc) == {"kind", "name", "description", "enabled", "config"}
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
    )
    parsed = parse_resource_doc(doc)
    assert parsed.kind == "channel"
    assert parsed.name == "tg"
    assert parsed.description is None
    assert parsed.enabled is False
    assert parsed.config == {"channel_type": "telegram", "token_ref": "x"}


def test_config_is_copied_not_aliased() -> None:
    config = {"a": 1}
    doc = resource_to_doc(
        kind="mcp_server", name="x", description=None, enabled=True, config=config
    )
    config["a"] = 2
    assert doc["config"]["a"] == 1


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
