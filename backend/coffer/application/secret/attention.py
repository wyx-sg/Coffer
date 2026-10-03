"""The secret boundary's contribution to the Overview's "needs you" list.

Three signals, each about the secret kind's own state:

- ``secret_missing_here`` — secrets with no value on this Mac: cited by a
  resource but not stored here, or stored under another Mac's master key and so
  unopenable here (spec secret "Show a secret this Mac cannot open as missing
  on this Mac"). One item for the set, an error: whatever uses them cannot
  start. Its action opens the Secrets page, where each row takes a value.
- ``secret_approvals_pending`` — changes waiting for a person in the desktop
  app (spec secret "Hold a secret for a new destination until a person
  approves it"). One item for the set, a warning, whose action opens the
  approvals dialog.
- ``secret_approval_off`` — spec secret "Turn the protection off only through
  the desktop app": while the approval requirement is off, a secret goes to any
  new destination without asking, which is something a person who switched it
  off a while ago should be told is still the case. The item's action is the
  call that turns it back on, which needs no approval — it only narrows.

A GET action is a navigation: the page it opens is the kind's to choose, not
the route's. The first two items are about a *set*, so their ``uid`` is a short
fingerprint of its members: ignoring one ignores exactly that set, and the
moment a secret goes missing, a value is added, or an approval arrives or is
decided, the key changes and the item comes back (layout principle "a banner
you can close comes back when the situation changes").
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Protocol

from coffer.application.attention import AttentionAction, AttentionItem, Severity
from coffer.domain.resource import Resource
from coffer.domain.secrets import SecretApproval

KIND = "secret"
REASON_CODE = "secret_approval_off"
MISSING_REASON_CODE = "secret_missing_here"
PENDING_REASON_CODE = "secret_approvals_pending"


class SecretCitationsPort(Protocol):
    async def cited_secret_refs(self) -> Mapping[str, Sequence[Resource]]: ...


class SecretFilesPort(Protocol):
    """The encrypted store, as far as presence goes (nothing is decrypted)."""

    def list_refs(self) -> list[tuple[str, str, str]]: ...

    def unreadable_refs(self) -> list[str]: ...


class PendingApprovalsPort(Protocol):
    def list(self, *, status: str | None = None) -> list[SecretApproval]: ...


def fingerprint(members: Iterable[str]) -> str:
    """A short, order-independent digest of a set of names or ids."""
    joined = "\n".join(sorted(set(members)))
    return hashlib.sha256(joined.encode()).hexdigest()[:12]


class SecretAttentionSource:
    name = "secret"
    feature: str | None = None

    def __init__(
        self,
        protections_on: Callable[[], bool],
        *,
        resources: SecretCitationsPort | None = None,
        store: SecretFilesPort | None = None,
        approvals: PendingApprovalsPort | None = None,
    ) -> None:
        self._protections_on = protections_on
        self._resources = resources
        self._store = store
        self._approvals = approvals

    async def items(self) -> Sequence[AttentionItem]:
        out: list[AttentionItem] = []
        if self._resources is not None and self._store is not None:
            missing = await self._missing_here(self._resources, self._store)
            if missing:
                out.append(_missing_item(missing))
        approvals = self._approvals
        if approvals is not None:
            pending = await asyncio.to_thread(lambda: approvals.list(status="pending"))
            if pending:
                out.append(_pending_item(pending))
        if not await asyncio.to_thread(self._protections_on):
            out.append(_approval_off_item())
        return out

    @staticmethod
    async def _missing_here(resources: SecretCitationsPort, store: SecretFilesPort) -> list[str]:
        cited = await resources.cited_secret_refs()
        stored = {ref for ref, _c, _u in await asyncio.to_thread(store.list_refs)}
        locked = set(await asyncio.to_thread(store.unreadable_refs))
        return sorted((set(cited) - stored) | locked)


def _missing_item(refs: list[str]) -> AttentionItem:
    n = len(refs)
    return AttentionItem(
        kind=KIND,
        uid=fingerprint(refs),
        title="Secrets",
        reason_code=MISSING_REASON_CODE,
        reason=(
            f"{n} secret has no value on this Mac."
            if n == 1
            else f"{n} secrets have no value on this Mac."
        ),
        severity=Severity.ERROR,
        action=AttentionAction(verb="open", method="GET", path="/api/v1/secrets"),
    )


def _pending_item(pending: list[SecretApproval]) -> AttentionItem:
    n = len(pending)
    return AttentionItem(
        kind=KIND,
        uid=fingerprint(a.id for a in pending),
        title="Secret approvals",
        reason_code=PENDING_REASON_CODE,
        reason=(
            "1 change waiting for approval." if n == 1 else f"{n} changes waiting for approval."
        ),
        severity=Severity.WARNING,
        action=AttentionAction(
            verb="review", method="GET", path="/api/v1/secrets/approvals?status=pending"
        ),
    )


def _approval_off_item() -> AttentionItem:
    return AttentionItem(
        kind=KIND,
        uid=None,
        title="Secret approval",
        reason_code=REASON_CODE,
        reason=(
            "Secret approval is off: a secret can be sent to a new destination without asking."
        ),
        severity=Severity.WARNING,
        action=AttentionAction(
            verb="turn_on",
            method="PUT",
            path="/api/v1/settings/secret-boundary",
            body={"require_approval": True},
        ),
    )


__all__ = ["SecretAttentionSource", "fingerprint"]
