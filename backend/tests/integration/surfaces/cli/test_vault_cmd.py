"""``coffer vault problems`` (coffer.surfaces.cli.vault_cmd; spec vault-storage
"Keep the last valid version when a hand edit is invalid").

The CLI client is pointed at the vault router over this test's own HOME, so
each command runs the route it names against a real vault repository.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.domain.vault.writers import WRITER_USER, CommitMeta
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.vault_routes import router as vault_router

_runner = CliRunner()
_TOKEN = "t-vault-cli"
USER = CommitMeta(writer=WRITER_USER, operation="edit", summary="Saved", actor="ui")


class _Audit:
    async def record(self, event_type: str, **_: Any) -> None:
        return None


class _Persistent:
    def __init__(self, inner: TestClient) -> None:
        self._inner = inner

    def __enter__(self) -> _Persistent:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


@pytest.fixture(autouse=True)
def daemon(monkeypatch: pytest.MonkeyPatch) -> Any:
    set_active_token(_TOKEN)
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(vault_router)
    app.dependency_overrides[get_audit_service] = lambda: _Audit()
    app.dependency_overrides[get_actor] = lambda: "cli"
    client = TestClient(app, base_url="http://localhost/api/v1", headers={"X-Coffer-Token": _TOKEN})
    info = DaemonInfo(
        version=1,
        pid=1,
        port=1,
        token=_TOKEN,
        started_at=datetime.now(tz=UTC),
        binary_path="/test",
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda **_kw: (_Persistent(client), info))
    with client:
        yield


@pytest.mark.acceptance(
    spec="vault-storage", scenario="refused hand edits are listed on REST and the command line"
)
def test_problems_lists_refused_hand_edits() -> None:
    empty = _runner.invoke(cli_app, ["vault", "problems"])
    assert empty.exit_code == 0 and "no problems" in empty.output
    r = _runner.invoke(cli_app, ["vault", "problems", "--json"])
    assert json.loads(r.output) == {"problems": []}
