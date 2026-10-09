"""The secret boundary: a secret goes somewhere new only with a person's approval.

Spec secret "Hold a secret for a new destination until a person approves
it"; ADR only-a-present-human-sees-a-secret-or-sends-it-somewhere-new, rules 2
and 3. Every consumer that injects a secret — an MCP spawn, a channel adapter,
the sync push, a provider connection — asks :meth:`SecretBoundary.require`
before it resolves, naming the destination and the target that will receive
the value. A binding is approved when:

* a person approved it in the desktop app (with a presence grant the daemon
  verified before calling :meth:`approve`);
* the value was supplied for it — the destination was just registered or
  changed (:meth:`bind`, called by the one post-register seam every resource
  kind goes through), and the ref has never been bound anywhere, is not a
  standalone ``secret/`` name and was written on this machine within
  ``FRESH_WINDOW`` — because a caller that just typed the value already has it.
  The binding is recorded right there, so a later destination citing the same
  ref is a second destination and waits: the window only bounds how old an
  unused value may be, it is no longer a race to the first use;
* or the protection is switched off, which itself takes an approval.

The local-process grant (``coffer run`` handing a standalone secret to a program
on this machine) is the exception to the last two: a program an agent starts can
read what it is given, so that grant is only ever a person's approval — never
the build's default, never a value just supplied — and revoking it needs nobody.

Everything else becomes a pending approval, and nothing is injected. A
destination reached only at the moment of use (:meth:`require`, :meth:`refresh`)
never counts as supplied: whatever arrived behind Coffer's back waits.

Synchronous on purpose: it is consulted from the resolver, which already runs
in a worker thread. Async callers use ``asyncio.to_thread``.
"""

from __future__ import annotations

import builtins
import secrets as _secrets
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta

from coffer.application.secret.boundary_ports import BoundaryStorePort, SealedValueStorePort
from coffer.domain.secret_errors import (
    ApprovalNotFound,
    ApprovalNotPending,
    SecretBindingPending,
    SecretBindingRejected,
)
from coffer.domain.secrets import (
    LOCAL_PROCESS_KIND,
    LOCAL_PROCESS_SLOT,
    LOCAL_PROCESS_UID,
    ORIGIN_DIALOG,
    SecretApproval,
    SecretBinding,
    SecretDestination,
    SecretNote,
    is_minted_ref,
    is_standalone_ref,
)

REQUIRE_APPROVAL_KEY = "require_approval"
#: How recently a never-bound value must have been stored to count as supplied
#: for the destination registered with it: an old value nothing ever used was
#: not typed for a destination being registered now.
FRESH_WINDOW = timedelta(minutes=5)
#: Every destination in use right now: where, which refs per slot, and who last
#: changed it (the actor an approval names).
Destinations = Iterable[tuple[SecretDestination, Mapping[str, str], str]]


def _now() -> datetime:
    return datetime.now(tz=UTC)


