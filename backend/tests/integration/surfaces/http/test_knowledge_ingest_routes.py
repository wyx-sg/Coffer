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

from .conftest import _create_collection


def _files_on_disk(tmp_path, collection: str = "shopee") -> list[str]:  # type: ignore[no-untyped-def]
    """Every file in the collection as the FILESYSTEM has it — hidden inbox,
    Markdown or not, README excluded.

    The tree route lists visible documents only, so asserting "nothing landed"
    through it would pass with a stray original, or an item in the inbox.
    """
    directory = tmp_path / ".coffer" / "vault" / "knowledge" / collection
    if not directory.is_dir():
        return []
    return sorted(
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file() and p.name != "README.md"
    )


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="an upload is kept as a Markdown source",
)
def test_an_upload_becomes_a_markdown_source_and_nothing_else(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("team.csv", b"name,owner\nsession,account\n")},
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()

    # The converted text is a source on the spot ("Promote submitted material
    # at once"). A CSV, because a `.txt` or `.md` converts by passthrough and
    # would not show that conversion happened.
    assert doc["path"] == "shopee/sources/team.md"
    assert "pending" not in doc
    assert doc["converter"] == "csv"
    assert doc["title"] and doc["description"]
    assert "original_path" not in doc

    # Only the Markdown source in the collection: the uploaded bytes stay on
    # this Mac ("Keep every upload as a Markdown source").
    assert _files_on_disk(tmp_path) == ["sources/team.md"]

    read = client.get("/api/v1/knowledge/file", params={"path": doc["path"]})
    assert read.status_code == 200, read.text
    file_out = read.json()
    # An upload is a person's action, so the frontmatter says so ("Fill frontmatter
    # on converted material").
    assert file_out["actor"] == "user"
    assert file_out["title"] == doc["title"]
    assert file_out["description"] == doc["description"]
    assert "| session | account |" in file_out["body"]
    assert (file_out["kind"], file_out["waiting"]) == ("source", True)
    assert file_out["original"] == "team.csv"


