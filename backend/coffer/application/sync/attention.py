"""What about sync needs a person, for the Overview's list (spec vault-sync
"Say a vault needs a human where the user already is").

One item per situation, each with the action that answers it:

- ``sync_conflicts`` — a round stopped on files both machines changed; the
  action opens the stopped round;
- ``sync_deletions_held`` — the deletion breaker held a round;
- ``sync_join_choices`` — a join left differing files for the person;
- ``sync_auth_failed`` — the remote refused the push secret;
- ``sync_push_failed`` — the remote refused the push itself (a protected
  branch, a secret without write access);
- ``sync_plaintext_found`` — a file the round would push holds a plaintext
  secret, so nothing was pushed;
- ``sync_paused`` — the vault is inside a folder another tool synchronises;
- ``sync_layout`` — the remote is at another layout than this build's.

Read off the round state and the last recorded round, only while a remote is
configured. A conflict an agent can merge, a refused sign-in, a refused push
and a plaintext secret carry the hand-off prompt the Sync page offers (spec
vault-sync "Hand a conflict's merge to an agent", "Hand a remote's failure to
an agent", "Refuse to push a plaintext secret").
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.domain.sync.handoffs import remote_failure_handoff, scrub_git_text
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
    async def conflict_handoff(self) -> str | None: ...
    def plaintext_handoff(self, last: RoundRecord) -> str | None: ...


def _item(
    code: str,
    reason: str,
    severity: Severity,
    path: str,
    since: str | None,
    verb: str = "review",
    handoff: str | None = None,
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
        handoff=handoff,
    )


def _files(n: int) -> str:
    return "1 file" if n == 1 else f"{n} files"


class SyncAttentionSource:
    name = "sync"
    feature: str | None = None

    def __init__(self, *, sync: SyncStatePort) -> None:
        self._sync = sync

    async def items(self) -> Sequence[AttentionItem]:
        remote = await self._sync.get_remote()
        if remote is None:
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
                    handoff=await self._sync.conflict_handoff(),
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
            found = _problem_item(last, remote, self._sync.plaintext_handoff)
            if found is not None:
                out.append(found)
        return out


def _handoff(kind: str, detail: str, remote: SyncRemote) -> str | None:
    return remote_failure_handoff(
        kind,
        url=remote.url,
        branch=remote.branch,
        detail=detail,
        secret_ref=remote.secret_ref,
        username=remote.username,
    )


def _problem_item(
    last: RoundRecord, remote: SyncRemote, plaintext: Callable[[RoundRecord], str | None]
) -> AttentionItem | None:
    detail = scrub_git_text(last.detail or "")
    if last.status is RoundStatus.PLAINTEXT_FOUND:
        files = sorted({f"{f.path}:{f.line}" for f in last.plaintext if f.current})
        return _item(
            "sync_plaintext_found",
            "Sync pushed nothing: a plaintext secret is in "
            + (", ".join(files[:3]) or "a file the round would push")
            + (f" and {len(files) - 3} more" if len(files) > 3 else "")
            + ". Move it into a secret, or push anyway.",
            Severity.ERROR,
            "/api/v1/sync/status",
            last.finished_at,
            handoff=plaintext(last),
        )
    if last.status is RoundStatus.AUTH_FAILED:
        return _item(
            "sync_auth_failed",
            f"The sync remote refused this machine's secret. {detail}".strip(),
            Severity.ERROR,
            "/api/v1/sync/remote",
            last.finished_at,
            handoff=_handoff("auth_failed", detail, remote),
        )
    if last.status is RoundStatus.PUSH_FAILED:
        return _item(
            "sync_push_failed",
            f"The sync remote refused this machine's push. {detail}".strip(),
            Severity.WARNING,
            "/api/v1/sync/status",
            last.finished_at,
            handoff=_handoff("push_failed", detail, remote),
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
