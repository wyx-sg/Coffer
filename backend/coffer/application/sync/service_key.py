"""The master-key half of ``SyncService`` (spec vault-sync "Import a master
key after showing whose key it is").

Split out along a real seam: a round never touches the key, and this half
never touches a round. It reports this machine's key fingerprint, previews a
key file beside it, and installs one. The key crosses nothing here but the
port: no route or return value carries it, and the passphrase that opens a
protected backup is used once and neither stored nor recorded.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.sync.errors import MasterKeyFileInvalid

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.audit_service import AuditService
    from coffer.application.sync.service_ports import MasterKeyPort, SecretFilesPort


@dataclass(frozen=True)
class KeyPreview:
    """A key file set beside this machine's key, before anything is replaced."""

    fingerprint: str
    #: This machine's key, or None when it holds none yet.
    current: str | None
    #: True when the file is a passphrase-protected backup.
    protected: bool


@dataclass(frozen=True)
class KeyImport:
    """What an import changed and what this machine can read afterwards."""

    fingerprint: str
    #: True when a different key was installed before.
    replaced: bool
    #: Secret files the installed key decrypts.
    readable: int
    #: Secret files it still cannot decrypt.
    locked_refs: list[str]


class KeyMixin:
    """Declares what it borrows from ``SyncService``, which assigns each."""

    _master_key: MasterKeyPort
    _secrets: SecretFilesPort
    _audit: AuditService

    def key_fingerprint(self) -> str | None:
        """A short SHA-256 fingerprint of the master key, never the key.

        Two machines showing the same fingerprint hold the same key; it rides
        in each machine's descriptor, so the machines list can say that
        another machine's secrets will not decrypt here.
        """
        return self._master_key.fingerprint()

    def preview_key(self, material: str) -> KeyPreview:
        """Whose key a file holds, beside this machine's, changing nothing.

        Opens nothing: a protected backup names its key's fingerprint in the
        clear, and the import checks it against the key.
        """
        fingerprint, protected = self._master_key.peek_backup(material)
        return KeyPreview(
            fingerprint=fingerprint, current=self.key_fingerprint(), protected=protected
        )

    async def import_key(self, material: str, passphrase: str | None = None) -> KeyImport:
        """Install the key a file holds, and say which secrets it opens here.

        A different key already installed is kept beside it (the manager's
        backup), never overwritten in place.
        """
        key = await asyncio.to_thread(self._master_key.open_backup, material, passphrase)
        previous = self.key_fingerprint()
        try:
            await asyncio.to_thread(self._master_key.install_key, key)
        except ValueError as e:
            raise MasterKeyFileInvalid("<import>", "not a valid Fernet key") from e
        fingerprint = self.key_fingerprint() or ""
        replaced = previous is not None and previous != fingerprint
        await self._audit.record(
            AuditEventType.MASTER_KEY_IMPORTED.value,
            actor="user",
            details={"fingerprint": fingerprint, "replaced": previous if replaced else None},
        )
        locked = await asyncio.to_thread(self._secrets.locked_refs)
        stored = await asyncio.to_thread(self._secrets.count)
        return KeyImport(
            fingerprint=fingerprint,
            replaced=replaced,
            readable=stored - len(locked),
            locked_refs=locked,
        )


__all__ = ["KeyImport", "KeyMixin", "KeyPreview"]
