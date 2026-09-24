"""Startup refuses to run without the key that opens the ciphertext it holds.

spec credentials FR — a master key is never regenerated over live ciphertext,
and a present-but-corrupt key is a named, fatal startup failure rather than a
silent re-key that orphans every stored secret.
"""

from __future__ import annotations

import pathlib
import sqlite3

import keyring.backends.fail
import keyring.core
import pytest
from keyring.errors import KeyringLocked
from sqlalchemy.ext.asyncio import create_async_engine

from coffer.domain.errors import CredentialLocked, MasterKeyMissing
from coffer.surfaces.http import credential_composition as cred_comp
from tests.fixtures.keyring import install_in_memory_keyring

_SCHEMA = """
CREATE TABLE credentials (
    ref TEXT PRIMARY KEY,
    ciphertext BLOB NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def _db_with_ciphertext(tmp_path: pathlib.Path) -> pathlib.Path:
    """A vault holding one credential row — i.e. live ciphertext."""
    db_path = tmp_path / "coffer.db"
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    conn.execute(
        "INSERT INTO credentials (ref, ciphertext, created_at, updated_at) "
        "VALUES ('gh', X'00', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture(autouse=True)
def _isolate_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    """init_credential_store publishes DI singletons; keep them out of other tests."""
    monkeypatch.setattr(cred_comp, "_credential_store", None, raising=False)
    monkeypatch.setattr(cred_comp, "_master_key_manager", None, raising=False)


@pytest.mark.acceptance(
    spec="credentials",
    scenario="the master key is never regenerated over existing ciphertext",
)
async def test_absent_key_over_ciphertext_refuses_to_start(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_in_memory_keyring(monkeypatch)  # empty: no key in the keychain either
    db_path = _db_with_ciphertext(tmp_path)
    key_path = tmp_path / "master.key"
    assert not key_path.exists()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        with pytest.raises(MasterKeyMissing) as excinfo:
            await cred_comp.init_credential_store(engine, db_path)
    finally:
        await engine.dispose()

    # The failure names the key it expected, and writes no replacement — so
    # restoring the original key restores access to the row above.
    assert str(key_path) in str(excinfo.value)
    assert not key_path.exists()


@pytest.mark.acceptance(
    spec="credentials",
    scenario="a missing master key is a named, fatal startup failure",
)
async def test_corrupt_key_file_is_a_named_fatal_failure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_in_memory_keyring(monkeypatch)
    db_path = _db_with_ciphertext(tmp_path)
    key_path = tmp_path / "master.key"
    key_path.write_bytes(b"not-a-fernet-key")  # present, but opens nothing

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        with pytest.raises(MasterKeyMissing) as excinfo:
            await cred_comp.init_credential_store(engine, db_path)
    finally:
        await engine.dispose()

    assert str(key_path) in str(excinfo.value)
    # The corrupt file is left exactly as found rather than replaced.
    assert key_path.read_bytes() == b"not-a-fernet-key"


def _empty_db(tmp_path: pathlib.Path) -> pathlib.Path:
    """A vault with the credentials table but no rows — creation is legal."""
    db_path = tmp_path / "coffer.db"
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    conn.commit()
    conn.close()
    return db_path


class _LockedKeyring:
    """A keychain that is there but locked: every read raises KeyringLocked,
    as macOS does while the login keychain is locked or its prompt is dismissed.

    Duck-typed rather than a ``KeyringBackend`` subclass on purpose: every
    subclass registers itself as a candidate backend, and one that always
    raises would be picked up by any later test that lets keyring choose."""

    def get_password(self, service: str, username: str) -> str | None:
        raise KeyringLocked("the keychain is locked")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise KeyringLocked("the keychain is locked")

    def delete_password(self, service: str, username: str) -> None:
        raise KeyringLocked("the keychain is locked")


@pytest.mark.acceptance(
    spec="credentials",
    scenario="a locked keychain at start creates no key",
)
async def test_locked_keychain_with_an_empty_store_refuses_to_start(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The key may be in the locked keychain (opted in earlier). A file key
    created now would win every later start, file-first, and the keychain key
    — the one any synced ciphertext was written under — would never be read."""
    monkeypatch.setattr(keyring.core, "_keyring_backend", _LockedKeyring())
    db_path = _empty_db(tmp_path)
    key_path = tmp_path / "master.key"

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        with pytest.raises(CredentialLocked) as excinfo:
            await cred_comp.init_credential_store(engine, db_path)
    finally:
        await engine.dispose()

    message = str(excinfo.value)
    assert "keychain is locked" in message
    assert "unlock" in message
    assert str(key_path) in message
    assert not key_path.exists()


async def test_no_keychain_backend_at_all_still_creates_the_file_key(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A host with no keychain backend (a bare Linux box) cannot have stored
    the key there, so a first start creates the default file key as before."""
    monkeypatch.setattr(keyring.core, "_keyring_backend", keyring.backends.fail.Keyring())
    db_path = _empty_db(tmp_path)
    key_path = tmp_path / "master.key"

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        wiring = await cred_comp.init_credential_store(engine, db_path)
    finally:
        await engine.dispose()

    assert key_path.exists()
    assert wiring.master_key.location == "file"
