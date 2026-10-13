"""A collection's files stay where their writer put them, through the routes
(spec knowledge "Sweep the knowledge root on its mechanical duties", "Undo a
knowledge delete from its toast").

Root management files (``index.md``, ``log.md``, ``schema.md``), a custom root
file, a folder of the person's own and ``assets/`` are ordinary collection
files: an upload moves none of them, the read and tree routes serve them, and a
collection's delete and its Undo carry them byte for byte.

``client`` (from ``conftest.py``) boots the full app with the knowledge root
under ``tmp_path``; the history is real git under it.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from coffer.infrastructure.knowledge.paths import knowledge_root

from .conftest import _create_collection

#: Collection-relative path -> bytes. Relative links between them must still
#: resolve after a restore, which they do when paths and bytes are unchanged.
_FILES: dict[str, bytes] = {
    "index.md": b"# Index\n\n- [Deep](notes/deep/x.md)\n- ![chart](assets/manual/chart.png)\n",
    "log.md": b"## 2026-10-13\r\n\r\n- ingested the gateway doc\r\n",
    "schema.md": b"---\ntitle: Schema\n---\n\nHow pages are laid out.\n",
    "glossary.md": b"SDU: service deployment unit.\n",
    "notes/deep/x.md": b"Deep note. Back to [index](../../index.md).\n",
    "assets/manual/chart.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xfe",
    "data.bin": bytes(range(256)),
}


def _plant(collection: str = "shopee") -> pathlib.Path:
    root = knowledge_root() / collection
    for relative, data in _FILES.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def _on_disk(root: pathlib.Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(root).parts)
    }


def _uid(client, name: str) -> str:  # type: ignore[no-untyped-def]
    rows = client.get("/api/v1/knowledge/collections").json()["collections"]
    return str(next(r["uid"] for r in rows if r["name"] == name))


def _change(client, operation: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    feed = client.get("/api/v1/knowledge/changes").json()["changes"]
    return next(c for c in feed if c["operation"] == operation)


def test_an_upload_creates_its_source_and_moves_nothing_else(client) -> None:  # type: ignore[no-untyped-def]
    _create_collection(client, "shopee")
    root = _plant()
    before = _on_disk(root)

    resp = client.post(
        "/api/v1/knowledge/upload",
        data={"collection": "shopee"},
        files={"file": ("team.csv", b"name,owner\nsession,account\n")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["path"] == "shopee/sources/team.md"

    after = _on_disk(root)
    assert set(after) - set(before) == {"sources/team.md"}
    assert {k: after[k] for k in before} == before


@pytest.mark.acceptance(
    spec="knowledge", scenario="root files are read, listed and restored with their collection"
)
def test_root_files_are_read_listed_and_restored_byte_for_byte(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.post(
        "/api/v1/knowledge/collections", json={"name": "shopee", "description": "Shopee."}
    )
    assert resp.status_code == 201, resp.text
    root = _plant()
    readme = (root / "README.md").read_bytes()

    # Read: a root management file and a file in a person's own folder.
    for path, text in (("shopee/index.md", "# Index"), ("shopee/notes/deep/x.md", "Deep note.")):
        read = client.get("/api/v1/knowledge/file", params={"path": path})
        assert read.status_code == 200, read.text
        assert text in read.json()["body"]

    # Listed: the root level names every root file (README excepted) and the
    # person's folders; the folder lists its own file.
    level = client.get("/api/v1/knowledge/tree", params={"path": "shopee"}).json()
    assert {f["path"] for f in level["files"]} == {
        "shopee/index.md",
        "shopee/log.md",
        "shopee/schema.md",
        "shopee/glossary.md",
        "shopee/data.bin",
    }
    assert {d["path"] for d in level["directories"]} >= {"shopee/notes", "shopee/assets"}
    deep = client.get("/api/v1/knowledge/tree", params={"path": "shopee/notes/deep"}).json()
    assert [f["path"] for f in deep["files"]] == ["shopee/notes/deep/x.md"]

    # Delete the collection, then Undo: every file is back, byte for byte, in place.
    deleted = client.delete(f"/api/v1/resources/{_uid(client, 'shopee')}")
    assert deleted.status_code in (200, 204), deleted.text
    assert not root.exists()
    removal = _change(client, "remove")
    removed = {d["path"] for d in removal["documents"]}
    assert {f"shopee/{relative}" for relative in _FILES} <= removed

    restored = client.post(f"/api/v1/knowledge/changes/{removal['version']}/restore")
    assert restored.status_code == 200, restored.text
    assert _on_disk(root) == {**_FILES, "README.md": readme}
