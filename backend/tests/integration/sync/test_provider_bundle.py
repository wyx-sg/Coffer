"""A provider connection crosses machines on the generic machinery alone.

A ``provider`` resource is pure config, so it rides ``ResourceDoc`` like any
other kind: :class:`SyncExporter` writes it and :class:`ResourceApplier` puts it
back, with no sync-specific code of its own anywhere in the provider module.
This is the regression test for that claim — if someone gives ``provider`` a
bespoke export path, or a new config field stops surviving the YAML round trip
(the curated ``models`` list and its per-entry modality are the fragile part),
it fails here.

Two independent vaults — separate SQLite files, separate homes — meet through
one bundle directory on disk. No git, no round, no convergence state.
"""

from __future__ import annotations

import dataclasses
import pathlib

import pytest
import yaml

from coffer.application.audit_service import AuditService
from coffer.application.provider.kind import make_provider_kind
from coffer.application.resource_service import ResourceService
from coffer.application.sync.appliers import ResourceApplier
from coffer.application.sync.exporter import SyncExporter
from coffer.domain.resource import ResourceRef
from coffer.domain.scope import Scope
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from coffer.infrastructure.sync.bundle import Bundle
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from tests.integration.sync.harness import NoKeyring

pytestmark = pytest.mark.timeout(60)

DOC = "resources/provider/acme.yaml"

CONFIG = {
    "protocol": "openai",
    "base_url": "https://gw/v1",
    "credential_ref": "provider/acme/key",
    # The curated set the connection offers downstream rides along with it,
    # each entry keeping the modality that says which picker may offer it.
    "models": [
        {"id": "gpt-5", "modality": "text"},
        {"id": "text-embedding-3-large", "modality": "embedding"},
    ],
    "is_active": True,
    # Both role flags travel, and both travel false here: which connection the
    # engine runs on and which one speech is transcribed on are decisions the
    # receiving vault makes for itself, on the machines it actually has.
    "internal_default": False,
    "transcribe_default": False,
}


@dataclasses.dataclass
class Vault:
    resources: ResourceService
    credentials: CredentialSyncAdapter
    home: pathlib.Path
    engine: object
    #: The vault's own master key, so a test can put a real secret in the
    #: store the exporter reads ciphertext out of.
    key: bytes


async def _vault(root: pathlib.Path) -> Vault:
    """One vault, whole enough to serialize a provider and take one back."""
    root.mkdir(parents=True, exist_ok=True)
    db = root / "coffer.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = session_maker(engine)
    resources = ResourceService(
        kinds={"provider": make_provider_kind()},
        repo=SqlAlchemyResourceRepo(sessions),
        audit=AuditService(SqlAlchemyAuditRepo(sessions)),
    )
    master_key = MasterKeyManager(root / "master.key", NoKeyring())
    key = master_key.resolve(allow_create=True)
    assert key is not None
    return Vault(
        resources=resources,
        credentials=CredentialSyncAdapter(db, master_key),
        home=root,
        engine=engine,
        key=key,
    )


@pytest.fixture
async def machines(tmp_path: pathlib.Path):
    """Two vaults and the bundle directory between them."""
    a = await _vault(tmp_path / "A")
    b = await _vault(tmp_path / "B")
    yield a, b, tmp_path / "bundle"
    await a.engine.dispose()  # type: ignore[attr-defined]
    await b.engine.dispose()  # type: ignore[attr-defined]


def _exporter(vault: Vault) -> SyncExporter:
    return SyncExporter(vault.resources, vault.credentials, home=str(vault.home))


def _applier(vault: Vault, bundle_dir: pathlib.Path) -> ResourceApplier:
    return ResourceApplier(vault.resources, worktree=bundle_dir, home=str(vault.home))


