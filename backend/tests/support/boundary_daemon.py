"""A real in-process daemon for the secret boundary's tests (spec secret).

The whole app over a throwaway ``HOME``, the keyring swapped for
the shared in-memory backend, and helpers that stand in for the desktop app:
``grant`` signs a presence challenge the way the shell does, with the key
derived from this daemon's own master key. Nothing touches the developer's
``~/.coffer`` or Keychain.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from starlette.testclient import TestClient

import coffer.surfaces.cli._client as _cli_client
from coffer.application.secret.presence import derive_grant_key, sign_grant
from coffer.domain.mcp.secret_target import mcp_destination
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.infrastructure.vault.home import local_root
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.secret_boundary_wiring import boundary_resolver, get_secret_boundary
from coffer.surfaces.http.secret_composition import (
    get_master_key_manager,
    get_secret_store,
)
from tests.fixtures.keyring import install_in_memory_keyring

TOKEN = "test-token-secret-boundary"


class BoundaryDaemon:
    def __init__(self, client: TestClient, home: pathlib.Path, db: pathlib.Path) -> None:
        self.client = client
        self.home = home
        self.db = db

    # --- the desktop app's half ---------------------------------------------

    def grant(self, op: str, target: str) -> dict[str, str]:
        r = self.client.post(
            "/api/v1/secrets/presence/challenge", json={"op": op, "target": target}
        )
        assert r.status_code == 200, r.text
        nonce = r.json()["nonce"]
        key = derive_grant_key(get_master_key_manager().current or b"")
        return {"nonce": nonce, "signature": sign_grant(key, op, target, nonce)}

    def approve(self, approval_id: str) -> Any:
        r = self.client.post(
            f"/api/v1/secrets/approvals/{approval_id}/approve",
            json=self.grant("approve", approval_id),
        )
        assert r.status_code == 200, r.text
        return r.json()

    # --- convenience ---------------------------------------------------------

    def store(self, ref: str, value: str) -> None:
        """Store a value; a new standalone secret is approved as the app would."""
        r = self.client.post("/api/v1/secrets", json={"ref": ref, "value": value})
        if r.status_code == 202 and r.json()["approval"]["op"] == "add_secret":
            self.approve(r.json()["approval"]["id"])
            return
        assert r.status_code == 204, r.text

    def value(self, ref: str) -> str | None:
        return get_secret_store().get(ref)

    def register_stdio(self, name: str, command: str, refs: dict[str, str]) -> dict[str, Any]:
        config = {"transport": {"type": "stdio", "command": command, "secret_refs": refs}}
        r = self.client.post(
            "/api/v1/resources", json={"kind": "mcp_server", "name": name, "config": config}
        )
        assert r.status_code == 201, r.text
        return dict(r.json())

    def resolve_for(self, resource: dict[str, Any]) -> dict[str, str]:
        """What the MCP spawn path would inject, through the guarded resolver."""
        config = MCPServerConfig.model_validate(resource["config"])
        dest = mcp_destination(resource["uid"], resource["name"], config)
        return boundary_resolver(get_secret_store()).materialize(
            dict(config.transport.secret_refs), dest
        )

    def pending(self, **params: str) -> list[dict[str, Any]]:
        r = self.client.get("/api/v1/secrets/approvals", params={"status": "pending", **params})
        assert r.status_code == 200, r.text
        return list(r.json()["approvals"])

    def audit(self, event_type: str) -> list[dict[str, Any]]:
        r = self.client.get("/api/v1/audit", params={"event_type": event_type, "limit": 500})
        assert r.status_code == 200, r.text
        return list(r.json()["entries"])

    def local_secrets(self, name: str) -> dict[str, Any]:
        """One of the boundary's machine-local files (``bindings``,
        ``approvals``, ``settings``) as it is on disk."""
        path = local_root(self.home) / "secret-boundary" / f"{name}.json"
        return dict(json.loads(path.read_text())) if path.is_file() else {}

    def sql(self, statement: str, *args: Any) -> list[tuple[Any, ...]]:
        with sqlite3.connect(self.db) as conn:
            return list(conn.execute(statement, args))

    @property
    def boundary(self) -> Any:
        return get_secret_boundary()


@contextmanager
def running_daemon(home: pathlib.Path, db: pathlib.Path) -> Iterator[BoundaryDaemon]:
    app = create_app()
    set_active_token(TOKEN)
    try:
        with TestClient(app, headers={"X-Coffer-Token": TOKEN}) as c:
            yield BoundaryDaemon(c, home, db)
    finally:
        set_active_token(None)


def prepare_home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    install_in_memory_keyring(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59940")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59949")
    return tmp_path / "c.db"


class CliTransport:
    """What ``client_or_exit`` hands a command: the daemon's own client, prefixed.

    Entering and leaving are no-ops so the one lifespan stays the fixture's.
    """

    def __init__(self, client: TestClient) -> None:
        self._client = client

    def __enter__(self) -> CliTransport:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def request(self, method: str, path: str, **kw: Any) -> Any:
        return self._client.request(method, f"/api/v1{path}", **kw)

    def get(self, path: str, **kw: Any) -> Any:
        return self._client.get(f"/api/v1{path}", **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self._client.post(f"/api/v1{path}", **kw)

    def put(self, path: str, **kw: Any) -> Any:
        return self._client.put(f"/api/v1{path}", **kw)

    def patch(self, path: str, **kw: Any) -> Any:
        return self._client.patch(f"/api/v1{path}", **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self._client.delete(f"/api/v1{path}", **kw)

    def close(self) -> None:
        return None


def point_cli_at(daemon: BoundaryDaemon, monkeypatch: pytest.MonkeyPatch) -> None:
    transport = CliTransport(daemon.client)
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (transport, object()))
