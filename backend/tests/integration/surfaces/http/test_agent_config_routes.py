"""HTTP coverage for the /api/v1/agents/{uid}/config-files listing and preview.

The route family hangs off the agent's immutable ``uid``, never its name
(ADR identity-is-the-uid-inside-the-file). ``_register_claude`` therefore
hands back the uid its own ``POST /api/v1/agents`` response carried, and every
test addresses the agent by that — no second request, and no place where a
label could be mistaken for an identity.
"""

from __future__ import annotations

import pathlib
import uuid

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-cfg"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    # Deterministic shim resolution, as every app built here resolves one.
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    return create_app(), shim


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _register_claude(c: TestClient, tmp_path: pathlib.Path) -> str:
    """Register the claude_code agent and return the uid its routes take.

    The uid is read off the creation response, which is the honest client flow:
    the server mints the identity, the caller keeps it. ``"cc"`` stays in the
    body as the agent's label — it is what a person would see in the UI, and it
    addresses nothing.
    """
    # config_dir defaults to <HOME>/.claude (HOME is monkeypatched to tmp_path).
    # Registration requires that config dir to already exist (it auto-creates
    # only the skills/ leaf), so create it up front.
    (tmp_path / ".claude").mkdir(exist_ok=True)
    r = c.post(
        "/api/v1/agents",
        json={"type": "claude_code", "name": "cc"},
    )
    assert r.status_code == 201, r.text
    return r.json()["uid"]


