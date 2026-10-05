"""Secret-store DI singletons and startup bootstrap.

Owns the ``_secret_store`` / ``_master_key_manager`` provider pairs,
``init_secret_store`` (resolves the Fernet master key, builds the
encrypted store, publishes both DI singletons).  Kept separate from
``dependencies.py`` and ``app.py`` to keep all three under the 400-line
guideline.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
from dataclasses import dataclass

from coffer.domain.secret_errors import MasterKeyMissing, SecretLocked
from coffer.domain.secrets import ORIGIN_DIALOG, SecretNote, is_minted_ref
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore, ref_files
from coffer.infrastructure.secret.master_key import MasterKeyManager
from coffer.infrastructure.secret.notes_store import VaultSecretNotes
from coffer.surfaces.http.secret_boundary_wiring import (
    boundary_resolver as boundary_resolver,
)
from coffer.surfaces.http.secret_boundary_wiring import (
    init_secret_boundary,
    make_master_key_manager,
    master_key_path,
)
from coffer.surfaces.http.secret_notes_wiring import set_secret_notes

_logger = logging.getLogger(__name__)
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


@dataclass(frozen=True)
class SecretWiring:
    """The encrypted store every kind resolves refs against, and the master
    key sync carries a fingerprint of."""

    store: EncryptedSecretStore
    master_key: MasterKeyManager


async def init_secret_store(*, home: pathlib.Path | None = None) -> SecretWiring:
    """Resolve the master key, build the encrypted store, publish DI singletons.

    Envelope encryption: resolve the Fernet master key (file first, then
    keychain), build the file-backed store over ``vault/secret/`` and
    ``local/secret-boundary/``. Creating a brand-new key is only legal while no
    ciphertext file exists — otherwise existing ciphertext would be silently
    undecryptable, so we fail loudly instead. ``home`` is the user's home
    (default: ``HOME``).
    """
    # The key's home is chosen by how this build was made (a signed release's
    # Keychain access group, or the development file / login-keychain pair).
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
    # A label and description belong to the ref: whichever path removes it (the
    # route, a resource's release, a rollback) drops its notes too.
    notes = VaultSecretNotes(home=home)
    set_secret_notes(notes)

    def drop_notes(ref: str) -> None:
        try:
            notes.put(ref, None, summary=f"drop notes of secret {ref}", actor=None)
        except Exception:
            _logger.exception("secret.notes_drop_failed", extra={"ref": ref})

    secret_store.on_removed(drop_notes)

    def mark_dialog(ref: str) -> None:
        """A value written under a new minted id, other than by the Secrets page
        (which re-marks it), was written for the resource about to cite it."""
        if not is_minted_ref(ref):
            return
        try:
            notes.update(
                ref,
                lambda note: note if note is not None else SecretNote(origin=ORIGIN_DIALOG),
                summary=f"secret {ref} written for a resource",
                actor=None,
            )
        except Exception:
            _logger.exception("secret.notes_mark_failed", extra={"ref": ref})

    secret_store.on_created(mark_dialog)
    return SecretWiring(store=secret_store, master_key=master_key_manager)
