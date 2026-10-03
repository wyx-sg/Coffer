"""Review-then-apply of one agent's model change, over REST on a fake HOME
(spec provider-switching "Review a model change before writing it").

The preview names every file the switch changes (Codex: ``config.toml`` AND
Coffer's own model catalogue) without writing; the apply refuses when a
previewed file was edited since."""

from __future__ import annotations

import json
import tomllib

import pytest

from coffer.domain.agent.tiers import tier_env_key
from tests.integration.providers.test_model_tiers_projection import _openai_body
from tests.integration.surfaces.http.test_provider_routes import (
    _agent_dir,
    _anthropic_body,
    _app,
    _client,
    _new,
    _register_agent,
)

PREVIEW = "/api/v1/providers/model-switch/preview"
APPLY = "/api/v1/providers/model-switch/apply"


@pytest.mark.acceptance(spec="provider-switching", scenario="a Codex change previews two files")
def test_codex_preview_lists_both_files_and_writes_nothing(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59901)
    cx_dir = _agent_dir(tmp_path, "cx")
    (cx_dir / "config.toml").write_text('approval_policy = "never"\n')
    with _client(app) as c:
        _register_agent(c, agent_type="codex", config_dir=cx_dir)
        openai = _new(
            c,
            _openai_body(models=[{"id": "gpt-x", "effort_levels": ["low", "high"]}]),
        )
        body = {
            "agent_type": "codex",
            "connection_uid": openai,
            "model": "gpt-x",
            "effort": "high",
        }
        out = c.post(PREVIEW, json=body)
        assert out.status_code == 200, out.text
        files = {f["path"].rsplit("/", 1)[-1]: f for f in out.json()["files"]}
        assert files["config.toml"]["op"] == "modify"
        assert files["coffer-model-catalog.json"]["op"] == "add"
        assert files["config.toml"]["added"] > 0
        assert any(
            r["kind"] == "add" and 'model = "gpt-x"' in r["text"]
            for r in files["config.toml"]["diff"]
        )
        # Nothing was written.
        assert (cx_dir / "config.toml").read_text() == 'approval_policy = "never"\n'
        assert not (cx_dir / "coffer-model-catalog.json").exists()

        seen = {f["path"]: f["fingerprint"] for f in out.json()["files"]}
        applied = c.post(APPLY, json=body | {"seen": seen})
        assert applied.status_code == 200, applied.text
    doc = tomllib.loads((cx_dir / "config.toml").read_text())
    assert doc["model"] == "gpt-x" and doc["model_reasoning_effort"] == "high"
    assert (cx_dir / "coffer-model-catalog.json").exists()


@pytest.mark.acceptance(
    spec="provider-switching", scenario="applying refuses a file that changed after the preview"
)
def test_apply_is_refused_when_a_previewed_file_changed(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59911)
    cc_dir = _agent_dir(tmp_path, "cc")
    (cc_dir / "settings.json").write_text(json.dumps({"theme": "dark"}))
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", config_dir=cc_dir)
        anthropic = _new(c, _anthropic_body(models=[{"id": "kimi-k3"}]))
        body = {"agent_type": "claude_code", "connection_uid": anthropic, "model": "kimi-k3"}
        out = c.post(PREVIEW, json=body).json()
        seen = {f["path"]: f["fingerprint"] for f in out["files"]}
        # The user saves the file after the preview was made.
        (cc_dir / "settings.json").write_text(json.dumps({"theme": "light"}))
        refused = c.post(APPLY, json=body | {"seen": seen})
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "CONFIG_FILE_STALE"
        assert json.loads((cc_dir / "settings.json").read_text()) == {"theme": "light"}
        # Previewed again, it goes through and keeps the user's edit.
        fresh = c.post(PREVIEW, json=body).json()
        seen = {f["path"]: f["fingerprint"] for f in fresh["files"]}
        assert c.post(APPLY, json=body | {"seen": seen}).status_code == 200
    settings = json.loads((cc_dir / "settings.json").read_text())
    assert settings["theme"] == "light" and settings["model"] == "kimi-k3"


def test_builtin_preview_removes_only_what_coffer_wrote(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59921)
    cc_dir = _agent_dir(tmp_path, "cc")
    (cc_dir / "settings.json").write_text(json.dumps({"theme": "dark"}))
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", config_dir=cc_dir)
        anthropic = _new(c, _anthropic_body(models=[{"id": "kimi-k3"}]))
        on = {"agent_type": "claude_code", "connection_uid": anthropic, "model": "kimi-k3"}
        seen = {f["path"]: f["fingerprint"] for f in c.post(PREVIEW, json=on).json()["files"]}
        assert c.post(APPLY, json=on | {"seen": seen}).status_code == 200

        off = {"agent_type": "claude_code", "connection_uid": None}
        out = c.post(PREVIEW, json=off).json()
        assert out["connection_name"] is None
        (settings,) = out["files"]
        assert settings["op"] == "modify" and settings["removed"] > 0
        assert not any(r["kind"] == "add" and "theme" in r["text"] for r in settings["diff"])
        seen = {f["path"]: f["fingerprint"] for f in out["files"]}
        assert c.post(APPLY, json=off | {"seen": seen}).status_code == 200
    assert json.loads((cc_dir / "settings.json").read_text()) == {"theme": "dark", "env": {}}


