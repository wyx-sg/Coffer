"""Secret-store DI singletons and startup bootstrap.

Owns the ``_secret_store`` / ``_master_key_manager`` provider pairs,
``init_secret_store`` (resolves the Fernet master key, builds the
encrypted store, publishes both DI singletons) and
``run_legacy_keychain_migration`` (best-effort one-time move of pre-0.2
OS-keychain secrets into the store).  Kept separate from ``dependencies.py``
and ``app.py`` to keep all three under the 400-line guideline.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import text as _sa_text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.secret_migration import (
    migrate_legacy_keychain,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import SecretMissing
from coffer.domain.resource import Kind
from coffer.domain.secret_errors import MasterKeyMissing, SecretLocked
from coffer.infrastructure.persistence.repos import SqlAlchemyResourceRepo
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.infrastructure.secret.keyring_adapter import KeyringAdapter
from coffer.infrastructure.secret.master_key import MasterKeyManager
from coffer.surfaces.http.secret_boundary_wiring import (
    adopt_existing_bindings,
    init_secret_boundary,
    make_master_key_manager,
)
from coffer.surfaces.http.secret_boundary_wiring import (
    boundary_resolver as boundary_resolver,
)

_secret_store: EncryptedSecretStore | None = None


def set_secret_store(store: EncryptedSecretStore) -> None:
    """Called by the composition root once on startup."""
    global _secret_store
    _secret_store = store


def get_secret_store() -> EncryptedSecretStore:
    """FastAPI Depends() target."""
    if _secret_store is None:
        raise RuntimeError("secret store not initialised")
    return _secret_store


_master_key_manager: MasterKeyManager | None = None


def set_master_key_manager(manager: MasterKeyManager) -> None:
    """Called by the composition root once on startup."""
    global _master_key_manager
    _master_key_manager = manager


def get_master_key_manager() -> MasterKeyManager:
    """FastAPI Depends() target."""
    if _master_key_manager is None:
        raise RuntimeError("master key manager not initialised")
    return _master_key_manager


def make_secret_resolver(store: EncryptedSecretStore) -> Callable[[str], str]:
    """Build the ``ref -> plaintext`` resolver used by internal-LLM consumers
    (knowledge curation, memory distil, transcription). Raises SecretMissing
    for an unknown ref."""

    def _resolve(ref: str) -> str:
        value: str | None = store.get(ref)
        if value is None:
            raise SecretMissing(ref)
        return value

    return _resolve


@dataclass(frozen=True)
class SecretWiring:
    """The encrypted store every kind resolves refs against, and the master
    key sync carries a fingerprint of."""

    store: EncryptedSecretStore
    master_key: MasterKeyManager


async def init_secret_store(engine: AsyncEngine, db_path: pathlib.Path) -> SecretWiring:
    """Resolve the master key, build the encrypted store, publish DI singletons.

    Envelope encryption: resolve the Fernet master key (file first, then
    keychain), build the encrypted store, and replace every KeyringAdapter
    injection point.  Creating a brand-new key is only legal while the
    secrets table is empty — otherwise existing ciphertext would be
    silently undecryptable, so we fail loudly instead.
    """
    # The key's home is chosen by how this build was made (a signed release's
    # Keychain access group, or the development file / legacy keychain pair).
    master_key_manager = make_master_key_manager(db_path)
    async with engine.connect() as conn:
        ciphertext_rows = (
            await conn.execute(_sa_text("SELECT COUNT(*) FROM secrets"))
        ).scalar_one()
    key_path = db_path.parent / "master.key"
    try:
        master_key = await asyncio.get_running_loop().run_in_executor(
            None, lambda: master_key_manager.resolve(allow_create=ciphertext_rows == 0)
        )
    except SecretLocked as e:
        # The keychain may hold the key; creating one in the file now would
        # shadow it on every later start (spec secret "Resolve the master
        # key file-first and create it only for an empty store").
        raise SecretLocked(
            f"the OS keychain is locked or unreadable ({e}) and may hold Coffer's master "
            f"key; no key was found at {key_path} and none was created — "
            "unlock the keychain and start Coffer again"
        ) from e
    if master_key is None:
        raise MasterKeyMissing(str(key_path))
    try:
        secret_store = EncryptedSecretStore(db_path=db_path, key=master_key)
    except ValueError as e:
        # A present-but-corrupt key (e.g. truncated file) must fail loudly and
        # name its location — regenerating over live ciphertext is never safe.
        raise MasterKeyMissing(str(db_path.parent / "master.key")) from e
    set_secret_store(secret_store)
    set_master_key_manager(master_key_manager)
    # The approval gate and the presence grants, before any consumer of a
    # secret is built (every one gets ``boundary_resolver``).
    init_secret_boundary(db_path, secret_store, master_key_manager)
    return SecretWiring(store=secret_store, master_key=master_key_manager)


_logger = logging.getLogger(__name__)


async def run_secret_startup(
    kinds: dict[str, Kind],
    sm: async_sessionmaker[AsyncSession],
    secret_store: EncryptedSecretStore,
    audit: AuditService,
    resources: ResourceService,
) -> None:
    """The secret steps that need every kind registered, once per start.

    The legacy keychain move below, the audit of a master key the signed build
    moved into its Keychain access group, and the one-time adoption of every
    secret binding in use before the secret boundary existed — so upgrading
    stops nothing that already worked (spec secret "Hold a secret for a
    new destination until a person approves it").
    """
    await run_legacy_keychain_migration(kinds, sm, secret_store, audit)
    manager = get_master_key_manager()
    if manager.migrated_from is not None:
        await audit.record(
            AuditEventType.MASTER_KEY_RELOCATED.value,
            actor="system",
            details={"from": manager.migrated_from, "to": "keychain_access_group"},
        )
    try:
        adopted = await adopt_existing_bindings(resources, audit)
        if adopted:
            _logger.info("secret_boundary.adopted", extra={"bindings": adopted})
    except Exception:
        # Not adopting leaves the marker unset, so the next start tries again;
        # meanwhile a binding with no approval waits, which is the safe side.
        _logger.exception("secret_boundary.adoption_failed")


async def run_legacy_keychain_migration(
    kinds: dict[str, Kind],
    sm: async_sessionmaker[AsyncSession],
    secret_store: EncryptedSecretStore,
    audit: AuditService,
) -> None:
    """One-time move of legacy OS-keychain secrets into the encrypted store.

    No-op once migrated.  Best-effort: failures must not block startup.
    Every citer is a resource now — the global embedding config was the last
    non-resource owner of a ref, and it went with the rest of the embedding
    layer (spec knowledge "Carry no vector or embedding dependency").
    """
    try:
        moved = await migrate_legacy_keychain(
            kinds,
            SqlAlchemyResourceRepo(sm),
            KeyringAdapter(),
            secret_store,
            audit,
        )
        if moved:
            _logger.info("secret_migration.completed", extra={"moved": moved})
    except Exception:
        _logger.exception("secret_migration.failed")
