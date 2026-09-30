"""An in-memory stand-in for the secret boundary's tables, for tests.

Same contract as ``infrastructure.secret.boundary_store.SqliteBoundaryStore``
(the application's ``BoundaryStorePort``), held in dicts, so the gate's rules
can be exercised without a database and route tests can install a real
``SecretBoundary`` over a fake secret store.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

from coffer.application.secret.boundary import SecretBoundary
from coffer.domain.secrets import SecretApproval, SecretBinding


class InMemoryBoundaryStore:
    def __init__(self) -> None:
        self.bindings_by_key: dict[tuple[str, str, str, str], SecretBinding] = {}
        self.approvals: dict[str, SecretApproval] = {}
        self.sealed: dict[str, bytes] = {}
        self.settings: dict[str, str] = {}

    def get_binding(self, ref: str, kind: str, uid: str, slot: str) -> SecretBinding | None:
        return self.bindings_by_key.get((ref, kind, uid, slot))

    def bindings(self, ref: str | None = None) -> list[SecretBinding]:
        return [b for b in self.bindings_by_key.values() if ref is None or b.ref == ref]

    def has_any_binding(self, ref: str) -> bool:
        return any(b.ref == ref for b in self.bindings_by_key.values())

    def put_binding(self, binding: SecretBinding) -> None:
        key = (binding.ref, binding.destination_kind, binding.destination_uid, binding.slot)
        self.bindings_by_key[key] = binding

    def delete_bindings(self, ref: str) -> None:
        for key in [k for k in self.bindings_by_key if k[0] == ref]:
            del self.bindings_by_key[key]

    def create_approval(self, approval: SecretApproval, ciphertext: bytes | None = None) -> None:
        self.approvals[approval.id] = approval
        if ciphertext is not None:
            self.sealed[approval.id] = ciphertext

    def get_approval(self, approval_id: str) -> SecretApproval | None:
        return self.approvals.get(approval_id)

    def pending_ciphertext(self, approval_id: str) -> bytes | None:
        return self.sealed.get(approval_id)

    def find_open_bind(
        self, ref: str, kind: str, uid: str, slot: str, target_fingerprint: str
    ) -> SecretApproval | None:
        for a in sorted(self.approvals.values(), key=lambda a: a.created_at, reverse=True):
            if (
                a.status in ("pending", "rejected")
                and a.op == "bind"
                and (
                    a.ref,
                    a.destination_kind,
                    a.destination_uid,
                    a.slot,
                    a.target_fingerprint,
                )
                == (ref, kind, uid, slot, target_fingerprint)
            ):
                return a
        return None

    def pending_of_op(self, op: str, ref: str | None = None) -> list[SecretApproval]:
        return [
            a
            for a in self.approvals.values()
            if a.status == "pending" and a.op == op and (ref is None or a.ref == ref)
        ]

    def list_approvals(
        self, *, status: str | None = None, destination_uid: str | None = None, limit: int = 200
    ) -> list[SecretApproval]:
        rows = [
            a
            for a in self.approvals.values()
            if (status is None or a.status == status)
            and (destination_uid is None or a.destination_uid == destination_uid)
        ]
        return sorted(rows, key=lambda a: (a.created_at, a.id), reverse=True)[:limit]

    def decide(self, approval_id: str, status: str, *, by: str, at: str) -> bool:
        a = self.approvals.get(approval_id)
        if a is None or a.status != "pending":
            return False
        self.approvals[approval_id] = dataclasses.replace(
            a,
            status=status,  # type: ignore[arg-type]
            decided_at=at,
            decided_by=by,
        )
        self.sealed.pop(approval_id, None)
        return True

    def get_setting(self, key: str) -> str | None:
        return self.settings.get(key)

    def set_setting(self, key: str, value: str) -> None:
        self.settings[key] = value


def install_boundary(values: Any) -> SecretBoundary:
    """Publish a real gate over ``values`` (a fake secret store) for route tests."""
    from coffer.surfaces.http.secret_boundary_wiring import set_secret_boundary

    boundary = SecretBoundary(InMemoryBoundaryStore(), values)
    set_secret_boundary(boundary, None)
    return boundary


class FakeSealedValues:
    """A secret store stand-in with the slice the boundary reads."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.created: dict[str, datetime] = {}

    def put(self, ref: str, value: str, *, created: datetime | None = None) -> None:
        self.values[ref] = value
        self.created[ref] = created or datetime.now(tz=UTC)

    def exists(self, ref: str) -> bool:
        return ref in self.values

    def created_at(self, ref: str) -> datetime | None:
        return self.created.get(ref)

    def get(self, ref: str) -> str | None:
        return self.values.get(ref)

    def set(self, ref: str, value: str) -> None:
        self.created.setdefault(ref, datetime.now(tz=UTC))
        self.values[ref] = value

    def seal(self, value: str) -> bytes:
        return b"sealed:" + value.encode()[::-1]

    def unseal(self, token: bytes) -> str:
        return token.removeprefix(b"sealed:")[::-1].decode()
