"""The plaintext scan and move over REST, against a real in-process daemon over a
throwaway HOME (spec secret "Move plaintext secrets in managed resources into the store")."""

from __future__ import annotations

import pathlib
import re
from collections.abc import Iterator
from typing import Any

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon

# Joined at run time so a secret scanner reading this file sees no literal key.
TOKEN_VALUE = "-".join(["fake", "token", "value"])
PASSWORD = "hunter2hunter2"
APIKEY = "-".join(["fake", "api", "key", "value"])


@pytest.fixture
def d(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as daemon:
        yield daemon


def _skill(home: pathlib.Path, body: str | None = None) -> pathlib.Path:
    skill = home / ".coffer" / "vault" / "skills" / "deploy"
    (skill / "scripts").mkdir(parents=True, exist_ok=True)
    script = skill / "scripts" / "run.sh"
    script.write_text(body or f'#!/bin/sh\nexport API_TOKEN="{TOKEN_VALUE}"\n')
    script.chmod(0o755)
    return script


def _register(d: BoundaryDaemon, name: str, transport: dict[str, Any]) -> dict[str, Any]:
    r = d.client.post(
        "/api/v1/resources",
        json={"kind": "mcp_server", "name": name, "config": {"transport": transport}},
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


def _servers(d: BoundaryDaemon) -> tuple[dict[str, Any], dict[str, Any]]:
    stdio = _register(
        d, "db-tool", {"type": "stdio", "command": "db-tool", "env": {"DB_PASSWORD": PASSWORD}}
    )
    api = _register(
        d,
        "orders-api",
        {
            "type": "http_api",
            "base_url": "https://api.example.com",
            "headers": {"X-Api-Key": APIKEY},
        },
    )
    return stdio, api


def _get(d: BoundaryDaemon, uid: str) -> dict[str, Any]:
    r = d.client.get(f"/api/v1/resources/{uid}")
    assert r.status_code == 200, r.text
    return dict(r.json())


@pytest.mark.acceptance(
    spec="secret",
    scenario="a scan names plaintext secrets in skills and MCP servers without their values",
)
def test_a_scan_names_plaintext_secrets_without_their_values(d: BoundaryDaemon) -> None:
    _skill(d.home)
    _servers(d)

    r = d.client.post("/api/v1/secrets/scan")

    assert r.status_code == 200, r.text
    found = {(f["source"], f["resource"], f["key"]) for f in r.json()["findings"]}
    assert found == {
        ("skill", "deploy", "API_TOKEN"),
        ("mcp_server", "db-tool", "DB_PASSWORD"),
        ("mcp_server", "orders-api", "X-Api-Key"),
    }
    skill = next(f for f in r.json()["findings"] if f["source"] == "skill")
    assert skill["proposed_name"] == "deploy.api_token" and skill["line"] == 2
    assert not any(v in r.text for v in (TOKEN_VALUE, PASSWORD, APIKEY))


@pytest.mark.acceptance(
    spec="secret", scenario="references, interpolations and placeholders are not findings"
)
def test_references_interpolations_and_placeholders_are_not_findings(d: BoundaryDaemon) -> None:
    _skill(
        d.home, "#!/bin/sh\ncoffer run --secret GH=github -- gh\nexport T=coffer://secret/github\n"
    )
    _register(
        d,
        "clean",
        {
            "type": "stdio",
            "command": "x",
            "env": {
                "API_TOKEN": "${API_TOKEN}",
                "MY_KEY": "<your-token>",
                "OTHER_TOKEN": "$HOST_TOKEN",
                "LOG_LEVEL": "debug",
            },
        },
    )

    body = d.client.post("/api/v1/secrets/scan").json()

    assert body["findings"] == []


@pytest.mark.acceptance(
    spec="secret", scenario="importing a skill's value leaves a reference in its file"
)
def test_importing_a_skill_value_leaves_a_reference(d: BoundaryDaemon) -> None:
    script = _skill(d.home)
    before = script.read_text()

    dry = d.client.post("/api/v1/secrets/import", json={"dry_run": True})
    assert dry.status_code == 200, dry.text
    assert script.read_text() == before and dry.json()["moved"][0]["label"] == "deploy.api_token"
    assert dry.json()["moved"][0]["ref"] is None

    moved = d.client.post("/api/v1/secrets/import", json={})

    assert moved.status_code == 200, moved.text
    row = moved.json()["moved"][0]
    assert re.fullmatch(r"[0-9a-f]{32}", row["name"]) and row["label"] == "deploy.api_token"
    assert d.value(row["ref"]) == TOKEN_VALUE
    assert f'API_TOKEN="coffer://secret/{row["name"]}"' in script.read_text()
    assert (script.stat().st_mode & 0o777) == 0o755
    assert TOKEN_VALUE not in moved.text
    assert d.client.get("/api/v1/secrets").json()["refs"][0]["label"] == "deploy.api_token"
    entries = d.audit("secret_imported")
    assert [e["details"]["name"] for e in entries] == [row["name"]]
    assert TOKEN_VALUE not in str(entries)


@pytest.mark.acceptance(
    spec="secret", scenario="importing a server's value moves it into the server's secret refs"
)
def test_importing_a_server_value_moves_it_into_its_secret_refs(d: BoundaryDaemon) -> None:
    stdio, api = _servers(d)

    dry = d.client.post("/api/v1/secrets/import", json={"dry_run": True})
    assert dry.status_code == 200, dry.text
    assert _get(d, stdio["uid"])["config"]["transport"]["env"] == {"DB_PASSWORD": PASSWORD}

    moved = d.client.post("/api/v1/secrets/import", json={})

    assert moved.status_code == 200, moved.text
    assert moved.json()["skipped"] == [] and len(moved.json()["moved"]) == 2
    s = _get(d, stdio["uid"])
    t = s["config"]["transport"]
    assert t["env"] == {} and list(t["secret_refs"]) == ["DB_PASSWORD"]
    assert re.fullmatch(r"secret/[0-9a-f]{32}", t["secret_refs"]["DB_PASSWORD"])
    assert d.value(t["secret_refs"]["DB_PASSWORD"]) == PASSWORD
    h = _get(d, api["uid"])["config"]["transport"]
    # A custom-tool group keeps its headers per environment (one, lifted, here).
    assert "X-Api-Key" not in h["environments"][0]["headers"]
    assert d.value(h["secret_refs"]["X-Api-Key"]) == APIKEY
    assert d.resolve_for(s) == {"DB_PASSWORD": PASSWORD} and d.pending() == []
    assert not any(v in moved.text for v in (PASSWORD, APIKEY))
    assert len(d.audit("secret_imported")) == 2
    assert d.client.post("/api/v1/secrets/scan").json()["findings"] == []


@pytest.mark.acceptance(
    spec="secret", scenario="a file that cannot be rewritten keeps its key and says so"
)
def test_a_file_that_cannot_be_rewritten_keeps_its_key_and_says_so(d: BoundaryDaemon) -> None:
    script = _skill(d.home)
    before = script.read_text()
    folder = script.parent
    folder.chmod(0o500)
    try:
        r = d.client.post("/api/v1/secrets/import", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["moved"] == []
        assert [s["stored"] for s in body["skipped"]] == [True]
        name = body["skipped"][0]["name"]
        assert script.read_text() == before
        assert d.value("secret/" + name) == TOKEN_VALUE
    finally:
        folder.chmod(0o755)

    again = d.client.post("/api/v1/secrets/import", json={})

    assert again.status_code == 200, again.text
    assert [m["label"] for m in again.json()["moved"]] == ["deploy.api_token"]
    assert "coffer://secret/" + again.json()["moved"][0]["name"] in script.read_text()


@pytest.mark.acceptance(spec="secret", scenario="a scan that finds nothing says how much it read")
def test_a_scan_that_finds_nothing_says_how_much_it_read(d: BoundaryDaemon) -> None:
    _skill(d.home, "# a skill\nnothing here\n")
    _register(d, "plain", {"type": "stdio", "command": "x", "env": {"LOG_LEVEL": "debug"}})

    body = d.client.post("/api/v1/secrets/scan").json()

    assert body["findings"] == []
    assert body["files_checked"] >= 1 and body["servers_checked"] >= 1
