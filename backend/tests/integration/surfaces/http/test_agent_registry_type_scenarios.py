"""Acceptance coverage, over the real app, for the per-type agent-registry facets.

Each test boots ``create_app`` against a temp ``HOME`` (so the type's standard
config directory — ``~/.claude`` or ``~/.codex`` — is a temp tree), registers an
agent through ``POST /api/v1/agents`` and drives the same routes the web UI and
the CLI call. Nothing here reads or writes the real home directory.
"""

from __future__ import annotations

import builtins
import json
import pathlib
import re
import tomllib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-agent-type-scenarios"


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


def _register(c: TestClient, agent_type: str, name: str) -> str:
    r = c.post("/api/v1/agents", json={"type": agent_type, "name": name})
    assert r.status_code == 201, r.text
    return r.json()["uid"]


def _audit_count(c: TestClient) -> int:
    r = c.get("/api/v1/audit")
    assert r.status_code == 200, r.text
    return len(r.json()["entries"])


# ---------------------------------------------------------------------------
# agent-registry (parent)
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="return an empty scan when the agent has no native memory on disk",
)
def test_native_memory_scan_without_layout_on_disk_is_empty_and_unaudited(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()  # no projects/ directory at all
    app = _app(tmp_path, monkeypatch, 61100)
    with _client(app) as c:
        uid = _register(c, "claude_code", "cc")
        before = _audit_count(c)

        r = c.get(f"/api/v1/agents/{uid}/native-memory")

        assert r.status_code == 200, r.text
        assert r.json()["items"] == []
        assert _audit_count(c) == before


# ---------------------------------------------------------------------------
# agent-registry/claude-code
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="agent-registry/claude-code", scenario="discover Claude Code by its config directory"
)
def test_claude_code_is_found_and_defaults_to_dot_claude(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()
    app = _app(tmp_path, monkeypatch, 61110)
    with _client(app) as c:
        cands = {x["type"]: x for x in c.get("/api/v1/agents/candidates").json()["candidates"]}
        assert cands["claude_code"]["config_dir"] == str(tmp_path / ".claude")

        uid = _register(c, "claude_code", "cc")
        files = {f["key"]: f for f in c.get(f"/api/v1/agents/{uid}/config-files").json()["items"]}
        assert files["settings"]["path"] == str(tmp_path / ".claude" / "settings.json")
        assert files["settings"]["folder_path"] == str(tmp_path / ".claude")


def _claude_mcp_fixture(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    global_cfg = tmp_path / ".claude.json"
    global_cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "only-global": {"command": "g-cmd"},
                    "both": {"command": "uvx", "args": ["both-global"]},
                }
            }
        ),
        encoding="utf-8",
    )
    settings = claude_dir / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "only-settings": {"url": "https://s.example/mcp", "type": "http"},
                    "both": {"command": "uvx", "args": ["both-settings"]},
                }
            }
        ),
        encoding="utf-8",
    )
    return global_cfg, settings


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="list MCP entries from both Claude Code config files",
)
def test_claude_mcp_entries_come_from_both_files_without_enabled(tmp_path, monkeypatch):
    _claude_mcp_fixture(tmp_path)
    app = _app(tmp_path, monkeypatch, 61120)
    with _client(app) as c:
        uid = _register(c, "claude_code", "cc")

        r = c.get(f"/api/v1/agents/{uid}/mcp-entries")

        assert r.status_code == 200, r.text
        pairs = sorted((e["name"], e["source"]) for e in r.json()["items"])
        assert pairs == [
            ("both", "global"),
            ("both", "settings"),
            ("only-global", "global"),
            ("only-settings", "settings"),
        ]
        assert all(e["enabled"] is None for e in r.json()["items"])


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="reject an ambiguous MCP entry removal without a source",
)
def test_claude_ambiguous_removal_is_rejected_and_writes_nothing(tmp_path, monkeypatch):
    global_cfg, settings = _claude_mcp_fixture(tmp_path)
    app = _app(tmp_path, monkeypatch, 61130)
    with _client(app) as c:
        uid = _register(c, "claude_code", "cc")
        g_before, s_before = global_cfg.read_bytes(), settings.read_bytes()

        r = c.delete(f"/api/v1/agents/{uid}/mcp-entries/both")

        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "MCP_ENTRY_SOURCE_AMBIGUOUS"
        assert global_cfg.read_bytes() == g_before
        assert settings.read_bytes() == s_before


