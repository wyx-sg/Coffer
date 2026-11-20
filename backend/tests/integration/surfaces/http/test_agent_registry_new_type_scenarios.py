"""Acceptance coverage, over the real app, for the Cursor, OpenCode and
DeepSeek Harness agent types (spec agent-registry/cursor, /opencode,
/deepseek-harness).

Each test boots ``create_app`` against a temp ``HOME``, registers the agent
through ``POST /api/v1/agents`` and drives the routes the web UI and the CLI
call. Nothing here reads or writes the real home directory.
"""

from __future__ import annotations

import json
import pathlib
import textwrap

import pytest
from starlette.testclient import TestClient

from coffer.domain.agent import mcp_cordis
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.support.facets import put_programs_on_path

TOKEN = "test-token-new-agent-types"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    shim = tmp_path / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _register(c: TestClient, agent_type: str) -> str:
    r = c.post("/api/v1/agents", json={"type": agent_type})
    assert r.status_code == 201, r.text
    return r.json()["uid"]


def _connect(c: TestClient, uid: str) -> None:
    r = c.post(f"/api/v1/agents/{uid}/coffer-connection")
    assert r.status_code in (200, 204), r.text


def _files(c: TestClient, uid: str) -> dict[str, dict]:
    items = c.get(f"/api/v1/agents/{uid}/config-files").json()["items"]
    return {f["key"]: f for f in items}


def _candidates(c: TestClient) -> dict[str, dict]:
    return {x["type"]: x for x in c.get("/api/v1/agents/candidates").json()["candidates"]}


def _shim(tmp_path: pathlib.Path) -> str:
    return str(tmp_path / "coffer-mcp-shim")


def _write_skill_folder(folder: pathlib.Path, name: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: A test skill named {name}.\n---\n\nbody\n",
        encoding="utf-8",
    )


def _assert_skill_reaches_agents_skills(tmp_path, monkeypatch, agent_type: str, port: int):
    src = tmp_path / "src"
    _write_skill_folder(src, "shared-one")
    app = _app(tmp_path, monkeypatch, port)
    with _client(app) as c:
        _register(c, agent_type)
        r = c.post("/api/v1/skills/import", json={"path": str(src)})
        assert r.status_code == 201, r.text
        link = tmp_path / ".agents" / "skills" / "shared-one"
        assert link.exists()
        assert (link / "SKILL.md").read_text(encoding="utf-8").startswith("---")


# ---------------------------------------------------------------------------
# agent-registry/cursor
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="agent-registry/cursor", scenario="discover Cursor by its config directory"
)
def test_cursor_is_found_and_defaults_to_dot_cursor(tmp_path, monkeypatch):
    (tmp_path / ".cursor").mkdir()
    put_programs_on_path(monkeypatch, tmp_path / "bin", {"cursor-agent": "2026.11.10"})
    app = _app(tmp_path, monkeypatch, 61500)
    with _client(app) as c:
        cand = _candidates(c)["cursor"]
        assert cand["config_dir"] == str(tmp_path / ".cursor")
        assert cand["state"] == "installed_active"
        uid = _register(c, "cursor")
        assert c.get(f"/api/v1/agents/{uid}").json()["config_dir"] == str(tmp_path / ".cursor")


@pytest.mark.acceptance(
    spec="agent-registry/cursor", scenario="list exactly Cursor's three config files"
)
def test_cursor_allowlist_is_exactly_three_json_files(tmp_path, monkeypatch):
    (tmp_path / ".cursor").mkdir()
    app = _app(tmp_path, monkeypatch, 61510)
    with _client(app) as c:
        uid = _register(c, "cursor")
        files = _files(c, uid)
        names = {pathlib.Path(f["path"]).name for f in files.values()}
        assert names == {"mcp.json", "cli-config.json", "hooks.json"}
        assert {f["format"] for f in files.values()} == {"json"}
        assert "instructions" not in files


@pytest.mark.acceptance(
    spec="agent-registry/cursor", scenario="install Coffer's MCP into Cursor's mcp.json"
)
def test_cursor_install_writes_mcp_servers_coffer(tmp_path, monkeypatch):
    cursor = tmp_path / ".cursor"
    cursor.mkdir()
    (cursor / "mcp.json").write_text(
        json.dumps({"mcpServers": {"github": {"command": "npx", "args": ["gh"]}}}),
        encoding="utf-8",
    )
    app = _app(tmp_path, monkeypatch, 61520)
    with _client(app) as c:
        uid = _register(c, "cursor")
        _connect(c, uid)
        data = json.loads((cursor / "mcp.json").read_text(encoding="utf-8"))
        assert data["mcpServers"]["coffer"] == {
            "command": _shim(tmp_path),
            "args": ["--agent-uid", uid],
        }
        assert "github" in data["mcpServers"]


