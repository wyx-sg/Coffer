"""HTTP contract tests for the backup half of /api/v1/sync.

Spec vault-export-import ``## Backup`` / ``### Restore`` / ``## Surfaces``.

These run against a real ``git`` binary and a real local bare repository
rather than a stubbed mirror: the surface's job is to report what a backup
actually did, and a fake that agrees with our assumptions would report that
the assumptions are self-consistent. No network is involved — the "remote" is
a bare repository in ``tmp_path``.
"""

from __future__ import annotations

import pathlib
import subprocess

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.resource_service import ResourceService
from coffer.application.sync.backup_service import BackupService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.service import SyncService
from coffer.domain.resource import Kind, ResourceRef
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.infrastructure.persistence.sync_remote_repo import SqlAlchemySyncRemoteRepo
from coffer.infrastructure.sync.bundle import Bundle
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from coffer.infrastructure.sync.git_mirror import GitMirror
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.sync_routes import router as sync_router
from coffer.surfaces.http.sync_routes import set_backup_service, set_sync_service

_TOKEN = "test-token"
#: Stands in for a push token. Distinctive enough that "the response does not
#: contain the secret" is a claim about a string that cannot turn up by
#: accident, and unmistakably fake so that neither a secrets scanner nor a
#: reviewer skimming the diff has to work out whether a real credential was
#: committed.
_PUSH_SECRET = "placeholder-not-a-real-secret-3f7c1a"
_CRED_REF = "sync/backup/token"

#: Exactly the fields ``GET /remote`` may carry. Pinned as a set so a field
#: added later that happens to hold the credential fails here rather than
#: quietly shipping the secret to a browser.
_REMOTE_FIELDS = {
    "url",
    "branch",
    "credential_ref",
    "include_credentials",
    "interval_seconds",
    "enabled",
    "worktree_path",
}


class _Cfg(BaseModel):
    value: str = ""


class _NoKeyring:
    def get(self, ref: str) -> str | None:
        return None

    def set(self, ref: str, value: str) -> None:
        pass

    def delete(self, ref: str) -> None:
        pass


def _bare_repo(path: pathlib.Path) -> None:
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(path)],
        check=True,
        capture_output=True,
    )


def _git_log(repo: pathlib.Path, branch: str = "main") -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline", branch],
        check=False,
        capture_output=True,
        text=True,
    )
    return out.stdout


@pytest_asyncio.fixture
async def client(tmp_path):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "c.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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

    sync = SyncService(
        exporter=SyncExporter(resources, cred_sync, home=None),
        importer=SyncImporter(resources, cred_sync, home=None),
        credentials=cred_sync,
        master_key=master_key,
        audit=audit,
        bundle_factory=lambda p: Bundle(p, trees=trees),
    )
    set_sync_service(sync)

    key = master_key.export_key()
    assert key is not None
    store = EncryptedCredentialStore(db_path, key)
    set_backup_service(
        BackupService(
            remotes=SqlAlchemySyncRemoteRepo(sm),
            sync=sync,
            mirror_factory=GitMirror,
            credentials=CredentialResolver(store),
            audit=audit,
        )
    )

    remote_path = tmp_path / "remote.git"
    _bare_repo(remote_path)

    app = FastAPI()
    app.include_router(sync_router)
    err_handlers.register(app)
    set_active_token(_TOKEN)
    transport = ASGITransport(app)
    async with AsyncClient(
        transport=transport, base_url="http://t", headers={"X-Coffer-Token": _TOKEN}
    ) as c:
        c.tmp_path = tmp_path  # type: ignore[attr-defined]
        c.resources = resources  # type: ignore[attr-defined]
        c.store = store  # type: ignore[attr-defined]
        c.remote_path = remote_path  # type: ignore[attr-defined]
        c.remote_url = str(remote_path)  # type: ignore[attr-defined]
        c.worktree = tmp_path / "worktree"  # type: ignore[attr-defined]
        c.knowledge = knowledge  # type: ignore[attr-defined]
        yield c
    set_active_token(None)
    await engine.dispose()