class SecretBoundary:
    def __init__(
        self,
        store: BoundaryStorePort,
        values: SealedValueStorePort,
        *,
        clock: Callable[[], datetime] = _now,
        default_on: bool = True,
        note_of: Callable[[str], SecretNote | None] | None = None,
    ) -> None:
        #: The uid of the resource a minted secret was minted for (its notes).
        self._note_of = note_of
        self._store = store
        self._values = values
        self._clock = clock
        #: The switch when nobody has set it: the build decides (spec secret
        #: "Default the approval protection by the build"). A signed release
        #: protects its master key, so approvals are on; an unsigned build
        #: cannot, so they are off until a person turns them on.
        self.default_on = default_on

    def _stamp(self) -> str:
        return self._now().isoformat()

    def _now(self) -> datetime:
        now = self._clock()
        return now if now.tzinfo else now.replace(tzinfo=UTC)

    # --- the switch ---------------------------------------------------------

    def protections_on(self) -> bool:
        """An explicitly stored setting wins; otherwise the build's default."""
        stored = self._store.get_setting(REQUIRE_APPROVAL_KEY)
        if stored is None:
            return self.default_on
        return stored != "false"

    def off_by_choice(self) -> bool:
        """Off although this build defaults on: a person turned it off, which is
        what the Overview tells them is still the case."""
        return self.default_on and not self.protections_on()

    def enable_protections(self) -> bool:
        """Turning the protection ON needs nobody: it only narrows. Answers
        whether it was off, so the caller audits only a real change."""
        was_off = not self.protections_on()
        self._store.set_setting(REQUIRE_APPROVAL_KEY, "true")
        for approval in self._store.pending_of_op("disable_protection"):
            self._store.decide(approval.id, "superseded", by="system", at=self._stamp())
        return was_off

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

    def _supplied(self, ref: str, dest_uid: str = "") -> bool:
        """Whether ``ref`` holds a value this machine was given for whichever
        destination first cites it: never bound, not a standalone secret, and
        written here a moment ago (a ciphertext that arrived from elsewhere was
        supplied to nobody on this machine)."""
        if is_minted_ref(ref):
            # A minted id is every secret's. A value written for a resource (a
            # dialog's) was given to it; one a person added on the page was not
            # and needs a person the first time a resource cites it.
            note = self._note_of(ref) if self._note_of else None
            if note is None or note.origin != ORIGIN_DIALOG:
                return False
            if note.created_for is not None and note.created_for != dest_uid:
                return False
        elif is_standalone_ref(ref):
            return False
        if self._store.has_any_binding(ref):
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

    def bind(
        self, dest: SecretDestination, refs: Mapping[str, str], *, actor: str
    ) -> list[SecretApproval]:
        """Evaluate ``dest`` the moment it is registered or changed.

        The one entry the post-register seam uses, for every kind that binds a
        secret (an MCP server, a channel, a provider connection, the sync
        remote): the value a person just supplied for this destination is
        approved with the registration, and a ref that is already in use
        elsewhere, or a target that moved, records its pending approval now —
        where the person is looking — instead of at the first spawn.
        """
        return self.check(dest, refs, actor=actor, supplied=True)

    def check(
        self,
        dest: SecretDestination,
        refs: Mapping[str, str],
        *,
        actor: str = "system",
        supplied: bool = False,
    ) -> list[SecretApproval]:
        """The approvals ``dest`` still waits on for ``refs``; empty means go.

        ``supplied`` is set only by :meth:`bind`: the destination was just
        registered or changed, so a never-bound ref written here counts as
        given to it.

        A refused binding (``status == "rejected"``) is returned too: it is not
        waiting, but it blocks until the target changes or it is asked again.

        ``refs`` maps each slot (an environment variable, a header, a config
        field) to the ref it cites. Records a pending approval for each slot
        that is neither approved nor auto-approvable, once per target — a
        target that changes again supersedes the approval for the old one.
        """
        pending: list[SecretApproval] = []
        fp = dest.target_fingerprint
        on = self.protections_on()
        # Handing a value to a program on this machine is a person's decision only.
        person_only = dest.kind == LOCAL_PROCESS_KIND
        for slot, ref in refs.items():
            bound = self._store.get_binding(ref, dest.kind, dest.uid, slot)
            if bound is not None and bound.target_fingerprint == fp:
                continue
            if not person_only and (
                not on or (supplied and bound is None and self._supplied(ref, dest.uid))
            ):
                self._supersede_bind(ref, dest.kind, dest.uid, slot)
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
        waiting = self.check(dest, refs, actor=actor)
        refused = [a for a in waiting if a.status == "rejected"]
        if refused:
            raise SecretBindingRejected([a.id for a in refused], [a.describe() for a in refused])
        if waiting:
            raise SecretBindingPending([a.id for a in waiting], [a.describe() for a in waiting])

    def _supersede_bind(self, ref: str, kind: str, uid: str, slot: str) -> None:
        for a in self._store.pending_of_op("bind", ref):
            if (a.destination_kind, a.destination_uid, a.slot) == (kind, uid, slot):
                self._store.decide(a.id, "superseded", by="system", at=self._stamp())

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
                if approval.status == "pending":
                    created.append(approval)
            for slot, ref in refs.items():
                wanted.add((ref, dest.kind, dest.uid, slot, dest.target_fingerprint))
        # A local-process request is asked by `coffer run`, not by any configuration:
        # it waits for the person until decided, whatever the configuration holds.
        undecided_kinds = {LOCAL_PROCESS_KIND}
        # Pending and refused bindings alike: a refusal of a target that has since
        # changed no longer says anything about the current one.
        undecided = self._store.pending_of_op("bind") + [
            a for a in self._store.list_approvals(status="rejected") if a.op == "bind"
        ]
        for approval in undecided:
            if approval.destination_kind in undecided_kinds:
                continue
            key = (
                approval.ref or "",
                approval.destination_kind or "",
                approval.destination_uid or "",
                approval.slot or "",
                approval.target_fingerprint or "",
            )
            if key not in wanted:
                self._store.decide(
                    approval.id,
                    "superseded",
                    by="system",
                    at=self._stamp(),
                    only_from=approval.status,
                )
        return created

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
        else:
            self._store.set_setting(REQUIRE_APPROVAL_KEY, "false")
        return self.get(approval_id)

    def reject(self, approval_id: str, *, actor: str) -> SecretApproval:
        """Refuse a pending approval. Anyone may: refusing only narrows."""
        approval = self.get(approval_id)
        if not self._store.decide(approval_id, "rejected", by=actor, at=self._stamp()):
            raise ApprovalNotPending(approval_id, approval.status)
        return self.get(approval_id)

    def ask_again(self, approval_id: str, *, actor: str) -> builtins.list[SecretApproval]:
        """Retire a refused binding and ask it afresh; grants nothing by itself."""
        a = self.get(approval_id)
        if a.op != "bind" or not self._store.decide(
            approval_id, "superseded", by=actor, at=self._stamp(), only_from="rejected"
        ):
            raise ApprovalNotPending(approval_id, a.status)
        return self.check(a.destination(), {a.slot or "": a.ref or ""}, actor=actor)

    def list(
        self, *, status: str | None = None, destination_uid: str | None = None
    ) -> builtins.list[SecretApproval]:
        return self._store.list_approvals(status=status, destination_uid=destination_uid)

    def bindings(self, ref: str | None = None) -> builtins.list[SecretBinding]:
        return self._store.bindings(ref)

    def revoke_local(self, ref: str) -> bool:
        """Withdraw ``ref``'s local-process grant, and any request for it. Needs
        nobody: it only narrows. Answers whether there was a grant to withdraw."""
        had = self._store.delete_binding(
            ref, LOCAL_PROCESS_KIND, LOCAL_PROCESS_UID, LOCAL_PROCESS_SLOT
        )
        self._supersede_bind(ref, LOCAL_PROCESS_KIND, LOCAL_PROCESS_UID, LOCAL_PROCESS_SLOT)
        self.retire_local_refusal(ref)
        return had

    def retire_local_refusal(self, ref: str) -> None:
        """Forget a refused local-process request for ``ref``, so asking for the
        grant again puts a new request in front of the person. Grants nothing."""
        for approval in self._store.list_approvals(status="rejected"):
            if approval.ref == ref and approval.destination_kind == LOCAL_PROCESS_KIND:
                self._store.decide(
                    approval.id, "superseded", by="system", at=self._stamp(), only_from="rejected"
                )

    def forget(self, ref: str) -> None:
        """A deleted secret takes its bindings with it; a new value is a new secret."""
        self._store.delete_bindings(ref)
