"""The master-key half of ``ConvergeService`` (spec vault-sync).

Split out for the file-size tier, along a real seam: a round never touches the
key, and this half never touches a round. It reports this machine's key
fingerprint, previews a key file beside it, and installs one (spec vault-sync
"Import a master key after showing whose key it is"). The key crosses nothing
here but the port: no route or return value carries it.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.sync.errors import MasterKeyFileInvalid

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.audit_service import AuditService
    from coffer.application.sync.ports import MasterKeyPort, SecretSyncPort


def _fingerprint(key: bytes) -> str:
    return hashlib.sha256(key.strip()).hexdigest()[:12]


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
    #: Stored secrets the installed key decrypts.
    readable: int
    #: Stored secrets it still cannot decrypt.
    locked_refs: list[str]


class KeyMixin:
    """Declares what it borrows from the service it is mixed into.

    The annotations are the contract, not state: ``ConvergeService`` assigns
    them in its constructor.
    """

    _master_key: MasterKeyPort
    _secret_store: SecretSyncPort
    _audit: AuditService

    def key_fingerprint(self) -> str | None:
        """A short SHA-256 fingerprint of the master key, never the key.

        Two machines showing the same fingerprint hold the same key. It rides
        in each machine's descriptor, so the machines table can say outright
        that another machine's secrets will not decrypt here.
        """
        key = self._master_key.export_key()
        return _fingerprint(key) if key else None

    def preview_key(self, material: str) -> KeyPreview:
        """Whose key a file holds, beside this machine's, before replacing it.

        Opens nothing: a passphrase-protected backup names its key's
        fingerprint in the clear, and the import checks it against the key.
        """
        fingerprint, protected = self._master_key.peek_backup(material)
        return KeyPreview(
            fingerprint=fingerprint, current=self.key_fingerprint(), protected=protected
        )

    async def import_key(self, material: str, passphrase: str | None = None) -> KeyImport:
        """Install the key a file holds, and say which secrets it opens here.

        A different key already installed is kept beside it (the manager's
        backup), never overwritten in place. The passphrase is used once, to
        open the file, and is neither stored nor recorded.
        """
        key = await asyncio.to_thread(self._master_key.open_backup, material, passphrase)
        previous = self.key_fingerprint()
        try:
            await asyncio.to_thread(self._master_key.install_key, key)
        except ValueError as e:
            raise MasterKeyFileInvalid("<import>", "not a valid Fernet key") from e
        fingerprint = _fingerprint(key)
        replaced = previous is not None and previous != fingerprint
        await self._audit.record(
            AuditEventType.MASTER_KEY_IMPORTED.value,
            actor="sync",
            details={"fingerprint": fingerprint, "replaced": previous if replaced else None},
        )
        locked = await asyncio.to_thread(self._secret_store.locked_refs)
        stored = await asyncio.to_thread(self._secret_store.list_refs)
        return KeyImport(
            fingerprint=fingerprint,
            replaced=replaced,
            readable=len(set(stored) - set(locked)),
            locked_refs=locked,
        )
