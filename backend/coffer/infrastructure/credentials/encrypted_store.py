"""Fernet-encrypted credentials as files, one per ref (ADR storage-is-five-classes-by-nature).

A ref's ciphertext is ``vault/secret/<ref>.enc`` — the Fernet token and a
trailing newline, the file name being the opaque ref (``ref_paths``). The
vault is where the user's configuration lives, and ciphertext is safe to hold
there because the key is not: it stays in the OS credential store or the
``0600`` key file, never in the tree. Whether the files are committed is the
repository's business, not this store's — ``secret/`` is in the vault's
``info/exclude`` until a sync remote carries credentials (ADR
credentials-across-machines) — so every vault write still goes through the
process's one vault writer (ADR every-vault-write-is-a-validated-commit-naming-its-writer),
compare-and-swap against what was just read, and becomes a ``daemon`` commit
naming the ref when the repository carries credentials.

Machine-local refs (a proxy token) live in ``local/secret/`` instead,
written atomically under this store's lock, and never enter the vault.

Timestamps. ``updated_at`` is the token's own encryption time, which the
ciphertext carries in clear (``coffer.domain.vault.fernet_time``), so it is
right on every machine without a second file to keep in step. ``created_at``
is when *this machine* first stored the ref, kept in
``local/secret-boundary/times.json``; a ref that arrived from elsewhere (a
sync round, the migration) has no such moment, so ``created_at`` answers None
for it and the secret boundary never counts it as a value a person here has
just supplied (spec credentials "Hold a secret for a new destination until a
person approves it"). Listings show the encryption time in its place.

Files are ``0600`` and the directories holding them ``0700``. Plaintext exists
only in memory between decrypt and the spawn that consumes it; no ciphertext
reaches logs or audit rows, and a commit summary names the ref only.

Async callers go through the ``a*`` wrappers: a vault write runs git, and
nothing blocking belongs on the event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from coffer.domain.errors import CredentialUnreadable
from coffer.domain.vault.fernet_time import encrypted_at
from coffer.domain.vault.layout import SECRET
from coffer.domain.vault.writers import WRITER_DAEMON, CommitMeta
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.credentials.ref_paths import is_local_ref, ref_to_relpath, relpath_to_ref
from coffer.infrastructure.vault.atomic import atomic_write, remove_file
from coffer.infrastructure.vault.home import local_root, vault_root
from coffer.infrastructure.vault.instance import vault_writer
from coffer.infrastructure.vault.json_store import JsonStore

OP_CREDENTIAL_SET = "credential-set"
OP_CREDENTIAL_DELETE = "credential-delete"

_FILE_MODE = 0o600
_DIR_MODE = 0o700


class EncryptedCredentialStore:
    """``get/set/delete`` over ciphertext files, plus the listing and sealing
    the Secrets page and the secret boundary need.

    ``home`` is the user's home (the parent of ``.coffer``); left out, every
    call resolves it from ``HOME`` so a test or a rehearsal in a throwaway
    home moves the store with it.
    """

    def __init__(self, key: bytes, *, home: Path | None = None) -> None:
        self._fernet = Fernet(key)
        self._home = home
        self._local_lock = threading.RLock()
        self._times = JsonStore(lambda: local_root(self._home) / "secret-boundary" / "times.json")

    # --- where things are ------------------------------------------------------

    def _vault_dir(self) -> Path:
        return _vault_dir(self._home)

    def _local_dir(self) -> Path:
        return _local_dir(self._home)

    def path_of(self, ref: str) -> Path:
        """The file ``ref``'s ciphertext is (or would be) stored in."""
        base = self._local_dir() if is_local_ref(ref) else self._vault_dir()
        return base / ref_to_relpath(ref)

    def _read(self, ref: str) -> bytes | None:
        try:
            return self.path_of(ref).read_bytes()
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
            return None

    # --- the credential port ---------------------------------------------------

    def get(self, ref: str) -> str | None:
        data = self._read(ref)
        if data is None:
            return None
        try:
            return self._fernet.decrypt(data.strip()).decode()
        except InvalidToken as e:
            raise CredentialUnreadable(ref) from e

    def set(self, ref: str, value: str) -> None:
        data = self._fernet.encrypt(value.encode()) + b"\n"
        if is_local_ref(ref):
            path = self.path_of(ref)
            with self._local_lock:
                _make_dirs(path.parent, stop_at=local_root(self._home))
                atomic_write(path, data, mode=_FILE_MODE)
        else:
            self._write_vault(ref, data)

        def first_seen(times: dict[str, object]) -> None:
            times.setdefault(ref, _now())

        self._times.update(first_seen)

    def exists(self, ref: str) -> bool:
        """Presence probe that never decrypts, so ciphertext written under
        another key still reports present."""
        return self.path_of(ref).is_file()

    def delete(self, ref: str) -> None:
        self.remove(ref)

    def remove(self, ref: str) -> bool:
        """Delete ``ref`` and report whether a file was actually removed.

        ``delete`` keeps the ``-> None`` shape the credential ports declare;
        a caller that must act only on a real removal (the HTTP route audits
        only then — spec credentials "Delete a credential idempotently") uses
        this instead.
        """
        if is_local_ref(ref):
            with self._local_lock:
                removed = remove_file(self.path_of(ref), stop_at=self._local_dir())
        else:
            removed = self._delete_vault(ref)

        def forget(times: dict[str, object]) -> None:
            times.pop(ref, None)

        self._times.update(forget)
        return removed

    def created_at(self, ref: str) -> datetime | None:
        """When this machine first stored ``ref``; None when it is not stored
        or arrived from elsewhere (see the module docstring)."""
        if not self.exists(ref):
            return None
        stamp = self._times.read().get(ref)
        return datetime.fromisoformat(stamp) if isinstance(stamp, str) else None

    def updated_at(self, ref: str) -> datetime | None:
        """When ``ref``'s current value was encrypted, read from its token."""
        data = self._read(ref)
        return _fernet_time(data) if data is not None else None

    def list_refs(self) -> list[tuple[str, str, str]]:
        """Every stored ref with its creation and update time, never a value.

        The enumeration the Secrets page and ``coffer credentials list`` need to
        show a stored secret nothing cites (ADR
        standalone-secrets-are-named-references-injected-into-one-child).
        """
        times = self._times.read()
        out: list[tuple[str, str, str]] = []
        for ref, path in sorted(self._files().items()):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            updated = _fernet_time(data) or datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            created = times.get(ref)
            out.append(
                (
                    ref,
                    created if isinstance(created, str) else updated.isoformat(),
                    updated.isoformat(),
                )
            )
        return out

    def count(self) -> int:
        """How many refs hold ciphertext here — whether a new master key may
        be created (only over none)."""
        return len(self._files())

    def seal(self, value: str) -> bytes:
        """Encrypt a value that is not stored yet — a replacement awaiting approval."""
        return self._fernet.encrypt(value.encode())

    def unseal(self, token: bytes) -> str:
        try:
            return self._fernet.decrypt(token).decode()
        except InvalidToken as e:
            raise CredentialUnreadable("<pending replacement>") from e

    # --- the files ---------------------------------------------------------------

    def _files(self) -> dict[str, Path]:
        return ref_files(self._home)

    def _write_vault(self, ref: str, data: bytes) -> None:
        rel = f"{SECRET}/{ref_to_relpath(ref)}"
        writer = vault_writer(vault_root(self._home))
        meta = CommitMeta(
            writer=WRITER_DAEMON, operation=OP_CREDENTIAL_SET, summary=f"Stored credential {ref}"
        )
        # One lock over the read and the write, so two sets of one ref queue
        # instead of the second failing its compare against the first.
        with writer.lock, writer.begin(meta) as txn:
            _make_dirs((writer.repo.root / rel).parent, stop_at=writer.repo.root)
            current = txn.read(rel)
            txn.write(rel, data, current.fingerprint or Expect.ABSENT)
            os.chmod(writer.repo.root / rel, _FILE_MODE)

    def _delete_vault(self, ref: str) -> bool:
        rel = f"{SECRET}/{ref_to_relpath(ref)}"
        writer = vault_writer(vault_root(self._home))
        if not (writer.repo.root / rel).is_file():
            return False
        meta = CommitMeta(
            writer=WRITER_DAEMON,
            operation=OP_CREDENTIAL_DELETE,
            summary=f"Deleted credential {ref}",
        )
        with writer.lock, writer.begin(meta) as txn:
            current = txn.read(rel)
            if current.fingerprint is None:
                return False
            txn.delete(rel, current.fingerprint)
        return True

    # --- async facade: the same calls, off the event loop --------------------

    async def aget(self, ref: str) -> str | None:
        return await asyncio.to_thread(self.get, ref)

    async def aexists(self, ref: str) -> bool:
        return await asyncio.to_thread(self.exists, ref)

    async def aset(self, ref: str, value: str) -> None:
        await asyncio.to_thread(self.set, ref, value)

    async def adelete(self, ref: str) -> None:
        await asyncio.to_thread(self.delete, ref)


