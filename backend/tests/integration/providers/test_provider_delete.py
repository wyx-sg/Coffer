"""Deleting a connection that agents run on, end to end over HTTP (spec provider-switching).

A delete first puts each agent on the connection back on its built-in login —
Coffer's keys leave its native config file and its record forgets the
connection — and ``GET /providers/{uid}/delete-preview`` shows exactly that
beforehand without writing anything.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from coffer.domain.provider.projection import CODEX_MODEL_CATALOG_FILENAME
from tests.integration.providers.test_provider_requirements import (
    _anthropic,
    _daemon,
    _new,
    _register_agent,
    env,  # noqa: F401  (fixture)
)

_USER_CODEX = """\
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[mcp_servers.docs]
command = "npx"
args = ["-y", "docs-server"]
"""


def _codex_with_coffer(catalog: pathlib.Path) -> str:
    """A realistic Codex config.toml: the user's own settings plus Coffer's projection."""
    return (
        'model = "gpt-5"\n'
        'model_provider = "coffer"\n'
        'model_reasoning_effort = "high"\n'
        f'model_catalog_json = "{catalog}"\n' + _USER_CODEX + "\n"
        "[model_providers.coffer]\n"
        'name = "Coffer (acme)"\n'
        'base_url = "http://127.0.0.1:8000/proxy/v1"\n'
        'wire_api = "responses"\n'
        "supports_websockets = false\n"
        "requires_openai_auth = false\n"
        'auth = { command = "coffer", args = ["x"] }\n'
    )


def test_preview_lists_exactly_the_coffer_lines_and_writes_nothing(env: pathlib.Path) -> None:  # noqa: F811
    cx = env / "codex"
    with _daemon() as c:
        _register_agent(c, "codex", "cx", cx)
        uid = _new(
            c,
            {
                "name": "acme",
                "protocol": "openai",
                "base_url": "https://gw/v1",
                "secret_value": "sk-x",
            },
        )
        assert (
            c.post(f"/api/v1/providers/{uid}/activate", json={"agent_type": "codex"}).status_code
            == 200
        )
        catalog = cx / CODEX_MODEL_CATALOG_FILENAME
        catalog.write_text("{}\n", encoding="utf-8")
        cfg = cx / "config.toml"
        cfg.write_text(_codex_with_coffer(catalog), encoding="utf-8")

        r = c.get(f"/api/v1/providers/{uid}/delete-preview")
        assert r.status_code == 200, r.text
        [agent] = r.json()["agents"]
        assert agent["agent_type"] == "codex"
        files = {f["path"]: f for f in agent["files"]}
        main = files[str(cfg)]
        assert main["op"] == "modify"
        removed = [row["text"] for row in main["diff"] if row["kind"] == "remove"]
        assert removed == [
            'model = "gpt-5"',
            'model_provider = "coffer"',
            f'model_catalog_json = "{catalog}"',
            "[model_providers.coffer]",
            'name = "Coffer (acme)"',
            'base_url = "http://127.0.0.1:8000/proxy/v1"',
            'wire_api = "responses"',
            "supports_websockets = false",
            "requires_openai_auth = false",
            'auth = { command = "coffer", args = ["x"] }',
        ]
        assert not [row for row in main["diff"] if row["kind"] == "add"]
        assert 'approval_policy = "on-request"' not in removed
        assert "[mcp_servers.docs]" not in removed
        assert files[str(catalog)]["op"] == "remove"
        # Read-only: nothing on disk or in the registry moved.
        assert cfg.read_text(encoding="utf-8") == _codex_with_coffer(catalog)
        assert catalog.exists()
        assert c.get("/api/v1/agents/codex").json()["connection_uid"] == uid


@pytest.mark.acceptance(spec="provider-switching", scenario="the delete preview writes nothing")
def test_preview_for_two_agents_lists_each_and_changes_nothing(env: pathlib.Path) -> None:  # noqa: F811
    cx, cc = env / "codex", env / "cc"
    with _daemon() as c:
        _register_agent(c, "codex", "cx", cx)
        _register_agent(c, "claude_code", "cc", cc)
        uid = _new(c, _anthropic("acme"))
        for agent_type in ("codex", "claude_code"):
            r = c.post(f"/api/v1/providers/{uid}/activate", json={"agent_type": agent_type})
            assert r.status_code == 200, r.text
        files = [p for p in (cx / "config.toml", cc / "settings.json") if p.exists()]
        before = {p: p.read_bytes() for p in files}
        listing = sorted(p.name for d in (cx, cc) for p in d.iterdir())
        agents_before = [c.get(f"/api/v1/agents/{n}").json() for n in ("codex", "claude_code")]

        r = c.get(f"/api/v1/providers/{uid}/delete-preview")
        assert r.status_code == 200, r.text
        agents = r.json()["agents"]
        assert sorted(a["agent_type"] for a in agents) == ["claude_code", "codex"]
        assert all(a["files"] and any(f["diff"] for f in a["files"]) for a in agents)

        assert {p: p.read_bytes() for p in files} == before
        assert sorted(p.name for d in (cx, cc) for p in d.iterdir()) == listing
        assert [c.get(f"/api/v1/agents/{n}").json() for n in ("codex", "claude_code")] == (
            agents_before
        )
        assert c.get(f"/api/v1/providers/{uid}").status_code == 200


def test_preview_of_claude_code_settings_and_unknown_uid(env: pathlib.Path) -> None:  # noqa: F811
    cc = env / "cc"
    with _daemon() as c:
        _register_agent(c, "claude_code", "cc", cc)
        uid = _new(c, _anthropic("acme"))
        assert c.get(f"/api/v1/providers/{'0' * 32}/delete-preview").status_code == 404
        # Unused connection: nothing to review.
        assert c.get(f"/api/v1/providers/{uid}/delete-preview").json() == {"agents": []}
        c.post(f"/api/v1/providers/{uid}/activate", json={"agent_type": "claude_code"})
        settings = cc / "settings.json"
        before = settings.read_text(encoding="utf-8")
        assert "ANTHROPIC_BASE_URL" in before

        [agent] = c.get(f"/api/v1/providers/{uid}/delete-preview").json()["agents"]
        [f] = agent["files"]
        assert f["path"] == str(settings) and f["op"] == "modify"
        removed = "\n".join(r["text"] for r in f["diff"] if r["kind"] == "remove")
        assert "ANTHROPIC_BASE_URL" in removed
        assert settings.read_text(encoding="utf-8") == before


def test_delete_deprojects_the_agent_and_clears_its_connection(env: pathlib.Path) -> None:  # noqa: F811
    cc = env / "cc"
    with _daemon() as c:
        _register_agent(c, "claude_code", "cc", cc)
        uid = _new(c, _anthropic("acme"))
        c.post(f"/api/v1/providers/{uid}/activate", json={"agent_type": "claude_code"})
        settings = cc / "settings.json"
        assert "ANTHROPIC_BASE_URL" in settings.read_text(encoding="utf-8")

        assert c.delete(f"/api/v1/providers/{uid}").status_code == 204
        assert c.get(f"/api/v1/providers/{uid}").status_code == 404
        assert c.get("/api/v1/agents/claude_code").json()["connection_uid"] is None
        text = settings.read_text(encoding="utf-8")
        assert "ANTHROPIC_BASE_URL" not in text and "apiKeyHelper" not in text


def test_delete_of_an_unused_connection_touches_no_agent_file(env: pathlib.Path) -> None:  # noqa: F811
    cc = env / "cc"
    with _daemon() as c:
        _register_agent(c, "claude_code", "cc", cc)
        mine = _new(c, _anthropic("mine"))
        other = _new(c, _anthropic("other", secret="sk-other"))
        c.post(f"/api/v1/providers/{mine}/activate", json={"agent_type": "claude_code"})
        settings = cc / "settings.json"
        before = settings.read_text(encoding="utf-8")
        mtime = settings.stat().st_mtime_ns

        assert c.delete(f"/api/v1/providers/{other}").status_code == 204
        assert settings.read_text(encoding="utf-8") == before
        assert settings.stat().st_mtime_ns == mtime
        assert c.get("/api/v1/agents/claude_code").json()["connection_uid"] == mine


def test_a_refused_deprojection_keeps_the_connection(
    env: pathlib.Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coffer.domain.workspace_errors import ConfigFileStale
    from coffer.infrastructure.agent.config_file_store import ConfigFileStore

    cc = env / "cc"
    with _daemon() as c:
        _register_agent(c, "claude_code", "cc", cc)
        uid = _new(c, _anthropic("acme"))
        c.post(f"/api/v1/providers/{uid}/activate", json={"agent_type": "claude_code"})

        def _stale(self: ConfigFileStore, *a: object, **k: object) -> None:
            raise ConfigFileStale("x")

        monkeypatch.setattr(ConfigFileStore, "write_text_atomic", _stale)
        r = c.delete(f"/api/v1/providers/{uid}")
        assert r.status_code == 409, r.text
        assert c.get(f"/api/v1/providers/{uid}").status_code == 200
        assert c.get("/api/v1/agents/claude_code").json()["connection_uid"] == uid
        assert json.loads((cc / "settings.json").read_text(encoding="utf-8"))