@pytest.mark.acceptance(spec="agent-registry/claude-code", scenario="list an agent's config files")
@pytest.mark.acceptance(
    spec="agent-registry", scenario="report each config file's path, folder and existence"
)
def test_list_config_files_reports_locations_and_existence(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59700)
    with _client(app) as c:
        uid = _register_claude(c, tmp_path)
        claude_dir = tmp_path / ".claude"
        settings_path = claude_dir / "settings.json"
        settings_path.write_text('{"theme": "dark"}', encoding="utf-8")

        r = c.get(f"/api/v1/agents/{uid}/config-files")
        assert r.status_code == 200, r.text
        items = {i["key"]: i for i in r.json()["items"]}
        assert list(items) == ["settings", "settings_local", "global", "instructions", "subagents"]
        assert items["settings"]["kind"] == "file"
        assert items["settings"]["files"] is None
        assert items["settings"]["path"] == str(settings_path)
        assert items["settings"]["folder_path"] == str(claude_dir)
        assert items["settings"]["exists"] is True
        assert items["settings"]["size"] == len('{"theme": "dark"}')
        assert items["settings"]["modified_at"] is not None
        assert items["instructions"]["exists"] is False
        assert items["instructions"]["size"] is None
        assert items["instructions"]["modified_at"] is None
        assert items["subagents"]["kind"] == "directory"
        # A directory entry's path IS the folder; folder_path is its parent.
        assert items["subagents"]["path"] == str(claude_dir / "agents")
        assert items["subagents"]["folder_path"] == str(claude_dir)


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="list nested subagent files in the agents directory",
)
@pytest.mark.acceptance(spec="agent-registry", scenario="list a directory config entry's files")
def test_directory_entry_lists_nested_files_with_absolute_paths(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59750)
    with _client(app) as c:
        uid = _register_claude(c, tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"

        # Before the agents/ dir exists: exists=false, no files, and listing
        # does not create the directory.
        r = c.get(f"/api/v1/agents/{uid}/config-files")
        sub = next(i for i in r.json()["items"] if i["key"] == "subagents")
        assert sub["kind"] == "directory"
        assert sub["exists"] is False
        assert sub["files"] is None
        assert not agents_dir.exists()

        (agents_dir / "team").mkdir(parents=True)
        (agents_dir / "reviewer.md").write_text("# Reviewer\n", encoding="utf-8")
        (agents_dir / "team" / "helper.md").write_text("# Helper\n", encoding="utf-8")
        r = c.get(f"/api/v1/agents/{uid}/config-files")
        sub = next(i for i in r.json()["items"] if i["key"] == "subagents")
        assert sub["exists"] is True
        assert [(f["relpath"], f["path"]) for f in sub["files"]] == [
            ("reviewer.md", str(agents_dir / "reviewer.md")),
            ("team/helper.md", str(agents_dir / "team" / "helper.md")),
        ]


@pytest.mark.acceptance(spec="agent-registry", scenario="preview a config file as written")
def test_preview_shows_the_file_as_written_and_writes_nothing(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59720)
    with _client(app) as c:
        uid = _register_claude(c, tmp_path)
        settings = tmp_path / ".claude" / "settings.json"
        original = '{\n  "theme": "dark",\n  "env": {"ANTHROPIC_AUTH_TOKEN": "sk-live-1"}\n}\n'
        settings.write_text(original, encoding="utf-8")
        audit_before = c.get("/api/v1/audit", params={"limit": 200}).json()["entries"]

        r = c.get(f"/api/v1/agents/{uid}/config-files/settings/content")

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["abs_path"] == str(settings)
        assert body["format"] == "json"
        assert body["size"] == len(original.encode())
        assert body["truncated"] is False and body["binary"] is False
        assert body["content"] == original
        assert settings.read_text(encoding="utf-8") == original
        audit_after = c.get("/api/v1/audit", params={"limit": 200}).json()["entries"]
        assert audit_after == audit_before


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="preview a file under a directory entry only when the listing names it",
)
def test_preview_under_a_directory_entry_is_limited_to_listed_files(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59760)
    with _client(app) as c:
        uid = _register_claude(c, tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir()
        (agents_dir / "reviewer.md").write_text("# Reviewer\n", encoding="utf-8")
        (tmp_path / ".claude" / "settings.json").write_text('{"x": 1}', encoding="utf-8")
        base = f"/api/v1/agents/{uid}/config-files"

        ok = c.get(f"{base}/subagents/content", params={"child": "reviewer.md"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["content"] == "# Reviewer\n"
        assert ok.json()["abs_path"] == str(agents_dir / "reviewer.md")

        for params in ({"child": "../settings.json"}, {}):
            r = c.get(f"{base}/subagents/content", params=params)
            assert r.status_code == 404, r.text
            assert '"x": 1' not in r.text
        # A file key takes no child, and an unknown key is refused.
        assert c.get(f"{base}/settings/content", params={"child": "x.md"}).status_code == 404
        assert c.get(f"{base}/credentials/content").status_code == 404


@pytest.mark.acceptance(
    spec="agent-registry", scenario="answer a config file not created yet as not found"
)
def test_preview_of_a_file_not_created_yet_is_404(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59770)
    with _client(app) as c:
        uid = _register_claude(c, tmp_path)
        r = c.get(f"/api/v1/agents/{uid}/config-files/instructions/content")
        assert r.status_code == 404, r.text
        assert not (tmp_path / ".claude" / "CLAUDE.md").exists()


def test_no_route_writes_a_config_file(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch, 59780)
    with _client(app) as c:
        uid = _register_claude(c, tmp_path)
        settings = tmp_path / ".claude" / "settings.json"
        settings.write_text('{"theme": "light"}', encoding="utf-8")
        base = f"/api/v1/agents/{uid}/config-files"
        for path in (
            f"{base}/settings",
            f"{base}/settings/content",
            f"{base}/subagents/files/x.md",
        ):
            assert c.put(path, json={"content": "{}"}).status_code in (404, 405), path
            assert c.delete(path).status_code in (404, 405), path
        assert settings.read_text(encoding="utf-8") == '{"theme": "light"}'


def test_config_routes_unknown_agent_404(tmp_path, monkeypatch):
    """A uid no agent answers to 404s before any config file is looked at.

    Covered in both spellings the route cannot tell apart: a well-formed uid
    that was never minted, and a name-shaped segment that is not a uid at all.
    The second is the case that used to succeed — back when the segment WAS a
    name.
    """
    app, _ = _app(tmp_path, monkeypatch, 59730)
    with _client(app) as c:
        for absent in (uuid.uuid4().hex, "ghost"):
            r = c.get(f"/api/v1/agents/{absent}/config-files")
            assert r.status_code == 404, f"{absent}: {r.text}"
