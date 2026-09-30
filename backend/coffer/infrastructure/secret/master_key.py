"""Master key lifecycle for the encrypted secret store.

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

That pair is the **development** arrangement. A signed release hands the
manager a ``vault`` — the Keychain access-group backend of
:mod:`master_key_backends` — and then the key lives there and nowhere else
(ADR master-key-lives-in-the-macos-keychain), and relocating it to a file is
refused. Which arrangement a daemon runs is decided by how it was built
(``build_identity``), never by a setting.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, Protocol

from cryptography.fernet import Fernet

from coffer.domain.errors import MasterKeyMissing, SecretLocked
from coffer.infrastructure.secret.master_key_backends import MasterKeyBackend

KEYCHAIN_REF = "master-key"

StorageLocation = Literal["file", "keychain", "keychain_access_group"]


class _KeyringLike(Protocol):
    def get(self, ref: str) -> str | None: ...
    def set(self, ref: str, value: str) -> None: ...
    def delete(self, ref: str) -> None: ...


class MasterKeyManager:
    """Find, create, and relocate the Fernet master key."""

    def __init__(
        self,
        key_path: pathlib.Path,
        keyring: _KeyringLike,
        *,
        vault: MasterKeyBackend | None = None,
        vault_backup: Callable[[str], MasterKeyBackend] | None = None,
    ) -> None:
        self._key_path = key_path
        self._keyring = keyring
        self._vault = vault
        self._vault_backup = vault_backup
        self._location: StorageLocation | None = None
        self._key: bytes | None = None

    @property
    def location(self) -> StorageLocation | None:
        """Where the key was found, None before resolve()."""
        return self._location

    @property
    def development(self) -> bool:
        """True unless the key lives in the signed build's access group."""
        return self._vault is None

    @property
    def current(self) -> bytes | None:
        """The key this daemon resolved, held for its lifetime (never written)."""
        return self._key

    def resolve(self, *, allow_create: bool) -> bytes | None:
        """Locate the master key, creating one in the file when allowed.

        Returns None when no key exists and ``allow_create`` is False — the
        caller decides whether that is fatal (it is, when ciphertext exists).

        A keychain that cannot be read right now (``SecretLocked``) is
        never taken as "no key" when creating is allowed: the key may sit in
        it (opted in through :meth:`relocate`), and a file key created now
        would shadow it on every later start, file-first. So the lock is
        re-raised and nothing is written (spec secret "Resolve the master
        key file-first and create it only for an empty store"). Without
        ``allow_create`` a locked keychain still reads as None — the caller
        then refuses on its own terms.
        """
        try:
            key = self.lookup()
        except SecretLocked:
            if allow_create:
                raise
            key = None
        if key is not None or not allow_create:
            self._key = key
            return key
        self._key = self._create()
        return self._key

    def lookup(self) -> bytes | None:
        """The key, or None when this machine genuinely holds none.

        Unlike :meth:`resolve`, a key that exists but cannot be read right now
        is not answered as None: a locked or unavailable keychain raises
        ``SecretLocked``, and a key file that cannot be read raises
        ``OSError``. A caller that must tell "no key" from "unknown" (spec
        vault-sync "Report the refs a key cannot open as locked") uses this.
        """
        if self._vault is not None:
            in_vault = self._vault.read()
            if in_vault is not None:
                self._location = "keychain_access_group"
            return in_vault
        if self._key_path.exists():
            key = self._key_path.read_bytes().strip()
            self._location = "file"
            return key
        stored = self._keyring.get(KEYCHAIN_REF)
        if stored:
            self._location = "keychain"
            return stored.encode()
        return None

    def _create(self) -> bytes:
        key = Fernet.generate_key()
        if self._vault is not None:
            self._vault.write(key)
            self._location = "keychain_access_group"
            return key
        self._write_file(key)
        self._location = "file"
        return key

    def export_key(self) -> bytes | None:
        """Return the current master key for out-of-band transfer, or None.

        Used by sync (spec vault-sync) to write the key to a file the user moves to
        another machine by a channel they trust — the key never travels through
        the sync medium itself.
        """
        return self.resolve(allow_create=False)

    def install_key(self, key: bytes) -> None:
        """Install a master key brought from another machine (spec vault-sync bootstrap).

        Writes to the 0600 file store (the default); a machine that prefers the
        keychain can ``relocate("keychain")`` afterwards. Validates the bytes are
        a usable Fernet key so a corrupt import fails loudly instead of locking
        every secret on next decrypt.

        When a *different* key is already installed, the old key is first copied
        to a timestamped ``master.key.bak-*`` sibling: the file being replaced
        may be the only copy of the key that decrypts existing ciphertext, so
        overwriting it in place would orphan those secrets permanently.
        """
        key = key.strip()
        Fernet(key)  # raises ValueError on a malformed key
        if self._vault is not None:
            self._install_in_vault(self._vault, key)
            return
        existing = self._key_path.read_bytes().strip() if self._key_path.exists() else b""
        self._key = key
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

    def _install_in_vault(self, vault: MasterKeyBackend, key: bytes) -> None:
        """Install an imported key; a different key already there is kept as a
        second Keychain item, never as a file."""
        existing = vault.read()
        if existing and existing != key:
            if self._vault_backup is None:
                raise SecretLocked("a different master key is installed and cannot be backed up")
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
            self._vault_backup(stamp).write(existing)
        vault.write(key)
        self._key = key
        self._location = "keychain_access_group"

    def relocate(self, to: StorageLocation) -> None:
        """Move the key between file and keychain. Old copy removed last."""
        if to == self._location:
            return
        if self._vault is not None:
            raise SecretLocked(
                "this signed build keeps the master key only in its Keychain access group"
            )
        if to == "keychain":
            key = self._key_path.read_bytes().strip()
            self._keyring.set(KEYCHAIN_REF, key.decode())
            if self._keyring.get(KEYCHAIN_REF) != key.decode():
                raise SecretLocked("keychain write could not be verified")
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
