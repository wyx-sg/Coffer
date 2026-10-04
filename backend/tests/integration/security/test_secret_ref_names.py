"""A resource's own secret is named for the resource and its slot, over REST,
against a real in-process daemon over a throwaway HOME (spec secret "Name a
resource's secret after the resource and its slot")."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from typing import Any

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon

PASSWORD = "hunter2hunter2"
JIRA = "jira-secret-value"
AGNES = "agnes-secret-value"
TEAM = "team-secret-value"
GITHUB = "github-secret-value"
OLD_JIRA = "mcp_server/643784232a6652abbf02c0f6aaf4a904/JIRA_TOKEN"


@pytest.fixture
def home(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[pathlib.Path, pathlib.Path]:
    return tmp_path, prepare_home(tmp_path, monkeypatch)


@pytest.fixture
def d(home: tuple[pathlib.Path, pathlib.Path]) -> Iterator[BoundaryDaemon]:
    with running_daemon(*home) as daemon:
        yield daemon


def _config(d: BoundaryDaemon, uid: str) -> dict[str, Any]:
    r = d.client.get(f"/api/v1/resources/{uid}")
    assert r.status_code == 200, r.text
    return dict(r.json()["config"])


def _exists(d: BoundaryDaemon, ref: str) -> bool:
    return bool(d.client.get(f"/api/v1/secrets/{ref}/exists").json()["present"])


def _provider(d: BoundaryDaemon, name: str, **body: Any) -> dict[str, Any]:
    payload = {"name": name, "protocol": "anthropic", "base_url": "https://gw/anthropic", **body}
    r = d.client.post("/api/v1/providers", json=payload)
    assert r.status_code == 201, r.text
    return dict(r.json())


@pytest.mark.acceptance(spec="secret", scenario="a new MCP server's secret is named after it")
def test_a_new_servers_secret_is_named_after_it(d: BoundaryDaemon) -> None:
    r = d.client.post(
        "/api/v1/resources",
        json={
            "kind": "mcp_server",
            "name": "confluence",
            "config": {
                "transport": {
                    "type": "stdio",
                    "command": "confluence-mcp",
                    "env": {"CONFLUENCE_PERSONAL_TOKEN": PASSWORD},
                }
            },
        },
    )
    assert r.status_code == 201, r.text
    uid = r.json()["uid"]
    assert d.client.post("/api/v1/secrets/import", json={}).status_code == 200

    refs = _config(d, uid)["transport"]["secret_refs"]

    assert refs == {"CONFLUENCE_PERSONAL_TOKEN": "mcp_server/confluence/CONFLUENCE_PERSONAL_TOKEN"}
    assert d.value(refs["CONFLUENCE_PERSONAL_TOKEN"]) == PASSWORD


@pytest.mark.acceptance(spec="secret", scenario="renaming a provider moves its key")
def test_renaming_a_provider_moves_its_key(d: BoundaryDaemon) -> None:
    created = _provider(d, "agnes", secret_value=AGNES)
    assert created["secret_ref"] == "provider/agnes/key"
    assert d.boundary.bindings("provider/agnes/key")

    r = d.client.patch(f"/api/v1/resources/{created['uid']}", json={"name": "agnes-hub"})
    assert r.status_code == 200, r.text

    assert _config(d, created["uid"])["secret_ref"] == "provider/agnes-hub/key"
    assert d.value("provider/agnes-hub/key") == AGNES
    assert not _exists(d, "provider/agnes/key")
    assert d.boundary.bindings("provider/agnes/key") == []
    assert d.boundary.bindings("provider/agnes-hub/key")
    assert d.pending() == []
    [entry] = d.audit("secret_renamed")
    assert entry["details"]["from"] == "provider/agnes/key"
    assert entry["details"]["to"] == "provider/agnes-hub/key"
    assert AGNES not in str(d.audit_all())


@pytest.mark.acceptance(
    spec="secret", scenario="start-up names an owned secret and leaves a shared one"
)
def test_startup_names_an_owned_secret_and_leaves_a_shared_one(
    home: tuple[pathlib.Path, pathlib.Path],
) -> None:
    with running_daemon(*home) as before:
        before.store(OLD_JIRA, JIRA)
        jira = before.register_stdio("jira", "jira-mcp", {"JIRA_TOKEN": OLD_JIRA})
        before.store("agnes-apihub", AGNES)
        agnes = _provider(before, "agnes", secret_ref="agnes-apihub")
        before.store("team.TOKEN", TEAM)
        one = before.register_stdio("one", "one-mcp", {"TOKEN": "team.TOKEN"})
        two = before.register_stdio("two", "two-mcp", {"TOKEN": "team.TOKEN"})
        before.store("secret/github", GITHUB)

    with running_daemon(*home) as d:
        assert _config(d, jira["uid"])["transport"]["secret_refs"] == {
            "JIRA_TOKEN": "mcp_server/jira/JIRA_TOKEN"
        }
        assert d.value("mcp_server/jira/JIRA_TOKEN") == JIRA
        assert _config(d, agnes["uid"])["secret_ref"] == "provider/agnes/key"
        assert d.value("provider/agnes/key") == AGNES
        assert not _exists(d, OLD_JIRA)
        assert not _exists(d, "agnes-apihub")
        moves = d.audit("secret_renamed")
        assert len(moves) == 2
        assert AGNES not in str(d.audit_all()) and JIRA not in str(d.audit_all())
        for uid in (one["uid"], two["uid"]):
            assert _config(d, uid)["transport"]["secret_refs"] == {"TOKEN": "team.TOKEN"}
        assert d.value("team.TOKEN") == TEAM and d.value("secret/github") == GITHUB

    with running_daemon(*home) as again:
        assert len(again.audit("secret_renamed")) == 2
