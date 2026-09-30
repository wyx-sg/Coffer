"""Ciphertext-only secret IO for convergence (spec vault-sync).

Reads/writes the ``secrets`` table as raw Fernet ciphertext — no master
key needed, so neither direction of a round touches plaintext. Locked-ref
detection *does* use the key: a ref is locked when no key is present on this
machine, or when the stored ciphertext cannot be decrypted with it (it was
encrypted under a different key whose owner hasn't bootstrapped here yet).

A round asks for the locked refs every time it runs, so the key is read through a
:class:`ResolvedMasterKey`, which resolves it once: ``master_key.py`` promises at
most one keychain prompt per daemon start, and a key that lives in the keychain
would otherwise be read — and prompted for — every round. Two absences are told
apart (spec vault-sync "Report refs without a key as locked"): a machine that
genuinely holds no key can open none of its ciphertext, so every ref is locked;
a key that exists but could not be read (a locked keychain, an unreadable key
file) says nothing about which refs are locked, so none are reported, rather
than every one, and the log says why.
"""

from __future__ import annotations

import logging
import pathlib
import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken

from coffer.domain.model_proxy.state import PROXY_TOKEN_REF_PREFIX
from coffer.domain.secret_errors import SecretLocked
from coffer.infrastructure.secret import key_backup
from coffer.infrastructure.secret.master_key import MasterKeyManager

_logger = logging.getLogger(__name__)


class ResolvedMasterKey:
    """The master key, read from where it lives once and kept.

    Implements ``application.sync.ports.MasterKeyPort``. The first answer is
    kept whatever it was — a key, no key, or a key that could not be read — so
    a locked keychain is asked once, not every round; a key installed through
    it replaces the answer.
    """

    def __init__(
        self,
        manager: MasterKeyManager,
        *,
        on_install: Callable[[bytes], None] | None = None,
    ) -> None:
        self._manager = manager
        # Told the new key once it is installed: the running secret store
        # encrypts and decrypts with the key it was built with, and after an
        # import that must be the imported one, or a secret saved now would be
        # sealed under a key this machine no longer keeps.
        self._on_install = on_install
        self._lock = threading.Lock()
        self._resolved = False
        self._key: bytes | None = None
        self._unreadable = False

    def _resolve(self) -> None:
        if self._resolved:
            return
        try:
            self._key = self._manager.lookup()
        except (SecretLocked, OSError) as e:
            self._key, self._unreadable = None, True
            _logger.warning("sync.master_key_unreadable", extra={"reason": str(e)})
        self._resolved = True

    def export_key(self) -> bytes | None:
        with self._lock:
            self._resolve()
            return self._key

    def unreadable(self) -> bool:
        """Whether a key exists here but could not be read when resolved."""
        with self._lock:
            self._resolve()
            return self._unreadable

    def install_key(self, key: bytes) -> None:
        self._manager.install_key(key)
        with self._lock:
            self._key, self._resolved, self._unreadable = key.strip(), True, False
        if self._on_install is not None:
            self._on_install(key.strip())

    def peek_backup(self, material: str) -> tuple[str, bool]:
        """The fingerprint a key file holds, and whether it needs a passphrase."""
        info = key_backup.peek(material)
        return info.fingerprint, info.protected

    def open_backup(self, material: str, passphrase: str | None) -> bytes:
        """The key a key file holds — a ``.cfk`` opened with its passphrase."""
        return key_backup.unwrap(material, passphrase)


class SecretSyncAdapter:
    """Implements ``application.sync.ports.SecretSyncPort``."""

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
        """Every ref that converges — the machine-local proxy tokens excluded
        (``PROXY_TOKEN_REF_PREFIX``): a token unlocks only this machine's
        loopback model proxy, so it has nowhere else to go."""
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT ref FROM secrets ORDER BY ref").fetchall()
        return [r[0] for r in rows if not str(r[0]).startswith(PROXY_TOKEN_REF_PREFIX)]

    def read_ciphertext(self, ref: str) -> bytes | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT ciphertext FROM secrets WHERE ref = ?", (ref,)).fetchone()
        return bytes(row[0]) if row is not None else None

    def write_ciphertext(self, ref: str, blob: bytes) -> None:
        now = datetime.now(tz=UTC).isoformat()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO secrets (ref, ciphertext, created_at, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(ref) DO UPDATE SET "
                "ciphertext = excluded.ciphertext, updated_at = excluded.updated_at",
                (ref, blob, now, now),
            )

    def delete_ciphertext(self, ref: str) -> None:
        """Drop a secret the vault no longer holds.

        Only ever reached because some machine deleted it relative to a shared
        base, so it is a decision rather than an absence. The master key is not
        involved: what goes is one row of ciphertext.
        """
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM secrets WHERE ref = ?", (ref,))

    def locked_refs(self) -> list[str]:
        refs = self.list_refs()
        if not refs:
            return []
        key = self._master_key.export_key()
        if key is None:
            if self._master_key.unreadable():
                # A key is there but could not be read (a locked keychain):
                # which refs it would open is unknown, and "unknown" is not
                # "all". Logged once, when the key was resolved.
                return []
            # No key at all, while holding ciphertext — ciphertext that
            # arrived from another machine before its key did. None of it can
            # be opened here.
            return [ref for ref in refs if self.read_ciphertext(ref) is not None]
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
