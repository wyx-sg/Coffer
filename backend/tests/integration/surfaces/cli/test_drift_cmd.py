"""The reconciler's read models over the real app: ``GET /reconcile/plan``,
``POST /reconcile/apply`` and ``GET /attention``, and ``coffer drift`` /
``coffer attention`` on the same routes.

The daemon is the real ``create_app`` (``_real_app.boot``): an agent is
registered and connected through the routes, drift is then planted in the
agent's own files the way an upgrade or another tool leaves it, and the plan,
the apply and the CLI are read against what is on disk.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.domain.agent.types import AgentType
from coffer.surfaces.cli.main import app as cli
from tests.support.homes import IsolatedHome, fake_agent_dir, make_home
from tests.support.reconcile import quiet_background_repair

from ._real_app import audit, boot, extract_json

runner = CliRunner()


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    home = make_home(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "coffer-mcp-shim"
    shim.write_text("#!/bin/sh\n", encoding="utf-8")
    shim.chmod(0o755)
    monkeypatch.setenv("COFFER_MCP_SHIM_PATH", str(shim))
    claude = fake_agent_dir(home, AgentType.CLAUDE_CODE)
    for client in boot(tmp_path, monkeypatch):
        r = client.post("/agents", json={"type": "claude_code"})
        assert r.status_code == 201, r.text
        uid = r.json()["uid"]
        r = client.post(f"/agents/{uid}/coffer-connection")
        assert r.status_code == 200, r.text
        # These tests plant drift for the drift command to find; the pass the
        # writes above hinted must not repair it first.
        quiet_background_repair(monkeypatch)
        yield {"client": client, "uid": uid, "home": home, "claude": claude, "shim": shim}


def _tree(home: IsolatedHome, skills_root: pathlib.Path) -> dict[str, tuple[int, str, int]]:
    """Every file any reconcile target writes: the agents' own trees and the
    skill links' master store."""
    roots = [home.root / ".claude", home.root / ".codex", skills_root]
    files = [home.root / ".claude.json"]
    for root in roots:
        if root.exists():
            files.extend(p for p in root.rglob("*") if p.is_file() or p.is_symlink())
    out: dict[str, tuple[int, str, int]] = {}
    for p in files:
        if not p.exists():
            continue
        st = p.lstat()
        body = p.read_bytes() if p.is_file() else str(p.readlink()).encode()
        out[str(p)] = (st.st_size, hashlib.sha256(body).hexdigest(), st.st_mtime_ns)
    return out


def _plant_stale_entry(home: IsolatedHome, uid: str) -> pathlib.Path:
    path = home.root / ".claude.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["mcpServers"]["coffer"] = {"command": "/old/coffer-mcp-shim", "args": ["--agent-uid", uid]}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _mcp_item(plan: dict[str, Any], uid: str) -> dict[str, Any]:
    (item,) = [i for i in plan["items"] if i["id"] == f"mcp_entry:{uid}"]
    return item


@pytest.mark.acceptance(
    spec="resource-framework", scenario="list drift with its file and before and after text"
)
@pytest.mark.acceptance(
    spec="resource-framework", scenario="a dry-run pass writes nothing under the home directory"
)
def test_the_plan_lists_drift_and_writes_nothing(
    daemon: dict[str, Any], tmp_path: pathlib.Path
) -> None:
    client: TestClient = daemon["client"]
    uid, home = daemon["uid"], daemon["home"]
    path = _plant_stale_entry(home, uid)
    audit_before = len(client.get("/audit", params={"limit": 500}).json()["entries"])
    rev_before = client.get(f"/agents/{uid}").json()
    tree_before = _tree(home, home.coffer_dir / "vault" / "skills")

    r = client.get("/reconcile/plan")
    assert r.status_code == 200, r.text
    plan = r.json()
    item = _mcp_item(plan, uid)
    assert (item["op"], item["disposition"], item["outcome"]) == ("modify", "repair", "planned")
    assert item["reason_code"] == "stale_entry"
    assert item["file"] == str(path)
    assert "command" in item["changed_params"]
    assert "/old/coffer-mcp-shim" in item["before"]
    assert str(daemon["shim"].resolve()) in item["after"]
    assert item["subject"] == {"kind": "agent", "uid": uid, "title": "Claude Code"}
    assert {t["name"] for t in plan["targets"]} >= {
        "mcp_entry",
        "skill_link",
        "provider_projection",
        "delivery_hook",
    }
    assert all(t["error"] is None for t in plan["targets"])

    # The CLI reads the same plan.
    out = runner.invoke(cli, ["drift", "list", "--json"])
    assert out.exit_code == 0, out.output
    assert _mcp_item(extract_json(out.output), uid)["op"] == "modify"

    # Nothing was written by either read.
    assert _tree(home, home.coffer_dir / "vault" / "skills") == tree_before
    assert len(client.get("/audit", params={"limit": 500}).json()["entries"]) == audit_before
    assert client.get(f"/agents/{uid}").json() == rev_before


