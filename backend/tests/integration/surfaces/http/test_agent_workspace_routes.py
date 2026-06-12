"""HTTP coverage for /api/v1/agents/{name}/mcp-entries and /plugins."""

from __future__ import annotations

import json
import pathlib
import tomllib

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-ws"

SECRET_VALUE = "supersecret-value-31337"
PLAIN_VALUE = "plain-value-xyz"

CODEX_CONFIG = f"""\
[mcp_servers.coffer]
command = "/usr/local/bin/coffer-mcp-shim"

[mcp_servers.fetcher]
command = "uvx"
args = ["mcp-fetch"]

[mcp_servers.fetcher.env]
API_TOKEN = "{SECRET_VALUE}"
PLAIN = "{PLAIN_VALUE}"

[mcp_servers.search]
url = "https://search.example/mcp"
enabled = false

[marketplaces.m1]
source_type = "git"
source = "https://example.com/m1.git"

[plugins."p1@m1"]
enabled = true

[plugins."p2@m1"]
enabled = false
"""


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


@pytest.fixture
def fake_keyring(monkeypatch) -> dict[str, str]:
    """Patch KeyringAdapter class-wide so no test ever touches the OS keychain.

    Affects both the adoption service's adapter (secret writes) and the
    ResourceService's register-time credential probe (secret reads).
    """
    store: dict[str, str] = {}
    monkeypatch.setattr(KeyringAdapter, "get", lambda self, ref: store.get(ref))
    monkeypatch.setattr(
        KeyringAdapter, "set", lambda self, ref, value: store.__setitem__(ref, value)
    )
    monkeypatch.setattr(KeyringAdapter, "delete", lambda self, ref: store.pop(ref, None))
    return store


def _register_codex(c: TestClient, tmp_path: pathlib.Path, config_text: str = CODEX_CONFIG) -> None:
    """Register a codex agent named ``cx`` with the standard fixture config.toml."""
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir(exist_ok=True)
    (codex_dir / "config.toml").write_text(config_text, encoding="utf-8")
    # Cache dir present for p1 only — p2 must list cache_present=False.
    (codex_dir / "plugins" / "cache" / "m1" / "p1").mkdir(parents=True, exist_ok=True)
    r = c.post("/api/v1/agents", json={"type": "codex", "name": "cx"})
    assert r.status_code == 201, r.text


def _register_claude(c: TestClient, tmp_path: pathlib.Path) -> None:
    """Register a claude_code agent named ``cc`` with MCP + plugin fixtures.

    The MCP entry ``dup`` appears in BOTH ~/.claude.json and settings.json so
    source-ambiguity rules can be exercised; ``solo`` exists only globally.
    """
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (tmp_path / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "dup": {"command": "uvx", "args": ["dup-global"]},
                    "solo": {"command": "solo-cmd"},
                }
            }
        ),
        encoding="utf-8",
    )
    (claude_dir / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {"dup": {"command": "uvx", "args": ["dup-settings"]}},
                "enabledPlugins": {"q1@mk": True, "q2@mk": False},
            }
        ),
        encoding="utf-8",
    )
    plugins_dir = claude_dir / "plugins"
    plugins_dir.mkdir(exist_ok=True)
    (plugins_dir / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {"q1@mk": [], "q2@mk": []}}),
        encoding="utf-8",
    )
    (plugins_dir / "known_marketplaces.json").write_text(
        json.dumps({"mk": {"source": {"source": "github", "repo": "owner/mk"}}}),
        encoding="utf-8",
    )
    r = c.post("/api/v1/agents", json={"type": "claude_code", "name": "cc"})
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# MCP entries
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="004-agent-registry", scenario="list an agent's real MCP entries")
def test_list_mcp_entries(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59800)
    with _client(app) as c:
        _register_codex(c, tmp_path)

        r = c.get("/api/v1/agents/cx/mcp-entries")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["parse_errors"] == []
        by_name = {e["name"]: e for e in body["items"]}
        assert set(by_name) == {"coffer", "fetcher", "search"}

        assert by_name["coffer"]["is_coffer"] is True
        fetcher = by_name["fetcher"]
        assert fetcher["source"] == "config"
        assert fetcher["transport"] == "stdio"
        assert fetcher["command"] == "uvx"
        assert fetcher["args"] == ["mcp-fetch"]
        assert fetcher["enabled"] is True
        assert fetcher["env_keys"] == ["API_TOKEN", "PLAIN"]
        assert fetcher["secret_keys"] == ["API_TOKEN"]
        search = by_name["search"]
        assert search["transport"] == "http"
        assert search["url"] == "https://search.example/mcp"
        assert search["enabled"] is False

        # Env/header VALUES must never cross HTTP — only key names do.
        assert SECRET_VALUE not in r.text
        assert PLAIN_VALUE not in r.text