async def test_a_provider_connection_crosses_to_another_vault_unchanged(machines) -> None:  # type: ignore[no-untyped-def]
    a, b, bundle_dir = machines
    await a.resources.register("provider", "acme", dict(CONFIG), "test", description="Acme gateway")
    # Narrowed on A, and deliberately: the assertion below is that B does NOT
    # inherit it. Which agents a connection reaches is its reach, and reach is
    # set on the machine it applies to — a connection arriving somewhere for
    # the first time takes that machine's own default instead.
    await a.resources.update_scope(
        ResourceRef("provider", "acme"), Scope(agents=["claude_code"]), actor="test"
    )

    summary = await _exporter(a).export(Bundle(bundle_dir, trees=[]))
    assert summary.failures == []

    # The document on disk is plain scalars — no python object tags, nothing a
    # build that does not share our classes would choke on.
    raw = (bundle_dir / DOC).read_text(encoding="utf-8")
    assert "!!python" not in raw
    assert yaml.safe_load(raw)["config"]["models"] == CONFIG["models"]

    await _applier(b, bundle_dir).upsert(DOC)

    got = await b.resources.get(ResourceRef("provider", "acme"))
    assert got.config == CONFIG
    assert got.description == "Acme gateway"
    # The connection crossed; A's answer about how far it reaches did not.
    # ``scope`` is not a config field, and it is not a document field either.
    assert "scope" not in yaml.safe_load(raw)
    assert "enabled" not in yaml.safe_load(raw)
    assert got.enabled is True
    # B minted its own: the wire's default for this protocol, which is exactly
    # what a connection registered by hand on B would have started with.
    default_scope = make_provider_kind().default_scope
    assert default_scope is not None
    assert got.scope == default_scope(dict(CONFIG))
    assert got.scope != Scope(agents=["claude_code"])
    # Spelled out: the curated set keeps its order AND each entry's modality,
    # which is what stops a chat picker from offering an embedding model.
    assert got.config["models"] == [
        {"id": "gpt-5", "modality": "text"},
        {"id": "text-embedding-3-large", "modality": "embedding"},
    ]


async def test_a_changed_provider_connection_crosses_again(machines) -> None:  # type: ignore[no-untyped-def]
    a, b, bundle_dir = machines
    await a.resources.register("provider", "acme", dict(CONFIG), "test", description="Acme gateway")
    await _exporter(a).export(Bundle(bundle_dir, trees=[]))
    await _applier(b, bundle_dir).upsert(DOC)

    edited = dict(CONFIG)
    edited["base_url"] = "https://gw-2/v1"
    edited["is_active"] = False
    edited["models"] = [{"id": "gpt-5-mini", "modality": "text"}]
    await a.resources.update_config(
        ResourceRef("provider", "acme"), edited, "test", description="Acme gateway (eu)"
    )

    await _exporter(a).export(Bundle(bundle_dir, trees=[]))
    await _applier(b, bundle_dir).upsert(DOC)

    got = await b.resources.get(ResourceRef("provider", "acme"))
    assert got.config == edited
    assert got.description == "Acme gateway (eu)"
    assert [r.name for r in await b.resources.list(kind="provider")] == ["acme"]


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a provider profile round-trips through sync export and import",
)
async def test_a_provider_key_crosses_as_ciphertext_and_never_as_plaintext(
    machines,  # type: ignore[no-untyped-def]
    tmp_path: pathlib.Path,
) -> None:
    """The profile crosses with its key, and the key crosses encrypted.

    The two halves travel by different machinery — the row through
    ``ResourceDoc``, the secret as one Fernet blob at
    ``credentials/<ref>.enc`` — and the bundle must be readable end to end
    without the plaintext appearing anywhere in it.
    """
    a, b, bundle_dir = machines
    secret = "sk-acme-do-not-leak"
    EncryptedCredentialStore(a.home / "coffer.db", a.key).set(CONFIG["credential_ref"], secret)
    await a.resources.register("provider", "acme", dict(CONFIG), "test", description="Acme gateway")

    bundle = Bundle(bundle_dir, trees=[])
    summary = await _exporter(a).export(bundle, with_credentials=True)

    assert summary.failures == []
    assert summary.credentials_included is True
    blob = bundle_dir / "credentials" / "provider" / "acme" / "key.enc"
    assert blob.is_file()
    assert blob.read_text(encoding="utf-8").startswith("gAAAAA")
    # Nothing in the bundle — the resource document included — carries the
    # secret or the key that would open it.
    for rel in bundle.list_files():
        content = (bundle_dir / rel).read_bytes()
        assert secret.encode() not in content
        assert a.key not in content

    # The profile itself still lands on the other vault intact.
    await _applier(b, bundle_dir).upsert(DOC)
    got = await b.resources.get(ResourceRef("provider", "acme"))
    assert got.config["credential_ref"] == CONFIG["credential_ref"]
    assert got.config == CONFIG
