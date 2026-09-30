"""POST /api/v1/agents/mcp-import/{plan,apply} on the full app.

Spec agent-registry "Plan an import of agents' direct MCP entries" and "Apply an
import of agents' direct MCP entries". Two real agents (Codex and Claude Code)
under a temp HOME, their real config files, real SQLite; the keychain is the
in-memory stand-in the neighbouring workspace tests use.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import tomllib

import pytest
from starlette.testclient import TestClient

from coffer.infrastructure.secret.keyring_adapter import KeyringAdapter
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-import"
SECRET = "tok-secret-value-777"
OTHER_SECRET = "other-entry-secret-999"

CODEX_CONFIG = f"""\
[mcp_servers.fetcher]
command = "uvx"
args = ["mcp-fetch"]

[mcp_servers.fetcher.env]
API_TOKEN = "{SECRET}"

[mcp_servers.keep]
command = "keep-cmd"

[mcp_servers.keep.env]
KEEP_TOKEN = "{OTHER_SECRET}"
"""


@pytest.fixture
def keyring_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    store: dict[str, str] = {}
    monkeypatch.setattr(KeyringAdapter, "get", lambda self, ref: store.get(ref))
    monkeypatch.setattr(KeyringAdapter, "set", lambda self, ref, v: store.__setitem__(ref, v))
    monkeypatch.setattr(KeyringAdapter, "delete", lambda self, ref: store.pop(ref, None))
    return store


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text(CODEX_CONFIG, encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "Fetcher": {"command": "uvx", "args": ["mcp-fetch"]},
                    "solo": {"command": "solo-cmd"},
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def client(home: pathlib.Path, keyring_store: dict[str, str]):
    app = create_app()
    set_active_token(TOKEN)
    with TestClient(app, headers={"X-Coffer-Token": TOKEN, "X-Coffer-Actor": "user"}) as c:
        yield c


def _agents(c: TestClient) -> tuple[str, str]:
    cx = c.post("/api/v1/agents", json={"type": "codex"})
    cc = c.post("/api/v1/agents", json={"type": "claude_code"})
    assert cx.status_code == 201, cx.text
    assert cc.status_code == 201, cc.text
    return cx.json()["uid"], cc.json()["uid"]


def _audit_count(home: pathlib.Path) -> int:
    with sqlite3.connect(home / "c.db") as conn:
        return int(conn.execute("SELECT count(*) FROM audit_log").fetchone()[0])


def _resources(c: TestClient) -> list[dict]:
    return c.get("/api/v1/resources", params={"kind": "mcp_server"}).json()["resources"]


def _entries(cx: str, cc: str) -> list[dict]:
    return [
        {"agent_uid": cx, "name": "fetcher", "source": "config"},
        {"agent_uid": cc, "name": "Fetcher", "source": "global"},
    ]


def _files(home: pathlib.Path) -> tuple[bytes, bytes]:
    return (home / ".codex" / "config.toml").read_bytes(), (home / ".claude.json").read_bytes()


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="an import plan merges one server two agents share and writes nothing",
)
def test_an_import_plan_merges_one_server_two_agents_share_and_writes_nothing(
    client: TestClient, home: pathlib.Path, keyring_store: dict[str, str]
) -> None:
    cx, cc = _agents(client)
    sources = {
        e["name"]: e["source"]
        for e in client.get(f"/api/v1/agents/{cc}/mcp-entries").json()["items"]
    }
    files_before = _files(home)
    audits_before = _audit_count(home)

    r = client.post("/api/v1/agents/mcp-import/plan", json={"entries": [
        {"agent_uid": cx, "name": "fetcher", "source": "config"},
        {"agent_uid": cc, "name": "Fetcher", "source": sources["Fetcher"]},
    ]})  # fmt: skip
    assert r.status_code == 200, r.text
    plan = r.json()
    assert len(plan["servers"]) == 1
    server = plan["servers"][0]
    assert (server["op"], server["name"], server["merged"]) == ("add", "fetcher", True)
    assert server["reach_agent_uids"] == [cx, cc]
    assert server["entries"][0]["secret_refs"] == {"API_TOKEN": "mcp/codex/fetcher/API_TOKEN"}
    assert [e["role"] for e in server["entries"]] == ["source", "merged"]

    by_agent = {f["agent_uid"]: f for f in plan["files"]}
    codex_file = by_agent[cx]
    assert codex_file["display_path"] == "~/.codex/config.toml"
    assert codex_file["entries_removed"] == ["fetcher"]
    assert codex_file["removed_lines"] >= 3
    assert codex_file["hunks"][0]["header"].startswith("@@ -")
    shown = [ln["text"] for f in plan["files"] for h in f["hunks"] for ln in h["lines"]]
    assert any("mcp-fetch" in t for t in shown)
    assert SECRET not in r.text
    assert OTHER_SECRET not in r.text
    assert any(c["target"] == "mcp_import" and c["op"] == "add" for c in plan["changes"])
    assert {a["uid"] for a in plan["agents"]} == {cx, cc}

    assert _files(home) == files_before
    assert _resources(client) == []
    assert (
        client.get("/api/v1/secrets/mcp/codex/fetcher/API_TOKEN/exists").json()["present"] is False
    )
    assert _audit_count(home) == audits_before


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="an import plan removes only the duplicate of a server Coffer has",
)
def test_an_import_plan_removes_only_the_duplicate_of_a_server_coffer_has(
    client: TestClient,
) -> None:
    cx, cc = _agents(client)
    created = client.post("/api/v1/resources", json={
        "kind": "mcp_server", "name": "solo",
        "config": {"transport": {"type": "stdio", "command": "solo-cmd"}},
    })  # fmt: skip
    uid = created.json()["uid"]
    client.put(f"/api/v1/resources/{uid}/scope", json={"scope": {"agents": [cx]}})
    plan = client.post(
        "/api/v1/agents/mcp-import/plan",
        json={"entries": [{"agent_uid": cc, "name": "solo", "source": "global"}]},
    ).json()
    (server,) = plan["servers"]
    assert (server["op"], server["resource_uid"], server["reach_agent_uids"]) == (
        "duplicate", uid, [cc],
    )  # fmt: skip
    assert server["entries"][0]["role"] == "duplicate"
    assert len(_resources(client)) == 1


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="applying an import adds, merges and removes duplicates as planned",
)
def test_applying_an_import_adds_merges_and_removes_duplicates_as_planned(
    client: TestClient, home: pathlib.Path, keyring_store: dict[str, str]
) -> None:
    cx, cc = _agents(client)
    created = client.post("/api/v1/resources", json={
        "kind": "mcp_server", "name": "solo",
        "config": {"transport": {"type": "stdio", "command": "solo-cmd"}},
    })  # fmt: skip
    solo_uid = created.json()["uid"]
    client.put(f"/api/v1/resources/{solo_uid}/scope", json={"scope": {"agents": [cx]}})
    entries = [*_entries(cx, cc), {"agent_uid": cc, "name": "solo", "source": "global"}]

    r = client.post("/api/v1/agents/mcp-import/apply", json={"entries": entries})
    assert r.status_code == 200, r.text
    out = r.json()
    outcomes = {(e["agent_uid"], e["name"]): e["outcome"] for e in out["entries"]}
    assert outcomes == {
        (cx, "fetcher"): "added",
        (cc, "Fetcher"): "merged",
        (cc, "solo"): "removed_duplicate",
    }
    (added,) = out["servers_added"]
    assert added["name"] == "fetcher"
    by_name = {r["name"]: r for r in _resources(client)}
    assert by_name["fetcher"]["scope"]["agents"] == [cx, cc]
    assert by_name["fetcher"]["config"]["transport"]["secret_refs"] == {
        "API_TOKEN": "mcp/codex/fetcher/API_TOKEN"
    }
    ref = "mcp/codex/fetcher/API_TOKEN"
    assert client.get(f"/api/v1/secrets/{ref}/exists").json()["present"] is True
    assert sorted(by_name["solo"]["scope"]["agents"]) == sorted([cx, cc])

    codex = tomllib.loads((home / ".codex" / "config.toml").read_text())
    assert set(codex["mcp_servers"]) == {"keep"}
    claude = json.loads((home / ".claude.json").read_text())
    assert claude["mcpServers"] == {}
    events = [
        e["event_type"]
        for e in client.get("/api/v1/audit", params={"limit": 100}).json()["entries"]
    ]
    assert "agent_mcp_entry_adopted" in events
    assert events.count("agent_mcp_entry_removed") >= 2


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="a partial import reports the entry that could not be imported",
)
def test_a_partial_import_reports_the_entry_that_could_not_be_imported(
    client: TestClient, home: pathlib.Path
) -> None:
    cx, cc = _agents(client)
    # The Claude Code entry is gone from its file between the plan and the apply.
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    out = client.post("/api/v1/agents/mcp-import/apply", json={"entries": _entries(cx, cc)}).json()
    outcomes = {(e["agent_uid"], e["name"]): e for e in out["entries"]}
    assert outcomes[(cx, "fetcher")]["outcome"] == "added"
    skipped = outcomes[(cc, "Fetcher")]
    assert skipped["outcome"] == "skipped"
    assert skipped["error_code"] == "MCP_ENTRY_NOT_FOUND"
    (server,) = [r for r in _resources(client) if r["name"] == "fetcher"]
    assert server["scope"]["agents"] == [cx]


def test_a_name_that_cannot_be_registered_fails_that_server_only(client: TestClient) -> None:
    cx, _cc = _agents(client)
    long_name = "x" * 30
    out = client.post(
        "/api/v1/agents/mcp-import/apply",
        json={
            "entries": [
                {"agent_uid": cx, "name": "fetcher", "source": "config", "new_name": long_name}
            ]
        },
    ).json()
    (entry,) = out["entries"]
    assert (entry["outcome"], entry["error_code"]) == ("failed", "NAME_UNUSABLE")
    assert _resources(client) == []


def test_plan_requires_at_least_one_entry(client: TestClient) -> None:
    assert client.post("/api/v1/agents/mcp-import/plan", json={"entries": []}).status_code == 422
