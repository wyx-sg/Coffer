"""Unit tests for deterministic resource <-> bundle-document projection.

A document is identity + description + config, and the identity is the
resource's immutable ``uid`` (ADR resource-identity-is-an-immutable-uid). The
name rides *inside* the document rather than being the document's filing, which
is what lets a rename cross the remote as a modification of one file.

It is *not* the resource's reach: ``enabled`` and ``scope`` are one decision the
user makes per machine, on the machine, and they no longer leave it (spec
vault-sync ``## What does not sync``). That absence is asserted here rather than
assumed, because it is the whole of the decision at this layer — and so, now, is
its mirror image: a document that spells one is refused like any other document
carrying a field this layout does not have.
"""

from __future__ import annotations

import pytest

from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.serialization import parse_resource_doc, resource_to_doc

UID = "7f3a1c2e4b5d6a7f8091a2b3c4d5e6f7"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a resource document is identity, description and config"
)
def test_doc_is_identity_description_and_config_and_nothing_else() -> None:
    doc = resource_to_doc(
        uid=UID,
        kind="mcp_server",
        name="confluence",
        description="wiki",
        config={"transport": {"kind": "stdio"}},
    )
    assert set(doc) == {"uid", "kind", "name", "description", "config"}
    # No id / created_at / updated_at leak into the exported form — they are
    # machine-local and would make two exports of one vault differ. The uid is
    # the opposite of machine-local: it is minted once and is the same string
    # on every machine that holds this resource, which is why it can be the
    # one field the whole layout is keyed on.
    assert "id" not in doc
    assert "created_at" not in doc
    assert "updated_at" not in doc


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a resource document is identity, description and config"
)
def test_doc_carries_no_reach() -> None:
    """The decision, at the smallest layer it is visible on.

    Reach is set per machine. A document that carried it would let the machine
    that exported last re-answer, silently and every round, a question the
    machine at the other end had already answered for itself.
    """
    doc = resource_to_doc(uid=UID, kind="mcp_server", name="x", description=None, config={"a": 1})
    assert "enabled" not in doc
    assert "scope" not in doc


def test_round_trip_preserves_fields() -> None:
    doc = resource_to_doc(
        uid=UID,
        kind="mcp_server",
        name="tg",
        description=None,
        config={"channel_type": "telegram", "token_ref": "x"},
    )
    parsed = parse_resource_doc(doc)
    assert parsed.uid == UID
    assert parsed.kind == "mcp_server"
    assert parsed.name == "tg"
    assert parsed.description is None
    assert parsed.config == {"channel_type": "telegram", "token_ref": "x"}


def test_a_renamed_resource_keeps_its_identity_through_the_document() -> None:
    """Two exports of one resource the user renamed in between.

    The uid is the same string, and it is the only thing about the two
    documents that has to be: everything else is free to change, which is what
    "the name is a label" means at this layer. The receiving machine can
    therefore tell a rename from a delete-and-create — the distinction the
    whole ADR turns on — without any rename event in the bundle.
    """
    before = resource_to_doc(
        uid=UID, kind="mcp_server", name="aaa", description=None, config={"v": 1}
    )
    after = resource_to_doc(
        uid=UID, kind="mcp_server", name="zzz", description="renamed", config={"v": 2}
    )
    assert before["uid"] == after["uid"] == UID
    assert parse_resource_doc(before).uid == parse_resource_doc(after).uid


def test_description_key_is_always_emitted() -> None:
    # Always present (even when null) so two exports stay byte-identical
    # rather than gaining and losing a key.
    doc = resource_to_doc(uid=UID, kind="mcp_server", name="tg", description=None, config={})
    assert "description" in doc and doc["description"] is None


def test_config_is_copied_not_aliased() -> None:
    config = {"a": 1}
    doc = resource_to_doc(uid=UID, kind="mcp_server", name="x", description=None, config=config)
    config["a"] = 2
    assert doc["config"]["a"] == 1


def test_parse_rejects_missing_fields() -> None:
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"uid": UID, "kind": "mcp_server", "name": "x"})


def test_parse_rejects_a_document_with_no_identity() -> None:
    """Everything the previous bundle layout wrote lands here.

    A document with no ``uid`` names a resource this build cannot identify, and
    there is nothing safe to do with it: matching it by name is exactly the
    identity the ADR removed. It is refused, and the round reports the path
    rather than importing something under a guess.
    """
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"kind": "mcp_server", "name": "x", "description": None, "config": {}})


def test_parse_rejects_an_unknown_field_including_a_retired_reach_one() -> None:
    """A typo'd key is a document that would import as something other than
    what it says.

    The two reach fields used to be the one exception — read and dropped — so a
    machine still on an older build could not quarantine its documents on every
    machine that had upgraded. Bumping the bundle layout took the problem away
    with the exception: such a build refuses this tree outright, so nothing
    that would write those fields can reach this parser any more.
    """
    with pytest.raises(SyncSerializationError):
        parse_resource_doc(
            {
                "uid": UID,
                "kind": "mcp_server",
                "name": "x",
                "description": None,
                "config": {},
                "id": 7,
            }
        )
    for retired in ("enabled", "scope"):
        with pytest.raises(SyncSerializationError):
            parse_resource_doc(
                {
                    "uid": UID,
                    "kind": "mcp_server",
                    "name": "x",
                    "description": None,
                    "config": {},
                    retired: None,
                }
            )


def test_parse_rejects_wrong_types() -> None:
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"uid": "", "kind": "k", "name": "x", "description": None, "config": {}})
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"uid": 7, "kind": "k", "name": "x", "description": None, "config": {}})
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"uid": UID, "kind": "", "name": "x", "description": None, "config": {}})
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"uid": UID, "kind": "k", "name": "", "description": None, "config": {}})
    with pytest.raises(SyncSerializationError):
        parse_resource_doc({"uid": UID, "kind": "k", "name": "x", "description": 7, "config": {}})
    with pytest.raises(SyncSerializationError):
        parse_resource_doc(
            {"uid": UID, "kind": "k", "name": "x", "description": None, "config": []}
        )
