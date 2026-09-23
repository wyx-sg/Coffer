"""``POST /api/v1/knowledge/upload`` end to end (spec knowledge).

The full app is booted through ``create_app`` so the route is wired exactly as
production wires it — real SQLite, real Markdown under a temp HOME, the real
converter registry — and driven with a Starlette ``TestClient``. ``client`` and
``_create_collection`` live in ``conftest.py``.

This module replaces one that also covered ``POST /knowledge/search`` and
``GET /knowledge/grep``. Both routes are gone with the retrieval surface ("Expose
exactly one knowledge tool"), and nothing took their place: a person greps the directory
with their own tools and an agent reads the paths its delivered skill carries. What
is kept is upload, because its refusals are a contract the UI keys messages off, and
because "nothing half-lands" is only provable through a real write.
"""

from __future__ import annotations

import pytest

from coffer.domain.knowledge.converter import Conversion
from coffer.infrastructure.knowledge.converters.registry import ConverterRegistry

from .conftest import _create_collection, _hold_material


def _files_on_disk(tmp_path, collection: str = "shopee") -> list[str]:  # type: ignore[no-untyped-def]
    """Every file in the collection as the FILESYSTEM has it — hidden inbox,
    Markdown or not, README excluded.

    The tree route lists visible documents only, so asserting "nothing landed"
    through it would pass with a stray original, or an item in the inbox.
    """
    directory = tmp_path / "knowledge" / collection
    if not directory.is_dir():
        return []
    return sorted(
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file() and p.name != "README.md"
    )


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="an upload is converted and submitted as material, keeping neither file",
)
def test_an_upload_becomes_one_document_and_keeps_no_file_of_its_own(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("team.csv", b"name,owner\nsession,account\n")},
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()

    # No internal model in this app, so the converted text is promoted to a document
    # on the spot ("Promote material directly when no model is configured"). A CSV,
    # because a `.txt` or `.md` converts by passthrough and would not show that
    # conversion happened.
    assert doc["path"] == "shopee/team.md"
    assert doc["pending"] is False
    assert doc["converter"] == "csv"
    assert doc["title"] and doc["description"]
    assert "original_path" not in doc

    # Neither the original bytes nor a separate extracted file: the one file in the
    # collection is the document the knowledge became ("Convert uploads into
    # material without keeping them").
    assert _files_on_disk(tmp_path) == ["team.md"]

    read = client.get("/api/v1/knowledge/file", params={"path": doc["path"]})
    assert read.status_code == 200, read.text
    file_out = read.json()
    # An upload is a person's action, so the frontmatter says so ("Fill frontmatter
    # on converted material").
    assert file_out["actor"] == "user"
    assert file_out["title"] == doc["title"]
    assert file_out["description"] == doc["description"]
    assert "| session | account |" in file_out["body"]


def test_an_upload_waits_in_the_inbox_when_a_pass_could_merge_it(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    """With a model to merge it, the upload is material like any other: it
    waits in the hidden inbox and the response says so rather than naming a
    document that does not exist yet ("Submit every entrance's input as material")."""
    _create_collection(client, "shopee")
    _hold_material(monkeypatch)

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("notes.md", b"# Notes\n\nSome prose.\n")},
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["path"] is None
    assert doc["pending"] is True
    assert _files_on_disk(tmp_path) == [".inbox/notes.md"]


def test_an_upload_takes_no_folder(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Where knowledge lands is curation's call, not the uploader's: a
    ``folder`` field is not part of the form and is ignored if sent."""
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee", "folder": "runbooks"},
        files={"file": ("notes.md", b"# Notes\n\nSome prose.\n")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["path"] == "shopee/notes.md"
    assert not (tmp_path / "knowledge" / "shopee" / "runbooks").exists()


@pytest.mark.acceptance(
    spec="knowledge", scenario="an upload of an unsupported type is refused with its reason"
)
def test_upload_of_unsupported_type_is_refused_with_its_reason(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("payload.exe", b"\x00\x01\x02")},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"]["code"] == "INGEST_REJECTED"
    assert body["error"]["details"]["reason"] == "unsupported_type"
    assert body["error"]["details"]["doc_type"] == "exe"
    # And the collection is left with no file at all — not even in the inbox.
    assert _files_on_disk(tmp_path) == []


@pytest.mark.acceptance(spec="knowledge", scenario="a document is never stored half-converted")
def test_upload_of_a_pdf_with_no_text_layer_is_refused_as_scanned(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    """Per "Bound uploads and leave nothing behind on failure", end to end,
    including the reason the UI keys its message off.

    A real image-only PDF is not worth carrying as a fixture: the rule is that
    ANY conversion producing no text is refused, so the converter is made to
    return ``""`` — which is exactly what MarkItDown does for a scanned PDF,
    without raising.
    """
    _create_collection(client, "shopee")

    async def _empty(self, data, filename):  # type: ignore[no-untyped-def]
        return Conversion(markdown="", title="Scan", converter="markitdown")

    monkeypatch.setattr(ConverterRegistry, "convert", _empty)

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("scan.pdf", b"%PDF-1.7 image only")},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["error"]["code"] == "INGEST_REJECTED"
    # The key `frontend/src/i18n/locales/{en,zh}.json` already define as
    # `INGEST_REJECTED_scanned_pdf` — it was a message with no producer.
    assert body["error"]["details"]["reason"] == "scanned_pdf"
    assert body["error"]["details"]["doc_type"] == "pdf"

    # Nothing — no document, no inbox item, no original ("Bound uploads and leave
    # nothing behind on failure").
    assert _files_on_disk(tmp_path) == []


def test_upload_into_an_unknown_collection_is_not_found(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "typo"},
        files={"file": ("notes.txt", b"hello")},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_NOT_FOUND"
    # A read or a write never provisions a collection ("Create collections only deliberately").
    assert not (tmp_path / "knowledge" / "typo").exists()


def test_oversize_upload_is_refused_and_names_the_limit(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import coffer.application.knowledge.ingest as ingest_module

    monkeypatch.setattr(ingest_module, "MAX_UPLOAD_BYTES", 8)
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("notes.txt", b"this payload is well over eight bytes")},
    )
    assert resp.status_code == 413, resp.text
    body = resp.json()
    assert body["error"]["code"] == "KNOWLEDGE_UPLOAD_TOO_LARGE"
    assert "8" in body["error"]["message"]
