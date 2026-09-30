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
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken

from coffer.domain.errors import CredentialUnreadable

#: How stale ``last_used_at`` may get before a read stamps it again.
_USE_STAMP_EVERY = timedelta(minutes=1)


class EncryptedCredentialStore:
    def __init__(self, db_path: pathlib.Path, key: bytes) -> None:
        self._db_path = db_path
        self._fernet = Fernet(key)

    def use_key(self, key: bytes) -> None:
        """Encrypt and decrypt with ``key`` from now on — an imported master key.

        Nothing stored is re-encrypted: ciphertext written under the previous
        key stays as it is and reads as unreadable until that key comes back.
        """
        self._fernet = Fernet(key)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def get(self, ref: str) -> str | None:
        """Decrypt ``ref`` for a consumer, and stamp when it was last used.

        The stamp is written at most once per ``_USE_STAMP_EVERY``, so a
        consumer that resolves on every request does not turn each read into
        a write. A read that is not a use — a reveal, an import's read-back —
        goes through :meth:`peek` instead.
        """
        return self._read(ref, stamp=True)

    def peek(self, ref: str) -> str | None:
        """Decrypt ``ref`` without counting it as a use."""
        return self._read(ref, stamp=False)

    def _read(self, ref: str, *, stamp: bool) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT ciphertext, last_used_at FROM credentials WHERE ref = ?", (ref,)
            ).fetchone()
        if row is None:
            return None
        try:
            value = self._fernet.decrypt(row[0]).decode()
        except InvalidToken as e:
            raise CredentialUnreadable(ref) from e
        if stamp:
            self._stamp_use(ref, row[1])
        return value

    def _stamp_use(self, ref: str, last: str | None) -> None:
        now = datetime.now(tz=UTC)
        if last is not None:
            try:
                if now - datetime.fromisoformat(last) < _USE_STAMP_EVERY:
                    return
            except ValueError:
                pass
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE credentials SET last_used_at = ? WHERE ref = ?", (now.isoformat(), ref)
            )

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
        only then — spec secret "Delete a credential idempotently") uses
        this instead.
        """
        with closing(self._connect()) as conn, conn:
            cur = conn.execute("DELETE FROM credentials WHERE ref = ?", (ref,))
            return cur.rowcount > 0

    def created_at(self, ref: str) -> datetime | None:
        """When ``ref`` was first stored, or None when it is not stored."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT created_at FROM credentials WHERE ref = ?", (ref,)
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def list_refs(self) -> list[tuple[str, str, str]]:
        """Every stored ref with its creation and update time, never a value.

        The enumeration the Secrets page and ``coffer secret list`` need to
        show a stored secret nothing cites (ADR
        standalone-secrets-are-named-references-injected-into-one-child).
        """
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT ref, created_at, updated_at FROM credentials ORDER BY ref"
            ).fetchall()
        return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]

    def last_used(self) -> dict[str, str]:
        """``{ref: when it was last used}`` for every stored ref ever used here."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT ref, last_used_at FROM credentials WHERE last_used_at IS NOT NULL"
            ).fetchall()
        return {str(r[0]): str(r[1]) for r in rows}

    def unreadable_refs(self) -> list[str]:
        """Stored refs this machine's master key cannot open — decrypting nothing.

        Each token's HMAC is checked against the key (``extract_timestamp``
        verifies the signature and reads no plaintext), so a ciphertext that
        came with the vault from a machine holding another key is found
        without any value being decrypted (spec secret "Show a secret this Mac
        cannot open as missing on this Mac").
        """
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT ref, ciphertext FROM credentials ORDER BY ref").fetchall()
        out: list[str] = []
        for ref, blob in rows:
            try:
                self._fernet.extract_timestamp(bytes(blob))
            except InvalidToken:
                out.append(str(ref))
        return out

    def seal(self, value: str) -> bytes:
        """Encrypt a value that is not stored yet — a replacement awaiting approval."""
        return self._fernet.encrypt(value.encode())

    def unseal(self, token: bytes) -> str:
        try:
            return self._fernet.decrypt(token).decode()
        except InvalidToken as e:
            raise CredentialUnreadable("<pending replacement>") from e

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
