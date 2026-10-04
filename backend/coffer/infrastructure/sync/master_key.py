"""The master key and the secret files, as sync reads them
(ADR secrets-cross-machines-only-as-ciphertext).

A sync round never needs the key: ciphertext travels as the files it is. The
key is read for two things only — the fingerprint each machine publishes in
its descriptor, so the machines list can say "secrets from that machine will
not decrypt here", and after a key import, which refs are still locked.

The key is read through :class:`ResolvedMasterKey`, which resolves it once:
``master_key.py`` promises at most one keychain prompt per daemon start, and
a key that lives in the keychain would otherwise be asked for every round.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from coffer.domain.secret_errors import SecretLocked
from coffer.infrastructure.secret import key_backup
from coffer.infrastructure.secret.encrypted_store import ref_files
from coffer.infrastructure.secret.master_key import MasterKeyManager
from coffer.infrastructure.secret.ref_paths import is_local_ref

_logger = logging.getLogger(__name__)


class ResolvedMasterKey:
    """The master key, read from where it lives once and kept.

    The first answer is kept whatever it was — a key, no key, or a key that
    could not be read — so a locked keychain is asked once, not every round;
    a key installed through it replaces the answer.
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

    def fingerprint(self) -> str | None:
        """A short SHA-256 of the key, never the key: two machines showing the
        same fingerprint hold the same key."""
        key = self.export_key()
        return key_backup.key_fingerprint(key) if key else None


class SecretFiles:
    """The ciphertext files of the vault's ``secret/`` tree (machine-local
    refs excluded: they never travel)."""

    def __init__(self, key: ResolvedMasterKey, *, home: Path | None = None) -> None:
        self._key = key
        self._home = home

    def _files(self) -> dict[str, Path]:
        return {r: p for r, p in ref_files(self._home).items() if not is_local_ref(r)}

    def count(self) -> int:
        """How many secrets a remote that carries them would push."""
        return len(self._files())

    def locked_refs(self) -> list[str]:
        """The refs whose ciphertext this machine's key cannot open.

        Two absences are told apart: a machine that holds no key can open
        none of its ciphertext, so every ref is locked; a key that exists but
        could not be read (a locked keychain) says nothing about which refs
        are locked, so none are reported rather than every one.
        """
        files = self._files()
        if not files:
            return []
        key = self._key.export_key()
        if key is None:
            return [] if self._key.unreadable() else sorted(files)
        fernet = Fernet(key)
        locked: list[str] = []
        for ref, path in sorted(files.items()):
            try:
                fernet.decrypt(path.read_bytes().strip())
            except (InvalidToken, OSError):
                locked.append(ref)
        return locked


__all__ = ["ResolvedMasterKey", "SecretFiles"]
