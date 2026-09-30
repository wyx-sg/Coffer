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

from coffer.application.audit_service import AuditService
from coffer.application.repos import ResourceRepo
from coffer.application.resource_service import ResourceService
from coffer.application.secret_migration import (
    migrate_legacy_keychain,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import SecretMissing
from coffer.domain.resource import Kind
from coffer.domain.secret_errors import MasterKeyMissing, SecretLocked
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore, ref_files
from coffer.infrastructure.secret.keyring_adapter import KeyringAdapter
from coffer.infrastructure.secret.master_key import MasterKeyManager
from coffer.surfaces.http.secret_boundary_wiring import (
    adopt_existing_bindings,
    init_secret_boundary,
    make_master_key_manager,
    master_key_path,
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


#: The resource repository the one-time legacy keychain move reads citers
#: from; None skips that move (a composition without resources).
_legacy_resource_repo: ResourceRepo | None = None


async def init_secret_store(
    *, home: pathlib.Path | None = None, resource_repo: ResourceRepo | None = None
) -> SecretWiring:
    """Resolve the master key, build the encrypted store, publish DI singletons.

    Envelope encryption: resolve the Fernet master key (file first, then
    keychain), build the file-backed store over ``vault/secret/`` and
    ``local/secret-boundary/``, and replace every KeyringAdapter injection point.
    Creating a brand-new key is only legal while no ciphertext file exists —
    otherwise existing ciphertext would be silently undecryptable, so we fail
    loudly instead. ``home`` is the user's home (default: ``HOME``);
    ``resource_repo`` feeds the legacy keychain move at
    :func:`run_secret_startup`.
    """
    global _legacy_resource_repo
    _legacy_resource_repo = resource_repo
    # The key's home is chosen by how this build was made (a signed release's
    # Keychain access group, or the development file / legacy keychain pair).
    master_key_manager = make_master_key_manager(home)
    stored = len(await asyncio.to_thread(ref_files, home))
    key_path = master_key_path(home)
    try:
        master_key = await asyncio.get_running_loop().run_in_executor(
            None, lambda: master_key_manager.resolve(allow_create=stored == 0)
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
        secret_store = EncryptedSecretStore(master_key, home=home)
    except ValueError as e:
        # A present-but-corrupt key (e.g. truncated file) must fail loudly and
        # name its location — regenerating over live ciphertext is never safe.
        raise MasterKeyMissing(str(key_path)) from e
    set_secret_store(secret_store)
    set_master_key_manager(master_key_manager)
    # The approval gate and the presence grants, before any consumer of a
    # secret is built (every one gets ``boundary_resolver``).
    init_secret_boundary(secret_store, master_key_manager, home=home)
    return SecretWiring(store=secret_store, master_key=master_key_manager)


_logger = logging.getLogger(__name__)


async def run_secret_startup(
    kinds: dict[str, Kind],
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
    if _legacy_resource_repo is not None:
        await run_legacy_keychain_migration(kinds, _legacy_resource_repo, secret_store, audit)
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
    resource_repo: ResourceRepo,
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
            resource_repo,
            KeyringAdapter(),
            secret_store,
            audit,
        )
        if moved:
            _logger.info("secret_migration.completed", extra={"moved": moved})
    except Exception:
        _logger.exception("secret_migration.failed")
