"""HTTP: POST /api/v1/agents/{name}/native-memory/import (takeover, spec 007).

Coffer takes over Claude Code's EXISTING on-disk project memory: for each
unmanaged ``<config_dir>/projects/<slug>/memory`` it decodes the slug back to a
real project root, backs the dir up, then establishes a SYMLINK projection so
the dir becomes a link into a canonical Coffer store (existing facts merged in).
Driven against the real wired stack on a temp HOME.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "native-import-token"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}


def _slug(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def _app(tmp_path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    return create_app()


def test_import_takes_over_unmanaged_claude_memory(tmp_path, monkeypatch):
    # A real project root (fake git marker so scope resolution succeeds) whose
    # Claude slug we will seed native memory under.
    project_root = tmp_path / "myrepo"
    project_root.mkdir()
    (project_root / ".git").mkdir()
    slug = _slug(project_root)

    mem = tmp_path / ".claude" / "projects" / slug / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("# index\n", encoding="utf-8")
    (mem / "build.md").write_text("builds via make\n", encoding="utf-8")
    (mem / "deploy.md").write_text("deploys via make release\n", encoding="utf-8")

    app = _app(tmp_path, monkeypatch, 59980)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "claude", "config_dir": str(tmp_path / ".claude")},
            headers=_HEADERS,
        )

        r = c.post("/api/v1/agents/claude/native-memory/import", headers=_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 1, body
        (item,) = [i for i in body["items"] if i["slug"] == slug]
        assert item["status"] == "imported"
        assert item["project_root"] == str(project_root)
        store_name = item["store_name"]
        assert store_name and store_name.startswith("project-")

        # The native dir is now a symlink (Coffer-managed), and a timestamped
        # backup of the original real files sits beside it.
        assert mem.is_symlink()
        backups = list(mem.parent.glob("memory.bak-*"))
        assert len(backups) == 1, backups
        names = {p.name for p in backups[0].iterdir()}
        assert {"build.md", "deploy.md"} <= names

        # The facts now live in the canonical Coffer store.
        facts = c.get(f"/api/v1/memory_stores/{store_name}/facts", headers=_HEADERS).json()
        titles = {f["name"] for f in facts["facts"]}
        assert {"build", "deploy"} <= titles

        # Re-scanning shows the project as managed now.
        disc = c.get("/api/v1/agents/claude/native-memory", headers=_HEADERS).json()
        managed = {p["slug"]: p["managed"] for p in disc["projects"]}
        assert managed.get(slug) is True

        # Idempotent: a second import takes over nothing new.
        again = c.post("/api/v1/agents/claude/native-memory/import", headers=_HEADERS).json()
        assert again["imported"] == 0


def test_import_skips_undecodable_slug(tmp_path, monkeypatch):
    # A slug that maps to no existing path is reported, never guessed/created.
    mem = tmp_path / ".claude" / "projects" / "-no-such-path-anywhere-zzz" / "memory"
    mem.mkdir(parents=True)
    (mem / "x.md").write_text("orphan fact\n", encoding="utf-8")

    app = _app(tmp_path, monkeypatch, 59960)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post(
            "/api/v1/agents",
            json={"type": "claude_code", "name": "claude", "config_dir": str(tmp_path / ".claude")},
            headers=_HEADERS,
        )
        body = c.post("/api/v1/agents/claude/native-memory/import", headers=_HEADERS).json()
        assert body["imported"] == 0
        assert body["skipped"] == 1
        (item,) = body["items"]
        assert item["status"] == "skipped_undecodable"
        assert not mem.is_symlink()  # untouched
