"""Two-machine sync, end to end (spec 010).

Two independent vaults (separate SQLite DBs, credential stores, workspaces) sync
through one real bare git repo, proving convergence, the ciphertext-only +
out-of-band-key credential model, conflict stop/resolve, and that only shared
state ever reaches the medium.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.sync.config_service import SyncConfigService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.identity import MachineIdentityService
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.service import SyncService
from coffer.application.sync.worker import SyncWorker
from coffer.domain.resource import Kind, ResourceRef
from coffer.domain.sync.models import SyncStatus
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
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from coffer.infrastructure.sync.git_repo import GitRepo
from coffer.infrastructure.sync.persistence import (
    SqlAlchemyMachineIdentityRepo,
    SqlAlchemySyncConfigRepo,
    SqlAlchemySyncStateRepo,
    SqlAlchemyTombstoneLedgerRepo,
)
from coffer.infrastructure.sync.workspace import Workspace


class _FakeConfig(BaseModel):
    value: str = ""


def _kinds() -> dict[str, Kind]:
    return {
        "mcp_server": Kind(
            name="mcp_server",
            display_name="MCP",
            config_schema=_FakeConfig,
            scope_axes=("machine", "agent"),
        )
    }


class _NoKeyring:
    """Master key never falls back to a keychain in these tests."""

    def get(self, ref: str) -> str | None:
        return None

    def set(self, ref: str, value: str) -> None:  # pragma: no cover - unused
        raise AssertionError("keychain not used")

    def delete(self, ref: str) -> None:  # pragma: no cover - unused
        pass


@dataclass
class Machine:
    name: str
    root: Path
    resources: ResourceService
    service: SyncService
    config_svc: SyncConfigService
    workspace: Workspace
    master_key: MasterKeyManager
    db_path: Path
    knowledge: Path
    sm: Any = None

    def cred_store(self) -> EncryptedCredentialStore:
        key = self.master_key.export_key()
        assert key is not None
        return EncryptedCredentialStore(self.db_path, key)


async def _make_machine(
    name: str,
    root: Path,
    remote: Path,
    *,
    create_key: bool,
    key_bytes: bytes | None = None,
    kinds: dict[str, Kind] | None = None,
    state_providers_factory: Any = None,
    home: str | None = None,
) -> Machine:
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "coffer.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))

    master_key = MasterKeyManager(root / "master.key", _NoKeyring())
    if key_bytes is not None:
        master_key.install_key(key_bytes)
    elif create_key:
        master_key.resolve(allow_create=True)
    key = master_key.export_key()
    resources = ResourceService(
        kinds=kinds or _kinds(),
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
        credentials=EncryptedCredentialStore(db_path, key) if key is not None else None,
    )
    cred_sync = CredentialSyncAdapter(db_path, master_key)

    knowledge = root / "live-knowledge"
    workspace = Workspace(root / "ws", trees=[("knowledge", knowledge)])
    git = GitRepo(root / "ws")

    config_svc = SyncConfigService(SqlAlchemySyncConfigRepo(sm), SqlAlchemySyncStateRepo(sm), audit)
    await config_svc.update_config(
        remote=str(remote),
        enabled=True,
        auto=False,
        interval_seconds=300,
        branch="main",
        actor="test",
    )
    ledger = SqlAlchemyTombstoneLedgerRepo(sm)
    resources.add_delete_listener(
        lambda ref, actor: None if actor == "sync" else ledger.record(ref.kind, ref.name)
    )
    providers = state_providers_factory(resources, sm) if state_providers_factory else ()
    exporter = SyncExporter(
        resources, cred_sync, workspace, ledger, state_providers=providers, home=home
    )
    importer = SyncImporter(resources, cred_sync, workspace, state_providers=providers, home=home)
    identity = MachineIdentityService(
        SqlAlchemyMachineIdentityRepo(sm),
        audit,
        new_id=lambda: f"01MACHINE{name * 17}"[:26].upper(),
        default_name=lambda: name,
    )
    service = SyncService(
        config=config_svc,
        git=git,
        exporter=exporter,
        importer=importer,
        credentials=cred_sync,
        master_key=master_key,
        audit=audit,
        identity=identity,
        workspace=workspace,
        coffer_version="0.0.0-test",
        home=home,
        resources=resources,
    )
    return Machine(
        name=name,
        root=root,
        resources=resources,
        service=service,
        config_svc=config_svc,
        workspace=workspace,
        master_key=master_key,
        db_path=db_path,
        knowledge=knowledge,
        sm=sm,
    )


@pytest_asyncio.fixture
async def remote(tmp_path):  # type: ignore[no-untyped-def]
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    return bare


@pytest.mark.acceptance(spec="010-sync", scenario="round-trip vault state to a second machine")
@pytest.mark.acceptance(spec="010-sync", scenario="locked credentials before key bootstrap")
@pytest.mark.acceptance(spec="010-sync", scenario="master key never enters the medium")
async def test_round_trip_and_credential_bootstrap(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    # A has a resource, a knowledge file, and a credential.
    await a.resources.register("mcp_server", "confluence", {"value": "A"}, "test")
    a.knowledge.mkdir(parents=True, exist_ok=True)
    (a.knowledge / "note.md").write_text("hello from A\n", encoding="utf-8")
    a.cred_store().set("cred-x", "super-secret")

    state_a = await a.service.run()
    assert state_a.status is SyncStatus.CLEAN

    # B starts with NO master key.
    b = await _make_machine("B", tmp_path / "B", remote, create_key=False)
    state_b = await b.service.run()

    # Resource + knowledge file converged.
    got = await b.resources.get(ResourceRef("mcp_server", "confluence"))
    assert got.config == {"value": "A"}
    assert (b.knowledge / "note.md").read_text() == "hello from A\n"

    # Credential ciphertext arrived but is locked (no key yet).
    assert state_b.status is SyncStatus.CREDENTIALS_LOCKED
    assert "cred-x" in state_b.locked_refs

    # The master key is NOT anywhere in the medium.
    for rel in b.workspace.list_files():
        assert "master" not in rel.lower()
    creds = b.workspace.read_credential_blobs()
    assert set(creds) == {"cred-x"}

    # Bootstrap the key out-of-band, then it decrypts and unlocks.
    key_file = tmp_path / "exported.key"
    await a.service.export_key(str(key_file))
    unlocked = await b.service.import_key(str(key_file))
    assert unlocked.status is SyncStatus.CLEAN
    assert unlocked.locked_refs == []
    assert b.cred_store().get("cred-x") == "super-secret"


@pytest.mark.acceptance(
    spec="010-sync", scenario="conflicting edits auto-resolve to the most recently synced edit"
)
async def test_conflict_auto_resolves_newest_wins(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "confluence", {"value": "base"}, "test")
    await a.service.run()

    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    # Both edit the same resource; A pushes first, B's edit is the newer one.
    await a.resources.update_config(ResourceRef("mcp_server", "confluence"), {"value": "A2"}, "t")
    await a.service.run()
    await b.resources.update_config(ResourceRef("mcp_server", "confluence"), {"value": "B2"}, "t")
    state = await b.service.run()

    # No user-facing conflict: the run auto-resolves (newest commit per path
    # wins; a tie keeps ours = the machine running the merge) and completes.
    assert state.status is not SyncStatus.CONFLICTED
    got = await b.resources.get(ResourceRef("mcp_server", "confluence"))
    assert got.config == {"value": "B2"}

    # A converges on the same winner on its next run.
    await a.service.run()
    got_a = await a.resources.get(ResourceRef("mcp_server", "confluence"))
    assert got_a.config == {"value": "B2"}


@pytest.mark.acceptance(spec="010-sync", scenario="auto-sync converges after a change")
async def test_auto_sync_converges(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    # Enable auto-sync on both; interval 0 so each tick is due immediately.
    for m in (a, b):
        await m.config_svc.update_config(
            remote=str(remote),
            enabled=True,
            auto=True,
            interval_seconds=30,
            branch="main",
            actor="test",
        )
    a_worker = SyncWorker(a.service, a.config_svc)
    b_worker = SyncWorker(b.service, b.config_svc)

    # A registers a resource; its worker tick pushes it.
    await a.resources.register("mcp_server", "shared", {"value": "auto"}, "test")
    await a_worker._maybe_sync()

    # B's worker tick pulls and imports it — no manual command on either side.
    await b_worker._maybe_sync()
    got = await b.resources.get(ResourceRef("mcp_server", "shared"))
    assert got.config == {"value": "auto"}


@pytest.mark.acceptance(spec="010-sync", scenario="only shared state syncs")
async def test_only_shared_state_in_medium(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "x", {"value": "1"}, "test")
    await a.service.run()

    files = a.workspace.list_files()
    assert "manifest.json" in files
    assert any(f.startswith("resources/") for f in files)
    # No local-only artifacts ever reach the workspace.
    assert not any(f.endswith(".db") for f in files)
    assert not any("daemon.json" in f for f in files)
    assert not any(f.startswith("logs/") for f in files)


@pytest.mark.acceptance(spec="010-sync", scenario="machines are visible after they sync")
async def test_machines_visible_after_sync(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    # B sees both machines, with itself marked local.
    identity_b, machines_b = await b.service.list_machines()
    assert {m.display_name for m in machines_b} == {"A", "B"}
    assert sum(1 for m in machines_b if m.machine_id == identity_b.machine_id) == 1

    # A pulls B's entry; every entry carries platform + last-sync time.
    await a.service.run()
    _identity_a, machines_a = await a.service.list_machines()
    assert {m.display_name for m in machines_a} == {"A", "B"}
    for m in machines_a:
        assert m.platform
        assert m.last_sync_at is not None

    # Renaming A propagates to B after the next round trip.
    await a.service.rename_machine("studio", actor="test")
    await a.service.run()
    await b.service.run()
    _identity_b2, machines_b2 = await b.service.list_machines()
    assert {m.display_name for m in machines_b2} == {"studio", "B"}


async def test_idle_run_does_not_rechurn_machine_entry(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """A no-change run must not rewrite the fresh machine entry (no commit chains)."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.service.run()
    entry_file = a.root / "ws" / "machines"
    first = next(entry_file.glob("*.json")).read_text(encoding="utf-8")

    await a.service.run()  # nothing changed since the last run
    second = next(entry_file.glob("*.json")).read_text(encoding="utf-8")
    assert second == first


