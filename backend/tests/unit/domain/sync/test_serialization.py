"""Unit tests for deterministic resource <-> bundle-document projection.

A document is identity + description + config. It is *not* the resource's
reach: ``enabled`` and ``scope`` are one decision the user makes per machine,
on the machine, and they no longer leave it (spec vault-sync
``## What does not sync``). That absence is asserted here rather than assumed,
because it is the whole of the decision at this layer — and so is its mirror
image, that a document an older build wrote with those fields in it still
parses instead of being quarantined.
"""

from __future__ import annotations

import pytest

from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.serialization import parse_resource_doc, resource_to_doc


def test_doc_is_identity_description_and_config_and_nothing_else() -> None:
    doc = resource_to_doc(
        kind="mcp_server",
        name="confluence",
        description="wiki",
        config={"transport": {"kind": "stdio"}},
    )
    assert set(doc) == {"kind", "name", "description", "config"}
    # No id / created_at / updated_at leak into the exported form — they are
    # machine-local and would make two exports of one vault differ.
    assert "id" not in doc
    assert "created_at" not in doc
    assert "updated_at" not in doc


def test_doc_carries_no_reach() -> None:
    """The decision, at the smallest layer it is visible on.

    Reach is set per machine. A document that carried it would let the machine
    that exported last re-answer, silently and every round, a question the
    machine at the other end had already answered for itself.
    """
    doc = resource_to_doc(kind="mcp_server", name="x", description=None, config={"a": 1})
    assert "enabled" not in doc
    assert "scope" not in doc


def test_round_trip_preserves_fields() -> None:
    doc = resource_to_doc(
        kind="mcp_server",
        name="tg",
        description=None,
        config={"channel_type": "telegram", "token_ref": "x"},
    )
    parsed = parse_resource_doc(doc)
    assert parsed.kind == "mcp_server"
    assert parsed.name == "tg"
    assert parsed.description is None
    assert parsed.config == {"channel_type": "telegram", "token_ref": "x"}


def test_description_key_is_always_emitted() -> None:
    # Always present (even when null) so two exports stay byte-identical
    # rather than gaining and losing a key.
    doc = resource_to_doc(kind="mcp_server", name="tg", description=None, config={})
    assert "description" in doc and doc["description"] is None


def test_config_is_copied_not_aliased() -> None:
    config = {"a": 1}
    doc = resource_to_doc(kind="mcp_server", name="x", description=None, config=config)
    config["a"] = 2
    assert doc["config"]["a"] == 1


def test_parse_rejects_missing_fields() -> None:
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"kind": "mcp_server", "name": "x"})


def test_parse_accepts_an_older_builds_reach_fields_and_drops_them() -> None:
    """The shared tree still holds documents written before reach stopped
    travelling, and every machine that has not upgraded keeps writing more.

    Refusing them the way an unknown key is refused would quarantine those
    documents on every upgraded machine, so one stale machine would stall the
    whole fleet. They parse, and what they said about reach goes nowhere: the
    parsed document has no field to carry it in.
    """
    parsed = parse_resource_doc(
        {
            "kind": "mcp_server",
            "name": "x",
            "description": None,
            "enabled": False,
            "config": {"value": "v"},
            "scope": {"agents": [], "machines": ["a1a1a1a1a1a1a1a1"]},
        }
    )
    assert parsed.kind == "mcp_server"
    assert parsed.name == "x"
    assert parsed.config == {"value": "v"}
    assert not hasattr(parsed, "enabled")
    assert not hasattr(parsed, "scope")


def test_parse_still_rejects_a_genuinely_unknown_field() -> None:
    """Leniency is for the two fields that were deliberately retired, and for
    nothing else — a typo'd key is a document that would import as something
    other than what it says."""
    with pytest.raises(SyncSerializationError):
        parse_resource_doc(
            {
                "kind": "mcp_server",
                "name": "x",
                "description": None,
                "config": {},
                "id": 7,
            }
        )
    with pytest.raises(SyncSerializationError):
        parse_resource_doc(
            {
                "kind": "mcp_server",
                "name": "x",
                "description": None,
                "config": {},
                # One retired field alongside one misspelling: the misspelling
                # still decides the outcome.
                "enabled": True,
                "scop": None,
            }
        )


def test_parse_rejects_wrong_types() -> None:
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"kind": "", "name": "x", "description": None, "config": {}})
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"kind": "k", "name": "", "description": None, "config": {}})
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"kind": "k", "name": "x", "description": 7, "config": {}})
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"kind": "k", "name": "x", "description": None, "config": []})
