"""The hooks route and the detection fields over the real app (spec
agent-registry "List every hook in the agent's native config", "Detect an
agent by its program and its config directory")."""

from __future__ import annotations

import json
import pathlib

from tests.integration.surfaces.http.test_agent_registry_type_scenarios import (
    _app,
    _audit_count,
    _client,
    _register,
)
from tests.support.facets import put_programs_on_path


def test_the_hooks_route_lists_hooks_and_writes_nothing(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir()
    settings = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "notify.sh"}]}]}}
    (claude / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    app = _app(tmp_path, monkeypatch, 61400)
    with _client(app) as c:
        uid = _register(c, "claude_code", "cc")
        before = _audit_count(c)

        r = c.get(f"/api/v1/agents/{uid}/hooks")

        assert r.status_code == 200, r.text
        body = r.json()
        assert [(h["event"], h["command"], h["source"], h["coffer"]) for h in body["items"]] == [
            ("Stop", "notify.sh", "user", False)
        ]
        assert body["coffer_hook"]["health"] == "missing"
        assert body["coffer_hook"]["event"] == "SessionStart"
        assert body["parse_errors"] == []
        assert _audit_count(c) == before
        assert c.get("/api/v1/agents/nope/hooks").status_code == 404


def test_the_agent_read_model_carries_state_and_version(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    (tmp_path / ".codex").mkdir()
    put_programs_on_path(monkeypatch, tmp_path / "bin", {"codex": "codex-cli 0.155.1"})
    app = _app(tmp_path, monkeypatch, 61410)
    with _client(app) as c:
        uid = _register(c, "codex", "cx")
        agent = c.get(f"/api/v1/agents/{uid}").json()
        assert agent["state"] == "installed_active"
        assert agent["version"]
        listed = c.get("/api/v1/agents").json()["items"]
        assert [a["state"] for a in listed] == ["installed_active"]
