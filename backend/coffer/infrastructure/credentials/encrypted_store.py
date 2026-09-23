"""Fernet-encrypted credential store backed by the coffer SQLite DB.

Drop-in replacement for KeyringAdapter (same get/set/delete shape, plus
count()). Deliberately uses stdlib sqlite3 with a short-lived connection
per call so the sync CredentialStorePort contract survives: materialize() and
register-time probing call this from sync code paths. WAL mode (set by
the async engine) makes concurrent sync readers safe; busy_timeout
matches the engine's PRAGMA suite.

Async callers MUST NOT call the sync methods on the event loop — use the
``a*`` wrappers (``aget``/``aexists``/``aset``/``adelete``), which run them in
``asyncio.to_thread``. A write's busy-wait blocks its thread, and on the event
loop that freezes the aiosqlite coroutine holding the write lock — its commit
can never run, so the wait becomes a deadlock that always exhausts
busy_timeout. A read is no better: it opens a connection and waits on the same
lock, stalling every other request for as long as the store takes.

Plaintext exists only in memory between decrypt and the spawn that
consumes it. The ciphertext column never reaches logs or audit rows.
"""

from __future__ import annotations

import asyncio
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

    def exists(self, ref: str) -> bool:
        """Presence probe that never decrypts (so a corrupt row can't raise).

        Reads only existence of the row, not the ciphertext, so a credential
        whose ciphertext no longer decrypts with the current master key still
        reports present.
        """
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT 1 FROM credentials WHERE ref = ?", (ref,)).fetchone()
        return row is not None

    def delete(self, ref: str) -> None:
        self.remove(ref)

    def remove(self, ref: str) -> bool:
        """Delete ``ref`` and report whether a row was actually removed.

        ``delete`` keeps the ``-> None`` shape the credential ports declare;
        a caller that must act only on a real removal (the HTTP route audits
        only then — spec credentials "Delete a credential idempotently") uses
        this instead.
        """
        with closing(self._connect()) as conn, conn:
            cur = conn.execute("DELETE FROM credentials WHERE ref = ?", (ref,))
            return cur.rowcount > 0

    def count(self) -> int:
        with closing(self._connect()) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM credentials").fetchone()[0])

    # --- async facade: the same calls, off the event loop --------------------
    # The sync API above stays for the CLI and other sync callers; anything
    # running under the loop goes through these so a slow or lock-contended
    # SQLite call never stalls unrelated requests.

    async def aget(self, ref: str) -> str | None:
        return await asyncio.to_thread(self.get, ref)

    async def aexists(self, ref: str) -> bool:
        return await asyncio.to_thread(self.exists, ref)

    async def aset(self, ref: str, value: str) -> None:
        await asyncio.to_thread(self.set, ref, value)

    async def adelete(self, ref: str) -> None:
        await asyncio.to_thread(self.delete, ref)
