"""A linked folder, observed through the routes (spec knowledge "Link a folder
the person keeps themselves", "Leave a linked folder to its own tools").

``client`` (from ``conftest.py``) pins ``HOME`` to ``tmp_path``, so a folder
under ``tmp_path`` is outside Coffer's own home, as a person's own vault is.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from coffer.infrastructure.vault.home import local_root, vault_root

from .conftest import _create_collection


def _vault_folder(tmp_path: pathlib.Path) -> pathlib.Path:
    folder = tmp_path / "Obsidian" / "Work"
    (folder / "Projects").mkdir(parents=True)
    (folder / ".obsidian").mkdir()
    (folder / ".obsidian" / "app.json").write_text("{}", encoding="utf-8")
    (folder / "AGENTS.md").write_text("# Rules\n\nOne note per project.\n", encoding="utf-8")
    (folder / "README.md").write_text("# Work\n\nMy work notes.\n", encoding="utf-8")
    (folder / "Projects" / "Gateway.md").write_text(
        "# Payment gateway\n\nTimeouts are 3s.\n", encoding="utf-8"
    )
    (folder / "Inbox note.md").write_text("Loose thought.\n", encoding="utf-8")
    return folder


def _link(client, folder: pathlib.Path, name: str | None = None) -> dict:  # type: ignore[no-untyped-def]
    body: dict[str, str] = {"folder": str(folder)}
    if name:
        body["name"] = name
    r = client.post("/api/v1/knowledge/collections/link", json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


def _snapshot(folder: pathlib.Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()
    }


@pytest.mark.acceptance(
    spec="knowledge", scenario="a linked folder is listed and shared without being copied"
)
def test_a_linked_folder_is_listed_and_shared_without_being_copied(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    folder = _vault_folder(tmp_path)
    before = _snapshot(folder)

    linked = _link(client, folder)

    assert linked["name"] == "Work"
    assert linked["linked"] is True
    assert linked["note_count"] == 4
    assert linked["rules_file"] == "AGENTS.md"
    assert linked["description"] == "My work notes."
    assert linked["folder_path"] == str(folder)
    listed = client.get("/api/v1/knowledge/collections").json()["collections"]
    assert [c["name"] for c in listed if c["linked"]] == ["Work"]
    # Nothing is copied into the vault, and the row is machine-local.
    assert not (vault_root() / "knowledge" / "Work").exists()
    rows = list((local_root() / "resources" / "knowledge").glob("*.json"))
    assert len(rows) == 1
    # The file names the home as a token, as every machine-local path does.
    assert json.loads(rows[0].read_text())["config"] == {"folder": "${HOME}/Obsidian/Work"}
    assert not list((vault_root() / "resources" / "knowledge").glob("*.json"))
    assert _snapshot(folder) == before


@pytest.mark.acceptance(spec="knowledge", scenario="a linked folder is read but never written")
def test_a_linked_folder_is_read_but_never_written(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    folder = _vault_folder(tmp_path)
    uid = _link(client, folder)["uid"]
    before = _snapshot(folder)

    tree = client.get("/api/v1/knowledge/tree", params={"path": "Work"}).json()
    assert [d["name"] for d in tree["directories"]] == ["Projects"]
    assert "Work/.obsidian" not in json.dumps(tree)
    note = client.get("/api/v1/knowledge/file", params={"path": "Work/Projects/Gateway.md"})
    assert note.status_code == 200, note.text
    assert note.json()["title"] == "Payment gateway"
    assert note.json()["file_path"] == str(folder / "Projects" / "Gateway.md")
    files = client.get(f"/api/v1/knowledge/collections/{uid}/files").json()["files"]
    assert "Work/Projects/Gateway.md" in [f["path"] for f in files]

    refused = [
        client.delete("/api/v1/knowledge/file", params={"path": "Work/Inbox note.md"}),
        client.get(f"/api/v1/knowledge/collections/{uid}/check"),
        client.post(f"/api/v1/knowledge/collections/{uid}/tidy/start"),
        client.put(f"/api/v1/knowledge/collections/{uid}/description", json={"description": "x"}),
        client.post(
            "/api/v1/knowledge/upload",
            data={"collection": "Work"},
            files={"file": ("a.md", b"# A\n\nText.\n", "text/markdown")},
        ),
    ]
    for r in refused:
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_LINKED"
    assert (
        client.get("/api/v1/knowledge/file", params={"path": "Work/.obsidian/app.json"}).status_code
        == 400
    )
    assert _snapshot(folder) == before


@pytest.mark.acceptance(
    spec="knowledge", scenario="disconnecting a linked folder leaves its files alone"
)
def test_disconnecting_a_linked_folder_leaves_its_files_alone(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    folder = _vault_folder(tmp_path)
    uid = _link(client, folder)["uid"]
    before = _snapshot(folder)

    renamed = client.patch(f"/api/v1/resources/{uid}", json={"name": "Notes"})
    assert renamed.status_code == 200, renamed.text
    deleted = client.delete(f"/api/v1/resources/{uid}")
    assert deleted.status_code in (200, 204), deleted.text

    assert _snapshot(folder) == before
    assert client.get("/api/v1/knowledge/collections").json()["collections"] == []


def test_a_folder_that_cannot_be_linked_is_refused(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    folder = _vault_folder(tmp_path)
    _create_collection(client, "Work")
    for body, code in (
        ({"folder": str(tmp_path / "missing")}, "KNOWLEDGE_FOLDER_REFUSED"),
        ({"folder": "relative/path"}, "KNOWLEDGE_FOLDER_REFUSED"),
        ({"folder": str(tmp_path)}, "KNOWLEDGE_FOLDER_REFUSED"),
        ({"folder": str(vault_root())}, "KNOWLEDGE_FOLDER_REFUSED"),
        ({"folder": str(folder)}, "KNOWLEDGE_COLLECTION_EXISTS"),
    ):
        r = client.post("/api/v1/knowledge/collections/link", json=body)
        assert r.status_code in (400, 409), r.text
        assert r.json()["error"]["code"] == code, body
    _link(client, folder, name="Mine")
    again = client.post(
        "/api/v1/knowledge/collections/link", json={"folder": str(folder), "name": "Other"}
    )
    assert again.json()["error"]["code"] == "KNOWLEDGE_COLLECTION_EXISTS"


def test_the_sweep_and_tidy_all_leave_a_linked_folder_out(client, tmp_path) -> None:  # type: ignore[no-untyped-def]
    folder = _vault_folder(tmp_path)
    _link(client, folder)
    before = _snapshot(folder)

    handoff = client.get("/api/v1/knowledge/tidy-handoff").json()["prompt"]
    assert "Work" not in handoff
    changes = client.get("/api/v1/knowledge/changes").json()["changes"]
    assert all("Work" not in json.dumps(c) for c in changes)
    assert _snapshot(folder) == before
