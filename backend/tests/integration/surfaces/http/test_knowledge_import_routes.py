"""``POST /api/v1/knowledge/upload`` as an import: the report, re-imports, a
dry run, and a source read with its storage markers expanded (design sections 4 to 7).

The Confluence page here is synthetic — a CLI-shaped read result with one
tiny PNG — never a real export.
"""

from __future__ import annotations

import base64
import json
import pathlib

import pytest

from coffer.infrastructure.knowledge import originals
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

from .conftest import _create_collection

#: A 1x1 transparent PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

STORAGE = (
    "<p>Account Core keeps the account records.</p>"
    '<ac:image ac:alt="arch"><ri:attachment ri:filename="arch.png" /></ac:image>'
)
MISSING = '<ac:image><ri:attachment ri:filename="gone.png" /></ac:image>'


def _page(*, version: int = 7, storage: str = STORAGE, png: bytes = PNG) -> bytes:
    return json.dumps(
        {
            "pageId": "123",
            "title": "Account Core",
            "version": version,
            "spaceKey": "ACC",
            "link": "https://wiki.example.com/pages/viewpage.action?pageId=123",
            "bodyFormat": "storage",
            "body": storage,
            "attachments": [
                {
                    "name": "arch.png",
                    "mimeType": "image/png",
                    "dataBase64": base64.b64encode(png).decode(),
                }
            ],
        }
    ).encode()


def _root(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / ".coffer" / "vault" / "knowledge"


def _upload(client, data: bytes, name: str = "page.json", **form: str):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee", **form},
        files={"file": (name, data)},
    )


def _files(tmp_path: pathlib.Path) -> list[str]:
    directory = _root(tmp_path) / "shopee"
    return sorted(
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file() and p.name != "README.md"
    )


