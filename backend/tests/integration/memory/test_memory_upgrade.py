"""The upgrade step that retires the old memory layer, through the real daemon
(spec memory "Remove the memory delivery hook on upgrade").

A first boot registers the agents; their settings then get the two entries an
older build installed, beside one of the person's own hooks, and ``derived/``
gets the retired tree. The next boot is the upgrade.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-memory-upgrade"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}
_CLI = "/Users/me/.coffer/bin/coffer"


def _old_entry(uid: str, matcher: str | None, timeout: int) -> dict[str, object]:
    command = f': coffer-memory; {_CLI} memory hook --agent-uid {uid} --cwd "$PWD"'
    leaf = {"type": "command", "command": command, "timeout": timeout}
    return {"matcher": matcher, "hooks": [leaf]} if matcher else {"hooks": [leaf]}


def _with_old_hook(uid: str, own: dict[str, object]) -> dict[str, object]:
    return {
        "env": {"A": "1"},
        "hooks": {
            "SessionStart": [_old_entry(uid, "startup|resume|clear|compact", 10)],
            "UserPromptSubmit": [_old_entry(uid, None, 5)],
            "Stop": [own],
        },
    }


def _removals(c: TestClient, uid: str) -> list[dict[str, object]]:
    params = {"event_type": "memory_hook_removed", "resource_uid": uid, "limit": 50}
    return c.get("/api/v1/audit", params=params).json()["entries"]  # type: ignore[no-any-return]


def _client() -> TestClient:
    app = create_app()
    set_active_token(_TOKEN)
    return TestClient(app, base_url="http://localhost", headers=_HEADERS)


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59350")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59359")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".codex").mkdir()
    return tmp_path


@pytest.mark.acceptance(spec="memory", scenario="an upgrade removes the old hook and derived tree")
def test_an_upgrade_removes_the_old_hook_and_derived_tree(home: pathlib.Path) -> None:
    with _client() as c:
        uids = {
            t: c.post("/api/v1/agents", json={"type": t}).json()["uid"]
            for t in ("claude_code", "codex")
        }
    own = {"hooks": [{"type": "command", "command": "echo mine"}]}
    files = {
        "claude_code": home / ".claude" / "settings.json",
        "codex": home / ".codex" / "hooks.json",
    }
    for agent_type, path in files.items():
        path.write_text(json.dumps(_with_old_hook(uids[agent_type], own)), encoding="utf-8")
    derived = home / ".coffer" / "derived"
    (derived / "memory" / "global" / "notes").mkdir(parents=True)
    (derived / "memory" / "global" / "MEMORY.md").write_text("# old\n", encoding="utf-8")
    (derived / "resources" / "memory").mkdir(parents=True)
    (derived / "resources" / "memory" / "global.json").write_text("{}", encoding="utf-8")

    with _client() as c:
        events = {t: _removals(c, uid) for t, uid in uids.items()}

    for path in files.values():
        doc = json.loads(path.read_text(encoding="utf-8"))
        # Both of Coffer's entries are gone; the person's hook and settings stay.
        assert doc == {"env": {"A": "1"}, "hooks": {"Stop": [own]}}
    assert not (derived / "memory").exists()
    assert not (derived / "resources" / "memory").exists()
    # One event per agent changed, recorded by the upgrade itself.
    assert {t: [e["actor"] for e in rows] for t, rows in events.items()} == {
        "claude_code": ["system:upgrade"],
        "codex": ["system:upgrade"],
    }

    # Done once: the next start finds nothing to remove and records nothing.
    with _client() as c:
        assert {t: len(_removals(c, uid)) for t, uid in uids.items()} == {
            "claude_code": 1,
            "codex": 1,
        }
