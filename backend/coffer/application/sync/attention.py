"""What about sync needs a person, for the Overview's list (spec vault-sync
"Say a vault needs a human where the user already is").

One item per situation, each with the action that answers it:

- ``sync_conflicts`` — a round stopped on files both machines changed; the
  action opens the stopped round;
- ``sync_deletions_held`` — the deletion breaker held a round;
- ``sync_join_choices`` — a join left differing files for the person;
- ``sync_auth_failed`` — the remote refused the push secret;
- ``sync_waiting_approval`` — the push token waits for approval in the desktop app;
- ``sync_push_failed`` — the remote refused the push itself (a protected
  branch, a secret without write access);
- ``sync_plaintext_found`` — a file the round would push holds a plaintext
  secret, so nothing was pushed;
- ``sync_paused`` — the vault is inside a folder another tool synchronises;
- ``sync_layout`` — the remote is at a newer layout than this build's;
- ``sync_unreachable`` — the remote cannot be reached;
- ``sync_git_missing`` — no ``git`` on this machine, so nothing can sync.

Ignoring is by the item's key (kind, uid, reason). The uid is a fingerprint of
the situation — which files conflict and against which commits, which files a
hold or a join left, which plaintext values a round found, which remote
failed — so an item ignored on the Overview or on the Sync page stays ignored
for as long as it is the same situation, and comes back as a new item when the
situation changes (principle: an ignored item is not a hidden one).

Read off the round state and the last recorded round, only while a remote is
configured. A conflict an agent can merge, a refused sign-in, a refused push
and a plaintext secret carry the hand-off prompt the Sync page offers (spec
vault-sync "Hand conflicting files to an agent", "Hand a remote's failure to
an agent", "Refuse to push a plaintext secret").
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from typing import Protocol

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.domain.features import SYNC
from coffer.domain.sync.handoffs import remote_failure_handoff, scrub_git_text
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import APPROVAL_WAIT, RoundRecord, RoundStatus
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
    def git_missing_handoff(self) -> str | None: ...


def fingerprint(*parts: str | Iterable[str]) -> str:
    """A short, stable name for one situation: the same facts give the same
    uid, other facts another."""
    h = hashlib.sha256()
    for part in parts:
        for piece in [part] if isinstance(part, str) else sorted(part):
            h.update(piece.encode("utf-8"))
            h.update(b"\0")
        h.update(b"\1")
    return h.hexdigest()[:12]


def _item(
    code: str,
    reason: str,
    severity: Severity,
    path: str,
    since: str | None,
    verb: str = "review",
    handoff: str | None = None,
    uid: str | None = None,
) -> AttentionItem:
    return AttentionItem(
        kind=KIND,
        uid=uid,
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
    feature: str | None = SYNC

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
                    uid=fingerprint(stop.local, stop.remote, (c.path for c in stop.conflicts)),
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
                    uid=fingerprint(stop.local, stop.remote, stop.hold.paths),
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
                    uid=fingerprint(c.path for c in choices),
                )
            )
        no_git = self._sync.git_missing_handoff()
        if no_git is not None:
            out.append(
                _item(
                    "sync_git_missing",
                    "Sync cannot run: git is not installed on this machine.",
                    Severity.ERROR,
                    "/api/v1/sync/status",
                    None,
                    handoff=no_git,
                )
            )
        last = await self._sync.last_round()
        if last is not None and no_git is None:
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
    # The same failing remote is one situation however many rounds repeat it.
    uid = fingerprint(remote.url, remote.branch)
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
            uid=fingerprint(f"{f.path}:{f.line}:{f.key}" for f in last.plaintext if f.current),
        )
    if last.status is RoundStatus.AUTH_FAILED and APPROVAL_WAIT in detail:
        return _item(
            "sync_waiting_approval",
            f"Sync is waiting for you: {detail}".strip(),
            Severity.WARNING,
            "/api/v1/secrets",
            last.finished_at,
            uid=uid,
        )
    if last.status is RoundStatus.AUTH_FAILED:
        return _item(
            "sync_auth_failed",
            f"The sync remote refused this machine's secret. {detail}".strip(),
            Severity.ERROR,
            "/api/v1/sync/remote",
            last.finished_at,
            handoff=_handoff("auth_failed", detail, remote),
            uid=uid,
        )
    if last.status is RoundStatus.PUSH_FAILED:
        return _item(
            "sync_push_failed",
            f"The sync remote refused this machine's push. {detail}".strip(),
            Severity.WARNING,
            "/api/v1/sync/status",
            last.finished_at,
            handoff=_handoff("push_failed", detail, remote),
            uid=uid,
        )
    if last.status is RoundStatus.UNREACHABLE:
        return _item(
            "sync_unreachable",
            f"Sync cannot reach the remote. {detail}".strip(),
            Severity.WARNING,
            "/api/v1/sync/status",
            last.finished_at,
            handoff=_handoff("unreachable", detail, remote),
            uid=uid,
        )
    if last.status is RoundStatus.PAUSED_CLOUD_FOLDER:
        return _item(
            "sync_paused",
            f"Sync is paused: the vault is inside a folder {detail} synchronises. "
            "Move the vault out of it.",
            Severity.ERROR,
            "/api/v1/sync/status",
            last.finished_at,
            uid=uid,
        )
    if last.status is RoundStatus.REMOTE_TOO_NEW:
        return _item(
            "sync_layout",
            detail,
            Severity.ERROR,
            "/api/v1/sync/status",
            last.finished_at,
            uid=uid,
        )
    return None


__all__ = ["KIND", "SyncAttentionSource", "SyncStatePort"]
