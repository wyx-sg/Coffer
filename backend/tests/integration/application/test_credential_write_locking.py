"""Regression: credential-store writes from async code must not freeze the loop.

CI failure on main (verify run 27414261416): ``test_adopt_mcp_entry`` died
with ``sqlite3.OperationalError: database is locked`` inside
``EncryptedCredentialStore.set``. Root cause: the sync, busy-waiting SQLite
write ran on the event loop itself, so a concurrent coroutine holding an
open write transaction (aiosqlite commits only run when the loop advances)
could never commit — the busy_timeout then expired no matter how long it
was. The same interleaving hit ``migrate_legacy_keychain`` during real
daemon startup (credential_migration.failed in the dev log).

These tests reproduce that interleaving deterministically: an in-flight
async writer holds the WAL write lock and commits only after a short
``asyncio.sleep`` — which requires a live event loop. The credential write
under test must let the loop advance while it waits for the lock.
"""

from __future__ import annotations

import asyncio
import pathlib
import sqlite3
from datetime import UTC, datetime

import aiosqlite
from cryptography.fernet import Fernet

from coffer.application.agent.mcp_entry_service import AgentMcpEntryService
from coffer.application.audit_service import AuditService
from coffer.application.credential_migration import migrate_legacy_keychain
from coffer.domain.agent.config_files import spec_for
from coffer.domain.agent.types import AgentType
from coffer.domain.resource import Resource, ResourceRef
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_SCHEMA = """
CREATE TABLE credentials (
    ref TEXT PRIMARY KEY,
    ciphertext BLOB NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CODEX_TOML = """[mcp_servers.jira]
command = "uvx"
args = ["mcp-jira"]

[mcp_servers.jira.env]
JIRA_API_TOKEN = "tok-123"
"""

_CONFIG_DIR = pathlib.Path("/fake/home/.codex")
_CONFIG_PATH = spec_for(AgentType.CODEX, "config", _CONFIG_DIR).path


class _AgentLookup:
    async def get(self, name: str) -> Resource:
        return Resource(
            id=1,
            kind="agent",
            name=name,
            description=None,
            config={"type": "codex", "config_dir": str(_CONFIG_DIR)},
            enabled=True,
            created_at=_NOW,
            updated_at=_NOW,
        )


class _FileStore:
    def __init__(self) -> None:
        self.files: dict[pathlib.Path, str] = {_CONFIG_PATH: _CODEX_TOML}

    def read_text(self, path: pathlib.Path) -> str | None:
        return self.files.get(path)

    def write_text_atomic(self, path: pathlib.Path, text: str) -> None:
        self.files[path] = text


class _ResourceService:
    def __init__(self) -> None:
        self.resources: dict[str, Resource] = {}

    async def register(self, kind, name, config, actor, description=None, **_) -> Resource:
        r = Resource(
            id=100,
            kind=kind,
            name=name,
            description=description,
            config=config,
            enabled=True,
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.resources[name] = r
        return r

    async def get(self, ref: ResourceRef) -> Resource:
        return self.resources[ref.name]

    async def list(self, kind=None, enabled=None) -> list[Resource]:
        return list(self.resources.values())

    async def delete(self, ref: ResourceRef, actor: str) -> None:
        self.resources.pop(ref.name, None)


class _AuditRepo:
    async def insert(self, entry) -> None:
        pass

    async def query(self, **_) -> list:
        return []


def _make_db(tmp_path: pathlib.Path) -> pathlib.Path:
    db_path = tmp_path / "coffer.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(_SCHEMA)
    conn.commit()
    conn.close()
    return db_path


async def _inflight_writer(db_path: pathlib.Path, lock_held: asyncio.Event) -> None:
    # Open write transaction on the same DB; the commit below only runs
    # if the event loop is still advancing while the credential write
    # under test waits for the lock.
    async with aiosqlite.connect(db_path) as wconn:
        await wconn.execute(
            "INSERT INTO credentials (ref, ciphertext, created_at, updated_at) "
            "VALUES ('inflight', X'00', 't', 't')"
        )
        lock_held.set()
        await asyncio.sleep(0.2)
        await wconn.commit()


async def test_adopt_credential_write_survives_inflight_async_writer(
    tmp_path: pathlib.Path,
) -> None:
    db_path = _make_db(tmp_path)

    creds = EncryptedCredentialStore(db_path=db_path, key=Fernet.generate_key())
    svc = AgentMcpEntryService(
        agent_service=_AgentLookup(),
        audit=AuditService(_AuditRepo()),
        store=_FileStore(),
        resource_service=_ResourceService(),
        credentials=creds,
    )

    lock_held = asyncio.Event()

    async def adopt() -> Resource:
        await lock_held.wait()
        return await svc.adopt("cx", "jira", secrets={"JIRA_API_TOKEN": "mcp/jira/JIRA_API_TOKEN"})

    _, resource = await asyncio.gather(_inflight_writer(db_path, lock_held), adopt())

    assert resource.name == "jira"
    assert creds.get("mcp/jira/JIRA_API_TOKEN") == "tok-123"


async def test_legacy_keychain_migration_survives_inflight_async_writer(
    tmp_path: pathlib.Path,
) -> None:
    db_path = _make_db(tmp_path)
    creds = EncryptedCredentialStore(db_path=db_path, key=Fernet.generate_key())

    class _LegacyKeyring:
        def __init__(self) -> None:
            self.data = {"mcp/jira/JIRA_API_TOKEN": "tok-456"}

        def get(self, ref: str) -> str | None:
            return self.data.get(ref)

        def set(self, ref: str, value: str) -> None:
            self.data[ref] = value

        def delete(self, ref: str) -> None:
            self.data.pop(ref, None)

    class _EmptyRepo:
        async def list(self) -> list:
            return []

    class _Audit:
        async def record(self, *args, **kwargs) -> None:
            pass

    lock_held = asyncio.Event()

    async def migrate() -> int:
        await lock_held.wait()
        return await migrate_legacy_keychain(
            kinds={},
            repo=_EmptyRepo(),
            legacy=_LegacyKeyring(),
            store=creds,
            audit=_Audit(),
            extra_refs=["mcp/jira/JIRA_API_TOKEN"],
        )

    _, moved = await asyncio.gather(_inflight_writer(db_path, lock_held), migrate())

    assert moved == 1
    assert creds.get("mcp/jira/JIRA_API_TOKEN") == "tok-456"
