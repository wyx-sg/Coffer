"""Ciphertext-only credential IO for sync (spec 010).

Reads/writes the ``credentials`` table as raw Fernet ciphertext — no master
key needed, so exporting/importing never touches plaintext. Locked-ref
detection *does* use the key: a ref is locked when no key is present on this
machine, or when the stored ciphertext cannot be decrypted with it (it was
encrypted under a different key whose owner hasn't bootstrapped here yet).
"""

from __future__ import annotations

import pathlib
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken

from coffer.infrastructure.credentials.master_key import MasterKeyManager


class CredentialSyncAdapter:
    """Implements ``application.sync.ports.CredentialSyncPort``."""

    def __init__(self, db_path: pathlib.Path, master_key: MasterKeyManager) -> None:
        self._db_path = db_path
        self._master_key = master_key

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def list_refs(self) -> list[str]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT ref FROM credentials ORDER BY ref").fetchall()
        return [r[0] for r in rows]

    def read_ciphertext(self, ref: str) -> bytes | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT ciphertext FROM credentials WHERE ref = ?", (ref,)
            ).fetchone()
        return bytes(row[0]) if row is not None else None

    def write_ciphertext(self, ref: str, blob: bytes) -> None:
        now = datetime.now(tz=UTC).isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO credentials (ref, ciphertext, created_at, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(ref) DO UPDATE SET "
                "ciphertext = excluded.ciphertext, updated_at = excluded.updated_at",
                (ref, blob, now, now),
            )

    def delete_ciphertext(self, ref: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM credentials WHERE ref = ?", (ref,))

    def locked_refs(self) -> list[str]:
        refs = self.list_refs()
        if not refs:
            return []
        key = self._master_key.export_key()
        if key is None:
            # No master key on this machine yet — everything is locked.
            return refs
        fernet = Fernet(key)
        locked: list[str] = []
        for ref in refs:
            blob = self.read_ciphertext(ref)
            if blob is None:
                continue
            try:
                fernet.decrypt(blob)
            except InvalidToken:
                locked.append(ref)
        return locked
