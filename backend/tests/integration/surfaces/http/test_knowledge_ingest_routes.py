"""``POST /api/v1/knowledge/upload`` end to end (spec knowledge FR-016..FR-019).

The full app is booted through ``create_app`` so the route is wired exactly as
production wires it — real SQLite, real Markdown under a temp HOME, the real
converter registry — and driven with a Starlette ``TestClient``. ``client`` and
``_create_collection`` live in ``conftest.py``.

This module replaces one that also covered ``POST /knowledge/search`` and
``GET /knowledge/grep``. Both routes are gone with the retrieval surface
(FR-033), and nothing took their place: a person greps the directory with
their own tools and an agent reads the paths its delivered skill carries. What
is kept is upload, because its refusals are a contract the UI keys messages
off, and because "nothing half-lands" is only provable through a real write.
"""

from __future__ import annotations

import pytest

from coffer.domain.knowledge.converter import Conversion
from coffer.infrastructure.knowledge.converters.registry import ConverterRegistry

from .conftest import _create_collection


def _sources_on_disk(tmp_path, collection: str = "shopee") -> list[str]:  # type: ignore[no-untyped-def]
    """The lane as the FILESYSTEM has it, Markdown or not.

    The tree route lists Markdown only, so asserting "nothing landed" through
    it would pass with a stray original sitting in the lane.
    """
    directory = tmp_path / "knowledge" / collection / "sources"
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir())


@pytest.mark.acceptance(
    spec="knowledge", scenario="an upload lands both the original and its text in sources"
)
def test_upload_lands_the_original_and_its_text_in_sources(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("team.csv", b"name,owner\nsession,account\n")},
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()

    # Both files, in the same lane, named for what was sent (FR-016). A CSV,
    # because a `.txt` or `.md` converts by passthrough and lands once — the
    # file that landed IS the original, and a second copy would be curated as a
    # second source.
    assert doc["path"] == "shopee/sources/team.md"
    assert doc["original_path"] == "shopee/sources/team.csv"
    assert doc["converter"] == "csv"
    assert doc["title"] and doc["description"]

    original = tmp_path / "knowledge" / "shopee" / "sources" / "team.csv"
    assert original.read_bytes() == b"name,owner\nsession,account\n"
    # No hidden directory anywhere in the collection: `.raw/` is gone, and with
    # no retrieval surface left there is nothing hiding an original would buy.
    assert not any(p.name.startswith(".") for p in (tmp_path / "knowledge" / "shopee").iterdir())

    read = client.get("/api/v1/knowledge/file", params={"path": doc["path"]})
    assert read.status_code == 200, read.text
    file_out = read.json()
    # An upload is a person's action, so the frontmatter says so (FR-017).
    assert file_out["actor"] == "user"
    assert file_out["title"] == doc["title"]
    assert file_out["description"] == doc["description"]
    assert "| session | account |" in file_out["body"]
    # Not yet curated: the watermark is what the page reads to say so (FR-028).
    assert file_out["ingested_at"] == ""


def test_an_upload_into_a_folder_nests_inside_the_lane(client) -> None:  # type: ignore[no-untyped-def]
    """``folder`` is a subdirectory of ``sources/``, never a sibling of it: the
    lane segment belongs to the layer, so no entrance can aim at ``topics/``
    (FR-013)."""
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee", "folder": "runbooks"},
        files={"file": ("notes.md", b"# Notes\n\nSome prose.\n")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["path"] == "shopee/sources/runbooks/notes.md"


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
    # And the lane is left with no file at all — not even the original.
    assert _sources_on_disk(tmp_path) == []


@pytest.mark.acceptance(spec="knowledge", scenario="a document is never stored half-converted")
def test_upload_of_a_pdf_with_no_text_layer_is_refused_as_scanned(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    """FR-019, end to end, including the reason the UI keys its message off.

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

    # Neither the extracted Markdown nor the original (FR-019).
    assert _sources_on_disk(tmp_path) == []


def test_upload_into_an_unknown_collection_is_not_found(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "typo"},
        files={"file": ("notes.txt", b"hello")},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_NOT_FOUND"
    # A read or a write never provisions a collection (FR-008).
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