@pytest.mark.acceptance(
    spec="agent-registry/cursor", scenario="deliver a skill for Cursor into ~/.agents/skills"
)
def test_cursor_skill_lands_in_agents_skills(tmp_path, monkeypatch):
    (tmp_path / ".cursor").mkdir()
    _assert_skill_reaches_agents_skills(tmp_path, monkeypatch, "cursor", 61530)


# ---------------------------------------------------------------------------
# agent-registry/opencode
# ---------------------------------------------------------------------------


def _opencode_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / ".config" / "opencode"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.mark.acceptance(
    spec="agent-registry/opencode", scenario="discover OpenCode by its config directory"
)
def test_opencode_is_found_at_config_opencode(tmp_path, monkeypatch):
    _opencode_dir(tmp_path)
    put_programs_on_path(monkeypatch, tmp_path / "bin", {"opencode": "1.19.6"})
    app = _app(tmp_path, monkeypatch, 61540)
    with _client(app) as c:
        cand = _candidates(c)["opencode"]
        assert cand["config_dir"] == str(tmp_path / ".config" / "opencode")
        assert cand["state"] == "installed_active"


@pytest.mark.acceptance(
    spec="agent-registry/opencode", scenario="list exactly OpenCode's two config files"
)
def test_opencode_allowlist_is_config_and_agents_md(tmp_path, monkeypatch):
    _opencode_dir(tmp_path)
    app = _app(tmp_path, monkeypatch, 61550)
    with _client(app) as c:
        uid = _register(c, "opencode")
        files = _files(c, uid)
        assert set(files) == {"config", "instructions"}
        assert pathlib.Path(files["config"]["path"]).name == "opencode.json"
        assert files["config"]["format"] == "json"
        assert pathlib.Path(files["instructions"]["path"]).name == "AGENTS.md"


@pytest.mark.acceptance(
    spec="agent-registry/opencode", scenario="install Coffer's MCP into OpenCode's config"
)
def test_opencode_install_writes_a_local_command_array(tmp_path, monkeypatch):
    config = _opencode_dir(tmp_path) / "opencode.json"
    config.write_text(json.dumps({"model": "anthropic/claude-x"}), encoding="utf-8")
    app = _app(tmp_path, monkeypatch, 61560)
    with _client(app) as c:
        uid = _register(c, "opencode")
        _connect(c, uid)
        data = json.loads(config.read_text(encoding="utf-8"))
        assert data["mcp"]["coffer"] == {
            "type": "local",
            "command": [_shim(tmp_path), "--agent-uid", uid],
        }
        assert data["model"] == "anthropic/claude-x"
        status = c.get(f"/api/v1/agents/{uid}/coffer-connection").json()
        assert status["state"] == "connected", status


@pytest.mark.acceptance(
    spec="agent-registry/opencode", scenario="list OpenCode servers of both config lines"
)
def test_opencode_lists_v1_and_v2_servers(tmp_path, monkeypatch):
    config = _opencode_dir(tmp_path) / "opencode.json"
    config.write_text(
        json.dumps(
            {
                "mcp": {
                    "old": {"type": "local", "command": ["npx", "old-server"]},
                    "servers": {"new": {"type": "remote", "url": "https://example.test/mcp"}},
                }
            }
        ),
        encoding="utf-8",
    )
    app = _app(tmp_path, monkeypatch, 61570)
    with _client(app) as c:
        uid = _register(c, "opencode")
        items = c.get(f"/api/v1/agents/{uid}/mcp-entries").json()["items"]
        assert {"old", "new"} <= {e["name"] for e in items}


@pytest.mark.acceptance(
    spec="agent-registry/opencode",
    scenario="deliver a skill for OpenCode into ~/.agents/skills",
)
def test_opencode_skill_lands_in_agents_skills(tmp_path, monkeypatch):
    _opencode_dir(tmp_path)
    _assert_skill_reaches_agents_skills(tmp_path, monkeypatch, "opencode", 61580)


# ---------------------------------------------------------------------------
# agent-registry/deepseek-harness
# ---------------------------------------------------------------------------

