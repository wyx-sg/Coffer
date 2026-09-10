"""Vault export/import, end to end (spec vault-export-import, ADR: vault-export-import).

Two independent vaults (separate SQLite DBs, credential stores, knowledge
trees, and *homes*) exchange state through one export bundle directory on
disk. No git, no remote, no worker — the bundle is the only thing that moves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.service import SyncService
from coffer.domain.error_base import CofferError
from coffer.domain.resource import Kind, ResourceRef
from coffer.domain.sync.errors import SyncBundleInvalid, SyncBundleTooNew
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
from coffer.infrastructure.sync.bundle import Bundle
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter


class _FakeConfig(BaseModel):
    value: str = ""
    config_dir: str = ""


def _kinds() -> dict[str, Kind]:
    return {
        "mcp_server": Kind(
            name="mcp_server",
            display_name="MCP",
            config_schema=_FakeConfig,
            supports_scope=True,
        ),
        "agent": Kind(name="agent", display_name="Agent", config_schema=_FakeConfig),
    }


class _NoKeyring:
    """Master key never falls back to a keychain in these tests."""

    def get(self, ref: str) -> str | None:
        return None

    def set(self, ref: str, value: str) -> None:  # pragma: no cover - unused
        raise AssertionError("keychain not used")

    def delete(self, ref: str) -> None:  # pragma: no cover - unused
        pass


class _StubStateProvider:
    """A module-owned shared-state area (spec vault-export-import "Shared state")."""

    area = "peers"

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, object]] = {}
        self.fail_on: set[str] = set()

    async def export_docs(self) -> tuple[list[tuple[str, dict[str, object]]], list[str]]:
        return sorted(self.docs.items()), [""]

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[tuple[str, str]]:
        failures: list[tuple[str, str]] = []
        for path, payload in docs:
            if path in self.fail_on:
                failures.append((path, "cannot bind here"))
                continue
            self.docs[path] = payload
        return failures


class _RefusingGate:
    """An import gate that fails one named resource on this machine."""

    kind = "agent"

    def __init__(self, refuse: str) -> None:
        self.refuse = refuse

    async def validate(self, config: Any, *, scope: Any = None) -> None:
        if config.get("config_dir") == self.refuse:
            raise CofferError(f"config_dir does not exist here: {self.refuse}")


class _RecordingHook:
    kind = "agent"

    def __init__(self) -> None:
        self.calls = 0

    async def reconcile(self) -> list[str]:
        self.calls += 1
        return []


@dataclass
class Vault:
    name: str
    root: Path
    home: str
    resources: ResourceService
    service: SyncService
    master_key: MasterKeyManager
    db_path: Path
    knowledge: Path
    memory: Path
    state: _StubStateProvider

    def cred_store(self) -> EncryptedCredentialStore:
        key = self.master_key.export_key()
        assert key is not None
        return EncryptedCredentialStore(self.db_path, key)


async def _make_vault(
    name: str,
    root: Path,
    *,
    create_key: bool,
    key_bytes: bytes | None = None,
    home: str | None = None,
    gates: tuple[Any, ...] = (),
    hooks: tuple[Any, ...] = (),
) -> Vault:
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

    resources = ResourceService(kinds=_kinds(), repo=SqlAlchemyResourceRepo(sm), audit=audit)
    cred_sync = CredentialSyncAdapter(db_path, master_key)
    knowledge = root / "knowledge"
    memory = root / "memory"
    knowledge.mkdir(parents=True, exist_ok=True)
    memory.mkdir(parents=True, exist_ok=True)
    trees = [("knowledge", knowledge)]
    state = _StubStateProvider()
    resolved_home = home or str(root)

    service = SyncService(
        exporter=SyncExporter(resources, cred_sync, state_providers=[state], home=resolved_home),
        importer=SyncImporter(
            resources,
            cred_sync,
            state_providers=[state],
            import_gates=gates,
            post_import_hooks=hooks,
            home=resolved_home,
        ),
        credentials=cred_sync,
        master_key=master_key,
        audit=audit,
        bundle_factory=lambda p: Bundle(p, trees=trees),
    )
    return Vault(
        name=name,
        root=root,
        home=resolved_home,
        resources=resources,
        service=service,
        master_key=master_key,
        db_path=db_path,
        knowledge=knowledge,
        memory=memory,
        state=state,
    )


@pytest_asyncio.fixture
async def alice(tmp_path):  # type: ignore[no-untyped-def]
    return await _make_vault("alice", tmp_path / "alice", create_key=True)


@pytest_asyncio.fixture
async def bob(tmp_path, alice):  # type: ignore[no-untyped-def]
    # No key: bob starts as a fresh machine that has not been bootstrapped.
    return await _make_vault("bob", tmp_path / "bob", create_key=False)


def _areas(summary) -> dict[str, int]:  # type: ignore[no-untyped-def]
    return {a.area: a.count for a in summary.areas}


# --- export ----------------------------------------------------------------


@pytest.mark.acceptance(spec="vault-export-import", scenario="export a vault to a directory")
@pytest.mark.asyncio
async def test_export_writes_a_bundle_and_reports_counts(alice, tmp_path) -> None:  # type: ignore[no-untyped-def]
    await alice.resources.register("mcp_server", "files", {"value": "a"}, "user")
    (alice.knowledge / "note.md").write_text("hello", encoding="utf-8")
    (alice.knowledge / "topic.md").write_text("remembered", encoding="utf-8")
    alice.state.docs["peer-1"] = {"paired": True}

    out = tmp_path / "bundle"
    summary = await alice.service.export_bundle(str(out))

    assert (out / "manifest.json").exists()
    assert (out / "resources" / "mcp_server" / "files.yaml").exists()
    assert (out / "knowledge" / "note.md").read_text(encoding="utf-8") == "hello"
    assert (out / "knowledge" / "topic.md").exists()
    assert (out / "state" / "peers" / "peer-1.yaml").exists()
    # No credentials/ directory without --with-credentials.
    assert not (out / "credentials").exists()

    counts = _areas(summary)
    assert counts["resources"] == 1
    assert counts["knowledge"] == 2
    assert counts["state/peers"] == 1
    assert summary.path == str(out)
    assert summary.failures == []


@pytest.mark.acceptance(
    spec="vault-export-import", scenario="an unchanged vault exports byte-identically"
)
@pytest.mark.asyncio
async def test_two_exports_of_an_unchanged_vault_match(alice, tmp_path) -> None:  # type: ignore[no-untyped-def]
    await alice.resources.register(
        "mcp_server", "files", {"value": "a", "config_dir": alice.home + "/x"}, "user"
    )
    (alice.knowledge / "note.md").write_text("hello", encoding="utf-8")
    alice.state.docs["peer-1"] = {"paired": True}

    first, second = tmp_path / "b1", tmp_path / "b2"
    await alice.service.export_bundle(str(first))
    await alice.service.export_bundle(str(second))

    names = {p.relative_to(first) for p in first.rglob("*") if p.is_file()}
    assert names == {p.relative_to(second) for p in second.rglob("*") if p.is_file()}
    for rel in names:
        a, b = (first / rel).read_bytes(), (second / rel).read_bytes()
        if rel.as_posix() == "manifest.json":
            # Creation time is the one field allowed to differ.
            assert json.loads(a)["schema_version"] == json.loads(b)["schema_version"]
            continue
        assert a == b, rel


@pytest.mark.asyncio
async def test_re_export_into_the_same_directory_is_a_snapshot(alice, tmp_path) -> None:  # type: ignore[no-untyped-def]
    await alice.resources.register("mcp_server", "gone", {"value": "a"}, "user")
    out = tmp_path / "bundle"
    await alice.service.export_bundle(str(out))
    await alice.resources.delete(ResourceRef("mcp_server", "gone"), "user")

    await alice.service.export_bundle(str(out))
    assert not (out / "resources" / "mcp_server" / "gone.yaml").exists()


# --- import ----------------------------------------------------------------


@pytest.mark.acceptance(spec="vault-export-import", scenario="import a bundle into an empty vault")
@pytest.mark.asyncio
async def test_import_into_an_empty_vault(alice, bob, tmp_path) -> None:  # type: ignore[no-untyped-def]
    await alice.resources.register("mcp_server", "files", {"value": "a"}, "user")
    (alice.knowledge / "note.md").write_text("hello", encoding="utf-8")
    alice.state.docs["peer-1"] = {"paired": True}
    out = tmp_path / "bundle"
    await alice.service.export_bundle(str(out))

    hook = _RecordingHook()
    bob.service._importer._hooks = [hook]
    summary = await bob.service.import_bundle(str(out))

    assert [(r.kind, r.name) for r in await bob.resources.list()] == [("mcp_server", "files")]
    assert (bob.knowledge / "note.md").read_text(encoding="utf-8") == "hello"
    assert bob.state.docs["peer-1"] == {"paired": True}
    assert hook.calls == 1  # each kind's post-import hook ran
    assert _areas(summary)["resources"] == 1
    assert summary.failures == []


@pytest.mark.acceptance(
    spec="vault-export-import", scenario="the bundle wins over an existing local resource"
)
@pytest.mark.asyncio
async def test_bundle_wins_over_a_local_resource(alice, bob, tmp_path) -> None:  # type: ignore[no-untyped-def]
    await alice.resources.register("mcp_server", "files", {"value": "from-alice"}, "user")
    out = tmp_path / "bundle"
    await alice.service.export_bundle(str(out))

    await bob.resources.register("mcp_server", "files", {"value": "from-bob"}, "user")
    await bob.service.import_bundle(str(out))

    row = await bob.resources.get(ResourceRef("mcp_server", "files"))
    assert row.config["value"] == "from-alice"


@pytest.mark.acceptance(
    spec="vault-export-import", scenario="import never deletes a local-only resource"
)
@pytest.mark.asyncio
async def test_import_never_deletes_local_only_state(alice, bob, tmp_path) -> None:  # type: ignore[no-untyped-def]
    await alice.resources.register("mcp_server", "shared", {"value": "a"}, "user")
    out = tmp_path / "bundle"
    await alice.service.export_bundle(str(out))

    await bob.resources.register("mcp_server", "local-only", {"value": "b"}, "user")
    (bob.knowledge / "bob-only.md").write_text("mine", encoding="utf-8")
    await bob.service.import_bundle(str(out))

    names = {r.name for r in await bob.resources.list()}
    assert names == {"shared", "local-only"}
    assert (bob.knowledge / "bob-only.md").exists()


@pytest.mark.acceptance(
    spec="vault-export-import", scenario="config paths follow each machine's home"
)
@pytest.mark.asyncio
async def test_home_paths_land_on_the_importing_machine(tmp_path) -> None:  # type: ignore[no-untyped-def]
    a_home, b_home = tmp_path / "homes" / "a", tmp_path / "homes" / "b"
    a = await _make_vault("a", tmp_path / "va", create_key=True, home=str(a_home))
    b = await _make_vault("b", tmp_path / "vb", create_key=True, home=str(b_home))
    await a.resources.register("agent", "coder", {"config_dir": f"{a_home}/.claude"}, "user")

    out = tmp_path / "bundle"
    await a.service.export_bundle(str(out))
    doc = (out / "resources" / "agent" / "coder.yaml").read_text(encoding="utf-8")
    assert "${HOME}/.claude" in doc  # the bundle never carries a literal home

    await b.service.import_bundle(str(out))
    row = await b.resources.get(ResourceRef("agent", "coder"))
    assert row.config["config_dir"] == f"{b_home}/.claude"


@pytest.mark.acceptance(
    spec="vault-export-import", scenario="a resource that cannot apply here is reported, not fatal"
)
@pytest.mark.asyncio
async def test_one_unappliable_resource_does_not_stop_the_rest(alice, tmp_path) -> None:  # type: ignore[no-untyped-def]
    await alice.resources.register("agent", "broken", {"config_dir": "/nope"}, "user")
    for n in ("one", "two", "three"):
        await alice.resources.register("mcp_server", n, {"value": n}, "user")
    out = tmp_path / "bundle"
    await alice.service.export_bundle(str(out))

    bob = await _make_vault(
        "bob", tmp_path / "bob2", create_key=True, gates=(_RefusingGate("/nope"),)
    )
    summary = await bob.service.import_bundle(str(out))

    assert {r.name for r in await bob.resources.list()} == {"one", "two", "three"}
    assert [ref for ref, _reason in summary.failures] == ["agent:broken"]
    assert "/nope" in summary.failures[0][1]
    assert _areas(summary)["resources"] == 3


@pytest.mark.asyncio
async def test_a_failing_state_doc_is_reported_not_fatal(alice, bob, tmp_path) -> None:  # type: ignore[no-untyped-def]
    alice.state.docs["good"] = {"ok": True}
    alice.state.docs["bad"] = {"ok": False}
    out = tmp_path / "bundle"
    await alice.service.export_bundle(str(out))

    bob.state.fail_on = {"bad"}
    summary = await bob.service.import_bundle(str(out))

    assert bob.state.docs == {"good": {"ok": True}}
    assert summary.failures == [("state/peers/bad", "cannot bind here")]


@pytest.mark.acceptance(
    spec="vault-export-import", scenario="an older build refuses a newer bundle"
)
@pytest.mark.asyncio
async def test_a_newer_bundle_is_refused(alice, bob, tmp_path) -> None:  # type: ignore[no-untyped-def]
    await alice.resources.register("mcp_server", "files", {"value": "a"}, "user")
    out = tmp_path / "bundle"
    await alice.service.export_bundle(str(out))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["schema_version"] += 1
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SyncBundleTooNew):
        await bob.service.import_bundle(str(out))
    assert await bob.resources.list() == []  # nothing was applied


@pytest.mark.asyncio
async def test_a_directory_that_is_not_a_bundle_is_refused(bob, tmp_path) -> None:  # type: ignore[no-untyped-def]
    empty = tmp_path / "not-a-bundle"
    empty.mkdir()
    with pytest.raises(SyncBundleInvalid):
        await bob.service.import_bundle(str(empty))
    with pytest.raises(SyncBundleInvalid):
        await bob.service.import_bundle(str(tmp_path / "missing"))


@pytest.mark.acceptance(spec="vault-export-import", scenario="a scoped resource imports dormant")
@pytest.mark.asyncio
async def test_scope_rides_the_bundle_unmodified(alice, bob, tmp_path) -> None:  # type: ignore[no-untyped-def]
    created = await alice.resources.register("mcp_server", "files", {"value": "a"}, "user")
    scope = ["not-registered-here"]
    await alice.resources.update_scope(created.ref, scope, actor="user")

    out = tmp_path / "bundle"
    await alice.service.export_bundle(str(out))
    await bob.service.import_bundle(str(out))

    row = await bob.resources.get(ResourceRef("mcp_server", "files"))
    # Registered and visible, scoped to an agent this vault does not have —
    # so nothing on this machine activates it.
    assert row.scope == scope
    assert row.enabled is True


# --- credentials -----------------------------------------------------------


@pytest.mark.acceptance(
    spec="vault-export-import", scenario="credentials are omitted unless requested"
)
@pytest.mark.asyncio
async def test_credentials_are_opt_in(alice, bob, tmp_path) -> None:  # type: ignore[no-untyped-def]
    alice.cred_store().set("mcp/files/token", "s3cret")
    out = tmp_path / "bundle"
    summary = await alice.service.export_bundle(str(out))

    assert not (out / "credentials").exists()
    assert summary.credentials_included is False

    await bob.service.import_bundle(str(out))
    assert CredentialSyncAdapter(bob.db_path, bob.master_key).list_refs() == []


@pytest.mark.acceptance(spec="vault-export-import", scenario="master key never enters the bundle")
@pytest.mark.asyncio
async def test_ciphertext_travels_but_the_key_never_does(alice, bob, tmp_path) -> None:  # type: ignore[no-untyped-def]
    alice.cred_store().set("mcp/files/token", "s3cret")
    key = alice.master_key.export_key()
    assert key is not None

    out = tmp_path / "bundle"
    summary = await alice.service.export_bundle(str(out), with_credentials=True)
    assert summary.credentials_included is True
    assert (out / "credentials" / "mcp" / "files" / "token.enc").exists()

    # No file the bundle lists contains the key.
    bundle = Bundle(out, trees=[])
    listed = bundle.list_files()
    assert listed  # the inspection primitive actually sees the bundle
    for rel in listed:
        assert key not in (out / rel).read_bytes(), rel

    # Bob has the ciphertext but not the key: locked, never a silent failure.
    summary = await bob.service.import_bundle(str(out))
    assert summary.locked_refs == ["mcp/files/token"]

    # The out-of-band key bootstrap unlocks it.
    assert await bob.service.import_key(await alice.service.export_key()) == []
    assert bob.cred_store().get("mcp/files/token") == "s3cret"


@pytest.mark.asyncio
async def test_key_fingerprints_match_after_the_bootstrap(alice, bob, tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert bob.service.key_fingerprint() is None
    await bob.service.import_key(await alice.service.export_key())
    assert bob.service.key_fingerprint() == alice.service.key_fingerprint()
