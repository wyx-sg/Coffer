"""Integration tests for `coffer sync ...` (spec vault-export-import vault export/import).

Drives the real CLI against a minimal app carrying only the sync router, so
these stay a test of the command surface rather than of daemon composition.
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime as dt

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.service import SyncService
from coffer.domain.resource import Kind
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.infrastructure.sync.bundle import Bundle
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.sync_routes import router as sync_router
from coffer.surfaces.http.sync_routes import set_sync_service

_runner = CliRunner()
_TOKEN = "test-token-sync-cli"


class _Cfg(BaseModel):
    value: str = ""


class _NoKeyring:
    def get(self, ref: str) -> str | None:
        return None

    def set(self, ref: str, value: str) -> None:
        pass

    def delete(self, ref: str) -> None:
        pass


@pytest.fixture
def sync_cli(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    import asyncio

    db_path = tmp_path / "c.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")

    async def _setup():  # type: ignore[no-untyped-def]
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_setup())
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds={"mcp_server": Kind(name="mcp_server", display_name="X", config_schema=_Cfg)},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    master_key = MasterKeyManager(tmp_path / "master.key", _NoKeyring())
    master_key.resolve(allow_create=True)
    cred_sync = CredentialSyncAdapter(db_path, master_key)
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    trees = [("knowledge", knowledge)]
    set_sync_service(
        SyncService(
            exporter=SyncExporter(resources, cred_sync, home=None),
            importer=SyncImporter(resources, cred_sync, home=None),
            credentials=cred_sync,
            master_key=master_key,
            audit=audit,
            bundle_factory=lambda p: Bundle(p, trees=trees),
        )
    )

    app = FastAPI()
    app.include_router(sync_router)
    err_handlers.register(app)
    set_active_token(_TOKEN)
    info = DaemonInfo(
        version=1,
        pid=1,
        port=59820,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    fake = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    fake.__enter__()

    class _Persistent:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *a):  # type: ignore[no-untyped-def]
            return None

        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(fake, item)

    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (_Persistent(), info))
    yield tmp_path
    fake.__exit__(None, None, None)
    set_active_token(None)


def test_export_reports_areas_and_the_bundle_path(sync_cli):  # type: ignore[no-untyped-def]
    out = sync_cli / "bundle"
    result = _runner.invoke(cli_app, ["sync", "export", str(out)])
    assert result.exit_code == 0, result.output
    # Rich soft-wraps the long tmp path, so match on the leaf, not the whole.
    assert "bundle" in result.output
    assert "resources" in result.output
    assert (out / "manifest.json").exists()
    assert not (out / "credentials").exists()


def test_export_with_credentials_warns(sync_cli):  # type: ignore[no-untyped-def]
    out = sync_cli / "bundle"
    result = _runner.invoke(cli_app, ["sync", "export", str(out), "--with-credentials"])
    assert result.exit_code == 0, result.output
    assert "trust" in result.output


def test_import_reports_a_summary(sync_cli):  # type: ignore[no-untyped-def]
    out = sync_cli / "bundle"
    _runner.invoke(cli_app, ["sync", "export", str(out)])
    result = _runner.invoke(cli_app, ["sync", "import", str(out)])
    assert result.exit_code == 0, result.output
    assert "bundle" in result.output
    assert "resources" in result.output


def test_import_of_a_non_bundle_fails(sync_cli):  # type: ignore[no-untyped-def]
    result = _runner.invoke(cli_app, ["sync", "import", str(sync_cli / "absent")])
    assert result.exit_code != 0


def test_key_export_then_import(sync_cli):  # type: ignore[no-untyped-def]
    target = sync_cli / "master.out"
    result = _runner.invoke(cli_app, ["sync", "key", "export", str(target)])
    assert result.exit_code == 0, result.output
    assert target.exists()
    result = _runner.invoke(cli_app, ["sync", "key", "import", str(target)])
    assert result.exit_code == 0, result.output
    assert "unlock" in result.output


def test_withdrawn_continuous_sync_commands_are_gone(sync_cli):  # type: ignore[no-untyped-def]
    # Vault export/import withdrew continuous sync; typer must not still offer
    # its verbs.
    #
    # ``sync status`` is deliberately absent from this list: the backup half of
    # the spec reintroduced the word for a different thing — the one backup
    # remote and its last run, not a convergence state between machines
    # (spec vault-export-import ``## Surfaces``). It is covered by
    # test_sync_backup_cmd.py.
    for argv in (
        ["sync", "init", "git@example.com:me/vault.git"],
        ["sync", "run"],
        ["sync", "config"],
        ["sync", "machines"],
        ["sync", "resolve", "--ours"],
        ["sync", "override", "list"],
        ["machines"],
    ):
        assert _runner.invoke(cli_app, argv).exit_code != 0, argv