@pytest.mark.acceptance(spec="004-agent-registry", scenario="remove a direct MCP entry")
def test_remove_mcp_entry(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59810)
    with _client(app) as c:
        _register_codex(c, tmp_path)
        config = tmp_path / ".codex" / "config.toml"

        r = c.delete("/api/v1/agents/cx/mcp-entries/fetcher")
        assert r.status_code == 204, r.text
        data = tomllib.loads(config.read_text(encoding="utf-8"))
        assert "fetcher" not in data["mcp_servers"]
        # Atomic write preserved the prior content in a .bak.
        bak = tmp_path / ".codex" / "config.toml.bak"
        assert bak.exists()
        assert "fetcher" in bak.read_text(encoding="utf-8")

        r = c.get("/api/v1/agents/cx/mcp-entries")
        assert "fetcher" not in [e["name"] for e in r.json()["items"]]


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="toggle a Codex MCP entry's enabled flag"
)
def test_toggle_codex_mcp_entry(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59820)
    with _client(app) as c:
        _register_codex(c, tmp_path)

        r = c.patch("/api/v1/agents/cx/mcp-entries/fetcher", json={"enabled": False})
        assert r.status_code == 204, r.text
        config = tmp_path / ".codex" / "config.toml"
        data = tomllib.loads(config.read_text(encoding="utf-8"))
        assert data["mcp_servers"]["fetcher"]["enabled"] is False

        r = c.get("/api/v1/agents/cx/mcp-entries")
        by_name = {e["name"]: e for e in r.json()["items"]}
        assert by_name["fetcher"]["enabled"] is False


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="reject toggling a Claude Code MCP entry"
)
def test_reject_toggle_claude_mcp_entry(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59830)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        before = (tmp_path / ".claude.json").read_bytes()

        r = c.patch("/api/v1/agents/cc/mcp-entries/solo", json={"enabled": False})
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "MCP_ENTRY_TOGGLE_UNSUPPORTED"
        assert (tmp_path / ".claude.json").read_bytes() == before


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="degrade to read-only when MCP config is unparseable"
)
def test_parse_error_degrades_listing(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59840)
    with _client(app) as c:
        _register_codex(c, tmp_path, config_text="not [valid toml ===")

        r = c.get("/api/v1/agents/cx/mcp-entries")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["items"] == []
        assert len(body["parse_errors"]) == 1
        assert body["parse_errors"][0]["source"] == "config"
        assert body["parse_errors"][0]["error"]


