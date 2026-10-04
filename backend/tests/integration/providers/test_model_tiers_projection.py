"""The Model tab's keys, end to end over REST on a fake HOME (spec
provider-switching "Project into Claude Code settings without clobbering
them", "Project into Codex config without overwriting it", "Revert an agent type
to its built-in login", "Record a context window with each
curated model")."""

from __future__ import annotations

import json
import tomllib

import pytest

from tests.integration.surfaces.http.test_provider_routes import (
    _agent_dir,
    _anthropic_body,
    _app,
    _client,
    _new,
    _register_agent,
)


def _openai_body(name: str = "gw", **over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "name": name,
        "protocol": "openai",
        "base_url": "https://gw.example/v1",
        "secret_value": "sk-openai-secret",
    }
    body.update(over)
    return body


@pytest.mark.acceptance(
    spec="provider-switching", scenario="switching back removes every key Coffer wrote"
)
# Back on the built-in login, settings.json carries no tier pin (the page half
# of the scenario is in AgentModelTab.test.tsx).
@pytest.mark.acceptance(spec="provider-switching", scenario="the built-in login shows no tiers")
def test_switching_back_removes_every_key_coffer_wrote(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59841)
    cc_dir = _agent_dir(tmp_path, "cc")
    cx_dir = _agent_dir(tmp_path, "cx")
    (cc_dir / "settings.json").write_text(json.dumps({"theme": "dark"}))
    (cx_dir / "config.toml").write_text('approval_policy = "never"\n')
    with _client(app) as c:
        cc = _register_agent(c, agent_type="claude_code", config_dir=cc_dir)
        cx = _register_agent(c, agent_type="codex", config_dir=cx_dir)
        models = [{"id": "kimi-k3"}, {"id": "kimi-k3-mini"}]
        anthropic = _new(c, _anthropic_body(models=models))
        openai = _new(
            c,
            _openai_body(models=[{"id": "gpt-x", "context_window": 200000}]),
        )
        c.patch(f"/api/v1/agents/{cc}", json={"model": "kimi-k3"})
        c.patch(f"/api/v1/agents/{cx}", json={"model": "gpt-x"})
        assert (
            c.post(
                f"/api/v1/providers/{anthropic}/activate", json={"agent_type": "claude_code"}
            ).status_code
            == 200
        )
        assert (
            c.post(f"/api/v1/providers/{openai}/activate", json={"agent_type": "codex"}).status_code
            == 200
        )

        settings = json.loads((cc_dir / "settings.json").read_text())
        assert settings["model"] == "kimi-k3" and "effortLevel" not in settings
        assert settings["modelPicker"]["replaceBuiltInOptions"] is True
        assert settings["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "kimi-k3"

        assert c.post("/api/v1/providers/use-builtin/claude_code").status_code == 200
        assert c.post("/api/v1/providers/use-builtin/codex").status_code == 200

    after = json.loads((cc_dir / "settings.json").read_text())
    assert after == {"theme": "dark", "env": {}}
    doc = tomllib.loads((cx_dir / "config.toml").read_text())
    assert doc == {"approval_policy": "never"}
    assert not (cx_dir / "coffer-model-catalog.json").exists()


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the Codex catalogue carries each model's window",
)
def test_codex_catalogue_carries_the_window(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59851)
    cx_dir = _agent_dir(tmp_path, "cx")
    with _client(app) as c:
        cx = _register_agent(c, agent_type="codex", config_dir=cx_dir)
        uid = _new(
            c,
            _openai_body(
                models=[
                    {"id": "gpt-x", "context_window": 200000},
                ]
            ),
        )
        c.patch(f"/api/v1/agents/{cx}", json={"model": "gpt-x"})
        assert (
            c.post(f"/api/v1/providers/{uid}/activate", json={"agent_type": "codex"}).status_code
            == 200
        )

    entry = json.loads((cx_dir / "coffer-model-catalog.json").read_text())["models"][0]
    assert entry["context_window"] == entry["max_context_window"] == 200000
    assert entry["auto_compact_token_limit"] == 180000
    # Codex's parser requires the field; Coffer records no levels.
    assert entry["supported_reasoning_levels"] == []
    assert "default_reasoning_level" not in entry
    assert "model_reasoning_effort" not in tomllib.loads((cx_dir / "config.toml").read_text())


@pytest.mark.acceptance(spec="provider-switching", scenario="a curated model keeps its window")
def test_a_curated_model_keeps_its_window(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59861)
    with _client(app) as c:
        uid = _new(c, _openai_body(models=[{"id": "gpt-x"}]))
        r = c.patch(
            f"/api/v1/providers/{uid}",
            json={
                "models": [
                    {"id": "gpt-x", "context_window": 200000},
                ]
            },
        )
        assert r.status_code == 200, r.text
        (model,) = c.get(f"/api/v1/providers/{uid}").json()["models"]
    assert model["context_window"] == 200000
    assert "effort_levels" not in model
