"""Startup refuses to run without the key that opens the ciphertext it holds.

spec credentials FR — a master key is never regenerated over live ciphertext,
and a present-but-corrupt key is a named, fatal startup failure rather than a
silent re-key that orphans every stored secret.
"""

from __future__ import annotations

import pathlib
import sqlite3

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from coffer.domain.errors import MasterKeyMissing
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