@pytest.mark.acceptance(spec="004-agent-registry", scenario="adopt a direct MCP entry into Coffer")
def test_adopt_mcp_entry(tmp_path, monkeypatch, fake_keyring):
    app = _app(tmp_path, monkeypatch, 59850)
    with _client(app) as c:
        _register_codex(c, tmp_path)
        ref = "mcp.fetcher.API_TOKEN"

        r = c.post(
            "/api/v1/agents/cx/mcp-entries/fetcher/adopt",
            json={"secrets": {"API_TOKEN": ref}},
        )
        assert r.status_code == 201, r.text
        assert r.json() == {"kind": "mcp_server", "name": "fetcher"}

        # The mcp_server resource exists and carries a ref, never the value.
        r = c.get("/api/v1/resources/mcp_server/fetcher")
        assert r.status_code == 200, r.text
        transport = r.json()["config"]["transport"]
        assert transport["credential_refs"] == {"API_TOKEN": ref}
        assert SECRET_VALUE not in r.text

        # The entry is gone from the agent's own file.
        data = tomllib.loads((tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8"))
        assert "fetcher" not in data["mcp_servers"]

        # The secret value landed in the encrypted credential store under the
        # ref (read back through the audited API — never via the keychain).
        r = c.get(f"/api/v1/credentials/{ref}")
        assert r.status_code == 200, r.text
        assert r.json() == {"value": SECRET_VALUE}


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="reject adoption on resource name conflict"
)
def test_adopt_name_conflict_409_with_suggestion(tmp_path, monkeypatch, fake_keyring):
    app = _app(tmp_path, monkeypatch, 59860)
    with _client(app) as c:
        _register_codex(c, tmp_path)
        config = tmp_path / ".codex" / "config.toml"
        before = config.read_bytes()

        r = c.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": "fetcher",
                "config": {"transport": {"type": "stdio", "command": "other-cmd"}},
            },
        )
        assert r.status_code == 201, r.text

        r = c.post(
            "/api/v1/agents/cx/mcp-entries/fetcher/adopt",
            json={"secrets": {"API_TOKEN": "mcp.fetcher.API_TOKEN"}},
        )
        assert r.status_code == 409, r.text
        err = r.json()["error"]
        assert err["code"] == "RESOURCE_ALREADY_EXISTS"
        assert err["details"]["suggested_name"] == "fetcher-codex"
        # Agent config untouched.
        assert config.read_bytes() == before


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="require keychain mapping for secret-like env values"
)
def test_adopt_requires_secret_mapping(tmp_path, monkeypatch, fake_keyring):
    app = _app(tmp_path, monkeypatch, 59870)
    with _client(app) as c:
        _register_codex(c, tmp_path)
        config = tmp_path / ".codex" / "config.toml"
        before = config.read_bytes()

        r = c.post("/api/v1/agents/cx/mcp-entries/fetcher/adopt", json={})
        assert r.status_code == 422, r.text
        err = r.json()["error"]
        assert err["code"] == "ADOPT_SECRET_UNRESOLVED"
        assert "API_TOKEN" in err["message"]
        assert config.read_bytes() == before

        # With the mapping supplied the adoption succeeds.
        r = c.post(
            "/api/v1/agents/cx/mcp-entries/fetcher/adopt",
            json={"secrets": {"API_TOKEN": "mcp.fetcher.API_TOKEN"}},
        )
        assert r.status_code == 201, r.text


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="adoption failure leaves agent config untouched"
)
def test_adopt_failure_rolls_back(tmp_path, monkeypatch, fake_keyring):
    app = _app(tmp_path, monkeypatch, 59880)
    with _client(app) as c:
        _register_codex(c, tmp_path)
        config = tmp_path / ".codex" / "config.toml"
        before = config.read_bytes()

        # Force the config-file removal write (the step AFTER resource
        # registration) to fail with the spec's example error.
        from coffer.domain.workspace_errors import ConfigFileStale

        def _stale(self, path, text):
            raise ConfigFileStale("config")

        monkeypatch.setattr(ConfigFileStore, "write_text_atomic", _stale)
        r = c.post(
            "/api/v1/agents/cx/mcp-entries/fetcher/adopt",
            json={"secrets": {"API_TOKEN": "mcp.fetcher.API_TOKEN"}},
        )
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "CONFIG_FILE_STALE"

        # Agent config byte-identical; the half-created resource rolled back.
        assert config.read_bytes() == before
        r = c.get("/api/v1/resources/mcp_server/fetcher")
        assert r.status_code == 404


def test_mcp_entries_unknown_agent_404(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59890)
    with _client(app) as c:
        r = c.get("/api/v1/agents/ghost/mcp-entries")
        assert r.status_code == 404


