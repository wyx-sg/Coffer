"""Desktop requests: what the command line asks the desktop shell to do.

Spec secret "Approve from the command line with the person's own presence
check" and desktop-app "Serve the command line's desktop requests"; design
align-cli-with-ui-and-add-tool-environments D8.

An agent cannot approve, reveal or back up anything itself: those take the
operating system's presence check in the desktop shell. ``coffer approval
approve <id>`` therefore leaves a request here, the shell (which polls every
second — each poll is its heartbeat) claims it and runs the very flow its own
buttons run: it reads the approvals from the daemon, shows the system prompt,
signs a grant pinned to each approval's target and calls the approve route.
The command waits on the request and then reports the approvals' REAL state as
the boundary holds it, so nothing written here — a forged "done" included — can
approve anything. A request carries no secret, grant or signature, and holds
nothing the agent did not already know.

In memory only: a request lives two minutes and dies with the daemon, which is
what a prompt waiting on a person should do. A key backup lives ten: its
request stays claimed while the app's backup dialog is open (the person types
a passphrase, checks presence and picks a folder there), and the shell ends it
only once the file is written or the dialog is closed.
"""

from __future__ import annotations

import secrets as _secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from coffer.domain.error_base import CofferError

DesktopOp = Literal[
    "approve",
    "reveal",
    "export_master_key",
    "import_master_key",
    "update_status",
    "update_check",
    "update_install",
    "update_auto_check",
    "uninstall",
]
DesktopStatus = Literal["waiting", "claimed", "done", "cancelled", "failed", "expired"]
TERMINAL: frozenset[str] = frozenset({"done", "cancelled", "failed", "expired"})

#: How long a request may wait for the shell and the person.
REQUEST_TTL_SECONDS = 120.0
#: How long a key backup may take: the dialog asks for more than a prompt does.
BACKUP_TTL_SECONDS = 600.0
#: A shell that polled within this long is running.
SHELL_FRESH_SECONDS = 5.0
#: Requests kept at once (finished ones included, for their reader).
_MAX_KEPT = 64


@dataclass
class DesktopRequest:
    id: str
    op: DesktopOp
    created_at: float
    expires_at: float
    #: ``approve``: the approvals, each pinned to the target it had when asked.
    approvals: dict[str, str] = field(default_factory=dict)
    #: ``reveal``: the secret's ref.
    ref: str | None = None
    #: ``update_auto_check``: the switch's new position; ``uninstall``: whether
    #: the dialog opens with Also delete my data ticked.
    enabled: bool | None = None
    #: What the shell reported (the updater's state); never a secret.
    result: dict[str, Any] | None = None
    status: DesktopStatus = "waiting"
    #: The shell's one line on how it ended (``cancelled``, a failure's reason).
    message: str | None = None
    claimed_at: float | None = None
    finished_at: float | None = None


class DesktopRequestNotFound(CofferError):  # noqa: N818
    code = "DESKTOP_REQUEST_NOT_FOUND"

    def __init__(self, request_id: str) -> None:
        super().__init__(f"no desktop request {request_id!r} (it may have expired)")


class DesktopRequests:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._requests: dict[str, DesktopRequest] = {}
        self._shell_seen_at: float | None = None

    # --- the command line's half --------------------------------------------

    def create(
        self,
        op: DesktopOp,
        *,
        approvals: dict[str, str] | None = None,
        ref: str | None = None,
        enabled: bool | None = None,
    ) -> DesktopRequest:
        self._expire()
        while len(self._requests) >= _MAX_KEPT:
            self._requests.pop(next(iter(self._requests)))
        now = self._clock()
        request = DesktopRequest(
            id=_secrets.token_hex(8),
            op=op,
            created_at=now,
            expires_at=now
            + (BACKUP_TTL_SECONDS if op == "export_master_key" else REQUEST_TTL_SECONDS),
            approvals=dict(approvals or {}),
            ref=ref,
            enabled=enabled,
        )
        self._requests[request.id] = request
        return request

    def get(self, request_id: str) -> DesktopRequest:
        self._expire()
        found = self._requests.get(request_id)
        if found is None:
            raise DesktopRequestNotFound(request_id)
        return found

    def cancel(self, request_id: str) -> DesktopRequest:
        """The command gave up waiting: a request the shell has not claimed is
        withdrawn; one it is showing finishes as the person decides."""
        request = self.get(request_id)
        if request.status == "waiting":
            self._finish(request, "cancelled", "withdrawn before the app showed it")
        return request

    # --- the shell's half -----------------------------------------------------

    def claim(self) -> DesktopRequest | None:
        """The oldest waiting request, now the shell's; ``None`` when there is
        none. Every call records the shell as running."""
        self._expire()
        self._shell_seen_at = self._clock()
        # One prompt at a time: nothing new is handed out while one is shown.
        if any(r.status == "claimed" for r in self._requests.values()):
            return None
        for request in self._requests.values():
            if request.status == "waiting":
                request.status = "claimed"
                request.claimed_at = self._clock()
                return request
        return None

    def finish(
        self,
        request_id: str,
        status: DesktopStatus,
        message: str | None,
        result: dict[str, Any] | None = None,
    ) -> DesktopRequest:
        request = self.get(request_id)
        if request.status in TERMINAL:
            return request
        if status not in TERMINAL:
            raise ValueError(f"{status!r} does not finish a request")
        self._finish(request, status, message)
        request.result = result
        return request

    def shell_running(self) -> bool:
        seen = self._shell_seen_at
        return seen is not None and self._clock() - seen <= SHELL_FRESH_SECONDS

    def shell_last_seen(self) -> float | None:
        seen = self._shell_seen_at
        return None if seen is None else self._clock() - seen

    # --- inside -----------------------------------------------------------------

    def _finish(self, request: DesktopRequest, status: DesktopStatus, message: str | None) -> None:
        request.status = status
        request.message = (message or "")[:500] or None
        request.finished_at = self._clock()

    def _expire(self) -> None:
        now = self._clock()
        for request in self._requests.values():
            if request.status not in TERMINAL and request.expires_at <= now:
                self._finish(request, "expired", "nobody answered in time")


__all__ = [
    "BACKUP_TTL_SECONDS",
    "REQUEST_TTL_SECONDS",
    "SHELL_FRESH_SECONDS",
    "TERMINAL",
    "DesktopOp",
    "DesktopRequest",
    "DesktopRequestNotFound",
    "DesktopRequests",
    "DesktopStatus",
]
