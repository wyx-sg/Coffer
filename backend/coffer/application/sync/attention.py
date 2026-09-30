"""What about sync needs a person, for the Overview's list (spec vault-sync
"Say a vault needs a human where the user already is").

One item per situation, each with the action that answers it:

- ``sync_conflicts`` — a round stopped on files both machines changed; the
  action opens the stopped round;
- ``sync_deletions_held`` — the deletion breaker held a round;
- ``sync_join_choices`` — a join left differing files for the person;
- ``sync_auth_failed`` — the remote refused the push token;
- ``sync_paused`` — the vault is inside a folder another tool synchronises;
- ``sync_layout`` — the remote is at another layout than this build's.

Read off the round state and the last recorded round, only while a remote is
configured.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import RoundRecord, RoundStatus
from coffer.domain.sync.stops import ConflictFile, Stop, StopKind

KIND = "sync"
_TITLE = "Sync"


class SyncStatePort(Protocol):
    async def get_remote(self) -> SyncRemote | None: ...
    async def stop(self) -> Stop | None: ...
    async def join_choices(self) -> tuple[ConflictFile, ...]: ...
    async def last_round(self) -> RoundRecord | None: ...


def _item(
    code: str, reason: str, severity: Severity, path: str, since: str | None, verb: str = "review"
) -> AttentionItem:
    return AttentionItem(
        kind=KIND,
        uid=None,
        title=_TITLE,
        reason_code=code,
        reason=reason,
        severity=severity,
        action=AttentionAction(verb=verb, method="GET", path=path),
        since=datetime.fromisoformat(since) if since else None,
    )


def _files(n: int) -> str:
    return "1 file" if n == 1 else f"{n} files"


class SyncAttentionSource:
    name = "sync"
    feature: str | None = None

    def __init__(self, *, sync: SyncStatePort) -> None:
        self._sync = sync

    async def items(self) -> Sequence[AttentionItem]:
        if await self._sync.get_remote() is None:
            return []
        out: list[AttentionItem] = []
        stop = await self._sync.stop()
        if stop is not None and stop.kind is StopKind.CONFLICTS:
            out.append(
                _item(
                    "sync_conflicts",
                    f"Sync stopped on {_files(len(stop.conflicts))} both machines changed; "
                    "choose which version to keep.",
                    Severity.ERROR,
                    "/api/v1/sync/stop",
                    stop.raised_at,
                )
            )
        elif stop is not None and stop.hold is not None:
            out.append(
                _item(
                    "sync_deletions_held",
                    f"A round would delete {_files(len(stop.hold.paths))}; review before "
                    "they are deleted or restored.",
                    Severity.WARNING,
                    "/api/v1/sync/stop",
                    stop.raised_at,
                )
            )
        choices = await self._sync.join_choices()
        if choices:
            out.append(
                _item(
                    "sync_join_choices",
                    f"{_files(len(choices))} differ between this machine and the remote; "
                    "choose which version to keep.",
                    Severity.WARNING,
                    "/api/v1/sync/join-choices",
                    None,
                )
            )
        last = await self._sync.last_round()
        if last is not None:
            found = _problem_item(last)
            if found is not None:
                out.append(found)
        return out


def _problem_item(last: RoundRecord) -> AttentionItem | None:
    detail = last.detail or ""
    if last.status is RoundStatus.AUTH_FAILED:
        return _item(
            "sync_auth_failed",
            f"The sync remote refused this machine's credential. {detail}".strip(),
            Severity.ERROR,
            "/api/v1/sync/remote",
            last.finished_at,
        )
    if last.status is RoundStatus.PAUSED_CLOUD_FOLDER:
        return _item(
            "sync_paused",
            f"Sync is paused: the vault is inside a folder {detail} synchronises. "
            "Move the vault out of it.",
            Severity.ERROR,
            "/api/v1/sync/status",
            last.finished_at,
        )
    if last.status in (RoundStatus.REMOTE_TOO_NEW, RoundStatus.REMOTE_TOO_OLD):
        return _item("sync_layout", detail, Severity.ERROR, "/api/v1/sync/status", last.finished_at)
    return None


__all__ = ["KIND", "SyncAttentionSource", "SyncStatePort"]
