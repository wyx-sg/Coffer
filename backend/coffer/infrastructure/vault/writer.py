"""The one way anything is written into the vault
(ADR every-vault-write-is-a-validated-commit-naming-its-writer).

Three writers change the vault and none waits for the others: a person (an
editor, a shell, an agent's own file tools), the daemon (a save from the web
UI, a CLI or API change, a curation pass, a uid minted, a layout upgrade) and
sync. Every change any of them makes is admitted the same way:

1. **Compare.** A write states what it expects the file to hold — the
   fingerprint of the bytes it read, "absent", or "what ``HEAD`` holds" — and
   under the vault's one write lock the file is re-read and compared. A
   mismatch is ``VaultFileStale`` (409); there is no unconditional mode, and
   modification time never decides anything.
2. **Write** a sibling temp file and rename it into place.
3. **Validate** every path the operation touched with the one validator.
   A blocking finding puts every touched file back as it was and raises
   ``VaultValidationFailed``: an invalid write never reaches ``HEAD``.
4. **Commit** exactly the touched paths as one commit whose author and
   trailers name the writer, then tell the listeners (caches, audit, hints).

A person's edits are not intercepted: they are found by :meth:`settle`,
which the scanner calls once a changed path has been quiet. Valid ones are
committed as ``disk`` writes; invalid ones stay in the working tree,
uncommitted and flagged (:meth:`problems`), and ``HEAD`` stays in effect.

A long operation (a curation pass) holds its paths as *owned* without holding
the lock: a settle never commits an owned path, and another operation's
compare against ``HEAD`` refuses it until the owner commits.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter
from collections.abc import Callable, Iterable, Sequence

from coffer.domain.vault.content_ids import fingerprint
from coffer.domain.vault.errors import VaultFileStale, VaultValidationFailed
from coffer.domain.vault.findings import Finding, blocking
from coffer.domain.vault.writers import OP_EDIT, OP_MINT_UID, WRITER_DAEMON, WRITER_DISK, CommitMeta
from coffer.domain.vault.writes import (
    Change,
    CommitResult,
    Expect,
    Fix,
    Listener,
    Snapshot,
    Validator,
    accept_all,
    check_path,
)
from coffer.infrastructure.vault.atomic import atomic_write, remove_file
from coffer.infrastructure.vault.repository import VaultRepository

logger = logging.getLogger(__name__)


def _nothing_held() -> tuple[str, ...]:
    return ()


class Transaction:
    """One operation's writes, committed once."""

    def __init__(self, writer: VaultWriter, meta: CommitMeta) -> None:
        self._writer = writer
        self.meta = meta
        self.paths: list[str] = []
        self._originals: dict[str, bytes | None] = {}
        self.version: str | None = None
        self._open = True

    def read(self, path: str) -> Snapshot:
        return Snapshot(path, self._writer.read_disk(check_path(path)))

    def touch(self, path: str) -> None:
        """Claim ``path`` for this commit (the caller writes it itself)."""
        path = check_path(path)
        if path not in self.paths:
            self.paths.append(path)
            self._originals.setdefault(path, self._writer.read_disk(path))
            self._writer._own(path)

    def write(self, path: str, data: bytes, expected: str | Expect | None = Expect.HEAD) -> None:
        self._put(check_path(path), data, expected)

    def delete(self, path: str, expected: str | Expect | None = Expect.HEAD) -> None:
        self._put(check_path(path), None, expected)

    def _put(self, path: str, data: bytes | None, expected: str | Expect | None) -> None:
        w = self._writer
        with w.lock:
            current = w.read_disk(path)
            if path not in self.paths:
                w.compare(path, current, expected)
            self.touch(path)
            if data is None:
                remove_file(w.repo.root / path, stop_at=w.repo.root)
            else:
                atomic_write(w.repo.root / path, data)

    def commit(self, meta: CommitMeta | None = None) -> str | None:
        """Validate and commit what this operation touched; answer the commit,
        or ``None`` when nothing changed. A second call commits nothing."""
        if not self._open:
            return self.version
        self._open = False
        try:
            result = self._writer._finish(self.paths, meta or self.meta, self._originals)
        finally:
            self._writer._release(self.paths)
        self.version = result.version if result else None
        if result is not None:
            self._writer._notify(result)
        return self.version

    def abort(self) -> None:
        """Put every touched file back as it was before this operation."""
        if not self._open:
            return
        self._open = False
        with self._writer.lock:
            self._writer._restore(self._originals)
        self._writer._release(self.paths)

    def __enter__(self) -> Transaction:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.abort()


