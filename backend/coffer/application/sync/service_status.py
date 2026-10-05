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

from coffer.application.sync import round_diff
from coffer.application.sync.round_merge import merge_info
from coffer.application.sync.views import (
    AreaCounts,
    FileVersions,
    HoldGroup,
    Problem,
    RoundFileDiff,
    StoppedFile,
    StoppedRound,
    SyncStatus,
    WaitingCommit,
)
from coffer.domain.git_handoff import git_install_handoff
from coffer.domain.sync.errors import SyncRoundFileNotListed, SyncRoundNotFound
from coffer.domain.sync.handoffs import (
    agent_mergeable,
    is_secret_file,
    remote_failure_handoff,
    scrub_git_text,
)
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import APPROVAL_WAIT, AppliedChange, RoundRecord, RoundStatus
from coffer.domain.sync.stops import ConflictFile, HoldDirection, StopKind
from coffer.domain.vault.layout import KNOWLEDGE, MACHINES, MANIFEST, RESOURCES, SKILLS

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.sync.round_engine import RoundEngine
    from coffer.application.sync.round_ports import RemoteStorePort, RoundHistoryPort
    from coffer.application.sync.service_ports import (
        HostMachinePort,
        SecretFilesPort,
        VaultMoverPort,
    )

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
    _mover: VaultMoverPort | None
    _running_since: str | None
    _next_round_at: str | None
    _git_available: Callable[[], bool]
    _host_label: Callable[[], str]

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
        ahead, behind = self._divergence(remote, head)
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
            ahead=ahead,
            behind=behind,
            vault_real_path=self._mover.real_path() if self._mover else None,
            default_vault_path=self._mover.default_path() if self._mover else None,
        )

    def _divergence(self, remote: SyncRemote | None, head: str | None) -> tuple[int, int]:
        """``(ahead, behind)`` against the remote as last fetched; ``(0, 0)``
        while there is no remote, no commit, or no fetch to compare with."""
        if remote is None or head is None:
            return 0, 0
        git = self._engine.d.git
        tip = git.remote_tip(remote.branch)
        if tip is None or tip == head:
            return 0, 0

        def carrying(since: str, until: str) -> int:
            """Commits that changed content — a machine's own registry entry is not a change."""
            return sum(
                1
                for c in git.commits_between(since, until)
                if any(_content(p.path) for p in c.paths)
            )

        return carrying(tip, head), carrying(head, tip)

    def git_missing_handoff(self) -> str | None:
        """The install hand-off while no ``git`` is found, read afresh each
        time so "Check again" is just asking again; ``None`` when git is there."""
        if self._git_available():
            return None
        return git_install_handoff(
            self._host_label(), needed_for="keeping the vault's history and syncing it"
        )

    def _current_problem(
        self, remote: SyncRemote | None, last: RoundRecord | None
    ) -> Problem | None:
        """Git missing first (nothing else can work without it), then the last
        round's failure."""
        if remote is None:
            return None
        missing = self.git_missing_handoff()
        if missing is not None:
            return Problem(
                kind="git_missing",
                message="git is not installed on this machine",
                handoff=missing,
            )
        if last is None:
            return None
        found = _problem(last, remote)
        if found is not None and found.kind == "plaintext_found":
            return dataclasses.replace(found, plaintext=last.plaintext)
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
        files = self._stopped_files(stop.conflicts) if stop.kind is StopKind.CONFLICTS else ()
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
        )

    def _stopped_files(self, conflicts: tuple[ConflictFile, ...]) -> tuple[StoppedFile, ...]:
        """Each file with where its copy is and where an agent's merge of it stands."""
        d = self._engine.d
        out: list[StoppedFile] = []
        for c in conflicts:
            info = merge_info(d, c)
            out.append(
                StoppedFile(
                    c,
                    editor_path=d.scratch.where(c.path) if d.scratch is not None else None,
                    secret=is_secret_file(c.path),
                    agent_mergeable=agent_mergeable(c),
                    agent_state=info.state if info else None,
                    merged_at=info.merged_at if info else None,
                )
            )
        return tuple(out)

    async def round_file_diff(self, round_id: int, path: str, side: str) -> RoundFileDiff:
        """One file a round applied or pushed, line by line (nothing stored)."""
        record = await self._history.get(round_id)
        if record is None:
            raise SyncRoundNotFound(round_id)
        return await asyncio.to_thread(round_diff.file_diff, self._engine.d, record, path, side)

    async def pending_file_diff(self, path: str) -> RoundFileDiff:
        """One file the next push carries, from the remote's tip to ``HEAD``:
        every waiting commit that touched it, as one change."""
        remote = await asyncio.to_thread(self._remotes.get)
        return await asyncio.to_thread(self._pending_file_diff, remote, path)

    def _pending_file_diff(self, remote: SyncRemote | None, path: str) -> RoundFileDiff:
        d = self._engine.d
        head = d.git.head()
        waiting = self._waiting(remote, head) if remote and head else ()
        if not any(c.path == path for w in waiting for c in w.changes):
            raise SyncRoundFileNotListed(path, "push")
        assert remote is not None
        return round_diff.between(d, path, "pending", d.git.remote_tip(remote.branch), head)

    async def held_file_diff(self, path: str) -> RoundFileDiff:
        """One file a held round would delete: its whole text, as removed."""
        return await asyncio.to_thread(self._held_file_diff, path)

    def _held_file_diff(self, path: str) -> RoundFileDiff:
        d = self._engine.d
        stop = d.state.stop()
        hold = stop.hold if stop else None
        if stop is None or hold is None or path not in hold.paths:
            raise SyncRoundFileNotListed(path, "delete")
        # Incoming: the other Mac deletes what this one still has; outgoing:
        # this Mac deletes what the remote still has.
        incoming = hold.direction is HoldDirection.INCOMING
        before, after = (stop.local, stop.remote) if incoming else (stop.remote, stop.local)
        return round_diff.between(d, path, "held", before, after)

    async def join_files(self) -> tuple[StoppedFile, ...]:
        """A join's differing files, in the shape a stopped round's are."""
        return await asyncio.to_thread(
            lambda: self._stopped_files(self._engine.d.state.join_choices())
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
        blobs = d.git.blobs([b for b in (found.ours, found.theirs) if b])
        texts: dict[str, str | None] = {}
        binary = False
        for side, blob in (("ours", found.ours), ("theirs", found.theirs)):
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
        return FileVersions(
            path=path,
            ours=texts["ours"],
            theirs=texts["theirs"],
            take_theirs=take,
            binary=binary,
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