def _vault_dir(home: Path | None) -> Path:
    return vault_root(home) / SECRET


def _local_dir(home: Path | None) -> Path:
    return local_root(home) / SECRET


def ref_files(home: Path | None = None) -> dict[str, Path]:
    """Every ref file, vault and local, each in the directory its family
    belongs to (a stray proxy token under ``vault/`` is not listed). Needs no
    key, so startup can ask whether any ciphertext exists before it has one."""
    found: dict[str, Path] = {}
    for base, local in ((_vault_dir(home), False), (_local_dir(home), True)):
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            ref = relpath_to_ref(path.relative_to(base).as_posix())
            if ref is not None and is_local_ref(ref) == local:
                found[ref] = path
    return found


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _fernet_time(data: bytes) -> datetime | None:
    seconds = encrypted_at(data)
    return datetime.fromtimestamp(seconds, tz=UTC) if seconds is not None else None


def _make_dirs(path: Path, *, stop_at: Path) -> None:
    """Create ``path`` and its parents up to ``stop_at``, each ``0700``."""
    missing: list[Path] = []
    cursor = path
    while cursor != stop_at and not cursor.is_dir():
        missing.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    stop_at.mkdir(parents=True, exist_ok=True)
    for directory in reversed(missing):
        with contextlib.suppress(FileExistsError):
            directory.mkdir(mode=_DIR_MODE)
        os.chmod(directory, _DIR_MODE)


__all__ = ["OP_CREDENTIAL_DELETE", "OP_CREDENTIAL_SET", "EncryptedCredentialStore", "ref_files"]
