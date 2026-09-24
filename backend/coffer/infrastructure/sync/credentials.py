"""Ciphertext-only credential IO for convergence (spec vault-sync).

Reads/writes the ``credentials`` table as raw Fernet ciphertext — no master
key needed, so neither direction of a round touches plaintext. Locked-ref
detection *does* use the key: a ref is locked when no key is present on this
machine, or when the stored ciphertext cannot be decrypted with it (it was
encrypted under a different key whose owner hasn't bootstrapped here yet).

A round asks for the locked refs every time it runs, so the key is read through a
:class:`ResolvedMasterKey`, which resolves it once: ``master_key.py`` promises at
most one keychain prompt per daemon start, and a key that lives in the keychain
would otherwise be read — and prompted for — every round. A key that could not be
read at all (a locked keychain) says nothing about which refs are locked, so none
are reported, rather than every one.
"""

from __future__ import annotations

import pathlib
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken

from coffer.infrastructure.credentials.master_key import MasterKeyManager


class ResolvedMasterKey:
    """The master key, read from where it lives once and kept.

    Implements ``application.sync.ports.MasterKeyPort``. The first answer is
    kept whatever it was — a key or ``None`` — so a locked keychain is asked
    once, not every round; a key installed through it replaces the answer.
    """

    def __init__(self, manager: MasterKeyManager) -> None:
        self._manager = manager
        self._lock = threading.Lock()
        self._resolved = False
        self._key: bytes | None = None

    def export_key(self) -> bytes | None:
        with self._lock:
            if not self._resolved:
                self._key = self._manager.export_key()
                self._resolved = True
            return self._key

    def install_key(self, key: bytes) -> None:
        self._manager.install_key(key)
        with self._lock:
            self._key, self._resolved = key.strip(), True


class CredentialSyncAdapter:
    """Implements ``application.sync.ports.CredentialSyncPort``."""

    def __init__(self, db_path: pathlib.Path, master_key: ResolvedMasterKey) -> None:
        # The same ResolvedMasterKey the key import goes through, so a key
        # imported mid-run is the one the next locked-ref check uses.
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
        """Drop a credential the vault no longer holds.

        Only ever reached because some machine deleted it relative to a shared
        base, so it is a decision rather than an absence. The master key is not
        involved: what goes is one row of ciphertext.
        """
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM credentials WHERE ref = ?", (ref,))

    def locked_refs(self) -> list[str]:
        refs = self.list_refs()
        if not refs:
            return []
        key = self._master_key.export_key()
        if key is None:
            # The key could not be read — in practice a locked keychain, since
            # the daemon creates a key at start when it holds no ciphertext.
            # Which refs it would open is unknown, and "unknown" is not "all".
            return []
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