class VaultWriter:
    """The vault's single write path. One instance per vault root."""

    def __init__(
        self,
        repo: VaultRepository,
        *,
        validator: Validator | None = None,
        machine: Callable[[], str | None] = lambda: None,
    ) -> None:
        self.repo = repo
        self.lock = threading.RLock()
        self._validator = validator or accept_all
        self._machine = machine
        self._owned: Counter[str] = Counter()
        self._listeners: list[Listener] = []
        self._problems: dict[str, tuple[Finding, ...]] = {}
        self._held: Callable[[], Iterable[str]] = _nothing_held

    # --- configuration -------------------------------------------------------

    def set_validator(self, validator: Validator) -> None:
        self._validator = validator

    @property
    def validator(self) -> Validator:
        """The one validator every write passes (a sync round's merged tree too)."""
        return self._validator

    def add_listener(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def set_held(self, provider: Callable[[], Iterable[str]]) -> None:
        """Paths deliberately kept different from ``HEAD`` — a join's files
        that differ, left as they are here until the person chooses. They are
        never settled; the stores read them from disk."""
        self._held = provider

    def held(self) -> frozenset[str]:
        return frozenset(self._held())

    def restore_disk(self, path: str, data: bytes | None) -> None:
        """Put ``data`` back at ``path`` on disk without committing — only for
        a held path, whose working-tree bytes are deliberately not ``HEAD``'s."""
        path = check_path(path)
        with self.lock:
            target = self.repo.root / path
            if data is None:
                remove_file(target, stop_at=self.repo.root)
            else:
                atomic_write(target, data)

    # --- reading ---------------------------------------------------------------

    def read_disk(self, path: str) -> bytes | None:
        target = self.repo.root / path
        try:
            return target.read_bytes() if target.is_file() else None
        except OSError:
            return None

    def compare(self, path: str, current: bytes | None, expected: str | Expect | None) -> None:
        """Raise ``VaultFileStale`` unless ``current`` is what was expected."""
        if expected is None:
            return
        if expected is Expect.ABSENT:
            if current is not None:
                raise VaultFileStale(path, f"{path} already exists")
            return
        if expected is Expect.HEAD:
            if self._owned[path]:
                raise VaultFileStale(path, f"{path} is being written by another operation")
            if current != self.repo.read("HEAD", path):
                raise VaultFileStale(
                    path, f"{path} has an edit on disk that is not settled yet; try again shortly"
                )
            return
        if current is None or fingerprint(current) != expected:
            raise VaultFileStale(path)

    # --- writing ---------------------------------------------------------------

    def begin(self, meta: CommitMeta) -> Transaction:
        self.repo.ensure()
        return Transaction(self, meta)

    transaction = begin

    def write_file(
        self,
        path: str,
        data: bytes,
        *,
        meta: CommitMeta,
        expected: str | Expect | None = Expect.HEAD,
    ) -> str | None:
        with self.begin(meta) as txn:
            txn.write(path, data, expected)
        return txn.version

    def delete_file(
        self, path: str, *, meta: CommitMeta, expected: str | Expect | None = Expect.HEAD
    ) -> str | None:
        with self.begin(meta) as txn:
            txn.delete(path, expected)
        return txn.version

    def _own(self, path: str) -> None:
        with self.lock:
            self._owned[path] += 1

    def _release(self, paths: Sequence[str]) -> None:
        with self.lock:
            for path in paths:
                self._owned[path] -= 1
                if self._owned[path] <= 0:
                    del self._owned[path]

    def _restore(self, originals: dict[str, bytes | None]) -> None:
        for path, data in originals.items():
            target = self.repo.root / path
            if data is None:
                remove_file(target, stop_at=self.repo.root)
            else:
                atomic_write(target, data)

    def _changes(self, paths: Sequence[str]) -> list[Change]:
        return [Change(p, self.read_disk(p), self.repo.read("HEAD", p)) for p in paths]

    def _finish(
        self, paths: Sequence[str], meta: CommitMeta, originals: dict[str, bytes | None]
    ) -> CommitResult | None:
        if not paths:
            return None
        with self.lock:
            verdict = self._validator(self._changes(paths), self.repo)
            refused = blocking(verdict.findings)
            if refused:
                self._restore(originals)
                raise VaultValidationFailed(refused)
            self.repo.stage(paths)
            version = self.repo.commit_staged(meta.with_machine(self._machine()))
            for path in paths:
                self._problems.pop(path, None)
        if version is None:
            return None
        return CommitResult(version, meta, tuple(paths))

    def notify(self, result: CommitResult) -> None:
        """Tell every listener about a commit made outside this writer's own
        transactions — a sync round's checkout, which moves ``HEAD`` itself
        under :attr:`lock`."""
        self._notify(result)

    def _notify(self, result: CommitResult) -> None:
        for listener in list(self._listeners):
            try:
                listener(result)
            except Exception:
                logger.warning("vault.listener_failed", exc_info=True)

    # --- a person's edits --------------------------------------------------------

    def pending(self) -> dict[str, str | None]:
        """Every working-tree path that differs from ``HEAD`` and no operation
        owns, with the fingerprint it has now (``None`` for a deletion)."""
        self.repo.ensure()
        with self.lock:
            out: dict[str, str | None] = {}
            changed = [p for _code, p in self.repo.status() if not p.endswith("/")]
            ignored = self.repo.ignored(changed) | self.repo.unsupported(changed)
            held = self.held()
            for path in changed:
                if self._owned[path] or path in ignored or path in held:
                    continue
                data = self.read_disk(path)
                out[path] = fingerprint(data) if data is not None else None
            return out

    def settle(
        self, paths: Sequence[str] | None = None, *, meta: CommitMeta | None = None
    ) -> CommitResult | None:
        """Commit what a person changed on disk (all pending paths, or the
        given ones): valid files as one ``disk`` commit, invalid ones left in
        the working tree and recorded in :meth:`problems`. Fixes the validator
        asks for (a minted uid) follow as one ``daemon`` commit."""
        meta = meta or CommitMeta(writer=WRITER_DISK, operation=OP_EDIT, summary="Edited on disk")
        with self.lock:
            held = self.held()
            candidates = [
                p
                for p in (paths if paths is not None else self.pending())
                if not self._owned[p] and p not in held
            ]
            if not candidates:
                return None
            changes = self._changes(candidates)
            verdict = self._validator(changes, self.repo)
            bad: dict[str, list[Finding]] = {}
            for finding in blocking(verdict.findings):
                bad.setdefault(finding.path, []).append(finding)
            good = [c.path for c in changes if c.path not in bad]
            for path in candidates:
                if path in bad:
                    self._problems[path] = tuple(bad[path])
                else:
                    self._problems.pop(path, None)
            result: CommitResult | None = None
            if good:
                self.repo.stage(good)
                version = self.repo.commit_staged(meta.with_machine(self._machine()))
                if version:
                    result = CommitResult(version, meta, tuple(good))
            fixes = [f for f in verdict.fixes if f.path in good]
        if result is not None:
            self._notify(result)
        if fixes:
            self._apply_fixes(fixes)
        return result

    def _apply_fixes(self, fixes: Sequence[Fix]) -> None:
        summary = fixes[0].summary if len(fixes) == 1 else f"Gave {len(fixes)} new files their uid"
        try:
            with self.begin(
                CommitMeta(writer=WRITER_DAEMON, operation=OP_MINT_UID, summary=summary)
            ) as txn:
                for fix in fixes:
                    txn.write(fix.path, fix.data, Expect.HEAD)
        except (VaultFileStale, VaultValidationFailed):
            logger.warning("vault.fix_failed", exc_info=True)

    def problems(self) -> dict[str, tuple[Finding, ...]]:
        """Files on disk that failed validation and are not committed."""
        with self.lock:
            return dict(self._problems)

    def forget_problem(self, path: str) -> None:
        with self.lock:
            self._problems.pop(path, None)


__all__ = ["Transaction", "VaultWriter"]