_PERSON_PATCH = textwrap.dedent(
    """\
    # my own preferences
    - insert:
        - id: memory
          name: '@deepseek-ai/dsh-mcp-client'
          config:
            serverName: memory
            transport: stdio
            command: memorix
            args: [serve]
            cwd: !!js process.cwd()
    """
)


def _dsh_dir(tmp_path: pathlib.Path, patch: str | None = None) -> pathlib.Path:
    d = tmp_path / ".dsh"
    d.mkdir(exist_ok=True)
    if patch is not None:
        (d / "cordis.patch.yml").write_text(patch, encoding="utf-8")
    return d


@pytest.mark.acceptance(
    spec="agent-registry/deepseek-harness",
    scenario="discover DeepSeek Harness by its config directory",
)
def test_deepseek_harness_is_found_at_dot_dsh(tmp_path, monkeypatch):
    _dsh_dir(tmp_path)
    put_programs_on_path(monkeypatch, tmp_path / "bin", {"dsh": "0.2.2-rc.5"})
    app = _app(tmp_path, monkeypatch, 61590)
    with _client(app) as c:
        cand = _candidates(c)["deepseek_harness"]
        assert cand["config_dir"] == str(tmp_path / ".dsh")
        assert cand["state"] == "installed_active"


@pytest.mark.acceptance(
    spec="agent-registry/deepseek-harness",
    scenario="list exactly DeepSeek Harness's three config files",
)
def test_deepseek_harness_allowlist(tmp_path, monkeypatch):
    _dsh_dir(tmp_path)
    app = _app(tmp_path, monkeypatch, 61600)
    with _client(app) as c:
        uid = _register(c, "deepseek_harness")
        files = _files(c, uid)
        assert set(files) == {"patch", "web_patch", "instructions"}
        assert files["patch"]["format"] == files["web_patch"]["format"] == "yaml"
        assert files["instructions"]["path"] == str(tmp_path / ".agents" / "AGENTS.md")


@pytest.mark.acceptance(
    spec="agent-registry/deepseek-harness",
    scenario="install Coffer's MCP into the home patch keeping the person's rows",
)
def test_deepseek_harness_install_and_uninstall_keep_the_person_s_text(tmp_path, monkeypatch):
    patch = _dsh_dir(tmp_path, _PERSON_PATCH) / "cordis.patch.yml"
    app = _app(tmp_path, monkeypatch, 61610)
    with _client(app) as c:
        uid = _register(c, "deepseek_harness")
        _connect(c, uid)
        text = patch.read_text(encoding="utf-8")
        assert text.startswith(_PERSON_PATCH.rstrip("\n"))
        assert text.rstrip().endswith(mcp_cordis.BLOCK_END)
        row = mcp_cordis.coffer_row(text)
        assert row is not None and row["config"]["args"] == ["--agent-uid", uid]

        r = c.delete(f"/api/v1/agents/{uid}/coffer-connection")
        assert r.status_code in (200, 204), r.text
        assert patch.read_text(encoding="utf-8").rstrip() == _PERSON_PATCH.rstrip()


@pytest.mark.acceptance(
    spec="agent-registry/deepseek-harness",
    scenario="refuse to remove a DeepSeek Harness MCP row",
)
def test_deepseek_harness_rows_are_listed_but_not_removed(tmp_path, monkeypatch):
    patch = _dsh_dir(tmp_path, _PERSON_PATCH) / "cordis.patch.yml"
    app = _app(tmp_path, monkeypatch, 61620)
    with _client(app) as c:
        uid = _register(c, "deepseek_harness")
        items = c.get(f"/api/v1/agents/{uid}/mcp-entries").json()["items"]
        assert "memory" in {e["name"] for e in items}

        r = c.delete(f"/api/v1/agents/{uid}/mcp-entries/memory")
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "MCP_ENTRY_NOT_EDITABLE"
        assert patch.read_text(encoding="utf-8") == _PERSON_PATCH


@pytest.mark.acceptance(
    spec="agent-registry/deepseek-harness",
    scenario="deliver a skill for DeepSeek Harness into ~/.agents/skills",
)
def test_deepseek_harness_skill_lands_in_agents_skills(tmp_path, monkeypatch):
    _dsh_dir(tmp_path)
    _assert_skill_reaches_agents_skills(tmp_path, monkeypatch, "deepseek_harness", 61630)
