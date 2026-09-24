"""Locked-ref detection reads the master key once and never takes a round down.

``master_key.py`` promises at most one keychain prompt per daemon start. A round
asks which credential refs are locked every time it runs, so the key it checks
against is resolved once and kept (spec vault-sync "Report refs without a key as
locked").
"""

from __future__ import annotations

import pathlib
import sqlite3
from contextlib import closing

import pytest
from cryptography.fernet import Fernet

from coffer.domain.credential_errors import CredentialLocked
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter, ResolvedMasterKey


class _CountingKeychain:
    """A keychain holding the key, counting every read (each one a prompt)."""

    def __init__(self, stored: str | None, *, locked: bool = False) -> None:
        self.stored = stored
        self.locked = locked
        self.reads = 0

    def get(self, ref: str) -> str | None:
        self.reads += 1
        if self.locked:
            raise CredentialLocked("keychain is locked")
        return self.stored

    def set(self, ref: str, value: str) -> None:  # pragma: no cover - unused
        raise AssertionError("not written in these tests")

    def delete(self, ref: str) -> None:  # pragma: no cover - unused
        raise AssertionError("not written in these tests")


@pytest.fixture
def db(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "c.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "CREATE TABLE credentials (ref TEXT PRIMARY KEY, ciphertext BLOB, "
            "created_at TEXT, updated_at TEXT)"
        )
    return path


def _adapter(
    db: pathlib.Path, tmp_path: pathlib.Path, keychain: _CountingKeychain
) -> CredentialSyncAdapter:
    # No key file: the key lives in the keychain, the case that prompts.
    manager = MasterKeyManager(tmp_path / "absent" / "master.key", keychain)
    return CredentialSyncAdapter(db, ResolvedMasterKey(manager))


def test_the_keychain_is_read_once_across_rounds(db: pathlib.Path, tmp_path: pathlib.Path) -> None:
    mine, theirs = Fernet.generate_key(), Fernet.generate_key()
    keychain = _CountingKeychain(mine.decode())
    adapter = _adapter(db, tmp_path, keychain)
    adapter.write_ciphertext("mcp/own/token", Fernet(mine).encrypt(b"x"))
    adapter.write_ciphertext("mcp/their/token", Fernet(theirs).encrypt(b"y"))

    answers = [adapter.locked_refs() for _ in range(3)]

    assert answers == [["mcp/their/token"]] * 3
    assert keychain.reads == 1


def test_an_unavailable_key_reports_nothing_locked_and_is_not_retried(
    db: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    # A locked keychain is not evidence that every credential is locked: the
    # answer is unknown, so the round names none rather than all of them.
    keychain = _CountingKeychain(None, locked=True)
    adapter = _adapter(db, tmp_path, keychain)
    adapter.write_ciphertext("mcp/files/token", Fernet(Fernet.generate_key()).encrypt(b"x"))

    assert adapter.locked_refs() == []
    assert adapter.locked_refs() == []
    assert keychain.reads == 1


def test_an_imported_key_is_what_the_next_check_uses(
    db: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    theirs = Fernet.generate_key()
    keychain = _CountingKeychain(Fernet.generate_key().decode())
    manager = MasterKeyManager(tmp_path / "keys" / "master.key", keychain)
    resolved = ResolvedMasterKey(manager)
    adapter = CredentialSyncAdapter(db, resolved)
    adapter.write_ciphertext("mcp/files/token", Fernet(theirs).encrypt(b"x"))
    assert adapter.locked_refs() == ["mcp/files/token"]

    resolved.install_key(theirs)

    assert adapter.locked_refs() == []
    assert resolved.export_key() == theirs
    assert keychain.reads == 1