@pytest.mark.acceptance(
    spec="knowledge", scenario="an upload reports what it kept and what it could not"
)
def test_a_confluence_page_is_kept_with_its_files_and_a_report(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    resp = _upload(client, _page())
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["path"] == "shopee/sources/account-core.md"
    assert (doc["status"], doc["issues"], doc["replaced"], doc["dry_run"]) == (
        "complete",
        [],
        None,
        False,
    )
    folder = "shopee/assets/confluence-123-v7"
    assert f"{folder}/arch.png" in doc["files"]
    assert f"{folder}/page.storage.xml" in doc["files"]

    source = _root(tmp_path) / doc["path"]
    fm, body = split_frontmatter(source.read_text(encoding="utf-8"))
    assert "![arch](../assets/confluence-123-v7/arch.png)" in body
    assert "coffer-asset:" not in body
    # Every relative link resolves from the source's own directory.
    for target in [fm["original_representation"], "../assets/confluence-123-v7/arch.png"]:
        assert (source.parent / target).resolve().is_file(), target
    assert fm["import_status"] == "complete" and fm["retrieved_at"]
    assert fm["original"] == "page.json"
    picture = client.get("/api/v1/knowledge/asset", params={"path": f"{folder}/arch.png"})
    assert picture.status_code == 200 and picture.content == PNG


@pytest.mark.acceptance(
    spec="knowledge", scenario="an upload reports what it kept and what it could not"
)
def test_a_missing_attachment_makes_the_import_partial(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    doc = _upload(client, _page(storage=STORAGE + MISSING)).json()
    assert doc["status"] == "partial"
    assert [(i["kind"], i["name"]) for i in doc["issues"]] == [("missing_attachment", "gone.png")]
    fm, _ = split_frontmatter((_root(tmp_path) / doc["path"]).read_text(encoding="utf-8"))
    assert fm["import_status"] == "partial"


def test_a_reimport_reuses_the_same_folder_and_suffixes_other_bytes(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    first = _upload(client, _page()).json()
    again = _upload(client, _page()).json()
    assert again["files"] == first["files"]
    changed_bytes = _page(png=PNG + b"\x00")
    changed = _upload(client, changed_bytes).json()
    sha8 = originals.digest(changed_bytes)[:8]
    assert f"shopee/assets/confluence-123-v7-{sha8}/arch.png" in changed["files"]
    folders = sorted({f.split("/")[1] for f in _files(tmp_path) if f.startswith("assets/")})
    assert folders == ["confluence-123-v7", f"confluence-123-v7-{sha8}"]


@pytest.mark.acceptance(
    spec="knowledge", scenario="a re-import replaces a source without losing the old one"
)
def test_replaces_supersedes_the_old_source_in_the_same_commit(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    old = _upload(client, _page()).json()
    new = _upload(client, _page(version=8), replaces="sources/account-core.md")
    assert new.status_code == 201, new.text
    doc = new.json()
    assert doc["replaced"] == old["path"]
    assert doc["path"] == "shopee/sources/account-core-2.md"
    fm, _ = split_frontmatter((_root(tmp_path) / old["path"]).read_text(encoding="utf-8"))
    assert fm["superseded_by"] == "account-core-2"
    assert fm["title"] == "Account Core"  # the old one keeps everything else

    feed = client.get("/api/v1/knowledge/changes").json()["changes"]
    latest = next(c for c in feed if c["operation"] == "promote")
    touched = {d["path"] for d in latest["documents"]}
    assert {old["path"], doc["path"]} <= touched

    read = client.get("/api/v1/knowledge/file", params={"path": old["path"]}).json()
    assert read["superseded_by"]["path"] == doc["path"]


def test_replaces_must_name_a_source_of_the_collection(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    resp = _upload(client, _page(), replaces="sources/nowhere.md")
    assert resp.status_code == 404, resp.text
    assert _files(tmp_path) == []


@pytest.mark.acceptance(
    spec="knowledge", scenario="a dry run previews an import and writes nothing"
)
def test_a_dry_run_writes_nothing(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    before = client.get("/api/v1/knowledge/changes").json()["changes"]
    resp = _upload(client, _page(storage=STORAGE + MISSING), dry_run="true")
    assert resp.status_code == 200, resp.text
    doc = resp.json()
    assert doc["dry_run"] is True and doc["status"] == "partial"
    assert doc["path"] == "shopee/sources/account-core.md"
    assert "shopee/assets/confluence-123-v7/arch.png" in doc["files"]
    assert _files(tmp_path) == []
    assert client.get("/api/v1/knowledge/changes").json()["changes"] == before
    kept = originals.originals_dir()
    assert not kept.exists() or not any(kept.iterdir())


MARKED = b"""---
title: Marked page
---

Opening prose of the marked page.

<!-- skynet-confluence-storage:v1 kind=macro
<ac:structured-macro ac:name="info"><ac:rich-text-body>
<p>Mind the cache.</p></ac:rich-text-body></ac:structured-macro>
-->
"""


@pytest.mark.acceptance(spec="knowledge", scenario="a Markdown upload keeps one frontmatter")
def test_a_marked_markdown_upload_is_expanded_and_kept_as_original(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    doc = _upload(client, MARKED, name="marked.md").json()
    assert doc["title"] == "Marked page"
    text = (_root(tmp_path) / doc["path"]).read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    assert "skynet-confluence-storage" not in body and "<ac:" not in body
    assert "Mind the cache." in body
    assert fm["representation"] == "markdown expanded from confluence storage markers"
    assert fm["original"] == "marked.md" and fm["original_sha256"] == originals.digest(MARKED)
    assert originals.local_copy(fm["original_sha256"], "marked.md") is not None
    assert fm["import_status"] == doc["status"]


@pytest.mark.acceptance(
    spec="knowledge", scenario="a source holding storage markers reads as Markdown"
)
def test_a_source_with_markers_reads_with_a_display_body(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    source = _root(tmp_path) / "shopee" / "sources" / "marked.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(MARKED)
    read = client.get("/api/v1/knowledge/file", params={"path": "shopee/sources/marked.md"})
    assert read.status_code == 200, read.text
    out = read.json()
    assert "skynet-confluence-storage:v1" in out["body"]
    assert "Mind the cache." in out["display_body"]
    assert "skynet-confluence-storage" not in out["display_body"]
    assert source.read_bytes() == MARKED

    plain = _upload(client, b"# Plain\n\nNo markers.\n", name="plain.md").json()
    assert (
        client.get("/api/v1/knowledge/file", params={"path": plain["path"]}).json()["display_body"]
        is None
    )
