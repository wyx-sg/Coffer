"""OpenCode on a Coffer connection (spec provider-switching "Project into
OpenCode config without overwriting it"; ADR
opencode-reads-its-proxy-token-from-a-file)."""

from __future__ import annotations

import json
import stat

import pytest

from tests.integration.surfaces.http.test_provider_routes import (
    _activate,
    _agent_dir,
    _app,
    _client,
    _connection_of,
    _new,
    _proxy_state,
    _register_agent,
)


def _openai(name: str = "oa") -> dict:
    return {"name": name, "protocol": "openai", "base_url": "https://gw/v1", "secret_value": "sk-x"}


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario=(
        "switching OpenCode onto a connection writes one provider reading its token from a file"
    ),
)
def test_activate_writes_opencode_config(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59900)
    cfg = _agent_dir(tmp_path)
    (cfg / "opencode.json").write_text(json.dumps({"theme": "tokyonight", "model": "anthropic/x"}))
    with _client(app) as c:
        oc = _register_agent(c, agent_type="opencode", config_dir=cfg)
        uid = _new(c, _openai())
        c.patch(f"/api/v1/agents/{oc}", json={"model": "gpt-x"})
        r = _activate(c, uid, "opencode")
        assert r.status_code == 200, r.text
        assert _connection_of(c, "opencode") == uid
        text = (cfg / "opencode.json").read_text()
        doc = json.loads(text)
        assert doc["theme"] == "tokyonight"
        assert doc["model"] == "coffer/gpt-x"
        block = doc["provider"]["coffer"]
        assert block["npm"] == "@ai-sdk/openai"
        assert block["options"]["baseURL"] == "http://127.0.0.1:38471/openai/v1"
        token_file = tmp_path / ".coffer" / "local" / "proxy-tokens" / "opencode"
        assert block["options"]["apiKey"] == "{file:" + str(token_file) + "}"
        assert "sk-x" not in text and "cfr_" not in text
        # The token file holds the agent's own proxy token, readable by the user only.
        _proxy_state(c)
        token = c.get(f"/api/v1/proxy/tokens/{oc}").json()["token"]
        assert token_file.read_text() == token
        assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
        assert any(r.agent_uid == oc for r in _proxy_state(c).routes)


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="switching OpenCode back to its own providers keeps the user's keys",
)
def test_use_builtin_removes_opencode_projection(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59910)
    cfg = _agent_dir(tmp_path)
    (cfg / "opencode.json").write_text(json.dumps({"theme": "x", "provider": {"mine": {}}}))
    with _client(app) as c:
        oc = _register_agent(c, agent_type="opencode", config_dir=cfg)
        uid = _new(c, _openai())
        c.patch(f"/api/v1/agents/{oc}", json={"model": "gpt-x"})
        assert _activate(c, uid, "opencode").status_code == 200
        r = c.post("/api/v1/providers/use-builtin/opencode")
        assert r.status_code == 200, r.text
        assert _connection_of(c, "opencode") is None
        assert json.loads((cfg / "opencode.json").read_text()) == {
            "theme": "x",
            "provider": {"mine": {}},
        }
