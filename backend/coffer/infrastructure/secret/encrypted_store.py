"""Fernet-encrypted secrets as files, one per ref (ADR storage-is-five-classes-by-nature).

A ref's ciphertext is ``vault/secret/<ref>.enc`` — the Fernet token and a
trailing newline, the file name being the opaque ref (``ref_paths``). The
vault is where the user's configuration lives, and ciphertext is safe to hold
there because the key is not: it stays in the OS secret store or the
``0600`` key file, never in the tree. Whether the files are committed is the
repository's business, not this store's — ``secret/`` is in the vault's
``info/exclude`` until a sync remote carries secrets (ADR
secrets-cross-machines-only-as-ciphertext) — so every vault write still goes through the
process's one vault writer (ADR every-vault-write-is-a-validated-commit-naming-its-writer),
compare-and-swap against what was just read, and becomes a ``daemon`` commit
naming the ref when the repository carries secrets.

Machine-local refs (a proxy token) live in ``local/secret/`` instead,
written atomically under this store's lock, and never enter the vault.

Timestamps. ``updated_at`` is the token's own encryption time, which the
ciphertext carries in clear (``coffer.domain.vault.fernet_time``), so it is
right on every machine without a second file to keep in step. ``created_at``
is when *this machine* first stored the ref, kept in
``local/secret-boundary/times.json``; a ref that arrived from another
machine by sync has no such moment, so ``created_at`` answers None
for it and the secret boundary never counts it as a value a person here has
just supplied (spec secret "Hold a secret for a new destination until a
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
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from coffer.domain.secret_errors import SecretUnreadable
from coffer.domain.vault.fernet_time import encrypted_at
from coffer.domain.vault.layout import SECRET
from coffer.domain.vault.writers import WRITER_DAEMON, CommitMeta
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.secret.ref_paths import is_local_ref, ref_to_relpath, relpath_to_ref
from coffer.infrastructure.vault.atomic import atomic_write, remove_file
from coffer.infrastructure.vault.home import local_root, vault_root
from coffer.infrastructure.vault.instance import vault_writer
from coffer.infrastructure.vault.json_store import JsonStore

OP_SECRET_SET = "secret-set"
OP_SECRET_DELETE = "secret-delete"

_FILE_MODE = 0o600
_DIR_MODE = 0o700

#: How stale ``last_used_at`` may get before a read stamps it again.
_USE_STAMP_EVERY = timedelta(minutes=1)


class EncryptedSecretStore:
    """``get/set/delete`` over ciphertext files, plus the listing and sealing
    the Secrets page and the secret boundary need.

    ``home`` is the user's home (the parent of ``.coffer``); left out, every
    call resolves it from ``HOME`` so a test in a throwaway home moves the
    store with it.
    """

    def __init__(self, key: bytes, *, home: Path | None = None) -> None:
        self._fernet = Fernet(key)
        self._home = home
        self._local_lock = threading.RLock()
        self._removed_hooks: list[Callable[[str], None]] = []
        self._times = JsonStore(lambda: local_root(self._home) / "secret-boundary" / "times.json")
        self._used = JsonStore(
            lambda: local_root(self._home) / "secret-boundary" / "last-used.json"
        )

    # --- where things are ------------------------------------------------------

    def _vault_dir(self) -> Path:
        return _vault_dir(self._home)

    def _local_dir(self) -> Path:
        return _local_dir(self._home)

    def on_removed(self, hook: Callable[[str], None]) -> None:
        """Call ``hook(ref)`` after a ref's ciphertext is really removed, by
        whichever path removed it. The secret boundary uses it to forget where
        the ref had been approved to go (spec secret "List every stored and cited
        secret with what uses it": a delete that removes a ref forgets its
        destinations)."""
        self._removed_hooks.append(hook)

    def use_key(self, key: bytes) -> None:
        """Encrypt and decrypt with ``key`` from now on — an imported master key.

        Nothing stored is re-encrypted: ciphertext written under the previous
        key stays as it is and reads as unreadable until that key comes back.
        """
        self._fernet = Fernet(key)

    def path_of(self, ref: str) -> Path:
        """The file ``ref``'s ciphertext is (or would be) stored in."""
        base = self._local_dir() if is_local_ref(ref) else self._vault_dir()
        return base / ref_to_relpath(ref)

    def _bytes(self, ref: str) -> bytes | None:
        try:
            return self.path_of(ref).read_bytes()
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
            return None

    # --- the secret port ---------------------------------------------------

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
        data = self._bytes(ref)
        if data is None:
            return None
        try:
            value = self._fernet.decrypt(data.strip()).decode()
        except InvalidToken as e:
            raise SecretUnreadable(ref) from e
        if stamp:
            self._stamp_use(ref)
        return value

    def _stamp_use(self, ref: str) -> None:
        """Record that ``ref`` was just used, in ``local/secret-boundary/last-used.json``.

        Machine-local: sync carries only the ciphertext, and when a value was
        last used is true of this machine only (spec secret "List every
        stored and cited secret with what uses it")."""
        now = datetime.now(tz=UTC)

        def stamp(used: dict[str, object]) -> None:
            last = used.get(ref)
            if isinstance(last, str):
                try:
                    if now - datetime.fromisoformat(last) < _USE_STAMP_EVERY:
                        return
                except ValueError:
                    pass
            used[ref] = now.isoformat()

        self._used.update(stamp)

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

        ``delete`` keeps the ``-> None`` shape the secret ports declare;
        a caller that must act only on a real removal (the HTTP route audits
        only then — spec secret "Delete a secret idempotently") uses
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
        self._used.update(forget)
        if removed:
            for hook in self._removed_hooks:
                hook(ref)
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
        data = self._bytes(ref)
        return _fernet_time(data) if data is not None else None

    def list_refs(self) -> list[tuple[str, str, str]]:
        """Every stored ref with its creation and update time, never a value.

        The enumeration the Secrets page and ``coffer secret list`` need to
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

    def last_used(self) -> dict[str, str]:
        """``{ref: when it was last used}`` for every stored ref ever used here."""
        stored = self._files()
        return {
            ref: when
            for ref, when in self._used.read().items()
            if ref in stored and isinstance(when, str)
        }

    def unreadable_refs(self) -> list[str]:
        """Stored refs this machine's master key cannot open — decrypting nothing.

        Each token's HMAC is checked against the key (``extract_timestamp``
        verifies the signature and reads no plaintext), so a ciphertext that
        came with the vault from a machine holding another key is found
        without any value being decrypted (spec secret "Show a secret this Mac
        cannot open as missing on this Mac").
        """
        out: list[str] = []
        for ref, path in sorted(self._files().items()):
            try:
                self._fernet.extract_timestamp(path.read_bytes().strip())
            except (OSError, InvalidToken):
                out.append(ref)
        return out

    # --- the files ---------------------------------------------------------------

    def _files(self) -> dict[str, Path]:
        return ref_files(self._home)

    def _write_vault(self, ref: str, data: bytes) -> None:
        rel = f"{SECRET}/{ref_to_relpath(ref)}"
        writer = vault_writer(vault_root(self._home))
        meta = CommitMeta(
            writer=WRITER_DAEMON, operation=OP_SECRET_SET, summary=f"Stored secret {ref}"
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
            operation=OP_SECRET_DELETE,
            summary=f"Deleted secret {ref}",
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


__all__ = ["OP_SECRET_DELETE", "OP_SECRET_SET", "EncryptedSecretStore", "ref_files"]
