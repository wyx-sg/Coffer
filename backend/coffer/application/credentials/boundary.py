"""The secret boundary: a secret goes somewhere new only with a person's approval.

Spec credentials "Hold a secret for a new destination until a person approves
it"; ADR only-a-present-human-sees-a-secret-or-sends-it-somewhere-new, rules 2
and 3. Every consumer that injects a secret — an MCP spawn, a channel adapter,
the sync push, a provider connection — asks :meth:`SecretBoundary.require`
before it resolves, naming the destination and the target that will receive
the value. A binding is approved when:

* a person approved it in the desktop app (with a presence grant the daemon
  verified before calling :meth:`approve`);
* it was in use before the boundary existed (adopted once, at the first start);
* the value was supplied for it moments ago — the ref has never been bound
  anywhere, is not a standalone ``secret/`` name, and was stored within
  ``FRESH_WINDOW`` — because a caller that just typed the value already has it;
* or the protection is switched off, which itself takes an approval.

Everything else becomes a pending approval, and nothing is injected.

Synchronous on purpose: it is consulted from the resolver, which already runs
in a worker thread. Async callers use ``asyncio.to_thread``.
"""

from __future__ import annotations

import builtins
import secrets as _secrets
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Protocol

from coffer.domain.credential_errors import (
    ApprovalNotFound,
    ApprovalNotPending,
    SecretBindingPending,
)
from coffer.domain.secrets import (
    SecretApproval,
    SecretBinding,
    SecretDestination,
    is_standalone_ref,
)

REQUIRE_APPROVAL_KEY = "require_approval"
ADOPTED_KEY = "adopted_existing_bindings"
#: How recently a never-bound value must have been stored to count as supplied
#: for the binding that cites it.
FRESH_WINDOW = timedelta(minutes=5)

#: Every destination in use right now: where, which refs per slot, and who last
#: changed it (the actor an approval names).
Destinations = Iterable[tuple[SecretDestination, Mapping[str, str], str]]


class BoundaryStorePort(Protocol):
    def get_binding(self, ref: str, kind: str, uid: str, slot: str) -> SecretBinding | None: ...
    def bindings(self, ref: str | None = None) -> builtins.list[SecretBinding]: ...
    def has_any_binding(self, ref: str) -> bool: ...
    def put_binding(self, binding: SecretBinding) -> None: ...
    def delete_bindings(self, ref: str) -> None: ...
    def create_approval(
        self, approval: SecretApproval, ciphertext: bytes | None = None
    ) -> None: ...
    def get_approval(self, approval_id: str) -> SecretApproval | None: ...
    def pending_ciphertext(self, approval_id: str) -> bytes | None: ...
    def find_open_bind(
        self, ref: str, kind: str, uid: str, slot: str, target_fingerprint: str
    ) -> SecretApproval | None: ...
    def pending_of_op(self, op: str, ref: str | None = None) -> list[SecretApproval]: ...
    def list_approvals(
        self, *, status: str | None = None, destination_uid: str | None = None, limit: int = 200
    ) -> list[SecretApproval]: ...
    def decide(self, approval_id: str, status: str, *, by: str, at: str) -> bool: ...
    def get_setting(self, key: str) -> str | None: ...
    def set_setting(self, key: str, value: str) -> None: ...


class SealedValueStorePort(Protocol):
    """The slice of the encrypted store the boundary needs."""

    def exists(self, ref: str) -> bool: ...
    def created_at(self, ref: str) -> datetime | None: ...
    def set(self, ref: str, value: str) -> None: ...
    def seal(self, value: str) -> bytes: ...
    def unseal(self, token: bytes) -> str: ...


def _now() -> datetime:
    return datetime.now(tz=UTC)


