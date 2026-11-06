"""What an MCP server requires, worked out from its config (spec mcp-gateway
"Show what an MCP server requires")."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.mcp.server_requires import ServerRequirements
from coffer.domain.resource import Resource
from coffer.domain.secrets import SecretApproval


class _Probe:
    def __init__(self, installed: set[str]) -> None:
        self.installed = installed

    def locate(self, command: str) -> str | None:
        return f"/bin/{command}" if command in self.installed else None


class _Secrets:
    def __init__(self, stored: set[str]) -> None:
        self._stored = stored

    def exists(self, ref: str) -> bool:
        return ref in self._stored


class _Boundary:
    def __init__(self, waiting_slots: set[str], refused_slots: set[str] = frozenset()) -> None:
        self.waiting = waiting_slots
        self.refused = refused_slots

    def check(self, dest: Any, refs: dict[str, str], *, actor: str = "system"):
        return [
            SecretApproval(
                id="a1", op="bind", status="rejected" if slot in self.refused else "pending",
                created_at="", requested_by="x", ref=ref, slot=slot,
            )
            for slot, ref in refs.items()
            if slot in self.waiting | self.refused
        ]  # fmt: skip


def _server(transport: dict[str, Any]) -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        uid="u" * 32, kind="mcp_server", name="notion", description=None,
        config={"transport": transport}, enabled=True, created_at=now, updated_at=now,
    )  # fmt: skip


def _of(server: Resource, probe=None, stored=(), waiting=(), refused=()):
    reqs = ServerRequirements(
        probe=probe or _Probe({"npx"}),
        secrets=_Secrets(set(stored)),
        boundary=lambda: _Boundary(set(waiting), set(refused)),
    )
    return asyncio.run(reqs.of(server))


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a server's page lists what it requires")
def test_a_stdio_server_requires_its_launcher_and_its_secrets():
    server = _server(
        {
            "type": "stdio",
            "command": "npx",
            "args": ["x"],
            "secret_refs": {"NOTION_TOKEN": "secret/notion", "DB_URL": "secret/db"},
        }
    )
    rows = _of(server, stored={"secret/notion"}, waiting=set())
    assert [(r.kind, r.name, r.status) for r in rows] == [
        ("cli", "npx", "found"),
        ("secret", "NOTION_TOKEN", "set"),
        ("secret", "DB_URL", "missing"),
    ]
    assert rows[1].secret == "notion"


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a server's page lists what it requires")
def test_a_missing_launcher_is_not_found_and_a_waiting_secret_says_so():
    server = _server({"type": "stdio", "command": "uvx", "secret_refs": {"TOKEN": "secret/t"}})
    rows = _of(server, stored={"secret/t"}, waiting={"TOKEN"})
    assert [(r.name, r.status) for r in rows] == [
        ("uvx", "not_found"),
        ("TOKEN", "waiting_approval"),
    ]


def test_a_refused_secret_is_refused_not_waiting():
    server = _server({"type": "stdio", "command": "npx", "secret_refs": {"A": "secret/a"}})
    rows = _of(server, stored={"secret/a"}, refused={"A"})
    assert [(r.name, r.status) for r in rows] == [("npx", "found"), ("A", "refused")]


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a server's page lists what it requires")
def test_an_http_server_has_no_launcher_and_a_plain_secret_uri_counts():
    server = _server(
        {
            "type": "http",
            "url": "https://mcp.example/mcp",
            "headers": {"Authorization": "coffer://secret/gh"},
        }
    )
    rows = _of(server, stored={"secret/gh"})
    assert [(r.kind, r.name, r.status, r.secret) for r in rows] == [
        ("secret", "Authorization", "set", "gh")
    ]


def test_a_config_that_does_not_parse_requires_nothing():
    assert _of(_server({"type": "stdio"})) == []