def test_an_upload_takes_no_folder(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Where knowledge lands is not the uploader's call: a
    ``folder`` field is not part of the form and is ignored if sent."""
    _create_collection(client, "shopee")

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee", "folder": "runbooks"},
        files={"file": ("notes.md", b"# Notes\n\nSome prose.\n")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["path"] == "shopee/sources/notes.md"
    assert not (tmp_path / ".coffer" / "vault" / "knowledge" / "shopee" / "runbooks").exists()


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
    # And the collection is left with no file at all.
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
    assert not (tmp_path / ".coffer" / "vault" / "knowledge" / "typo").exists()


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


# ----- pictures and the original (ADR
# knowledge-sources-keep-their-images-and-originals-stay-on-this-mac) -----


def _png(color: str = "red", side: int = 64) -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (side, side), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _with_pictures(monkeypatch) -> bytes:  # type: ignore[no-untyped-def]
    """The converter answers with two pictures, linked by bare name, as the
    MarkItDown converter does once it has taken them out."""
    from coffer.domain.knowledge.converter import ConvertedImage

    picture = _png()

    async def _convert(self, data, filename):  # type: ignore[no-untyped-def]
        return Conversion(
            markdown="# Deck\n\nThe flow:\n\n![flow](image-1.png)\n\n![](image-2.png)\n",
            title="Deck",
            converter="markitdown",
            images=(
                ConvertedImage("image-1.png", picture),
                ConvertedImage("image-2.png", _png("blue")),
            ),
        )

    monkeypatch.setattr(ConverterRegistry, "convert", _convert)
    return picture


@pytest.mark.acceptance(
    spec="knowledge", scenario="an upload's pictures are kept beside its source"
)
def test_an_uploads_pictures_land_under_assets_and_the_source_links_them(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    _create_collection(client, "shopee")
    _with_pictures(monkeypatch)

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("deck.pptx", b"PK fake deck bytes")},
    )
    assert resp.status_code == 201, resp.text
    on_disk = _files_on_disk(tmp_path)
    assert on_disk[0] == "assets/deck-" + on_disk[0].split("deck-")[1]
    folder = on_disk[0].split("/")[1]
    assert on_disk == [
        f"assets/{folder}/image-1.png",
        f"assets/{folder}/image-2.png",
        "sources/deck.md",
    ]
    body = client.get("/api/v1/knowledge/file", params={"path": "shopee/sources/deck.md"}).json()[
        "body"
    ]
    assert f"![flow](../assets/{folder}/image-1.png)" in body
    assert f"![](../assets/{folder}/image-2.png)" in body

    # The pictures are in the same commit as the source: one change.
    changes = client.get("/api/v1/knowledge/changes", params={"limit": 5}).json()["changes"]
    added = next(c for c in changes if c["summary"] == "Add Deck")
    assert {d["path"] for d in added["documents"]} >= {
        "shopee/sources/deck.md",
        f"shopee/assets/{folder}/image-1.png",
    }


@pytest.mark.acceptance(spec="knowledge", scenario="a picture is read through the knowledge routes")
def test_the_asset_route_serves_a_picture_and_nothing_else(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    _create_collection(client, "shopee")
    picture = _with_pictures(monkeypatch)
    client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("deck.pptx", b"PK fake deck bytes")},
    )
    asset = next(p for p in _files_on_disk(tmp_path) if p.endswith("image-1.png"))

    resp = client.get("/api/v1/knowledge/asset", params={"path": f"shopee/{asset}"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == picture

    # A document is not a picture, and a path out of the root is refused.
    assert (
        client.get("/api/v1/knowledge/asset", params={"path": "shopee/sources/deck.md"}).status_code
        == 404
    )
    assert (
        client.get("/api/v1/knowledge/asset", params={"path": "shopee/../x.png"}).status_code >= 400
    )


@pytest.mark.acceptance(
    spec="knowledge", scenario="the original is kept on the Mac that uploaded it"
)
def test_the_original_is_kept_locally_and_named_by_the_source(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    import hashlib

    _create_collection(client, "shopee")
    _with_pictures(monkeypatch)
    data = b"PK fake deck bytes"
    client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("deck.pptx", data)},
    )
    sha = hashlib.sha256(data).hexdigest()
    kept = tmp_path / ".coffer" / "local" / "knowledge-originals" / f"{sha}.pptx"
    assert kept.read_bytes() == data

    file_out = client.get(
        "/api/v1/knowledge/file", params={"path": "shopee/sources/deck.md"}
    ).json()
    assert file_out["original"] == "deck.pptx"
    assert file_out["original_path"] == str(kept)
    # Nothing of it is in the vault, which syncs.
    assert not any(p.endswith(".pptx") for p in _files_on_disk(tmp_path))


@pytest.mark.acceptance(
    spec="knowledge", scenario="another Mac knows an original exists but not where"
)
def test_a_source_whose_original_is_elsewhere_names_it_without_a_path(  # type: ignore[no-untyped-def]
    client, tmp_path, monkeypatch
) -> None:
    _create_collection(client, "shopee")
    _with_pictures(monkeypatch)
    client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("deck.pptx", b"PK fake deck bytes")},
    )
    # What another Mac sees: the source synced, the original did not.
    for kept in (tmp_path / ".coffer" / "local" / "knowledge-originals").iterdir():
        kept.unlink()

    file_out = client.get(
        "/api/v1/knowledge/file", params={"path": "shopee/sources/deck.md"}
    ).json()
    assert file_out["original"] == "deck.pptx"
    assert file_out["original_path"] is None


@pytest.mark.acceptance(spec="knowledge", scenario="a Markdown upload keeps no original")
def test_a_markdown_upload_is_its_own_source_and_keeps_no_original(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("notes.md", b"# Notes\n\nSome prose.\n")},
    )
    file_out = client.get(
        "/api/v1/knowledge/file", params={"path": "shopee/sources/notes.md"}
    ).json()
    assert (file_out["original"], file_out["original_path"]) == ("", None)
    assert not (tmp_path / ".coffer" / "local" / "knowledge-originals").exists()
