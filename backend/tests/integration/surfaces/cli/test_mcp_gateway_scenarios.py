"""mcp-gateway scenarios over REST and the commands the CLI keeps (`coffer mcp test`,
`coffer log mcp`): daemon-unreachable exit, JSON output, capability toggles by typed
ref, a server shown by its name."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceStore
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.main import app
from tests.integration.surfaces.cli.test_activity_cli_readers import _seed_rows
from tests.integration.surfaces.cli.test_mcp_cmd import (  # noqa: F401  (fixture import)
    STUB,
    _register_server,
    mcp_daemon,
)
from tests.support.vault_stores import derived_sm, make_resource_repo

_runner = CliRunner()


def _client() -> Any:
    client, _info = _cli_client.client_or_exit()
    return client


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="coffer mcp test exits 3 when no daemon is reachable"
)
def test_mcp_test_exits_3_when_no_daemon_is_reachable(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(_cli_client, "_spawn_daemon", lambda: None)
    monkeypatch.setattr(_cli_client, "_DAEMON_BOOT_TIMEOUT", 0.05)

    result = _runner.invoke(app, ["mcp", "test", "fs"])

    assert result.exit_code == 3, result.output
    assert "daemon" in (result.output + (result.stderr or "")).lower()


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="coffer log mcp --json prints a parseable document"
)
def test_log_mcp_json_is_machine_readable(mcp_daemon: Any) -> None:  # noqa: F811
    uid = _register_server()
    _seed_rows([(uid, "read_file", "ok")])

    result = _runner.invoke(app, ["log", "mcp", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload.get("invocations")
    assert "\x1b[" not in result.output


def _seed_pref(uid: str, capability_type: str, key: str) -> None:
    """The preference row discovery would have written, so a toggle has a row to flip."""

    async def _seed() -> None:
        resource = await make_resource_repo().find(uid)
        assert resource is not None
        now = datetime.now(tz=UTC)
        await MCPCapabilityPreferenceStore(derived_sm()).insert(
            resource.uid, capability_type, key, True, now, now
        )

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_seed())
    loop.close()


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="capabilities are toggled by typed ref over REST"
)
def test_capabilities_are_toggled_by_typed_ref(mcp_daemon: Any) -> None:  # noqa: F811
    STUB["discovery"].tools = ["read_file", "write_file"]
    STUB["discovery"].prompts = ["summarize"]
    uid = _register_server()
    for type_, key in (("tool", "read_file"), ("tool", "write_file"), ("prompt", "summarize")):
        _seed_pref(uid, type_, key)
    base = f"/resources/mcp_server/{uid}/capabilities"
    c = _client()

    assert c.post(f"{base}/tool/disable", json={"capability_key": "read_file"}).status_code == 204
    assert c.post(f"{base}/prompt/disable", json={"capability_key": "summarize"}).status_code == 204

    caps = c.get(base).json()
    assert {t["original_name"]: t["enabled"] for t in caps["tools"]} == {
        "read_file": False,
        "write_file": True,
    }
    assert [p["enabled"] for p in caps["prompts"]] == [False]

    refused = c.post(f"{base}/tool/enable", json={"capability_key": "no-such-tool"})
    assert refused.status_code == 404, refused.text
    after = c.get(base).json()
    assert {t["original_name"]: t["enabled"] for t in after["tools"]}["read_file"] is False


@pytest.mark.acceptance(spec="mcp-gateway", scenario="an MCP server is shown by its name")
def test_an_mcp_server_is_shown_by_its_name(mcp_daemon: Any) -> None:  # noqa: F811
    c = _client()
    config = {"transport": {"type": "stdio", "command": "cat", "args": []}}
    r = c.post(
        "/resources",
        json={
            "kind": "mcp_server",
            "name": "fs",
            "description": "Local files",
            "config": config,
        },
    )
    assert r.status_code == 201, r.text
    uid = r.json()["uid"]

    [row] = c.get("/resources", params={"kind": "mcp_server"}).json()["resources"]
    assert (row["name"], row["description"]) == ("fs", "Local files")
    shown = c.get(f"/resources/{uid}").json()
    assert shown["name"] == "fs" and shown["title"] is None

    refused = c.patch(f"/resources/{uid}", json={"title": "Files"})
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "CONFIG_INVALID"
    assert c.get(f"/resources/{uid}").json()["title"] is None
