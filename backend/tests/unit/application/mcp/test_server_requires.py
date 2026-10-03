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
    def __init__(self, installed: dict[str, str | None]) -> None:
        self.installed = installed
        self.version_runs = 0

    def locate(self, command: str) -> str | None:
        return f"/bin/{command}" if command in self.installed else None

    def version(self, path: str) -> str | None:
        self.version_runs += 1
        return self.installed[path.rsplit("/", 1)[-1]]


class _Secrets:
    def __init__(self, stored: set[str]) -> None:
        self._stored = stored

    def exists(self, ref: str) -> bool:
        return ref in self._stored


class _Boundary:
    def __init__(self, waiting_slots: set[str]) -> None:
        self.waiting = waiting_slots

    def check(self, dest: Any, refs: dict[str, str], *, actor: str = "system"):
        return [
            SecretApproval(
                id="a1", op="bind", status="pending", created_at="", requested_by="x",
                ref=ref, slot=slot,
            )
            for slot, ref in refs.items()
            if slot in self.waiting
        ]  # fmt: skip


def _server(transport: dict[str, Any]) -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        uid="u" * 32, kind="mcp_server", name="notion", description=None, title=None,
        config={"transport": transport}, enabled=True, created_at=now, updated_at=now,
    )  # fmt: skip


def _of(server: Resource, probe=None, stored=(), waiting=()):
    reqs = ServerRequirements(
        probe=probe or _Probe({"npx": "10.9.2"}),
        secrets=_Secrets(set(stored)),
        boundary=lambda: _Boundary(set(waiting)),
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
    assert rows[0].version == "10.9.2" and rows[1].secret == "notion"


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a server's page lists what it requires")
def test_a_missing_launcher_is_not_found_and_a_waiting_secret_says_so():
    server = _server({"type": "stdio", "command": "uvx", "secret_refs": {"TOKEN": "secret/t"}})
    rows = _of(server, stored={"secret/t"}, waiting={"TOKEN"})
    assert [(r.name, r.status) for r in rows] == [
        ("uvx", "not_found"),
        ("TOKEN", "waiting_approval"),
    ]


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


def test_a_found_launchers_version_is_read_once():
    probe = _Probe({"npx": "10.9.2"})
    reqs = ServerRequirements(probe=probe, secrets=_Secrets(set()), boundary=lambda: None)
    server = _server({"type": "stdio", "command": "npx"})
    asyncio.run(reqs.of(server))
    asyncio.run(reqs.of(server))
    assert probe.version_runs == 1


def test_a_config_that_does_not_parse_requires_nothing():
    assert _of(_server({"type": "stdio"})) == []
