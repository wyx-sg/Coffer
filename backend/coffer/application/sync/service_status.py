"""The read half of ``SyncService``: what the Sync page and ``coffer sync
status`` show (spec vault-sync "Say a vault needs a human where the user
already is").

Everything here is read from where it already is — the remote file, the round
waiting for a person, the vault's ``HEAD``, the commits the remote lacks, the
last recorded round — and nothing is written. A problem is always the last
round's, classified by what a person can do about it.
"""

from __future__ import annotations

import asyncio
import dataclasses
import difflib
import posixpath
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from coffer.application.sync import round_answers
from coffer.application.sync.views import (
    AreaCounts,
    FileVersions,
    HoldGroup,
    Problem,
    StoppedFile,
    StoppedRound,
    SyncStatus,
    WaitingCommit,
)
from coffer.domain.git_handoff import git_install_handoff
from coffer.domain.sync.handoffs import (
    MergeFile,
    agent_mergeable,
    conflict_merge_handoff,
    is_secret_file,
    remote_failure_handoff,
    scrub_git_text,
)
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import APPROVAL_WAIT, AppliedChange, RoundRecord, RoundStatus
from coffer.domain.sync.stops import ConflictFile, HoldDirection, Stop, StopKind
from coffer.domain.vault.layout import KNOWLEDGE, MACHINES, MANIFEST, RESOURCES, SKILLS

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.sync.round_engine import RoundEngine
    from coffer.application.sync.round_ports import RemoteStorePort, RoundHistoryPort
    from coffer.application.sync.service_ports import HostMachinePort, SecretFilesPort

#: How many unpushed commits the status lists.
WAITING_LIMIT = 50

_PROBLEMS = {
    RoundStatus.UNREACHABLE: "unreachable",
    RoundStatus.AUTH_FAILED: "auth_failed",
    RoundStatus.PUSH_FAILED: "push_failed",
    RoundStatus.PLAINTEXT_FOUND: "plaintext_found",
    RoundStatus.PAUSED_CLOUD_FOLDER: "cloud_folder",
    RoundStatus.REMOTE_TOO_NEW: "layout",
    RoundStatus.FAILED: "failed",
}


def _content(path: str) -> bool:
    return not path.startswith(MACHINES + "/") and path != MANIFEST


