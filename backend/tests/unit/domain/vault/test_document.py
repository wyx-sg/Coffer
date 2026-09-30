"""The resource document and the vault's JSON encoding (coffer.domain.vault.document)."""

from __future__ import annotations

import json

import pytest

from coffer.domain.vault.document import (
    DocumentInvalid,
    ResourceDocument,
    decode,
    encode,
    parse_resource,
)


def _raw(**extra: object) -> bytes:
    doc = {
        "uid": "0" * 32,
        "kind": "mcp_server",
        "format_version": 1,
        "name": "linear",
        "description": None,
        "config": {"transport": {"type": "stdio", "command": "npx"}},
    }
    doc.update(extra)
    return encode(doc)


def test_the_encoding_is_deterministic_and_ends_in_a_newline() -> None:
    data = _raw()
    assert data.endswith(b"\n")
    assert encode(decode(data)) == data


@pytest.mark.acceptance(spec="vault-sync", scenario="an unchanged vault serializes to an identical tree")
def test_a_document_round_trips_to_the_same_bytes() -> None:
    data = _raw()
    assert parse_resource(data).to_bytes() == data


def test_unknown_fields_are_kept_in_place_on_a_write() -> None:
    raw = json.loads(_raw())
    doc = {}
    for key, value in raw.items():
        doc[key] = value
        if key == "name":
            doc["enabeld"] = True  # a typo, or a newer build's field
    parsed = parse_resource(encode(doc))
    assert parsed.unknown_fields == ("enabeld",)
    changed = parsed.replace(description="now described")
    out = json.loads(changed.to_bytes())
    assert list(out) == list(doc)
    assert out["enabeld"] is True
    assert out["description"] == "now described"


def test_an_optional_field_is_not_written_as_null_by_default() -> None:
    doc = ResourceDocument(kind="skill", name="pdf", config={}, uid="a" * 32)
    out = json.loads(doc.to_bytes())
    assert "title" not in out and "created_at" not in out
    assert out["description"] is None
    assert list(out)[:4] == ["uid", "kind", "format_version", "name"]


def test_a_new_known_field_lands_in_its_canonical_place() -> None:
    parsed = parse_resource(_raw())
    out = json.loads(parsed.replace(title="Linear").to_bytes())
    keys = list(out)
    assert keys.index("title") == keys.index("name") + 1


def test_a_file_without_a_uid_parses_as_a_new_resource() -> None:
    raw = json.loads(_raw())
    del raw["uid"]
    assert parse_resource(encode(raw)).uid is None


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"not json", "not valid JSON"),
        (b"[1, 2]", "must be a JSON object"),
        (encode({"kind": "x", "config": {}}), "missing field: name"),
        (encode({"kind": "x", "name": "y", "config": []}), "config must be an object"),
        (encode({"kind": "x", "name": "y", "config": {}, "uid": "../etc"}), "uid must be"),
        (encode({"kind": "x", "name": "y", "config": {}, "format_version": 0}), "format_version"),
    ],
)
def test_what_is_not_a_resource_document_is_refused(data: bytes, reason: str) -> None:
    with pytest.raises(DocumentInvalid, match=reason):
        parse_resource(data)
