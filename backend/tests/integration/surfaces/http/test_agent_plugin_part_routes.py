"""HTTP coverage for the read-only /agents/{uid}/plugins/{plugin_id}/... item routes.

What a plugin provides, opened item by item and read-only. The plugin owns the
files: nothing here writes, a name is matched against what the package holds,
and a file path leaving a skill's folder is refused.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-parts"
SECRET = "sk-live-do-not-leak"


def _client(tmp_path: pathlib.Path, monkeypatch, port: int) -> TestClient:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port + 9))
    set_active_token(TOKEN)
    return TestClient(create_app(), headers={"X-Coffer-Token": TOKEN})


def _install_plugin(tmp_path: pathlib.Path) -> pathlib.Path:
    claude = tmp_path / ".claude"
    pkg = claude / "plugins" / "cache" / "mk" / "q1" / "1.2.0"
    (pkg / ".claude-plugin").mkdir(parents=True)
    (pkg / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "q1"}))
    skill = pkg / "skills" / "tdd"
    (skill / "refs").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: tdd\ndescription: Test first\n---\nBody\n")
    (skill / "refs" / "notes.md").write_text("notes")
    (pkg / "commands").mkdir()
    (pkg / "commands" / "lint.md").write_text("---\ndescription: Lint it\n---\nRun lint\n")
    (pkg / "agents").mkdir()
    (pkg / "agents" / "rev.md").write_text("---\nname: reviewer\ndescription: Reviews\n---\nHi\n")
    (pkg / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "srv": {"command": "q1", "env": {"API_TOKEN": SECRET}},
                }
            }
        )
    )
    # Something outside the skill that a traversal would reach.
    (pkg / "secret.txt").write_text("outside")
    (claude / "settings.json").write_text(json.dumps({"enabledPlugins": {"q1@mk": True}}))
    (claude / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {"q1@mk": [{"installPath": str(pkg)}]}})
    )
    (claude / "plugins" / "known_marketplaces.json").write_text(json.dumps({}))
    return pkg


@pytest.fixture
def agent(tmp_path, monkeypatch):
    pkg = _install_plugin(tmp_path)
    with _client(tmp_path, monkeypatch, 58830) as c:
        r = c.post("/api/v1/agents", json={"type": "claude_code", "name": "cc"})
        assert r.status_code == 201, r.text
        yield c, f"/api/v1/agents/{r.json()['uid']}/plugins/q1@mk", pkg


def test_skill_metadata_tree_and_file(agent):
    c, base, pkg = agent
    r = c.get(f"{base}/skills/tdd")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "name": "tdd",
        "description": "Test first",
        "path": str((pkg / "skills" / "tdd").resolve()),
    }
    tree = c.get(f"{base}/skills/tdd/files").json()["root"]
    assert {n["name"] for n in tree["children"]} == {"SKILL.md", "refs"}
    f = c.get(f"{base}/skills/tdd/files/content", params={"path": "refs/notes.md"})
    assert f.status_code == 200 and f.json()["content"] == "notes"


@pytest.mark.parametrize("bad", ["../../secret.txt", "/etc/hosts", "refs/../../../secret.txt"])
def test_skill_file_path_traversal_is_refused(agent, bad):
    c, base, _pkg = agent
    r = c.get(f"{base}/skills/tdd/files/content", params={"path": bad})
    assert r.status_code == 400, r.text
    assert "outside" not in r.text.replace("outside the skill folder", "")


def test_skill_name_is_matched_not_joined(agent):
    c, base, _pkg = agent
    assert c.get(f"{base}/skills/nope").status_code == 404
    assert c.get(f"{base}/skills/nope/files").status_code == 404
    r = c.get(f"{base}/skills/..%2F..%2Fskills%2Ftdd")
    assert r.status_code == 404


def test_command_and_subagent_documents(agent):
    c, base, pkg = agent
    r = c.get(f"{base}/commands/lint")
    assert r.status_code == 200, r.text
    assert r.json()["description"] == "Lint it"
    assert "Run lint" in r.json()["content"]
    assert r.json()["path"] == str((pkg / "commands" / "lint.md").resolve())
    # A subagent is addressed by its frontmatter name, not its file stem.
    assert c.get(f"{base}/agents/reviewer").json()["description"] == "Reviews"
    assert c.get(f"{base}/agents/rev").status_code == 404


def test_mcp_server_entry_is_masked(agent):
    c, base, _pkg = agent
    r = c.get(f"{base}/mcp-servers/srv")
    assert r.status_code == 200, r.text
    assert SECRET not in r.text
    assert r.json()["config"]["command"] == "q1"
    assert list(r.json()["config"]["env"]) == ["API_TOKEN"]
    assert c.get(f"{base}/mcp-servers/ghost").status_code == 404


def test_unknown_plugin_is_404(agent):
    c, base, _pkg = agent
    r = c.get(base.replace("q1@mk", "ghost@mk") + "/skills/tdd")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "PLUGIN_NOT_FOUND"
