"""What the encrypted store itself promises (spec credentials).

Real SQLite file, real Fernet key, and the store's own code — the tests read
the ``credentials`` row back with plain ``sqlite3`` so they see exactly what is
persisted, not what the store chooses to return.
"""

from __future__ import annotations

import asyncio
import pathlib
import sqlite3
import threading
import time

import pytest
from cryptography.fernet import Fernet

from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore

_SCHEMA = """
CREATE TABLE credentials (
    ref TEXT PRIMARY KEY,
    ciphertext BLOB NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


@pytest.fixture
def db_path(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "coffer.db"
    conn = sqlite3.connect(p)
    conn.execute(_SCHEMA)
    conn.commit()
    conn.close()
    return p


def _rows(db_path: pathlib.Path, ref: str) -> list[tuple[bytes, str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT ciphertext, created_at, updated_at FROM credentials WHERE ref = ?", (ref,)
        ).fetchall()
    finally:
        conn.close()


@pytest.mark.acceptance(
    spec="credentials", scenario="a stored secret is only ciphertext in the credentials table"
)
def test_a_stored_secret_is_only_ciphertext_in_the_credentials_table(
    db_path: pathlib.Path,
) -> None:
    key = Fernet.generate_key()
    store = EncryptedCredentialStore(db_path=db_path, key=key)
    secret = "sk-plaintext-must-not-persist"

    store.set("svc/key", secret)

    rows = _rows(db_path, "svc/key")
    assert len(rows) == 1
    ciphertext = bytes(rows[0][0])
    assert secret.encode() not in ciphertext
    assert Fernet(key).decrypt(ciphertext).decode() == secret
    # Nothing else in the file spells it either.
    assert secret.encode() not in db_path.read_bytes()


@pytest.mark.acceptance(
    spec="credentials", scenario="writing an existing ref re-encrypts it in place"
)
def test_writing_an_existing_ref_re_encrypts_it_in_place(db_path: pathlib.Path) -> None:
    key = Fernet.generate_key()
    store = EncryptedCredentialStore(db_path=db_path, key=key)

    store.set("svc/key", "first-value")
    [(first_cipher, created_at, first_updated)] = _rows(db_path, "svc/key")
    time.sleep(0.01)  # timestamps are ISO strings; make "later" observable
    store.set("svc/key", "second-value")

    rows = _rows(db_path, "svc/key")
    assert len(rows) == 1
    cipher, created_again, updated = rows[0]
    assert bytes(cipher) != bytes(first_cipher)
    assert Fernet(key).decrypt(bytes(cipher)).decode() == "second-value"
    assert store.get("svc/key") == "second-value"
    assert created_again == created_at
    assert updated > first_updated


@pytest.mark.acceptance(
    spec="credentials", scenario="an async caller reaches the store through its async facade"
)
async def test_an_async_caller_reaches_the_store_through_its_async_facade(
    db_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = EncryptedCredentialStore(db_path=db_path, key=Fernet.generate_key())
    loop_thread = threading.get_ident()
    seen: list[int] = []
    real_connect = store._connect

    def _recording_connect() -> sqlite3.Connection:
        seen.append(threading.get_ident())
        return real_connect()

    monkeypatch.setattr(store, "_connect", _recording_connect)
    assert asyncio.get_running_loop() is not None

    await store.aset("svc/key", "async-value")
    assert await store.aget("svc/key") == "async-value"
    assert await store.aexists("svc/key") is True
    await store.adelete("svc/key")
    assert await store.aexists("svc/key") is False
    assert await store.aget("svc/key") is None

    # Every blocking SQLite call ran — and none of them on the loop's thread.
    assert len(seen) == 6
    assert all(ident != loop_thread for ident in seen)
