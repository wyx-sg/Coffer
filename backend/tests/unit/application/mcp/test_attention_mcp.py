"""McpAttentionSource: what about an enabled MCP server needs a person."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from coffer.application.attention import AttentionAction, Severity
from coffer.application.mcp.attention import McpAttentionSource
from coffer.application.mcp.runner_detect import missing_runner_of
from tests.unit.application._attention_fakes import T0, FakeResources, resource

STDIO = {"transport": {"type": "stdio", "command": "uvx"}}


class FakeHealth:
    def __init__(self, rows: dict[str, tuple[str, datetime]] | None = None) -> None:
        self.rows = rows or {}

    async def get(self, resource_uid: str) -> tuple[str, datetime] | None:
        return self.rows.get(resource_uid)


class FakeStore:
    def __init__(self, held: set[str]) -> None:
        self.held = held

    def exists(self, ref: str) -> bool:
        return ref in self.held


def _source(
    resources: FakeResources,
    *,
    health: FakeHealth | None = None,
    held: set[str] | None = None,
    missing: dict[str, str] | None = None,
) -> McpAttentionSource:
    def runner(config: dict[str, Any]) -> str | None:
        return (missing or {}).get(config["transport"].get("command", ""))

    return McpAttentionSource(
        resources=resources,
        health=health or FakeHealth(),
        secrets=FakeStore(held or set()),
        runner_missing=runner,
    )


async def test_failing_health_row_is_an_error_with_the_test_action_and_its_time() -> None:
    # A server carries no title: the item is labelled by its fixed name.
    srv = resource("u1", "mcp_server", STDIO, name="atlassian")
    items = await _source(FakeResources([srv]), health=FakeHealth({"u1": ("failing", T0)})).items()
    assert len(items) == 1
    item = items[0]
    assert (item.kind, item.uid, item.title) == ("mcp_server", "u1", "atlassian")
    assert item.reason_code == "mcp_failing"
    assert item.severity is Severity.ERROR
    assert item.since == T0
    assert item.action == AttentionAction(
        verb="test", method="POST", path="/api/v1/resources/mcp_server/u1/test"
    )


async def test_healthy_or_untested_server_reports_nothing() -> None:
    a = resource("a", "mcp_server", STDIO)
    b = resource("b", "mcp_server", STDIO)
    source = _source(FakeResources([a, b]), health=FakeHealth({"a": ("healthy", T0)}))
    assert await source.items() == []


async def test_missing_launcher_wins_over_the_failing_row_it_causes() -> None:
    srv = resource("u1", "mcp_server", STDIO, name="jira")
    items = await _source(
        FakeResources([srv]),
        health=FakeHealth({"u1": ("failing", T0)}),
        missing={"uvx": "uvx"},
    ).items()
    assert [i.reason_code for i in items] == ["mcp_missing_launcher"]
    assert items[0].title == "jira"  # no title set: the name
    assert items[0].severity is Severity.ERROR
    assert "uvx" in items[0].reason
    assert items[0].action.path == "/api/v1/resources/mcp_server/u1/test"
    assert items[0].action.method == "POST"
    assert items[0].since is None


async def test_a_cited_ref_the_store_lacks_asks_for_the_secret_without_a_value() -> None:
    srv = resource("u1", "mcp_server", STDIO)
    other = resource("c1", "channel", {})
    resources = FakeResources(
        [srv, other],
        cited={"mcp/jira/token": [srv], "mcp/held": [srv], "channel/bot": [other]},
    )
    items = await _source(resources, held={"mcp/held"}).items()
    assert len(items) == 1
    item = items[0]
    assert item.reason_code == "mcp_missing_secret"
    assert item.severity is Severity.ERROR
    assert "mcp/jira/token" in item.reason
    assert item.action == AttentionAction(
        verb="set_secret",
        method="POST",
        path="/api/v1/secrets",
        body={"ref": "mcp/jira/token"},
    )


async def test_disabled_servers_are_not_asked() -> None:
    off = resource("off", "mcp_server", STDIO, enabled=False)
    resources = FakeResources([off], cited={"mcp/x": [off]})
    source = _source(resources, health=FakeHealth({"off": ("failing", T0)}), missing={"uvx": "uvx"})
    assert await source.items() == []


async def test_a_raising_dependency_propagates() -> None:
    class Broken(FakeHealth):
        async def get(self, resource_uid: str) -> tuple[str, datetime] | None:
            raise RuntimeError("db gone")

    srv = resource("u1", "mcp_server", STDIO)
    with pytest.raises(RuntimeError, match="db gone"):
        await _source(FakeResources([srv]), health=Broken()).items()


def test_source_identity() -> None:
    source = _source(FakeResources([]))
    assert (source.name, source.feature) == ("mcp_server", None)


def test_missing_runner_of_reads_only_stdio_launchers(tmp_path) -> None:  # type: ignore[no-untyped-def]
    gone = tmp_path / "gone-runner"
    assert missing_runner_of({"transport": {"type": "stdio", "command": str(gone)}}) == (
        "gone-runner"
    )
    assert missing_runner_of({"transport": {"type": "stdio", "command": "sh"}}) is None
    assert missing_runner_of({"transport": {"type": "http", "url": "https://x.test/mcp"}}) is None
    assert missing_runner_of({"transport": "not a transport"}) is None