async def test_stale_machine_entry_refreshed_by_heartbeat(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """An entry >24h old is rewritten even when the run has no other changes."""
    from datetime import UTC, datetime, timedelta

    from coffer.domain.sync.models import MachineEntry

    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.service.run()

    identity, entries = await a.service.list_machines()
    own = next(e for e in entries if e.machine_id == identity.machine_id)
    stale_ts = datetime.now(tz=UTC) - timedelta(hours=25)
    a.workspace.write_machine_entry(
        MachineEntry(
            machine_id=own.machine_id,
            display_name=own.display_name,
            platform=own.platform,
            os_version=own.os_version,
            coffer_version=own.coffer_version,
            last_sync_at=stale_ts,
        )
    )
    # Commit the staled entry so the tree is clean — isolating the heartbeat
    # branch from the has_changes() branch.
    GitRepo(a.root / "ws").commit_all("stale the entry")

    await a.service.run()
    _identity, refreshed = await a.service.list_machines()
    own_after = next(e for e in refreshed if e.machine_id == identity.machine_id)
    assert own_after.last_sync_at is not None
    assert own_after.last_sync_at > stale_ts + timedelta(hours=1)


async def test_corrupt_machine_entry_never_blocks_sync(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """A truncated/hand-mangled machines/*.json is skipped, not fatal."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.service.run()

    machines_dir = a.root / "ws" / "machines"
    (machines_dir / "01CORRUPTED0000000000000AA.json").write_text("{ trunca", encoding="utf-8")

    state = await a.service.run()  # must not raise; the bad entry is ignored
    assert state.status is SyncStatus.CLEAN
    _identity, entries = await a.service.list_machines()
    assert {e.display_name for e in entries} == {"A"}


@pytest.mark.acceptance(spec="010-sync", scenario="deletions propagate as tombstones")
async def test_deletion_propagates_as_tombstone(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "shared", {"value": "x"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()
    assert (await b.resources.get(ResourceRef("mcp_server", "shared"))).config == {"value": "x"}

    # A deletes; the deletion reaches B as an explicit tombstone.
    await a.resources.delete(ResourceRef("mcp_server", "shared"), "test")
    await a.service.run()
    await b.service.run()
    assert not [r for r in await b.resources.list() if r.name == "shared"]
    assert any(t.kind == "mcp_server" and t.name == "shared" for t in b.workspace.read_tombstones())
    assert not any(f == "resources/mcp_server/shared.yaml" for f in b.workspace.list_files())

    # B re-registers: the resource resurrects everywhere, the tombstone clears.
    await b.resources.register("mcp_server", "shared", {"value": "again"}, "test")
    await b.service.run()
    await a.service.run()
    assert (await a.resources.get(ResourceRef("mcp_server", "shared"))).config == {"value": "again"}
    assert not a.workspace.read_tombstones()


@pytest.mark.acceptance(
    spec="010-sync", scenario="a failed import never deletes the resource elsewhere"
)
async def test_failed_import_quarantines_instead_of_deleting(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    from pydantic import field_validator

    class _PickyConfig(BaseModel):
        value: str = ""

        @field_validator("value")
        @classmethod
        def _reject_only_a(cls, v: str) -> str:
            if v == "only-a":
                raise ValueError("this machine cannot hold 'only-a'")
            return v

    picky = {"mcp_server": Kind(name="mcp_server", display_name="MCP", config_schema=_PickyConfig)}
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "portable", {"value": "only-a"}, "test")
    await a.service.run()

    # B cannot import that config — quarantined, not fatal, and status stays clean.
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True, kinds=picky)
    state_b = await b.service.run()
    assert state_b.status is SyncStatus.CLEAN
    assert state_b.quarantined_refs == ["mcp_server:portable"]
    assert not [r for r in await b.resources.list() if r.name == "portable"]

    # Another full round trip: B's export preserves the doc; A keeps the resource.
    await b.service.run()
    await a.service.run()
    assert (await a.resources.get(ResourceRef("mcp_server", "portable"))).config == {
        "value": "only-a"
    }
    assert any(f == "resources/mcp_server/portable.yaml" for f in b.workspace.list_files())


@pytest.mark.acceptance(spec="010-sync", scenario="machine x agent activation scope rides sync")
async def test_scope_rides_sync_and_converges(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """Scope (ADR-045) travels through the sync medium like any other curated
    field: a changed scope on an existing row converges, and a resource
    registered WITH a scope already set converges its scope on first import
    too (Task 6)."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "confluence", {"value": "A"}, "test")
    await a.resources.update_scope(
        ResourceRef("mcp_server", "confluence"), {"machine-1": ["agent-a"]}, actor="test"
    )
    await a.service.run()

    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()
    got = await b.resources.get(ResourceRef("mcp_server", "confluence"))
    assert got.scope == {"machine-1": ["agent-a"]}

    # A changes scope on the existing row; B's next import converges onto it.
    await a.resources.update_scope(
        ResourceRef("mcp_server", "confluence"), {"machine-2": "*"}, actor="test"
    )
    await a.service.run()
    await b.service.run()
    got2 = await b.resources.get(ResourceRef("mcp_server", "confluence"))
    assert got2.scope == {"machine-2": "*"}

    # A registers a brand-new resource and scopes it before B has ever seen
    # it: the first import that creates the row on B must also apply scope.
    await a.resources.register("mcp_server", "fresh", {"value": "new"}, "test")
    await a.resources.update_scope(
        ResourceRef("mcp_server", "fresh"), {"machine-3": "*"}, actor="test"
    )
    await a.service.run()
    await b.service.run()
    fresh = await b.resources.get(ResourceRef("mcp_server", "fresh"))
    assert fresh.scope == {"machine-3": "*"}

    # Clearing scope back to unscoped converges too.
    await a.resources.update_scope(ResourceRef("mcp_server", "confluence"), None, actor="test")
    await a.service.run()
    await b.service.run()
    got3 = await b.resources.get(ResourceRef("mcp_server", "confluence"))
    assert got3.scope is None


@pytest.mark.acceptance(
    spec="010-sync", scenario="an older build refuses a workspace one schema ahead"
)
async def test_manifest_gate_rejects_next_schema_version(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """The too-new gate must hold at the very next version boundary, not just
    for a wildly future one — meaningful after the v4 bump (Task 6)."""
    import json as _json

    from coffer.domain.sync.errors import SyncWorkspaceTooNew
    from coffer.domain.sync.manifest import SCHEMA_VERSION

    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "baseline", {"value": "1"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    ws = a.root / "ws"
    repo = GitRepo(ws)
    repo.pull("main")
    (ws / "manifest.json").write_text(
        _json.dumps({"schema_version": SCHEMA_VERSION + 1}) + "\n", encoding="utf-8"
    )
    repo.commit_all("next layout")
    repo.push("main")

    with pytest.raises(SyncWorkspaceTooNew):
        await b.service.run()
    names = {r.name for r in await b.resources.list()}
    assert "baseline" in names


@pytest.mark.acceptance(spec="010-sync", scenario="an older build refuses a newer workspace")
async def test_older_build_refuses_newer_workspace(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    import json as _json

    from coffer.domain.sync.errors import SyncWorkspaceTooNew

    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "baseline", {"value": "1"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()  # shared history + baseline resource on B

    # A future build pushes a newer workspace layout plus a resource doc only
    # that layout understands.
    ws = a.root / "ws"
    repo = GitRepo(ws)
    repo.pull("main")  # catch up with B's push before rewriting history forward
    (ws / "manifest.json").write_text(_json.dumps({"schema_version": 99}) + "\n", encoding="utf-8")
    (ws / "resources" / "mcp_server" / "newer.yaml").write_text(
        "config: {value: '2'}\ndescription: null\nenabled: true\nkind: mcp_server\nname: newer\n",
        encoding="utf-8",
    )
    repo.commit_all("future layout")
    repo.push("main")

    with pytest.raises(SyncWorkspaceTooNew):
        await b.service.run()
    # Nothing from the newer workspace was imported; the baseline is untouched.
    names = {r.name for r in await b.resources.list()}
    assert "newer" not in names
    assert "baseline" in names


async def test_interrupted_run_does_not_resurrect_deletion(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """A run that merged a tombstone but died before import (push race / crash)
    must not resurrect the deletion on its next run (review #281 blocker 2)."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "shared", {"value": "x"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    await a.resources.delete(ResourceRef("mcp_server", "shared"), "test")
    await a.service.run()

    # Simulate B's interrupted run: the pull merged A's tombstone into B's
    # workspace, but the import never ran — locally the resource is still live.
    GitRepo(b.root / "ws").pull("main")
    assert any(t.name == "shared" for t in b.workspace.read_tombstones())
    assert [r for r in await b.resources.list() if r.name == "shared"]

    # B's next full run must apply the deletion, not undo it.
    await b.service.run()
    assert not [r for r in await b.resources.list() if r.name == "shared"]
    await a.service.run()
    assert not [r for r in await a.resources.list() if r.name == "shared"]


async def test_tombstone_provenance_stable_across_importers(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """Machines that merely import a deletion never rewrite its tombstone."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "shared", {"value": "x"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    await a.resources.delete(ResourceRef("mcp_server", "shared"), "test")
    await a.service.run()
    original = next(t for t in a.workspace.read_tombstones() if t.name == "shared")

    await b.service.run()  # applies the deletion on B
    await b.service.run()  # B's follow-up export must not touch the tombstone
    await a.service.run()
    final = next(t for t in a.workspace.read_tombstones() if t.name == "shared")
    assert final.deleted_at == original.deleted_at
    assert final.by == original.by


async def test_quarantined_ref_never_gets_a_tombstone(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """A stale deletion ledger row must not fight a quarantined doc with
    add/remove tombstone ping-pong (review #281 finding 3)."""
    from pydantic import field_validator

    class _PickyConfig(BaseModel):
        value: str = ""

        @field_validator("value")
        @classmethod
        def _reject_only_b(cls, v: str) -> str:
            if v == "only-b":
                raise ValueError("machine A cannot hold 'only-b'")
            return v

    picky = {"mcp_server": Kind(name="mcp_server", display_name="MCP", config_schema=_PickyConfig)}
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True, kinds=picky)
    await a.resources.register("mcp_server", "contested", {"value": "ok"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    # A deletes; B applies the deletion, then re-creates a config A rejects.
    await a.resources.delete(ResourceRef("mcp_server", "contested"), "test")
    await a.service.run()
    await b.service.run()
    await b.resources.register("mcp_server", "contested", {"value": "only-b"}, "test")
    await b.service.run()

    # A quarantines the new doc; its stale ledger row must not emit a tombstone.
    state_a = await a.service.run()
    assert state_a.quarantined_refs == ["mcp_server:contested"]
    files = a.workspace.list_files()
    assert "resources/mcp_server/contested.yaml" in files
    assert not any(f.startswith("tombstones/") and "contested" in f for f in files)

    # And the workspace stays stable on B's next round trip (no ping-pong).
    await b.service.run()
    assert (await b.resources.get(ResourceRef("mcp_server", "contested"))).config == {
        "value": "only-b"
    }


async def test_too_new_gate_holds_on_second_run(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """The schema gate must not disarm itself: run 2 fails like run 1, the
    remote manifest keeps its newer version, and status shows the error
    (review #281 blocker 1)."""
    import json as _json

    from coffer.domain.sync.errors import SyncWorkspaceTooNew

    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    ws = a.root / "ws"
    repo = GitRepo(ws)
    repo.pull("main")
    (ws / "manifest.json").write_text(_json.dumps({"schema_version": 99}) + "\n", encoding="utf-8")
    repo.commit_all("future layout")
    repo.push("main")

    with pytest.raises(SyncWorkspaceTooNew):
        await b.service.run()  # run 1: pull merges v99, import gate fires
    with pytest.raises(SyncWorkspaceTooNew):
        await b.service.run()  # run 2: early gate fires BEFORE export
    # The workspace manifest was not downgraded back to 2.
    data = _json.loads((b.root / "ws" / "manifest.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 99
    # The failure is visible in sync state, not silently clean.
    state = await b.service.status()
    assert state.status is SyncStatus.ERROR
    assert "newer" in (state.last_error or "")


async def test_auto_resolve_handles_delete_modify(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """delete/modify conflict auto-resolves without user action, and the
    tombstone machinery still decides the outcome: an edit that PREDATES the
    deletion never resurrects the resource (review #281 finding 4 semantics,
    carried into auto-resolve)."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "contested", {"value": "base"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    # A deletes and pushes; B edits the same resource -> delete/modify conflict.
    await a.resources.delete(ResourceRef("mcp_server", "contested"), "test")
    await a.service.run()
    await b.resources.update_config(
        ResourceRef("mcp_server", "contested"), {"value": "edited"}, "test"
    )
    state = await b.service.run()
    assert state.status is not SyncStatus.CONFLICTED

    # B's edit predates A's tombstone, so the deletion wins as the runs
    # settle: B withholds the stale doc from export and applies the
    # tombstone on import.
    await b.service.run()
    assert not [r for r in await b.resources.list() if r.name == "contested"]


async def test_expired_tombstone_pruned_from_workspace(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime, timedelta

    from coffer.domain.sync.models import TOMBSTONE_TTL_SECONDS, Tombstone

    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.service.run()
    a.workspace.write_tombstone(
        Tombstone(
            kind="mcp_server",
            name="ancient",
            deleted_at=datetime.now(tz=UTC) - timedelta(seconds=TOMBSTONE_TTL_SECONDS + 3600),
            by="someone",
        )
    )
    await a.service.run()
    assert not any(t.name == "ancient" for t in a.workspace.read_tombstones())


async def test_update_failure_quarantines_and_keeps_local_row(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """An UPDATE that fails locally quarantines the ref, keeps the old local
    row, and never re-exports the stale local state over the remote intent."""
    from pydantic import field_validator

    class _PickyConfig(BaseModel):
        value: str = ""

        @field_validator("value")
        @classmethod
        def _reject_v2(cls, v: str) -> str:
            if v == "v2":
                raise ValueError("machine B cannot hold 'v2'")
            return v

    picky = {"mcp_server": Kind(name="mcp_server", display_name="MCP", config_schema=_PickyConfig)}
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "shared", {"value": "v1"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True, kinds=picky)
    await b.service.run()

    await a.resources.update_config(ResourceRef("mcp_server", "shared"), {"value": "v2"}, "test")
    await a.service.run()
    state_b = await b.service.run()
    assert state_b.quarantined_refs == ["mcp_server:shared"]
    # B keeps its old importable row; the workspace keeps A's new intent.
    assert (await b.resources.get(ResourceRef("mcp_server", "shared"))).config == {"value": "v1"}
    await b.service.run()
    await a.service.run()
    assert (await a.resources.get(ResourceRef("mcp_server", "shared"))).config == {"value": "v2"}


async def test_tombstone_delete_failure_reports_error(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """A kind on_delete hook that refuses the deletion surfaces as an ERROR run
    instead of silently keeping the resource."""
    from coffer.domain.errors import ConfigValidationError

    def _refuse(ref) -> None:  # type: ignore[no-untyped-def]
        raise ConfigValidationError("cannot tear down on this machine")

    stubborn = {
        "mcp_server": Kind(
            name="mcp_server",
            display_name="MCP",
            config_schema=_FakeConfig,
            on_delete=_refuse,
        )
    }
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "sticky", {"value": "x"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True, kinds=stubborn)
    await b.service.run()

    await a.resources.delete(ResourceRef("mcp_server", "sticky"), "test")
    await a.service.run()
    state_b = await b.service.run()
    assert state_b.status is SyncStatus.ERROR
    assert "sticky" in (state_b.last_error or "")


async def test_near_real_time_change_and_probe_convergence(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """Push side: a local change schedules a debounced run. Pull side: the
    remote-head probe detects the other machine's push — no interval wait."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    for m in (a, b):
        await m.config_svc.update_config(
            remote=str(remote),
            enabled=True,
            auto=True,
            interval_seconds=3600,  # fallback effectively off after startup
            branch="main",
            actor="test",
            poll_remote_seconds=5,
        )

    class _Clock:
        now = 1000.0

        def __call__(self) -> float:
            return self.now

    clock_a, clock_b = _Clock(), _Clock()
    worker_a = SyncWorker(
        a.service, a.config_svc, GitRepo(a.root / "ws"), debounce_seconds=1.0, clock=clock_a
    )
    worker_b = SyncWorker(
        b.service, b.config_svc, GitRepo(b.root / "ws"), debounce_seconds=1.0, clock=clock_b
    )
    await worker_a._maybe_sync()  # startup sweeps
    await worker_b._maybe_sync()

    # A registers a resource; the change listener path is the worker's notify.
    clock_a.now += 3  # leave the startup run's suppression grace window
    await a.resources.register("mcp_server", "instant", {"value": "nrt"}, "test")
    worker_a.notify_change()
    clock_a.now += 2  # past the 1s debounce
    await worker_a._maybe_sync()

    # B's probe sees the moved head and converges without any interval wait.
    clock_b.now += 6  # past poll_remote_seconds
    await worker_b._maybe_sync()
    got = await b.resources.get(ResourceRef("mcp_server", "instant"))
    assert got.config == {"value": "nrt"}


async def test_rerun_settles_a_preexisting_merge_deterministically(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """A run entered with an unresolved merge on disk (e.g. a crashed prior
    run) must NOT export over the conflicted files (review #283 blocker 2);
    it auto-resolves them by the same newest-wins policy FIRST, then proceeds
    — both machines converge on the same winner."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "contested", {"value": "base"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    await a.resources.update_config(ResourceRef("mcp_server", "contested"), {"value": "A2"}, "test")
    await a.service.run()
    await b.resources.update_config(ResourceRef("mcp_server", "contested"), {"value": "B2"}, "test")
    # Simulate a run that merged into conflict and died before resolving:
    # produce the conflicted working tree directly via git on B's workspace.
    b_git = GitRepo(b.root / "ws")
    (b.root / "ws" / "resources" / "mcp_server" / "contested.yaml").write_text(
        "config:\n  value: B2\ndescription: null\nenabled: true\n"
        "kind: mcp_server\nname: contested\n",
        encoding="utf-8",
    )
    b_git.commit_all("b edit")
    outcome = b_git.pull("main")
    assert outcome.is_conflict

    # The next run settles the leftover merge (newest edit wins: B2) instead
    # of parking in conflicted or exporting over the unmerged files.
    state = await b.service.run()
    assert state.status is not SyncStatus.CONFLICTED
    assert (await b.resources.get(ResourceRef("mcp_server", "contested"))).config == {"value": "B2"}
    await a.service.run()
    assert (await a.resources.get(ResourceRef("mcp_server", "contested"))).config == {"value": "B2"}


async def test_import_preserves_local_derived_indexes(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """The workspace→live mirror is diff-aware: it must not delete the
    machine-local derived indexes nor rewrite unchanged files
    (review #283 blocker 1, root cause)."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    a.knowledge.mkdir(parents=True, exist_ok=True)
    (a.knowledge / "note.md").write_text("v1\n", encoding="utf-8")
    (a.knowledge / "INDEX.md").write_text("machine-local index\n", encoding="utf-8")
    await a.service.run()

    # The derived index survives the import and the note is intact.
    assert (a.knowledge / "INDEX.md").read_text() == "machine-local index\n"
    assert (a.knowledge / "note.md").read_text() == "v1\n"

    # A no-change run must not rewrite the unchanged live file (same inode).
    ino_before = (a.knowledge / "note.md").stat().st_ino
    await a.service.run()
    assert (a.knowledge / "note.md").stat().st_ino == ino_before
    assert (a.knowledge / "INDEX.md").exists()


@pytest.mark.acceptance(spec="010-sync", scenario="config paths follow each machine's home")
async def test_home_paths_follow_the_machine(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True, home="/Users/alice")
    await a.resources.register("mcp_server", "claude", {"value": "/Users/alice/.claude"}, "test")
    await a.service.run()
    # The medium speaks ${HOME}, never a literal home.
    doc = (a.root / "ws" / "resources" / "mcp_server" / "claude.yaml").read_text()
    assert "${HOME}/.claude" in doc
    assert "/Users/alice" not in doc

    b = await _make_machine("B", tmp_path / "B", remote, create_key=True, home="/home/bob")
    await b.service.run()
    got = await b.resources.get(ResourceRef("mcp_server", "claude"))
    assert got.config == {"value": "/home/bob/.claude"}


@pytest.mark.acceptance(
    spec="010-sync", scenario="a per-machine override survives sync round trips"
)
async def test_override_round_trip_never_leaks(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "tool", {"value": "/usr/local/bin/x"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    # B overrides the path for its own hardware; applies on its next run.
    await b.service.set_override(
        "mcp_server", "tool", {"value": "/opt/homebrew/bin/x"}, actor="test"
    )
    await b.service.run()
    assert (await b.resources.get(ResourceRef("mcp_server", "tool"))).config == {
        "value": "/opt/homebrew/bin/x"
    }

    # The specialization never leaks into the medium or onto A.
    await a.service.run()
    assert (await a.resources.get(ResourceRef("mcp_server", "tool"))).config == {
        "value": "/usr/local/bin/x"
    }
    await b.service.run()
    await a.service.run()
    assert (await a.resources.get(ResourceRef("mcp_server", "tool"))).config == {
        "value": "/usr/local/bin/x"
    }

    # A shared edit to a NON-overridden field still reaches B (patch reapplies).
    await a.resources.update_config(
        ResourceRef("mcp_server", "tool"), {"value": "/usr/local/bin/x2"}, "test"
    )
    await a.service.run()
    await b.service.run()
    assert (await b.resources.get(ResourceRef("mcp_server", "tool"))).config == {
        "value": "/opt/homebrew/bin/x"  # override still wins on B
    }

    # Unset: B converges back to the shared value on its next run.
    await b.service.unset_override("mcp_server", "tool", actor="test")
    await b.service.run()
    assert (await b.resources.get(ResourceRef("mcp_server", "tool"))).config == {
        "value": "/usr/local/bin/x2"
    }


async def test_dict_valued_override_round_trips(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """A nested/dict patch (and a type-changing one) must revert cleanly on
    export — never publish a corrupted {} (review #286 finding 2)."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "tool", {"value": "shared"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    # Type-changing patch: scalar shared value overridden by a dict.
    await b.service.set_override("mcp_server", "tool", {"value": {"cmd": "/opt/x"}}, actor="test")
    await b.service.run()
    await a.service.run()
    assert (await a.resources.get(ResourceRef("mcp_server", "tool"))).config == {
        "value": "shared"  # never {} and never the dict
    }
    doc = (a.root / "ws" / "resources" / "mcp_server" / "tool.yaml").read_text()
    assert "shared" in doc and "/opt/x" not in doc


async def test_override_before_first_export_keeps_the_baseline(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """An override set before the resource ever reached the medium must not
    withhold the key from the shared doc (review #286 finding 3)."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "fresh", {"value": "/usr/local/bin/x"}, "test")
    await a.service.set_override(
        "mcp_server", "fresh", {"value": "/opt/homebrew/bin/x"}, actor="test"
    )
    await a.service.run()

    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()
    got = await b.resources.get(ResourceRef("mcp_server", "fresh"))
    assert got.config == {"value": "/usr/local/bin/x"}  # baseline, not missing


async def test_override_ref_segments_validated(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    from coffer.domain.errors import ConfigValidationError

    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    with pytest.raises(ConfigValidationError):
        await a.service.set_override("..", "x", {"a": 1}, actor="test")
    with pytest.raises(ConfigValidationError):
        await a.service.set_override("mcp_server", "a/b", {"a": 1}, actor="test")


@pytest.mark.acceptance(
    spec="010-sync", scenario="a first sync against a populated remote merges, never deletes"
)
async def test_first_export_preserves_unimported_foreign_content(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """The 2026-07-10 incident guard: content that arrived in the workspace
    but was never imported here (resource docs, tree files, credential
    ciphertext) survives an export that runs before any completed import."""
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    ws = b.root / "ws"
    (ws / "resources" / "mcp_server").mkdir(parents=True)
    (ws / "resources" / "mcp_server" / "foreign.yaml").write_text(
        "config:\n  value: theirs\ndescription: null\nenabled: true\n"
        "kind: mcp_server\nname: foreign\n",
        encoding="utf-8",
    )
    (ws / "knowledge").mkdir(parents=True, exist_ok=True)
    (ws / "knowledge" / "foreign-note.md").write_text("from A\n", encoding="utf-8")
    (ws / "credentials").mkdir(parents=True)
    (ws / "credentials" / "foreign-ref.enc").write_text("Zm9v\n", encoding="utf-8")

    await b.service.run(pull=False, push=False)

    assert (ws / "resources" / "mcp_server" / "foreign.yaml").exists()
    assert (ws / "knowledge" / "foreign-note.md").read_text() == "from A\n"
    assert (ws / "credentials" / "foreign-ref.enc").exists()


async def test_auto_resolve_handles_non_ascii_paths(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """A conflicted Chinese-named file auto-resolves instead of crashing on a
    C-quoted path (core.quotepath) — review #290 finding 1."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    a.knowledge.mkdir(parents=True, exist_ok=True)
    (a.knowledge / "记忆笔记.md").write_text("base\n", encoding="utf-8")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    (a.knowledge / "记忆笔记.md").write_text("from A\n", encoding="utf-8")
    await a.service.run()
    (b.knowledge / "记忆笔记.md").write_text("from B\n", encoding="utf-8")
    state = await b.service.run()

    assert state.status is not SyncStatus.CONFLICTED
    assert state.status is not SyncStatus.ERROR
    assert (b.knowledge / "记忆笔记.md").read_text() == "from B\n"
    await a.service.run()
    assert (a.knowledge / "记忆笔记.md").read_text() == "from B\n"


async def test_deletions_still_propagate_after_a_transient_error(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """A machine that HAS imported keeps propagating deletions even when its
    previous run failed — a network flake must not resurrect the user's
    deletion via the next import (review #290 finding 2)."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    a.knowledge.mkdir(parents=True, exist_ok=True)
    (a.knowledge / "note.md").write_text("v1\n", encoding="utf-8")
    await a.service.run()  # clean run: imported at least once

    # A transient failure is recorded (last_sync_at survives, status=ERROR).
    await a.service._record_error("fetch flake")

    # The user deletes a live file; the next run must still export the
    # deletion, not silently restore the file from the workspace.
    (a.knowledge / "note.md").unlink()
    state = await a.service.run()
    assert state.status is SyncStatus.CLEAN
    assert not (a.knowledge / "note.md").exists()
    assert not (a.root / "ws" / "knowledge" / "note.md").exists()


# ---------------------------------------------------------------------------
# Credential freshness guards (2026-07-10 stale-clobber incident).
# A Fernet blob's embedded encryption time orders ciphertext without any key;
# an older encryption must never replace a newer one — not via merge conflict,
# not via export after an interrupted run, not via import from a machine that
# still holds the stale copy.
# ---------------------------------------------------------------------------

_REF = "channel/Telegram/bot-token"


def _blob(machine: Machine, value: bytes, ts: int) -> bytes:
    key = machine.master_key.export_key()
    assert key is not None
    return Fernet(key).encrypt_at_time(value, ts)


def _adapter(machine: Machine) -> CredentialSyncAdapter:
    return CredentialSyncAdapter(machine.db_path, machine.master_key)


@pytest.mark.acceptance(spec="010-sync", scenario="stale credential never wins a conflict")
async def test_conflicting_credential_edits_fresher_ciphertext_wins(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """Both machines rewrite the same ref from a shared base; the machine whose
    ciphertext is OLDER commits last. Newest-commit-wins used to hand the merge
    to the stale blob (the 2026-07-10 incident); the Fernet timestamp must win
    instead."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)

    _adapter(a).write_ciphertext(_REF, _blob(a, b"base", 1_500))
    await a.service.run()
    await b.service.run()  # B ingests the base blob

    fresh = _blob(a, b"fresh-token", 2_000)
    _adapter(a).write_ciphertext(_REF, fresh)
    await a.service.run()  # remote now holds the fresher blob

    # B rewrites the same ref with an OLDER encryption and syncs after A:
    # its commit is newer, its content is staler.
    _adapter(b).write_ciphertext(_REF, _blob(b, b"stale-token", 1_000))
    state = await b.service.run()

    assert state.status is not SyncStatus.CONFLICTED
    assert _adapter(b).read_ciphertext(_REF) == fresh

    await a.service.run()
    assert _adapter(a).read_ciphertext(_REF) == fresh


@pytest.mark.acceptance(
    spec="010-sync", scenario="interrupted run cannot re-export stale ciphertext"
)
async def test_export_after_interrupted_run_keeps_fresher_workspace_blob(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """A run that pulled a fresher blob but crashed before importing it leaves
    workspace newer than the DB; the next export must not clobber the
    workspace copy with the stale DB blob."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)

    stale = _blob(a, b"stale-token", 1_000)
    _adapter(a).write_ciphertext(_REF, stale)
    await a.service.run()
    await b.service.run()  # B: DB and workspace both hold the stale blob

    fresh = _blob(a, b"fresh-token", 2_000)
    _adapter(a).write_ciphertext(_REF, fresh)
    await a.service.run()  # remote now fresher

    # Simulate B's crash between pull and import: workspace has the fresher
    # blob, the DB still has the stale one.
    subprocess.run(
        ["git", "fetch", "origin", "main"],
        cwd=b.root / "ws",
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "merge", "--no-edit", "FETCH_HEAD"],
        cwd=b.root / "ws",
        check=True,
        capture_output=True,
    )
    assert _adapter(b).read_ciphertext(_REF) == stale

    await b.service.run()
    assert _adapter(b).read_ciphertext(_REF) == fresh

    await a.service.run()
    assert _adapter(a).read_ciphertext(_REF) == fresh


@pytest.mark.acceptance(
    spec="010-sync", scenario="stale blob from an unguarded machine is not imported"
)
async def test_import_keeps_local_credential_when_remote_holds_staler_blob(  # type: ignore[no-untyped-def]
    tmp_path, remote
) -> None:
    """A machine running an older build can still push a stale blob without
    conflict; importing it must not roll the local DB back."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)

    fresh = _blob(a, b"fresh-token", 2_000)
    _adapter(a).write_ciphertext(_REF, fresh)
    await a.service.run()
    await b.service.run()

    # Legacy machine: rewrite the blob file in B's workspace clone by hand and
    # push, bypassing every engine-side guard.
    stale = _blob(b, b"stale-token", 1_000)
    blob_path = b.root / "ws" / "credentials" / f"{_REF}.enc"
    blob_path.write_bytes(stale)
    subprocess.run(
        ["git", "commit", "-am", "legacy push"],
        cwd=b.root / "ws",
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", "HEAD:main"],
        cwd=b.root / "ws",
        check=True,
        capture_output=True,
    )

    await a.service.run()  # pulls the stale blob cleanly (fast-forward)
    assert _adapter(a).read_ciphertext(_REF) == fresh

    # A's next run heals the vault back to the fresher blob.
    await a.service.run()
    ws_blob = (a.root / "ws" / "credentials" / f"{_REF}.enc").read_bytes()
    assert ws_blob == fresh


@pytest.mark.acceptance(
    spec="010-sync", scenario="deleting a resource releases its credential everywhere"
)
async def test_delete_releases_credential_on_every_machine(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """A deleted channel's credential must not linger as an orphan row on any
    machine — orphans re-export forever and eventually clobber a re-created
    ref (the 2026-07-10 incident)."""

    class _TokenConfig(BaseModel):
        token_ref: str = ""

    def _secret_kinds() -> dict[str, Kind]:
        return {
            "mcp_server": Kind(
                name="mcp_server",
                display_name="MCP",
                config_schema=_TokenConfig,
                credential_ref_extractor=lambda cfg: (
                    {"token": cfg["token_ref"]} if cfg.get("token_ref") else {}
                ),
            )
        }

    a = await _make_machine("A", tmp_path / "A", remote, create_key=True, kinds=_secret_kinds())
    key = a.master_key.export_key()
    assert key is not None
    b = await _make_machine(
        "B", tmp_path / "B", remote, create_key=False, key_bytes=bytes(key), kinds=_secret_kinds()
    )

    a.cred_store().set(_REF, "token-value")
    await a.resources.register("mcp_server", "chan", {"token_ref": _REF}, "test")
    await a.service.run()
    await b.service.run()
    assert _adapter(b).read_ciphertext(_REF) is not None  # blob + resource reached B

    await a.resources.delete(ResourceRef("mcp_server", "chan"), "user")
    assert not a.cred_store().exists(_REF)  # released with its only citer

    await a.service.run()  # exports the tombstones, prunes the blob
    await b.service.run()  # applies them: resource AND credential row go
    assert _adapter(b).read_ciphertext(_REF) is None

    # No resurrection on later rounds (B's pre-pull export must not re-seed
    # the blob into the medium, and A must not re-import it).
    await a.service.run()
    await b.service.run()
    await a.service.run()
    assert _adapter(a).read_ciphertext(_REF) is None
    assert _adapter(b).read_ciphertext(_REF) is None
    assert not (a.root / "ws" / "credentials" / f"{_REF}.enc").exists()