class StatusMixin:
    """Declares what it borrows from ``SyncService``, which assigns each."""

    _engine: RoundEngine
    _remotes: RemoteStorePort
    _history: RoundHistoryPort
    _machine: HostMachinePort
    _secrets: SecretFilesPort
    _vault_path: Callable[[], Path]
    _running_since: str | None
    _next_round_at: str | None
    _git_available: Callable[[], bool]
    _host_label: Callable[[], str]

    def plaintext_handoff(self, last: RoundRecord) -> str | None: ...

    # --- the status ---------------------------------------------------------------

    async def status(self) -> SyncStatus:
        remote = await asyncio.to_thread(self._remotes.get)
        last = await self._history.recent(1)
        return await asyncio.to_thread(self._status, remote, last[0] if last else None)

    def _status(self, remote: SyncRemote | None, last: RoundRecord | None) -> SyncStatus:
        d = self._engine.d
        head = d.git.head()
        files = d.git.files(head) if head else {}
        stop = d.state.stop()
        return SyncStatus(
            remote=remote,
            machine_id=self._machine.machine_id(),
            machine_name=self._machine.label(),
            joined=d.state.joined(),
            running_since=self._running_since,
            last_round=last,
            next_round_at=self._next_round_at if remote and remote.enabled else None,
            machines=sum(1 for p in files if p.startswith(MACHINES + "/")),
            areas=AreaCounts(
                knowledge_documents=sum(1 for p in files if p.startswith(KNOWLEDGE + "/")),
                skills=len({p.split("/")[1] for p in files if p.startswith(SKILLS + "/")}),
                resources=sum(1 for p in files if p.startswith(RESOURCES + "/")),
                secrets=self._secrets.count(),
                secrets_synced=bool(remote and remote.include_secret),
            ),
            waiting=self._waiting(remote, head) if remote and head else (),
            vault_path=str(self._vault_path()),
            synchroniser=d.cloud_folder(),
            problem=self._current_problem(remote, last),
            conflicts=len(stop.unanswered) if stop and stop.kind is StopKind.CONFLICTS else 0,
            held=len(stop.hold.paths) if stop and stop.hold else 0,
            join_choices=len(d.state.join_choices()),
        )

    def _current_problem(
        self, remote: SyncRemote | None, last: RoundRecord | None
    ) -> Problem | None:
        """Git missing first (nothing else can work without it), then the last
        round's failure."""
        if remote is None:
            return None
        if not self._git_available():
            return Problem(
                kind="git_missing",
                message="git is not installed on this machine",
                handoff=git_install_handoff(
                    self._host_label(), needed_for="keeping the vault's history and syncing it"
                ),
            )
        if last is None:
            return None
        found = _problem(last, remote)
        if found is not None and found.kind == "plaintext_found":
            return dataclasses.replace(
                found, handoff=self.plaintext_handoff(last), plaintext=last.plaintext
            )
        return found

    def _waiting(self, remote: SyncRemote, head: str) -> tuple[WaitingCommit, ...]:
        """The commits ``origin/<branch>..HEAD``: what the next push carries."""
        git = self._engine.d.git
        tip = git.remote_tip(remote.branch)
        if tip == head:
            return ()
        commits = git.log(start=f"{tip}..{head}" if tip else head, limit=WAITING_LIMIT)
        out: list[WaitingCommit] = []
        for c in commits:
            changes = tuple(AppliedChange(p.path, p.status) for p in c.paths if _content(p.path))
            if not changes:
                continue
            out.append(
                WaitingCommit(
                    version=c.version,
                    time=c.time.isoformat(timespec="seconds"),
                    writer=c.meta.writer,
                    summary=c.meta.summary,
                    changes=changes,
                )
            )
        return tuple(out)

    # --- the round waiting for a person ---------------------------------------------

    async def stopped(self) -> StoppedRound | None:
        return await asyncio.to_thread(self._stopped)

    def _stopped(self) -> StoppedRound | None:
        d = self._engine.d
        stop = d.state.stop()
        if stop is None:
            return None
        scratch = d.scratch
        handed = (
            tuple(c for c in stop.conflicts if agent_mergeable(c))
            if stop.kind is StopKind.CONFLICTS and scratch is not None
            else ()
        )
        handoff = self._merge_handoff(stop, handed) if handed else None
        files = tuple(
            StoppedFile(
                c,
                editor_path=scratch.where(c.path) if scratch is not None else None,
                secret=is_secret_file(c.path),
                agent_merge=c in handed,
            )
            for c in stop.conflicts
        )
        groups: tuple[HoldGroup, ...] = ()
        machines: tuple[str, ...] = ()
        if stop.hold is not None:
            before = stop.local if stop.hold.direction is HoldDirection.INCOMING else stop.base
            groups = _groups(stop.hold.paths, d.git.files(before) if before else {})
            if stop.hold.direction is HoldDirection.INCOMING:
                machines = d.pulled(stop.local, stop.remote)[1]
            else:
                machines = (self._machine.label(),)
        return StoppedRound(
            stop,
            files=files,
            groups=groups,
            machines=machines,
            confirmed=d.state.confirmed() == (stop.local, stop.remote),
            handoff=handoff,
        )

    def _merge_handoff(self, stop: Stop, handed: tuple[ConflictFile, ...]) -> str | None:
        """The agent's prompt. Each handed file's marked-up copy is written
        first (once; the same copy "Open in editor" opens), so the prompt can
        name where the agent edits."""
        d = self._engine.d
        merge: list[MergeFile] = []
        with d.lock:
            for c in handed:
                copy = round_answers.editor_copy(self._engine, c.path)
                ours = d.git.log(c.path, start=stop.local, limit=1)
                theirs = d.git.log(c.path, start=stop.remote, limit=1)
                merge.append(
                    MergeFile(
                        c,
                        copy=copy,
                        ours_commit=ours[0].version if ours else None,
                        theirs_commit=theirs[0].version if theirs else None,
                    )
                )
        return conflict_merge_handoff(
            vault=str(self._vault_path()),
            machine=self._machine.label(),
            local=stop.local,
            remote=stop.remote,
            base=stop.base,
            files=merge,
            secret_files=sum(1 for c in stop.unanswered if is_secret_file(c.path)),
        )

    async def file_versions(self, path: str) -> FileVersions | None:
        """A stopped file's versions, and what taking the other side's changes here."""
        return await asyncio.to_thread(self._file_versions, path)

    def _file_versions(self, path: str) -> FileVersions | None:
        d = self._engine.d
        stop = d.state.stop()
        # A stopped round's file, or a join's differing file (the same answer
        # "what does taking the other side change here" serves both).
        candidates = (*(stop.conflicts if stop else ()), *d.state.join_choices())
        found = next((c for c in candidates if c.path == path), None)
        if found is None:
            return None
        blobs = d.git.blobs([b for b in (found.ours, found.theirs, found.base) if b])
        texts: dict[str, str | None] = {}
        binary = False
        for side, blob in (("ours", found.ours), ("theirs", found.theirs), ("base", found.base)):
            raw = blobs.get(blob) if blob else None
            try:
                texts[side] = raw.decode("utf-8") if raw is not None else None
            except UnicodeDecodeError:
                texts[side], binary = None, True
        take = "".join(
            difflib.unified_diff(
                (texts["ours"] or "").splitlines(keepends=True),
                (texts["theirs"] or "").splitlines(keepends=True),
                fromfile=f"this machine/{path}",
                tofile=f"{found.theirs_machine or 'the other machine'}/{path}",
            )
        )
        saved = d.scratch.read(path) if d.scratch and not is_secret_file(path) else None
        return FileVersions(
            path=path,
            ours=texts["ours"],
            theirs=texts["theirs"],
            base=texts["base"],
            take_theirs=take,
            binary=binary,
            edited=saved.decode("utf-8", "replace") if saved is not None else None,
        )


