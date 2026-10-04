"""The secret boundary's machine-local state: bindings, approvals, switches.

Which destinations a ref has been approved for, the approvals waiting on a
person, and the boundary's own switches are true of this machine only — the
approval happened here, in front of this machine's app (ADR
only-a-present-human-sees-a-secret-or-sends-it-somewhere-new) — so they are
``local/`` state (ADR storage-is-five-classes-by-nature), never in the vault
and never synced. Three JSON files under ``local/secret-boundary/``, each read whole
and changed under its file's lock (``JsonStore``):

- ``bindings.json`` — ``{"bindings": [binding, ...]}``, unique on
  ``(ref, destination_kind, destination_uid, slot)``;
- ``approvals.json`` — ``{"approvals": [approval, ...]}``;
- ``settings.json`` — ``{key: value}``.

The gate is consulted from the synchronous ``SecretResolver.materialize``
path in worker threads; async callers go through ``asyncio.to_thread``. No
plaintext is ever written here.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any

from coffer.domain.secrets import SecretApproval, SecretBinding
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.json_store import JsonStore

_BINDINGS = "bindings"
_APPROVALS = "approvals"
_BINDING_FIELDS = tuple(f.name for f in dataclasses.fields(SecretBinding))
_APPROVAL_FIELDS = tuple(f.name for f in dataclasses.fields(SecretApproval))


def _binding(row: dict[str, Any]) -> SecretBinding:
    fields: dict[str, Any] = {k: row.get(k) for k in _BINDING_FIELDS}
    return SecretBinding(**fields)


def _approval(row: dict[str, Any]) -> SecretApproval:
    fields: dict[str, Any] = {k: row.get(k) for k in _APPROVAL_FIELDS}
    return SecretApproval(**fields)


def _binding_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (row["ref"], row["destination_kind"], row["destination_uid"], row["slot"])


def _newest_first(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (r.get("created_at") or "", r.get("id") or ""), reverse=True)


class FileBoundaryStore:
    """Bindings, approvals and switches as JSON files under ``local/secret-boundary/``.

    ``home`` is the user's home; left out, every call resolves it from
    ``HOME``.
    """

    def __init__(self, home: Path | None = None) -> None:
        def at(name: str) -> Callable[[], Path]:
            return lambda: local_root(home) / "secret-boundary" / name

        self._bindings = JsonStore(at("bindings.json"))
        self._approvals = JsonStore(at("approvals.json"))
        self._settings = JsonStore(at("settings.json"))

    def _binding_rows(self) -> list[dict[str, Any]]:
        return list(self._bindings.read().get(_BINDINGS, []))

    def _approval_rows(self) -> list[dict[str, Any]]:
        return list(self._approvals.read().get(_APPROVALS, []))

    # --- bindings -----------------------------------------------------------

    def get_binding(self, ref: str, kind: str, uid: str, slot: str) -> SecretBinding | None:
        wanted = (ref, kind, uid, slot)
        for row in self._binding_rows():
            if _binding_key(row) == wanted:
                return _binding(row)
        return None

    def bindings(self, ref: str | None = None) -> list[SecretBinding]:
        rows = [r for r in self._binding_rows() if ref is None or r["ref"] == ref]
        return [_binding(r) for r in sorted(rows, key=lambda r: (r["ref"], r["slot"]))]

    def has_any_binding(self, ref: str) -> bool:
        return any(r["ref"] == ref for r in self._binding_rows())

    def put_binding(self, binding: SecretBinding) -> None:
        row = dataclasses.asdict(binding)

        def upsert(doc: dict[str, Any]) -> None:
            rows = [r for r in doc.get(_BINDINGS, []) if _binding_key(r) != _binding_key(row)]
            doc[_BINDINGS] = [*rows, row]

        self._bindings.update(upsert)

    def delete_bindings(self, ref: str) -> None:
        """Forget every binding of a ref — only when the ref itself is deleted."""

        def drop(doc: dict[str, Any]) -> None:
            doc[_BINDINGS] = [r for r in doc.get(_BINDINGS, []) if r["ref"] != ref]

        self._bindings.update(drop)

    # --- approvals ----------------------------------------------------------

    def create_approval(self, approval: SecretApproval) -> None:
        row = dataclasses.asdict(approval)

        def insert(doc: dict[str, Any]) -> None:
            rows = doc.get(_APPROVALS, [])
            if any(r["id"] == approval.id for r in rows):
                raise ValueError(f"approval {approval.id!r} already exists")
            doc[_APPROVALS] = [*rows, row]

        self._approvals.update(insert)

    def get_approval(self, approval_id: str) -> SecretApproval | None:
        for row in self._approval_rows():
            if row["id"] == approval_id:
                return _approval(row)
        return None

    def find_open_bind(
        self, ref: str, kind: str, uid: str, slot: str, target_fingerprint: str
    ) -> SecretApproval | None:
        """The pending — or refused — approval for exactly this binding and target."""
        for row in _newest_first(self._approval_rows()):
            if (
                row["status"] in ("pending", "rejected")
                and row["op"] == "bind"
                and row.get("ref") == ref
                and row.get("destination_kind") == kind
                and row.get("destination_uid") == uid
                and row.get("slot") == slot
                and row.get("target_fingerprint") == target_fingerprint
            ):
                return _approval(row)
        return None

    def pending_of_op(self, op: str, ref: str | None = None) -> list[SecretApproval]:
        return [
            _approval(r)
            for r in self._approval_rows()
            if r["status"] == "pending" and r["op"] == op and (ref is None or r.get("ref") == ref)
        ]

    def list_approvals(
        self, *, status: str | None = None, destination_uid: str | None = None, limit: int = 200
    ) -> list[SecretApproval]:
        rows = [
            r
            for r in _newest_first(self._approval_rows())
            if (status is None or r["status"] == status)
            and (destination_uid is None or r.get("destination_uid") == destination_uid)
        ]
        return [_approval(r) for r in rows[:limit]]

    def decide(
        self, approval_id: str, status: str, *, by: str, at: str, only_from: str = "pending"
    ) -> bool:
        """Move an approval that is ``only_from`` (pending by default) to
        ``status``; False when it was not in that state.

        Compare-and-set on the status under the file's lock, so two answers to
        one approval cannot both take effect.
        """
        moved = False

        def settle(doc: dict[str, Any]) -> None:
            nonlocal moved
            for row in doc.get(_APPROVALS, []):
                if row["id"] == approval_id and row["status"] == only_from:
                    row.update(status=status, decided_at=at, decided_by=by)
                    moved = True
                    return

        self._approvals.update(settle)
        return moved

    # --- switches -----------------------------------------------------------

    def get_setting(self, key: str) -> str | None:
        value = self._settings.read().get(key)
        return str(value) if value is not None else None

    def set_setting(self, key: str, value: str) -> None:
        def put(doc: dict[str, Any]) -> None:
            doc[key] = value

        self._settings.update(put)


__all__ = ["FileBoundaryStore"]
