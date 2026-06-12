"""Fernet-encrypted credential store backed by the coffer SQLite DB.

Drop-in replacement for KeyringAdapter (same get/set/delete shape, plus
count()). Deliberately uses stdlib sqlite3 with a short-lived connection
per call so the sync CredentialStorePort contract survives: materialize() and
register-time probing call this from sync code paths. WAL mode (set by
the async engine) makes concurrent sync readers safe; busy_timeout
matches the engine's PRAGMA suite.

Plaintext exists only in memory between decrypt and the spawn that
consumes it. The ciphertext column never reaches logs or audit rows.
"""

from __future__ import annotations

import pathlib
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken

from coffer.domain.errors import CredentialUnreadable


class EncryptedCredentialStore:
    def __init__(self, db_path: pathlib.Path, key: bytes) -> None:
        self._db_path = db_path
        self._fernet = Fernet(key)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def get(self, ref: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT ciphertext FROM credentials WHERE ref = ?", (ref,)
            ).fetchone()
        if row is None:
            return None
        try:
            return self._fernet.decrypt(row[0]).decode()
        except InvalidToken as e:
            raise CredentialUnreadable(ref) from e

    def set(self, ref: str, value: str) -> None:
        now = datetime.now(tz=UTC).isoformat()
        ciphertext = self._fernet.encrypt(value.encode())
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO credentials (ref, ciphertext, created_at, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(ref) DO UPDATE SET "
                "ciphertext = excluded.ciphertext, updated_at = excluded.updated_at",
                (ref, ciphertext, now, now),
            )

    def delete(self, ref: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM credentials WHERE ref = ?", (ref,))

    def count(self) -> int:
        with closing(self._connect()) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM credentials").fetchone()[0])