class SecretBoundary:
    def __init__(
        self,
        store: BoundaryStorePort,
        values: SealedValueStorePort,
        *,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._store = store
        self._values = values
        self._clock = clock

    def _stamp(self) -> str:
        return self._now().isoformat()

    def _now(self) -> datetime:
        now = self._clock()
        return now if now.tzinfo else now.replace(tzinfo=UTC)

    # --- the switch ---------------------------------------------------------

    def protections_on(self) -> bool:
        return self._store.get_setting(REQUIRE_APPROVAL_KEY) != "false"

    def enable_protections(self) -> None:
        """Turning the protection ON needs nobody: it only narrows."""
        self._store.set_setting(REQUIRE_APPROVAL_KEY, "true")
        for approval in self._store.pending_of_op("disable_protection"):
            self._store.decide(approval.id, "superseded", by="system", at=self._stamp())

    def request_disable(self, actor: str) -> SecretApproval:
        """Turning it OFF waits for the desktop app, like any other widening."""
        existing = self._store.pending_of_op("disable_protection")
        if existing:
            return existing[0]
        approval = SecretApproval(
            id=_secrets.token_hex(8),
            op="disable_protection",
            status="pending",
            created_at=self._stamp(),
            requested_by=actor,
        )
        self._store.create_approval(approval)
        return approval

    # --- the gate -----------------------------------------------------------

    def _fresh(self, ref: str) -> bool:
        if is_standalone_ref(ref) or self._store.has_any_binding(ref):
            return False
        created = self._values.created_at(ref)
        if created is None:
            return False
        created = created if created.tzinfo else created.replace(tzinfo=UTC)
        return self._now() - created <= FRESH_WINDOW

    def _approve_binding(
        self, ref: str, dest: SecretDestination, slot: str, approval_id: str | None
    ) -> None:
        self._store.put_binding(
            SecretBinding(
                ref=ref,
                destination_kind=dest.kind,
                destination_uid=dest.uid,
                slot=slot,
                target_fingerprint=dest.target_fingerprint,
                approved_at=self._stamp(),
                approval_id=approval_id,
            )
        )

    def check(
        self, dest: SecretDestination, refs: Mapping[str, str], *, actor: str = "system"
    ) -> list[SecretApproval]:
        """The approvals ``dest`` still waits on for ``refs``; empty means go.

        ``refs`` maps each slot (an environment variable, a header, a config
        field) to the ref it cites. Records a pending approval for each slot
        that is neither approved nor auto-approvable, once per target — a
        target that changes again supersedes the approval for the old one.
        """
        pending: list[SecretApproval] = []
        fp = dest.target_fingerprint
        on = self.protections_on()
        for slot, ref in refs.items():
            bound = self._store.get_binding(ref, dest.kind, dest.uid, slot)
            if bound is not None and bound.target_fingerprint == fp:
                continue
            if not on or (bound is None and self._fresh(ref)):
                self._approve_binding(ref, dest, slot, None)
                continue
            # A refused binding stays refused for this target: asking again
            # would put the same question back in front of the person.
            waiting = self._store.find_open_bind(ref, dest.kind, dest.uid, slot, fp)
            if waiting is None:
                self._supersede_bind(ref, dest.kind, dest.uid, slot)
                waiting = SecretApproval(
                    id=_secrets.token_hex(8),
                    op="bind",
                    status="pending",
                    created_at=self._stamp(),
                    requested_by=actor,
                    ref=ref,
                    destination_kind=dest.kind,
                    destination_uid=dest.uid,
                    destination_label=dest.label,
                    slot=slot,
                    target=dest.target,
                    target_fingerprint=fp,
                )
                self._store.create_approval(waiting)
            pending.append(waiting)
        return pending

    def require(
        self, dest: SecretDestination, refs: Mapping[str, str], *, actor: str = "system"
    ) -> None:
        """Raise ``SecretBindingPending`` unless every binding is approved.

        The one call every consumer — and every future destination type, such
        as a provider connection's base URL or a custom tool's auth — makes
        before it resolves a secret for ``dest``.
        """
        pending = self.check(dest, refs, actor=actor)
        if pending:
            raise SecretBindingPending([a.id for a in pending], [a.describe() for a in pending])

    def _supersede_bind(self, ref: str, kind: str, uid: str, slot: str) -> None:
        for approval in self._store.pending_of_op("bind", ref):
            if (approval.destination_kind, approval.destination_uid, approval.slot) == (
                kind,
                uid,
                slot,
            ):
                self._store.decide(approval.id, "superseded", by="system", at=self._stamp())

    def adopt(self, current: Destinations) -> int:
        """Approve, once, every binding in use before the boundary existed."""
        if self._store.get_setting(ADOPTED_KEY) == "true":
            return 0
        adopted = 0
        for dest, refs, _actor in current:
            for slot, ref in refs.items():
                if self._store.get_binding(ref, dest.kind, dest.uid, slot) is None:
                    self._approve_binding(ref, dest, slot, None)
                    adopted += 1
        self._store.set_setting(ADOPTED_KEY, "true")
        return adopted

    def refresh(self, current: Destinations) -> list[SecretApproval]:
        """Evaluate every current destination and retire approvals nothing wants.

        Run before listing approvals, so an approval is on the list as soon as
        the change that needs it is saved, not only at the next spawn; and an
        approval whose destination was deleted, or whose target moved on, no
        longer asks the person anything.
        """
        wanted: set[tuple[str, str, str, str, str]] = set()
        created: list[SecretApproval] = []
        for dest, refs, actor in current:
            for approval in self.check(dest, refs, actor=actor):
                created.append(approval)
            for slot, ref in refs.items():
                wanted.add((ref, dest.kind, dest.uid, slot, dest.target_fingerprint))
        for approval in self._store.pending_of_op("bind"):
            key = (
                approval.ref or "",
                approval.destination_kind or "",
                approval.destination_uid or "",
                approval.slot or "",
                approval.target_fingerprint or "",
            )
            if key not in wanted:
                self._store.decide(approval.id, "superseded", by="system", at=self._stamp())
        return created

    # --- replacing a value that is in use ------------------------------------

    def in_use(self, ref: str) -> bool:
        """Whether replacing ``ref``'s value changes what an approved place gets."""
        return is_standalone_ref(ref) or self._store.has_any_binding(ref)

    def write(self, ref: str, value: str, *, actor: str) -> SecretApproval | None:
        """Store ``value`` now, or hold it for approval when ``ref`` is in use.

        A new ref, or one nothing was ever sent to, is written at once: the
        caller supplied the value. Replacing the value of a ref that an
        approved destination receives — or of a standalone secret — changes
        what that destination gets, so it waits, sealed, for the desktop app.
        """
        if not self.protections_on() or not self._values.exists(ref) or not self.in_use(ref):
            self._values.set(ref, value)
            return None
        for approval in self._store.pending_of_op("replace_value", ref):
            self._store.decide(approval.id, "superseded", by="system", at=self._stamp())
        approval = SecretApproval(
            id=_secrets.token_hex(8),
            op="replace_value",
            status="pending",
            created_at=self._stamp(),
            requested_by=actor,
            ref=ref,
        )
        self._store.create_approval(approval, self._values.seal(value))
        return approval

    # --- deciding -----------------------------------------------------------

    def get(self, approval_id: str) -> SecretApproval:
        approval = self._store.get_approval(approval_id)
        if approval is None:
            raise ApprovalNotFound(approval_id)
        return approval

    def approve(self, approval_id: str, *, actor: str) -> SecretApproval:
        """Apply a pending approval. The caller has verified a presence grant."""
        approval = self.get(approval_id)
        if approval.status != "pending":
            raise ApprovalNotPending(approval_id, approval.status)
        sealed = self._store.pending_ciphertext(approval_id)
        if not self._store.decide(approval_id, "approved", by=actor, at=self._stamp()):
            raise ApprovalNotPending(approval_id, self.get(approval_id).status)
        if approval.op == "bind":
            assert approval.ref and approval.destination_kind and approval.destination_uid
            self._store.put_binding(
                SecretBinding(
                    ref=approval.ref,
                    destination_kind=approval.destination_kind,
                    destination_uid=approval.destination_uid,
                    slot=approval.slot or "",
                    target_fingerprint=approval.target_fingerprint or "",
                    approved_at=self._stamp(),
                    approval_id=approval.id,
                )
            )
        elif approval.op == "replace_value":
            assert approval.ref and sealed is not None
            self._values.set(approval.ref, self._values.unseal(sealed))
        else:
            self._store.set_setting(REQUIRE_APPROVAL_KEY, "false")
        return self.get(approval_id)

    def reject(self, approval_id: str, *, actor: str) -> SecretApproval:
        """Refuse a pending approval. Anyone may: refusing only narrows."""
        approval = self.get(approval_id)
        if not self._store.decide(approval_id, "rejected", by=actor, at=self._stamp()):
            raise ApprovalNotPending(approval_id, approval.status)
        return self.get(approval_id)

    def list(
        self, *, status: str | None = None, destination_uid: str | None = None
    ) -> builtins.list[SecretApproval]:
        return self._store.list_approvals(status=status, destination_uid=destination_uid)

    def bindings(self, ref: str | None = None) -> builtins.list[SecretBinding]:
        return self._store.bindings(ref)

    def forget(self, ref: str) -> None:
        """A deleted secret takes its bindings with it; a new value is a new secret."""
        self._store.delete_bindings(ref)