def _claude_plugins_fixture(tmp_path: pathlib.Path) -> dict[str, pathlib.Path]:
    claude_dir = tmp_path / ".claude"
    plugins_dir = claude_dir / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    present = plugins_dir / "cache" / "mk" / "here" / "1.0.0"
    present.mkdir(parents=True)
    gone = plugins_dir / "cache" / "mk" / "gone" / "1.0.0"  # never created on disk
    installed = plugins_dir / "installed_plugins.json"
    installed.write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "here@mk": [{"scope": "user", "installPath": str(present), "version": "1.0.0"}],
                    "gone@mk": [{"scope": "user", "installPath": str(gone), "version": "1.0.0"}],
                },
            }
        ),
        encoding="utf-8",
    )
    marketplaces = plugins_dir / "known_marketplaces.json"
    marketplaces.write_text(
        json.dumps({"mk": {"source": {"source": "github", "repo": "owner/mk"}}}),
        encoding="utf-8",
    )
    settings = claude_dir / "settings.json"
    settings.write_text(
        json.dumps({"enabledPlugins": {"here@mk": True, "gone@mk": False}}), encoding="utf-8"
    )
    return {"installed": installed, "marketplaces": marketplaces, "settings": settings}


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="toggle a Claude Code plugin without touching its inventory",
)
def test_claude_toggle_leaves_inventory_and_marketplaces_byte_identical(tmp_path, monkeypatch):
    files = _claude_plugins_fixture(tmp_path)
    app = _app(tmp_path, monkeypatch, 61150)
    with _client(app) as c:
        uid = _register(c, "claude_code", "cc")
        installed_before = files["installed"].read_bytes()
        marketplaces_before = files["marketplaces"].read_bytes()

        r = c.patch(f"/api/v1/agents/{uid}/plugins/here@mk", json={"enabled": False})

        assert r.status_code == 204, r.text
        settings = json.loads(files["settings"].read_text(encoding="utf-8"))
        assert settings["enabledPlugins"]["here@mk"] is False
        assert files["installed"].read_bytes() == installed_before
        assert files["marketplaces"].read_bytes() == marketplaces_before


def _claude_session_line(sid: str, cwd: str, text: str) -> str:
    return json.dumps(
        {
            "type": "user",
            "cwd": cwd,
            "sessionId": sid,
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {"role": "user", "content": text},
        }
    )


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="list sessions from projects and refuse a sibling as a memory store",
)
def test_claude_transcripts_live_under_projects_and_a_sibling_is_no_store(tmp_path, monkeypatch):
    project = tmp_path / ".claude" / "projects" / "-work-repo"
    (project / "memory").mkdir(parents=True)
    (project / "memory" / "fact.md").write_text("a fact", encoding="utf-8")
    session = project / "s1.jsonl"
    session.write_text(_claude_session_line("s1", "/work/repo", "set up auth"), encoding="utf-8")
    app = _app(tmp_path, monkeypatch, 61160)
    with _client(app) as c:
        uid = _register(c, "claude_code", "cc")

        listed = c.get(f"/api/v1/agents/{uid}/transcripts")
        assert listed.status_code == 200, listed.text
        assert [s["source_path"] for s in listed.json()["sessions"]] == [str(session)]

        sibling = c.get(f"/api/v1/agents/{uid}/native-memory/files", params={"dir": str(project)})
        assert sibling.status_code == 404, sibling.text
        # The real store beside it is readable — the refusal is about the shape.
        store = c.get(
            f"/api/v1/agents/{uid}/native-memory/files", params={"dir": str(project / "memory")}
        )
        assert store.status_code == 200, store.text


# ---------------------------------------------------------------------------
# agent-registry/codex
# ---------------------------------------------------------------------------

_CODEX_INTERNAL_TABLES = """\
[marketplaces.m1]
source_type = "git"
source = "https://example.com/m1.git"

[hooks.state.pre]
last_run = "2026-06-01T00:00:00Z"

[projects."/work/repo"]
trust_level = "trusted"
"""

_CODEX_CONFIG = (
    """\
# the user's own notes about this file
model = "gpt-5-codex"

[mcp_servers.fetcher]
command = "uvx"
args = ["mcp-fetch"]

[mcp_servers.search]
url = "https://search.example/mcp"
enabled = false

[plugins."p1@m1"]
enabled = true

[plugins."p2@m1"]
enabled = true

"""
    + _CODEX_INTERNAL_TABLES
)


