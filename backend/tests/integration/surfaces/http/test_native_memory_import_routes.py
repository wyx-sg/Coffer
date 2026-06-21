"""HTTP coverage for POST /api/v1/agents/{name}/native-memory/import (spec 007).

Boots the real app, registers a claude_code agent whose config_dir temp tree
carries a ``projects/<slug>/memory`` store with frontmatter fact files (+ the
``MEMORY.md`` index, which must be skipped), where ``<slug>`` decodes to a real
git repo. POST adopts the store into project memory; with no internal model
configured the organizer no-ops (``organized`` stays True).
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-native-mem-import"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _register_claude(c: TestClient, config_dir: pathlib.Path) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    r = c.post(
        "/api/v1/agents",
        json={"type": "claude_code", "name": "cc", "config_dir": str(config_dir)},
    )
    assert r.status_code == 201, r.text


def _git_init(path: pathlib.Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


def _write_fact(mem: pathlib.Path, filename: str, body: str, **fm: str) -> None:
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines += ["---", "", body]
    (mem / filename).write_text("\n".join(lines), encoding="utf-8")


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="importing a native memory store adopts it into Coffer",
)
def test_import_native_memory_into_project(tmp_path, monkeypatch):
    # A real git repo. The slug decode is lossy whenever a path segment contains
    # a '-' (the temp root does), so the REAL path is recovered from a sibling
    # transcript's "cwd" — exactly the Claude Code on-disk shape.
    project = tmp_path / "proj" / "demo"
    _git_init(project)
    slug = str(project).replace("/", "-")  # leading '-' → absolute path

    config_dir = tmp_path / "cc-config"
    mem = config_dir / "projects" / slug / "memory"
    mem.mkdir(parents=True)
    # Sibling transcript carrying the real cwd (step-2 path resolution).
    (mem.parent / "session.jsonl").write_text(
        json.dumps({"cwd": str(project), "sessionId": "s1"}) + "\n",
        encoding="utf-8",
    )
    _write_fact(
        mem,
        "a.md",
        "alpha body",
        name="Alpha",
        description="alpha desc",
        type="working-state",
    )
    _write_fact(mem, "b.md", "beta body", name="Beta", description="beta desc")
    (mem / "MEMORY.md").write_text("---\nname: index\n---\nindex", encoding="utf-8")

    app = _app(tmp_path, monkeypatch, 59830)
    with _client(app) as c:
        _register_claude(c, config_dir)

        r = c.post(
            "/api/v1/agents/cc/native-memory/import",
            json={"memory_dir": str(mem)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Two facts imported (MEMORY.md skipped); project path resolved to the repo.
        assert body["imported"] == 2
        assert body["skipped"] == 0
        assert body["project_path"] == str(project)
        assert body["store"] is not None and body["store"].startswith("project-")
        # No internal model configured → organizer no-ops, organized stays True.
        assert body["organized"] is True

        # The facts are now present in the project store.
        lst = c.get(f"/api/v1/memory_stores/{body['store']}/facts")
        assert lst.status_code == 200, lst.text
        assert lst.json()["total"] == 2


def test_import_unknown_agent_404(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59840)
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents/ghost/native-memory/import",
            json={"memory_dir": str(tmp_path)},
        )
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.acceptance(
    spec="004-agent-registry",
    scenario="importing a store outside a git project maps to no Coffer store",
)
def test_import_unresolvable_dir_returns_zero(tmp_path, monkeypatch):
    config_dir = tmp_path / "cc-config"
    # A slug that decodes to a non-existent dir + no jsonl → path unresolved.
    mem = config_dir / "projects" / "-no-such-decoded-path-xyz" / "memory"
    mem.mkdir(parents=True)

    app = _app(tmp_path, monkeypatch, 59850)
    with _client(app) as c:
        _register_claude(c, config_dir)
        r = c.post(
            "/api/v1/agents/cc/native-memory/import",
            json={"memory_dir": str(mem)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 0
        assert body["store"] is None
        assert body["project_path"] is None
        assert body["organized"] is False