def test_the_plan_filters_by_target_and_resource(daemon: dict[str, Any]) -> None:
    client: TestClient = daemon["client"]
    uid = daemon["uid"]
    _plant_stale_entry(daemon["home"], uid)
    only = client.get("/reconcile/plan", params={"target": "mcp_entry"}).json()
    assert [t["name"] for t in only["targets"]] == ["mcp_entry"]
    assert {i["target"] for i in only["items"]} == {"mcp_entry"}
    mine = client.get("/reconcile/plan", params={"kind": "agent", "uid": uid}).json()
    assert mine["items"] and all(i["subject"]["uid"] == uid for i in mine["items"])
    none = client.get("/reconcile/plan", params={"uid": "nobody"}).json()
    assert none["items"] == []
    r = client.get("/reconcile/plan", params={"target": "nope"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.acceptance(spec="resource-framework", scenario="apply one drift item as the caller")
def test_applying_an_item_repairs_it_as_the_caller(daemon: dict[str, Any]) -> None:
    client: TestClient = daemon["client"]
    uid, home = daemon["uid"], daemon["home"]
    path = _plant_stale_entry(home, uid)
    r = client.post(
        "/reconcile/apply",
        json={"ids": [f"mcp_entry:{uid}", "mcp_entry:nobody"]},
        headers={"X-Coffer-Actor": "user"},
    )
    assert r.status_code == 200, r.text
    (item,) = r.json()["items"]
    assert item["outcome"] == "applied"
    entry = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["coffer"]
    assert entry == {"command": str(daemon["shim"].resolve()), "args": ["--agent-uid", uid]}
    installs = audit(client, "agent_mcp_installed")
    assert installs[0]["actor"] == "user"
    assert installs[0]["details"]["reconcile"] == "manual"
    assert not [
        i for i in client.get("/reconcile/plan").json()["items"] if i["target"] == "mcp_entry"
    ]
    # An empty body is refused.
    assert client.post("/reconcile/apply", json={"ids": []}).status_code == 422


def test_drift_repair_on_the_command_line(daemon: dict[str, Any]) -> None:
    uid, home = daemon["uid"], daemon["home"]
    path = _plant_stale_entry(home, uid)
    out = runner.invoke(cli, ["drift", "repair", f"mcp_entry:{uid}", "--json"])
    assert out.exit_code == 0, out.output
    assert extract_json(out.output)["items"][0]["outcome"] == "applied"
    assert json.loads(path.read_text(encoding="utf-8"))["mcpServers"]["coffer"]["command"] == str(
        daemon["shim"].resolve()
    )
    # Nothing left: --all repairs nothing and says so.
    out = runner.invoke(cli, ["drift", "repair", "--all"])
    assert out.exit_code == 0, out.output
    out = runner.invoke(cli, ["drift", "repair"])
    assert out.exit_code == 2
    out = runner.invoke(cli, ["drift", "list"])
    assert out.exit_code == 0 and "mcp_entry" not in out.output


def test_the_attention_list_and_its_command(daemon: dict[str, Any]) -> None:
    client: TestClient = daemon["client"]
    r = client.get("/attention")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"items", "errors", "counts_by_kind", "ignored"}
    assert body["errors"] == []
    assert sum(body["counts_by_kind"].values()) == len(body["items"])
    for item in body["items"]:
        assert item["severity"] in {"error", "warning", "info"}
        assert item["action"]["path"].startswith("/api/v1/")
    out = runner.invoke(cli, ["attention", "--json"])
    assert out.exit_code == 0, out.output
    assert extract_json(out.output)["counts_by_kind"] == body["counts_by_kind"]