def _codex_fixture(tmp_path: pathlib.Path, config: str = _CODEX_CONFIG) -> pathlib.Path:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir(exist_ok=True)
    (codex_dir / "config.toml").write_text(config, encoding="utf-8")
    (codex_dir / "plugins" / "cache" / "m1" / "p1").mkdir(parents=True, exist_ok=True)
    return codex_dir


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="discover Codex by its config directory"
)
def test_codex_is_found_and_defaults_to_dot_codex(tmp_path, monkeypatch):
    (tmp_path / ".codex").mkdir()
    app = _app(tmp_path, monkeypatch, 61200)
    with _client(app) as c:
        cands = {x["type"]: x for x in c.get("/api/v1/agents/candidates").json()["candidates"]}
        assert cands["codex"]["config_dir"] == str(tmp_path / ".codex")

        uid = _register(c, "codex", "cx")
        files = {f["key"]: f for f in c.get(f"/api/v1/agents/{uid}/config-files").json()["items"]}
        assert files["config"]["path"] == str(tmp_path / ".codex" / "config.toml")


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="list exactly Codex's three config files"
)
def test_codex_allowlist_is_exactly_three_files(tmp_path, monkeypatch):
    _codex_fixture(tmp_path)
    app = _app(tmp_path, monkeypatch, 61210)
    with _client(app) as c:
        uid = _register(c, "codex", "cx")

        items = c.get(f"/api/v1/agents/{uid}/config-files").json()["items"]

        by_name = {pathlib.Path(f["path"]).name: f for f in items}
        assert set(by_name) == {"config.toml", "AGENTS.md", "hooks.json"}
        assert by_name["config.toml"]["format"] == "toml"
        assert by_name["AGENTS.md"]["key"] == "instructions"
        assert all(f.get("kind", "file") == "file" for f in items)


@pytest.mark.acceptance(spec="agent-registry/codex", scenario="refuse to read auth.json")
def test_codex_auth_json_is_never_listed_or_readable(tmp_path, monkeypatch):
    codex_dir = _codex_fixture(tmp_path)
    auth = codex_dir / "auth.json"
    auth.write_text('{"OPENAI_API_KEY": "sk-secret"}', encoding="utf-8")
    app = _app(tmp_path, monkeypatch, 61220)
    with _client(app) as c:
        uid = _register(c, "codex", "cx")

        # "No filesystem read": spy on every way the process could touch the
        # file — open(), the Path readers, and the config store's own read/stat
        # — from here on. Registration above is excluded; the scenario is about
        # the listing and the by-key request.
        touched: list[str] = []
        real_open = builtins.open
        real_read_text = pathlib.Path.read_text
        real_read_bytes = pathlib.Path.read_bytes
        real_stat = pathlib.Path.stat

        def _note(path: object) -> None:
            if pathlib.Path(str(path)).name == "auth.json":
                touched.append(str(path))

        def spy_open(file, *args, **kwargs):
            if isinstance(file, (str, pathlib.PurePath)):
                _note(file)
            return real_open(file, *args, **kwargs)

        def spy_read_text(self, *args, **kwargs):
            _note(self)
            return real_read_text(self, *args, **kwargs)

        def spy_read_bytes(self):
            _note(self)
            return real_read_bytes(self)

        def spy_stat(self, *args, **kwargs):
            _note(self)
            return real_stat(self, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", spy_open)
        monkeypatch.setattr(pathlib.Path, "read_text", spy_read_text)
        monkeypatch.setattr(pathlib.Path, "read_bytes", spy_read_bytes)
        monkeypatch.setattr(pathlib.Path, "stat", spy_stat)

        listing = c.get(f"/api/v1/agents/{uid}/config-files")
        assert listing.status_code == 200, listing.text
        names = {pathlib.Path(f["path"]).name for f in listing.json()["items"]}
        assert names == {"config.toml", "AGENTS.md", "hooks.json"}
        assert "auth.json" not in listing.text
        assert "sk-secret" not in listing.text

        for key in ("auth", "auth.json"):
            r = c.get(f"/api/v1/agents/{uid}/config-files/{key}")
            assert r.status_code == 404, r.text
            assert r.json()["error"]["code"] == "CONFIG_FILE_NOT_ALLOWED", r.text
            assert "sk-secret" not in r.text

        assert touched == [], f"auth.json was touched on disk: {touched}"


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="report the enabled flag of Codex MCP entries"
)
def test_codex_mcp_entries_report_enabled(tmp_path, monkeypatch):
    _codex_fixture(tmp_path)
    app = _app(tmp_path, monkeypatch, 61240)
    with _client(app) as c:
        uid = _register(c, "codex", "cx")

        items = {e["name"]: e for e in c.get(f"/api/v1/agents/{uid}/mcp-entries").json()["items"]}

        assert items["search"]["source"] == items["fetcher"]["source"] == "config"
        assert items["search"]["enabled"] is False
        assert items["fetcher"]["enabled"] is True


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="flag a Codex plugin without its cache directory"
)
def test_codex_plugins_flag_a_missing_cache_dir(tmp_path, monkeypatch):
    _codex_fixture(tmp_path)
    app = _app(tmp_path, monkeypatch, 61250)
    with _client(app) as c:
        uid = _register(c, "codex", "cx")

        items = {p["id"]: p for p in c.get(f"/api/v1/agents/{uid}/plugins").json()["items"]}

        assert {p["marketplace"] for p in items.values()} == {"m1"}
        assert items["p1@m1"]["cache_present"] is True
        assert items["p2@m1"]["cache_present"] is False


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="toggle a Codex plugin by its enabled field"
)
def test_codex_toggle_writes_only_the_plugins_enabled_field(tmp_path, monkeypatch):
    codex_dir = _codex_fixture(tmp_path)
    cache_root = codex_dir / "plugins"
    app = _app(tmp_path, monkeypatch, 61260)
    with _client(app) as c:
        uid = _register(c, "codex", "cx")
        before = tomllib.loads((codex_dir / "config.toml").read_text(encoding="utf-8"))
        plugins_before = sorted(str(p) for p in cache_root.rglob("*"))

        r = c.patch(f"/api/v1/agents/{uid}/plugins/p1@m1", json={"enabled": False})

        assert r.status_code == 204, r.text
        after = tomllib.loads((codex_dir / "config.toml").read_text(encoding="utf-8"))
        assert after["plugins"]["p1@m1"] == {"enabled": False}
        before["plugins"]["p1@m1"]["enabled"] = False
        assert after == before
        assert sorted(str(p) for p in cache_root.rglob("*")) == plugins_before


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="reject a wire_api other than responses"
)
def test_codex_wire_api_other_than_responses_is_422(tmp_path, monkeypatch):
    (tmp_path / ".codex").mkdir()
    app = _app(tmp_path, monkeypatch, 61270)
    with _client(app) as c:
        uid = _register(c, "codex", "cx")
        ok = c.patch(f"/api/v1/agents/{uid}", json={"wire_api": "responses"})
        assert ok.status_code == 200, ok.text

        r = c.patch(f"/api/v1/agents/{uid}", json={"wire_api": "chat"})

        assert r.status_code == 422, r.text
        assert c.get(f"/api/v1/agents/{uid}").json()["wire_api"] == "responses"


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="list Codex sessions from the sessions directory"
)
def test_codex_transcripts_come_from_the_sessions_directory(tmp_path, monkeypatch):
    codex_dir = _codex_fixture(tmp_path)
    nested = codex_dir / "sessions" / "2026" / "06" / "01"
    nested.mkdir(parents=True)
    session = nested / "rollout-x.jsonl"
    session.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-06-01T00:00:00Z",
                        "type": "session_meta",
                        "payload": {"id": "x", "cwd": "/work/repo"},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-01T00:00:01Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "hello"}],
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    # A .jsonl outside sessions/ is not a Codex transcript.
    (codex_dir / "stray.jsonl").write_text(session.read_text(encoding="utf-8"), encoding="utf-8")
    app = _app(tmp_path, monkeypatch, 61280)
    with _client(app) as c:
        uid = _register(c, "codex", "cx")

        r = c.get(f"/api/v1/agents/{uid}/transcripts")

        assert r.status_code == 200, r.text
        assert [s["source_path"] for s in r.json()["sessions"]] == [str(session)]


