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
    return {"mcp_server": Kind(name="mcp_server", display_name="MCP", config_schema=_FakeConfig)}


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
    resources = ResourceService(
        kinds=kinds or _kinds(), repo=SqlAlchemyResourceRepo(sm), audit=audit
    )

    master_key = MasterKeyManager(root / "master.key", _NoKeyring())
    if create_key:
        master_key.resolve(allow_create=True)
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


@pytest.mark.acceptance(spec="010-sync", scenario="conflicting edits stop the run for resolution")
async def test_conflict_then_resolve(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "confluence", {"value": "base"}, "test")
    await a.service.run()

    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    # Both edit the same resource; A pushes first.
    await a.resources.update_config(ResourceRef("mcp_server", "confluence"), {"value": "A2"}, "t")
    await a.service.run()
    await b.resources.update_config(ResourceRef("mcp_server", "confluence"), {"value": "B2"}, "t")
    conflicted = await b.service.run()

    assert conflicted.status is SyncStatus.CONFLICTED
    assert any("confluence" in p for p in conflicted.conflict_paths)

    resolved = await b.service.resolve("theirs", [])
    assert resolved.status is SyncStatus.CLEAN
    got = await b.resources.get(ResourceRef("mcp_server", "confluence"))
    assert got.config == {"value": "A2"}


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


async def test_resolve_theirs_accepts_a_deletion(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """delete/modify conflict: resolving --theirs toward the deleting side
    removes the file instead of erroring (review #281 finding 4)."""
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
    assert state.status is SyncStatus.CONFLICTED

    resolved = await b.service.resolve("theirs", [])
    assert resolved.status is not SyncStatus.CONFLICTED
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


async def test_rerun_does_not_blow_through_conflict(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    """Running sync again while conflicted must stay conflicted — never
    export over the unmerged files and silently resolve local-wins
    (review #283 blocker 2, service-level guard)."""
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    await a.resources.register("mcp_server", "contested", {"value": "base"}, "test")
    await a.service.run()
    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    await b.service.run()

    await a.resources.update_config(ResourceRef("mcp_server", "contested"), {"value": "A2"}, "test")
    await a.service.run()
    await b.resources.update_config(ResourceRef("mcp_server", "contested"), {"value": "B2"}, "test")
    state = await b.service.run()
    assert state.status is SyncStatus.CONFLICTED

    # A second (auto or manual) run must not auto-resolve the conflict.
    state = await b.service.run()
    assert state.status is SyncStatus.CONFLICTED
    # A's copy is untouched by B's rerun.
    await a.service.run()
    assert (await a.resources.get(ResourceRef("mcp_server", "contested"))).config == {"value": "A2"}

    # Resolution still works normally afterwards.
    resolved = await b.service.resolve("theirs", [])
    assert resolved.status is not SyncStatus.CONFLICTED
    assert (await b.resources.get(ResourceRef("mcp_server", "contested"))).config == {"value": "A2"}


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
