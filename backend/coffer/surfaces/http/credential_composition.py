"""Credential-store DI singletons and startup bootstrap.

Owns the ``_credential_store`` / ``_master_key_manager`` provider pairs and
``init_credential_store``, which resolves the Fernet master key, builds the
encrypted store, and publishes both DI singletons.  Kept separate from
``dependencies.py`` to keep both files under the 400-line guideline.
"""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any

from sqlalchemy import text as _sa_text
from sqlalchemy.ext.asyncio import AsyncEngine

from coffer.domain.credential_errors import MasterKeyMissing
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.credentials.master_key import MasterKeyManager

_credential_store: Any | None = None


def set_credential_store(store: Any) -> None:
    """Called by the composition root once on startup."""
    global _credential_store
    _credential_store = store


def get_credential_store() -> Any:
    """FastAPI Depends() target — actual type is EncryptedCredentialStore."""
    if _credential_store is None:
        raise RuntimeError("credential store not initialised")
    return _credential_store


_master_key_manager: Any | None = None


def set_master_key_manager(manager: Any) -> None:
    """Called by the composition root once on startup."""
    global _master_key_manager
    _master_key_manager = manager


def get_master_key_manager() -> Any:
    """FastAPI Depends() target — actual type is MasterKeyManager."""
    if _master_key_manager is None:
        raise RuntimeError("master key manager not initialised")
    return _master_key_manager


async def init_credential_store(
    engine: AsyncEngine, db_path: pathlib.Path
) -> EncryptedCredentialStore:
    """Resolve the master key, build the encrypted store, publish DI singletons.

    Envelope encryption: resolve the Fernet master key (file first, then
    keychain), build the encrypted store, and replace every KeyringAdapter
    injection point.  Creating a brand-new key is only legal while the
    credentials table is empty — otherwise existing ciphertext would be
    silently undecryptable, so we fail loudly instead.
    """
    master_key_manager = MasterKeyManager(
        key_path=db_path.parent / "master.key", keyring=KeyringAdapter()
    )
    async with engine.connect() as conn:
        ciphertext_rows = (
            await conn.execute(_sa_text("SELECT COUNT(*) FROM credentials"))
        ).scalar_one()
    master_key = await asyncio.get_running_loop().run_in_executor(
        None, lambda: master_key_manager.resolve(allow_create=ciphertext_rows == 0)
    )
    if master_key is None:
        raise MasterKeyMissing(str(db_path.parent / "master.key"))
    try:
        credential_store = EncryptedCredentialStore(db_path=db_path, key=master_key)
    except ValueError as e:
        # A present-but-corrupt key (e.g. truncated file) must fail loudly and
        # name its location — regenerating over live ciphertext is never safe.
        raise MasterKeyMissing(str(db_path.parent / "master.key")) from e
    set_credential_store(credential_store)
    set_master_key_manager(master_key_manager)
    return credential_store