def _table_text(config_text: str, header: str) -> str:
    """The text of one ``[header]`` table, up to the next table header."""
    match = re.search(
        rf"^\[{re.escape(header)}\]\n(?:(?!\[).*\n?)*", config_text, flags=re.MULTILINE
    )
    assert match is not None, f"table [{header}] missing from:\n{config_text}"
    return match.group(0).rstrip("\n")


@pytest.mark.acceptance(
    spec="agent-registry/codex",
    scenario="keep internal-state tables byte-identical across every write",
)
def test_codex_internal_state_tables_survive_every_write(tmp_path, monkeypatch):
    codex_dir = _codex_fixture(tmp_path)
    config = codex_dir / "config.toml"
    headers = ("marketplaces.m1", "hooks.state.pre", 'projects."/work/repo"')
    original = {h: _table_text(config.read_text(encoding="utf-8"), h) for h in headers}
    app = _app(tmp_path, monkeypatch, 61290)
    with _client(app) as c:
        uid = _register(c, "codex", "cx")
        writes = [
            lambda: c.post(f"/api/v1/agents/{uid}/mcp-install"),
            lambda: c.patch(f"/api/v1/agents/{uid}/plugins/p2@m1", json={"enabled": False}),
            lambda: c.delete(f"/api/v1/agents/{uid}/plugins/p1@m1"),
            lambda: c.delete(f"/api/v1/agents/{uid}/mcp-entries/fetcher"),
        ]
        for write in writes:
            r = write()
            assert r.status_code in (200, 204), r.text
            text = config.read_text(encoding="utf-8")
            for h in headers:
                assert _table_text(text, h) == original[h], h
        # Every write landed — the loop above did not pass on untouched files.
        data = tomllib.loads(config.read_text(encoding="utf-8"))
        assert "coffer" in data["mcp_servers"]
        assert "fetcher" not in data["mcp_servers"]
        assert "p1@m1" not in data["plugins"]
        assert data["plugins"]["p2@m1"]["enabled"] is False