async def _configure(client, **overrides) -> dict:  # type: ignore[no-untyped-def]
    body = {
        "url": client.remote_url,
        "worktree_path": str(client.worktree),
        **overrides,
    }
    r = await client.put("/api/v1/sync/remote", json=body)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


@pytest.mark.acceptance(spec="vault-export-import", scenario="configure a backup remote")
async def test_configure_a_backup_remote(client) -> None:  # type: ignore[no-untyped-def]
    """A fresh vault has no remote; setting one stores every field and leaves
    the status reporting the remote with no run yet."""
    r = await client.get("/api/v1/sync/remote")
    assert r.status_code == 200
    assert r.json() == {"configured": False, "remote": None}

    stored = await _configure(
        client, branch="backup", interval_seconds=900, include_credentials=True
    )
    assert stored["url"] == client.remote_url
    assert stored["branch"] == "backup"
    assert stored["interval_seconds"] == 900
    assert stored["include_credentials"] is True
    assert stored["enabled"] is True

    r = await client.get("/api/v1/sync/status")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["remote"]["url"] == client.remote_url
    assert body["remote"]["branch"] == "backup"
    # Configured but never run: the surface says so rather than inventing a run.
    assert body["last_run"] is None


async def test_get_remote_never_returns_the_credential(client) -> None:  # type: ignore[no-untyped-def]
    """The push credential is a ref on the wire and a secret only inside the
    daemon (spec ``## Backup``): nothing the UI renders needs redacting."""
    client.store.set(_CRED_REF, _PUSH_SECRET)
    await _configure(client, credential_ref=_CRED_REF)

    for path in ("/api/v1/sync/remote", "/api/v1/sync/status"):
        r = await client.get(path)
        assert r.status_code == 200
        assert _PUSH_SECRET not in r.text
        assert _CRED_REF in r.text

    remote = (await client.get("/api/v1/sync/remote")).json()["remote"]
    assert set(remote) == _REMOTE_FIELDS
    assert remote["credential_ref"] == _CRED_REF
    # Belt and braces: no value anywhere in the payload is the secret, whatever
    # a future field might be called.
    assert all(value != _PUSH_SECRET for value in remote.values())