@pytest.mark.parametrize("connection", ["missing"])
def test_preview_of_an_unknown_connection_is_404(tmp_path, monkeypatch, connection):
    app = _app(tmp_path, monkeypatch, 59931)
    cc_dir = _agent_dir(tmp_path, "cc")
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", config_dir=cc_dir)
        out = c.post(
            PREVIEW,
            json={"agent_type": "claude_code", "connection_uid": "0" * 32, "model": "m"},
        )
        assert out.status_code == 404


_TIERS = {"opus": "kimi-k3", "sonnet": "kimi-k3", "haiku": "my-own-haiku", "fable": "kimi-k3"}


@pytest.mark.acceptance(
    spec="provider-switching", scenario="previewing a model change writes nothing"
)
def test_a_claude_code_preview_writes_nothing_and_refuses_an_unreached_connection(
    tmp_path, monkeypatch
):
    app = _app(tmp_path, monkeypatch, 59941)
    cc_dir = _agent_dir(tmp_path, "cc")
    original = json.dumps({"theme": "dark"})
    (cc_dir / "settings.json").write_text(original)
    with _client(app) as c:
        uid = _register_agent(c, agent_type="claude_code", config_dir=cc_dir)
        anthropic = _new(c, _anthropic_body(models=[{"id": "kimi-k3"}]))
        body = {
            "agent_type": "claude_code",
            "connection_uid": anthropic,
            "model": "kimi-k3",
            "effort": "high",
            "tier_models": _TIERS,
        }
        agent_before = c.get(f"/api/v1/agents/{uid}").json()
        listing = sorted(p.name for p in cc_dir.iterdir())
        out = c.post(PREVIEW, json=body)
        assert out.status_code == 200, out.text
        (settings,) = out.json()["files"]
        assert settings["path"].endswith("settings.json") and settings["fingerprint"]
        added = "\n".join(r["text"] for r in settings["diff"] if r["kind"] == "add")
        assert "kimi-k3" in added and tier_env_key("haiku") in added

        # Nothing moved: the file, any .bak, and the agent's record.
        assert (cc_dir / "settings.json").read_text() == original
        assert sorted(p.name for p in cc_dir.iterdir()) == listing
        assert c.get(f"/api/v1/agents/{uid}").json() == agent_before

        # A connection scoped away from the agent is refused with 409.
        other = _register_agent(c, agent_type="codex", config_dir=_agent_dir(tmp_path, "cx"))
        scoped = c.put(f"/api/v1/resources/{anthropic}/scope", json={"scope": {"agents": [other]}})
        assert scoped.status_code == 200, scoped.text
        assert c.post(PREVIEW, json=body).status_code == 409


@pytest.mark.acceptance(
    spec="provider-switching", scenario="an edited tier is written as the user chose it"
)
def test_an_edited_tier_is_previewed_and_recorded_as_chosen(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59951)
    cc_dir = _agent_dir(tmp_path, "cc")
    (cc_dir / "settings.json").write_text(json.dumps({"theme": "dark"}))
    with _client(app) as c:
        uid = _register_agent(c, agent_type="claude_code", config_dir=cc_dir)
        anthropic = _new(c, _anthropic_body(models=[{"id": "kimi-k3"}]))
        body = {
            "agent_type": "claude_code",
            "connection_uid": anthropic,
            "model": "kimi-k3",
            "tier_models": _TIERS,
        }
        out = c.post(PREVIEW, json=body).json()
        (settings,) = out["files"]
        added = "\n".join(r["text"] for r in settings["diff"] if r["kind"] == "add")
        assert f'"{tier_env_key("haiku")}": "my-own-haiku"' in added
        assert f'"{tier_env_key("opus")}": "kimi-k3"' in added
        seen = {f["path"]: f["fingerprint"] for f in out["files"]}
        assert c.post(APPLY, json=body | {"seen": seen}).status_code == 200
        assert c.get(f"/api/v1/agents/{uid}").json()["tier_models"] == _TIERS
    env = json.loads((cc_dir / "settings.json").read_text())["env"]
    assert env[tier_env_key("haiku")] == "my-own-haiku"
