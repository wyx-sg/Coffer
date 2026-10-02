"""HTTP coverage for GET /api/v1/agents/{uid}/mcp-entries/{entry}.

The one-entry read behind the direct-server detail page (spec agent-registry
"Show one direct MCP entry's full configuration without its secrets"). It
carries everything the agent's file says about the entry — the file's path, the
command, the working directory, every other key — and none of its secret
values: env and header values stay key-names-only exactly as in the listing,
and any other key whose name looks secret-like is masked server-side.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-mcp-entry-detail"

ENV_SECRET = "env-secret-value-4242"
ENV_PLAIN = "env-plain-value-4242"
HEADER_SECRET = "header-secret-value-4242"
BEARER = "bearer-token-value-4242"
NESTED_SECRET = "nested-secret-value-4242"

CODEX_CONFIG = f"""\
[mcp_servers.coffer]
command = "/usr/local/bin/coffer-mcp-shim"

[mcp_servers.fetcher]
command = "uvx"
args = ["mcp-fetch", "--verbose"]
cwd = "/srv/fetcher"
startup_timeout_sec = 30
env_vars = ["HOME", "LANG"]
bearer_token = "{BEARER}"

[mcp_servers.fetcher.env]
API_TOKEN = "{ENV_SECRET}"
PLAIN = "{ENV_PLAIN}"

[mcp_servers.fetcher.extra_auth]
client_secret = "{NESTED_SECRET}"

[mcp_servers.search]
url = "https://search.example/mcp"

[mcp_servers.search.http_headers]
Authorization = "{HEADER_SECRET}"
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


def _register_codex(c: TestClient, tmp_path: pathlib.Path) -> str:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir(exist_ok=True)
    (codex_dir / "config.toml").write_text(CODEX_CONFIG, encoding="utf-8")
    r = c.post("/api/v1/agents", json={"type": "codex", "name": "cx"})
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


def _register_claude(c: TestClient, tmp_path: pathlib.Path) -> str:
    """``dup`` lives in both of claude_code's MCP files; ``solo`` only globally."""
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "dup": {"command": "uvx", "args": ["dup-global"]},
                    "solo": {"type": "sse", "url": "https://solo.example/sse"},
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"mcpServers": {"dup": {"command": "uvx", "args": ["dup-settings"]}}}),
        encoding="utf-8",
    )
    r = c.post("/api/v1/agents", json={"type": "claude_code", "name": "cc"})
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


@pytest.mark.acceptance(
    spec="agent-registry", scenario="read one direct MCP entry with its secrets withheld"
)
def test_get_mcp_entry_returns_full_config_and_masks_secrets(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 61940)
    with _client(app) as c:
        uid = _register_codex(c, tmp_path)

        r = c.get(f"/api/v1/agents/{uid}/mcp-entries/fetcher")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "fetcher"
        assert body["source"] == "config"
        assert body["path"] == str(tmp_path / ".codex" / "config.toml")
        assert body["transport"] == "stdio"
        assert body["command"] == "uvx"
        assert body["args"] == ["mcp-fetch", "--verbose"]
        assert body["cwd"] == "/srv/fetcher"
        assert body["env_keys"] == ["API_TOKEN", "PLAIN"]
        assert body["secret_keys"] == ["API_TOKEN"]
        assert body["is_coffer"] is False
        assert body["matches_resource"] is None

        extra = {f["key"]: f for f in body["extra"]}
        # Sorted by key, and nothing the typed fields already carry repeats.
        assert [f["key"] for f in body["extra"]] == sorted(extra)
        assert set(extra) == {"bearer_token", "env_vars", "extra_auth", "startup_timeout_sec"}
        assert extra["startup_timeout_sec"] == {
            "key": "startup_timeout_sec",
            "value": "30",
            "masked": False,
        }
        assert extra["env_vars"]["value"] == '["HOME", "LANG"]'
        # A secret-looking key is withheld; so is a table that nests one.
        assert extra["bearer_token"] == {"key": "bearer_token", "value": None, "masked": True}
        assert extra["extra_auth"] == {"key": "extra_auth", "value": None, "masked": True}

        # No secret — and no env value at all — crosses HTTP.
        for value in (ENV_SECRET, ENV_PLAIN, BEARER, NESTED_SECRET):
            assert value not in r.text

        # The whole entry as the file holds it — its own key names and shape —
        # with every credential-bearing value masked.
        assert body["config"] == {
            "command": "uvx",
            "args": ["mcp-fetch", "--verbose"],
            "cwd": "/srv/fetcher",
            "startup_timeout_sec": 30,
            "env_vars": ["HOME", "LANG"],
            "bearer_token": "••••••",
            "env": {"API_TOKEN": "••••••", "PLAIN": "••••••"},
            "extra_auth": {"client_secret": "••••••"},
        }

        r = c.get(f"/api/v1/agents/{uid}/mcp-entries/search")
        assert r.status_code == 200, r.text
        search = r.json()
        assert search["transport"] == "http"
        assert search["url"] == "https://search.example/mcp"
        assert search["header_keys"] == ["Authorization"]
        assert search["secret_keys"] == ["Authorization"]
        assert search["cwd"] is None
        assert HEADER_SECRET not in r.text
        assert search["config"] == {
            "url": "https://search.example/mcp",
            "http_headers": {"Authorization": "••••••"},
        }


def test_get_mcp_entry_reports_an_equivalent_registered_server(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 61950)
    with _client(app) as c:
        uid = _register_codex(c, tmp_path)
        r = c.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": "search-managed",
                "config": {"transport": {"type": "http", "url": "https://search.example/mcp"}},
            },
        )
        assert r.status_code == 201, r.text

        r = c.get(f"/api/v1/agents/{uid}/mcp-entries/search")
        assert r.status_code == 200, r.text
        assert r.json()["matches_resource"] == "search-managed"


def test_get_mcp_entry_disambiguates_by_source(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 61960)
    with _client(app) as c:
        uid = _register_claude(c, tmp_path)

        r = c.get(f"/api/v1/agents/{uid}/mcp-entries/dup")
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "MCP_ENTRY_SOURCE_AMBIGUOUS"

        r = c.get(f"/api/v1/agents/{uid}/mcp-entries/dup", params={"source": "settings"})
        assert r.status_code == 200, r.text
        assert r.json()["args"] == ["dup-settings"]
        assert r.json()["path"] == str(tmp_path / ".claude" / "settings.json")

        # A remote entry declared `type = "sse"` keeps that declaration visible.
        r = c.get(f"/api/v1/agents/{uid}/mcp-entries/solo")
        assert r.status_code == 200, r.text
        solo = r.json()
        assert solo["transport"] == "http"
        assert solo["url"] == "https://solo.example/sse"
        assert solo["extra"] == [{"key": "type", "value": "sse", "masked": False}]


def test_get_mcp_entry_error_paths(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 61970)
    with _client(app) as c:
        uid = _register_codex(c, tmp_path)

        r = c.get(f"/api/v1/agents/{uid}/mcp-entries/nope")
        assert r.status_code == 404, r.text

        r = c.get(f"/api/v1/agents/{uid}/mcp-entries/coffer")
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "MCP_ENTRY_PROTECTED"

        r = c.get(f"/api/v1/agents/{'0' * 32}/mcp-entries/fetcher")
        assert r.status_code == 404, r.text

        r = TestClient(app).get(f"/api/v1/agents/{uid}/mcp-entries/fetcher")
        assert r.status_code == 401, r.text