def _groups(paths: tuple[str, ...], before: dict[str, str]) -> tuple[HoldGroup, ...]:
    """The held paths by folder, with how many files each folder held."""
    held: dict[str, list[str]] = {}
    for path in paths:
        held.setdefault(posixpath.dirname(path) or ".", []).append(path)
    sizes = Counter(posixpath.dirname(p) or "." for p in before)
    return tuple(
        HoldGroup(folder, tuple(sorted(items)), max(sizes.get(folder, 0), len(items)))
        for folder, items in sorted(held.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    )


def _problem(last: RoundRecord, remote: SyncRemote) -> Problem | None:
    kind = _PROBLEMS.get(last.status)
    if kind is None:
        return None
    message = scrub_git_text(last.detail or last.status.value.replace("_", " "))
    if kind == "auth_failed" and APPROVAL_WAIT in message:
        # Not a refused sign-in: the token waits for a person in the desktop
        # app, so the fix is to approve it there.
        return Problem(
            kind="waiting_approval",
            message=message,
            secret_ref=remote.secret_ref,
            since=last.finished_at,
        )
    return Problem(
        kind=kind,
        message=message,
        secret_ref=remote.secret_ref if kind == "auth_failed" else None,
        since=last.finished_at,
        handoff=remote_failure_handoff(
            kind,
            url=remote.url,
            branch=remote.branch,
            detail=message,
            secret_ref=remote.secret_ref,
            username=remote.username,
        ),
    )


__all__ = ["WAITING_LIMIT", "StatusMixin"]
