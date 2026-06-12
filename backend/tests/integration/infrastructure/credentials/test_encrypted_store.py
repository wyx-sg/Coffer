"""EncryptedCredentialStore — Fernet-encrypted secrets in SQLite."""

from __future__ import annotations

import pathlib
import sqlite3

import pytest
from cryptography.fernet import Fernet

from coffer.domain.errors import CredentialUnreadable
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


@pytest.fixture
def store(db_path: pathlib.Path) -> EncryptedCredentialStore:
    return EncryptedCredentialStore(db_path=db_path, key=Fernet.generate_key())


def test_set_get_roundtrip(store: EncryptedCredentialStore) -> None:
    store.set("github-token", "ghp_secret123")
    assert store.get("github-token") == "ghp_secret123"


def test_get_missing_returns_none(store: EncryptedCredentialStore) -> None:
    assert store.get("nope") is None


def test_set_overwrites(store: EncryptedCredentialStore) -> None:
    store.set("ref", "v1")
    store.set("ref", "v2")
    assert store.get("ref") == "v2"


def test_delete_is_idempotent(store: EncryptedCredentialStore) -> None:
    store.set("ref", "v")
    store.delete("ref")
    store.delete("ref")
    assert store.get("ref") is None


def test_count(store: EncryptedCredentialStore) -> None:
    assert store.count() == 0
    store.set("a", "1")
    store.set("b", "2")
    assert store.count() == 2


def test_plaintext_not_in_db_file(db_path: pathlib.Path, store: EncryptedCredentialStore) -> None:
    store.set("ref", "super-plain-secret")
    assert b"super-plain-secret" not in db_path.read_bytes()


def test_wrong_key_raises_credential_unreadable(db_path: pathlib.Path) -> None:
    EncryptedCredentialStore(db_path=db_path, key=Fernet.generate_key()).set("ref", "v")
    other = EncryptedCredentialStore(db_path=db_path, key=Fernet.generate_key())
    with pytest.raises(CredentialUnreadable):
        other.get("ref")


def test_exists_true_for_present(store: EncryptedCredentialStore) -> None:
    store.set("ref", "v")
    assert store.exists("ref") is True


def test_exists_false_for_missing(store: EncryptedCredentialStore) -> None:
    assert store.exists("nope") is False


def test_exists_does_not_decrypt_corrupt_row(db_path: pathlib.Path) -> None:
    # A row written under one key is undecryptable under another: exists()
    # must report present (no decrypt) while get() raises CredentialUnreadable.
    EncryptedCredentialStore(db_path=db_path, key=Fernet.generate_key()).set("ref", "v")
    other = EncryptedCredentialStore(db_path=db_path, key=Fernet.generate_key())
    assert other.exists("ref") is True
    with pytest.raises(CredentialUnreadable):
        other.get("ref")
