"""The hooks route and the detection fields over the real app (spec
agent-registry "List every hook in the agent's native config", "Detect an
agent by its program and its config directory")."""

from __future__ import annotations

import json
import pathlib

import pytest

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
    settings = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {"command": "x.sh"},
                        {"type": "command", "command": "notify.sh", "timeout": 7},
                    ]
                }
            ]
        }
    }
    (claude / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    app = _app(tmp_path, monkeypatch, 61400)
    with _client(app) as c:
        uid = _register(c, "claude_code", "cc")
        before = _audit_count(c)

        r = c.get(f"/api/v1/agents/{uid}/hooks")

        assert r.status_code == 200, r.text
        body = r.json()
        assert [(h["event"], h["command"], h["source"]) for h in body["items"]] == [
            ("Stop", "x.sh", "user"),
            ("Stop", "notify.sh", "user"),
        ]
        # Timeout and the position `hooks.Stop[0].hooks[1]` come with each hook.
        second = body["items"][1]
        assert (second["timeout"], second["group_index"], second["hook_index"]) == (7, 0, 1)
        assert "coffer_hook" not in body and "coffer" not in body["items"][0]
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


@pytest.mark.acceptance(
    spec="agent-registry/cursor", scenario="Cursor's hooks are listed from its hooks.json"
)
def test_cursor_hooks_are_listed_from_its_hooks_json(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cursor = tmp_path / ".cursor"
    cursor.mkdir()
    hooks = {
        "version": 1,
        "hooks": {
            "beforeShellExecution": [
                {"command": "./scripts/approve-network.sh", "timeout": 30, "matcher": "curl|wget"}
            ],
            "beforeSubmitPrompt": [
                {"type": "prompt", "prompt": "Is this safe?", "timeout": 10},
                {"command": "./audit.sh"},
            ],
        },
    }
    (cursor / "hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
    app = _app(tmp_path, monkeypatch, 61420)
    with _client(app) as c:
        uid = _register(c, "cursor", "cu")
        types = {t["type"]: t for t in c.get("/api/v1/agents/types").json()["types"]}
        assert "hooks" in types["cursor"]["features"]

        r = c.get(f"/api/v1/agents/{uid}/hooks")

        assert r.status_code == 200, r.text
        rows = [
            (h["event"], h["matcher"], h["command"], h["type"], h["timeout"], h["group_index"])
            for h in r.json()["items"]
        ]
        assert rows == [
            ("beforeShellExecution", "curl|wget", "./scripts/approve-network.sh", "command", 30, 0),
            ("beforeSubmitPrompt", None, "Is this safe?", "prompt", 10, 0),
            ("beforeSubmitPrompt", None, "./audit.sh", "command", None, 1),
        ]
        assert r.json()["parse_errors"] == []
