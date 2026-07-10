"""Master key lifecycle for the encrypted credential store.

Envelope encryption: secrets are Fernet-encrypted in SQLite; the only
secret material outside the DB is the master key managed here. It lives
in EXACTLY one of two places:

- a 0600 file next to the DB (default — no keychain prompts, matches the
  threat model: an attacker who can read ~/.coffer/ is out of scope), or
- the OS keychain under ref ``master-key`` (opt-in hardening — survives
  ~/.coffer/ exfiltration, costs at most one keychain prompt per daemon
  start).

Resolution is file-first so a crash mid-relocation can never split brain:
``relocate("keychain")`` deletes the file LAST, so an interrupted move
resolves back to "file" with a stale-but-identical keychain copy.
"""

from __future__ import annotations

import os
import pathlib
from datetime import UTC, datetime
from typing import Literal, Protocol

from cryptography.fernet import Fernet

from coffer.domain.errors import CredentialLocked, MasterKeyMissing

KEYCHAIN_REF = "master-key"

StorageLocation = Literal["file", "keychain"]


class _KeyringLike(Protocol):
    def get(self, ref: str) -> str | None: ...
    def set(self, ref: str, value: str) -> None: ...
    def delete(self, ref: str) -> None: ...


class MasterKeyManager:
    """Find, create, and relocate the Fernet master key."""

    def __init__(self, key_path: pathlib.Path, keyring: _KeyringLike) -> None:
        self._key_path = key_path
        self._keyring = keyring
        self._location: StorageLocation | None = None

    @property
    def location(self) -> StorageLocation | None:
        """Where the key was found ("file" | "keychain"), None before resolve()."""
        return self._location

    def resolve(self, *, allow_create: bool) -> bytes | None:
        """Locate the master key, creating one in the file when allowed.

        Returns None when no key exists and ``allow_create`` is False — the
        caller decides whether that is fatal (it is, when ciphertext exists).
        """
        if self._key_path.exists():
            self._location = "file"
            return self._key_path.read_bytes().strip()
        try:
            stored = self._keyring.get(KEYCHAIN_REF)
        except CredentialLocked:
            stored = None
        if stored:
            self._location = "keychain"
            return stored.encode()
        if not allow_create:
            return None
        key = Fernet.generate_key()
        self._write_file(key)
        self._location = "file"
        return key

    def export_key(self) -> bytes | None:
        """Return the current master key for out-of-band transfer, or None.

        Used by sync (spec 010) to write the key to a file the user moves to
        another machine by a channel they trust — the key never travels through
        the sync medium itself.
        """
        return self.resolve(allow_create=False)

    def install_key(self, key: bytes) -> None:
        """Install a master key brought from another machine (spec 010 bootstrap).

        Writes to the 0600 file store (the default); a machine that prefers the
        keychain can ``relocate("keychain")`` afterwards. Validates the bytes are
        a usable Fernet key so a corrupt import fails loudly instead of locking
        every credential on next decrypt.

        When a *different* key is already installed, the old key is first copied
        to a timestamped ``master.key.bak-*`` sibling: the file being replaced
        may be the only copy of the key that decrypts existing ciphertext, so
        overwriting it in place would orphan those credentials permanently.
        """
        key = key.strip()
        Fernet(key)  # raises ValueError on a malformed key
        existing = self._key_path.read_bytes().strip() if self._key_path.exists() else b""
        if existing == key:
            self._location = "file"
            return
        if existing:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
            backup = self._key_path.with_name(f"{self._key_path.name}.bak-{stamp}")
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(existing)
        self._write_file(key)
        self._location = "file"

    def relocate(self, to: StorageLocation) -> None:
        """Move the key between file and keychain. Old copy removed last."""
        if to == self._location:
            return
        if to == "keychain":
            key = self._key_path.read_bytes().strip()
            self._keyring.set(KEYCHAIN_REF, key.decode())
            if self._keyring.get(KEYCHAIN_REF) != key.decode():
                raise CredentialLocked("keychain write could not be verified")
            self._key_path.unlink(missing_ok=True)
        else:
            stored = self._keyring.get(KEYCHAIN_REF)
            if stored is None:
                raise MasterKeyMissing(str(self._key_path))
            self._write_file(stored.encode())
            self._keyring.delete(KEYCHAIN_REF)
        self._location = to

    def _write_file(self, key: bytes) -> None:
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