async def test_put_remote_refuses_an_empty_url(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.put("/api/v1/sync/remote", json={"url": "   "})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "BACKUP_REMOTE_INVALID"


async def test_put_remote_refuses_a_non_positive_interval(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.put(
        "/api/v1/sync/remote", json={"url": client.remote_url, "interval_seconds": 0}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "BACKUP_REMOTE_INVALID"


async def test_put_remote_replaces_the_previous_one(client) -> None:  # type: ignore[no-untyped-def]
    """At most one remote exists, so configuring a second one is a change of
    mind rather than a conflict."""
    await _configure(client)
    second = str(client.tmp_path / "other.git")
    await _configure(client, url=second)
    assert (await client.get("/api/v1/sync/remote")).json()["remote"]["url"] == second


async def test_delete_remote_turns_backup_off(client) -> None:  # type: ignore[no-untyped-def]
    await _configure(client)
    r = await client.delete("/api/v1/sync/remote")
    assert r.status_code == 200
    assert r.json() == {"cleared": True}
    assert (await client.get("/api/v1/sync/remote")).json() == {
        "configured": False,
        "remote": None,
    }
    # Idempotent: clearing nothing is not an error.
    r = await client.delete("/api/v1/sync/remote")
    assert r.status_code == 200
    assert r.json() == {"cleared": False}


async def test_push_runs_one_backup_and_reports_it(client) -> None:  # type: ignore[no-untyped-def]
    await client.resources.register("mcp_server", "files", {"value": "a"}, "user")
    (client.knowledge / "note.md").write_text("hi", encoding="utf-8")
    await _configure(client)

    r = await client.post("/api/v1/sync/push")
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "ok"
    assert run["commit"]
    assert run["error"] is None
    assert run["ran_at"]
    # It really reached the remote, and the message names the counts per area.
    assert "coffer backup" in _git_log(client.remote_path)

    status = (await client.get("/api/v1/sync/status")).json()
    assert status["last_run"]["status"] == "ok"
    assert status["last_run"]["commit"] == run["commit"]


async def test_push_with_a_disabled_remote_does_nothing(client) -> None:  # type: ignore[no-untyped-def]
    """Disabled is not deleted: the config survives, but a run is a no-op and
    the remote never hears from us."""
    await client.resources.register("mcp_server", "files", {"value": "a"}, "user")
    await _configure(client, enabled=False)

    r = await client.post("/api/v1/sync/push")
    assert r.status_code == 200
    assert r.json()["status"] == "no_change"
    assert _git_log(client.remote_path) == ""
    assert (await client.get("/api/v1/sync/remote")).json()["remote"]["enabled"] is False


async def test_push_to_an_unreachable_remote_reports_the_failure(client) -> None:  # type: ignore[no-untyped-def]
    """A push that cannot land is a run with a story, not an HTTP error: the
    commit exists locally and the next run carries it out."""
    await client.resources.register("mcp_server", "files", {"value": "a"}, "user")
    await _configure(client, url=str(client.tmp_path / "nowhere.git"))

    r = await client.post("/api/v1/sync/push")
    assert r.status_code == 200
    run = r.json()
    assert run["status"] == "push_failed"
    assert run["commit"]
    assert run["error"]


async def test_restore_brings_back_a_deleted_resource(client) -> None:  # type: ignore[no-untyped-def]
    await client.resources.register("mcp_server", "files", {"value": "a"}, "user")
    await _configure(client)
    assert (await client.post("/api/v1/sync/push")).json()["status"] == "ok"

    await client.resources.delete(ResourceRef(kind="mcp_server", name="files"), "user")

    r = await client.post("/api/v1/sync/restore", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert {a["area"]: a["count"] for a in body["areas"]}["resources"] == 1
    restored = await client.resources.get(ResourceRef(kind="mcp_server", name="files"))
    assert restored.config["value"] == "a"


async def test_restore_at_an_earlier_revision(client) -> None:  # type: ignore[no-untyped-def]
    """The tip cannot return something deleted last week, so ``at`` names the
    revision that still held it."""
    await client.resources.register("mcp_server", "files", {"value": "a"}, "user")
    await _configure(client)
    first = (await client.post("/api/v1/sync/push")).json()["commit"]

    await client.resources.delete(ResourceRef(kind="mcp_server", name="files"), "user")
    assert (await client.post("/api/v1/sync/push")).json()["status"] == "ok"

    r = await client.post("/api/v1/sync/restore", json={"at": first})
    assert r.status_code == 200, r.text
    restored = await client.resources.get(ResourceRef(kind="mcp_server", name="files"))
    assert restored.config["value"] == "a"


async def test_restore_without_a_remote_or_a_url_is_422(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/api/v1/sync/restore", json={})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "BACKUP_REMOTE_INVALID"


async def test_restore_from_an_unreachable_url_is_502(client) -> None:  # type: ignore[no-untyped-def]
    """A git invocation that failed is the remote refusing us, not the caller
    getting the request wrong."""
    r = await client.post(
        "/api/v1/sync/restore",
        json={"from_url": str(client.tmp_path / "nowhere.git")},
    )
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "GIT_MIRROR_FAILED"


async def test_backup_routes_require_the_token(client) -> None:  # type: ignore[no-untyped-def]
    headers = {"X-Coffer-Token": "wrong"}
    assert (await client.get("/api/v1/sync/remote", headers=headers)).status_code == 401
    assert (await client.get("/api/v1/sync/status", headers=headers)).status_code == 401
    assert (await client.post("/api/v1/sync/push", headers=headers)).status_code == 401


async def test_restore_accepts_an_absent_body(client) -> None:  # type: ignore[no-untyped-def]
    """``at`` and ``from_url`` are both optional, so a bare POST restores the
    tip — the CLI's ``coffer sync restore`` with no flags sends nothing."""
    await client.resources.register("mcp_server", "files", {"value": "a"}, "user")
    await _configure(client)
    assert (await client.post("/api/v1/sync/push")).json()["status"] == "ok"
    await client.resources.delete(ResourceRef(kind="mcp_server", name="files"), "user")

    r = await client.post("/api/v1/sync/restore")
    assert r.status_code == 200, r.text
    assert await client.resources.get(ResourceRef(kind="mcp_server", name="files"))