def test_mcp_entries_unknown_entry_404(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59900)
    with _client(app) as c:
        _register_codex(c, tmp_path)
        r = c.delete("/api/v1/agents/cx/mcp-entries/nope")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "MCP_ENTRY_NOT_FOUND"


def test_mcp_entry_source_ambiguous_without_source_param(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59910)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        # "dup" lives in BOTH ~/.claude.json and settings.json.
        r = c.delete("/api/v1/agents/cc/mcp-entries/dup")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "MCP_ENTRY_SOURCE_AMBIGUOUS"

        # Naming the source disambiguates.
        r = c.delete("/api/v1/agents/cc/mcp-entries/dup", params={"source": "settings"})
        assert r.status_code == 204, r.text
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        assert "dup" not in settings["mcpServers"]
        global_cfg = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))
        assert "dup" in global_cfg["mcpServers"]


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="list an agent's plugins with enabled state"
)
def test_list_plugins(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59920)
    with _client(app) as c:
        _register_codex(c, tmp_path)

        r = c.get("/api/v1/agents/cx/plugins")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["parse_errors"] == []
        by_id = {p["id"]: p for p in body["items"]}
        assert set(by_id) == {"p1@m1", "p2@m1"}
        p1 = by_id["p1@m1"]
        assert p1["name"] == "p1"
        assert p1["marketplace"] == "m1"
        assert p1["enabled"] is True
        assert p1["cache_present"] is True
        assert by_id["p2@m1"]["enabled"] is False
        assert body["marketplaces"] == [
            {"name": "m1", "source_type": "git", "source": "https://example.com/m1.git"}
        ]


@pytest.mark.acceptance(spec="004-agent-registry", scenario="toggle a plugin's enabled state")
def test_toggle_claude_plugin_writes_settings_only(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59930)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        installed = tmp_path / ".claude" / "plugins" / "installed_plugins.json"
        installed_before = installed.read_bytes()

        r = c.patch("/api/v1/agents/cc/plugins/q1@mk", json={"enabled": False})
        assert r.status_code == 204, r.text

        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        assert settings["enabledPlugins"]["q1@mk"] is False
        # The internal inventory file is byte-identical — never written.
        assert installed.read_bytes() == installed_before

        r = c.get("/api/v1/agents/cc/plugins")
        by_id = {p["id"]: p for p in r.json()["items"]}
        assert by_id["q1@mk"]["enabled"] is False


@pytest.mark.acceptance(spec="004-agent-registry", scenario="uninstall a Codex plugin")
def test_uninstall_codex_plugin(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59940)
    with _client(app) as c:
        _register_codex(c, tmp_path)
        cache_dir = tmp_path / ".codex" / "plugins" / "cache" / "m1" / "p1"
        assert cache_dir.is_dir()

        r = c.delete("/api/v1/agents/cx/plugins/p1@m1")
        assert r.status_code == 204, r.text
        data = tomllib.loads((tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8"))
        assert "p1@m1" not in data.get("plugins", {})
        assert not cache_dir.exists()


@pytest.mark.acceptance(
    spec="004-agent-registry", scenario="reject uninstalling a Claude Code plugin"
)
def test_reject_uninstall_claude_plugin(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59950)
    with _client(app) as c:
        _register_claude(c, tmp_path)
        settings = tmp_path / ".claude" / "settings.json"
        before = settings.read_bytes()

        r = c.delete("/api/v1/agents/cc/plugins/q1@mk")
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "PLUGIN_UNINSTALL_UNSUPPORTED"
        assert settings.read_bytes() == before


@pytest.mark.acceptance(spec="004-agent-registry", scenario="flag a plugin whose cache is missing")
def test_plugin_cache_missing_flagged(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59960)
    with _client(app) as c:
        _register_codex(c, tmp_path)

        r = c.get("/api/v1/agents/cx/plugins")
        by_id = {p["id"]: p for p in r.json()["items"]}
        # p2 has no cache dir on disk — reported, not repaired.
        assert by_id["p2@m1"]["cache_present"] is False
        assert not (tmp_path / ".codex" / "plugins" / "cache" / "m1" / "p2").exists()
