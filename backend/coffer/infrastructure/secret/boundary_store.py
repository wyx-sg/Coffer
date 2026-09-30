"""The secret boundary's tables: approved bindings, pending approvals, switches.

Same shape as :mod:`encrypted_store`: stdlib ``sqlite3`` with a short-lived
connection per call, because the gate is consulted from the synchronous
``SecretResolver.materialize`` path that runs in worker threads. Async
callers go through ``asyncio.to_thread``; nothing here is called on the loop.

No plaintext is ever written here. A pending value replacement arrives already
encrypted by the secret store's Fernet key.
"""

from __future__ import annotations

import pathlib
import sqlite3
from contextlib import closing
from typing import Any

from coffer.domain.secrets import SecretApproval, SecretBinding

_APPROVAL_COLUMNS = (
    "id, op, status, created_at, requested_by, ref, destination_kind, destination_uid, "
    "destination_label, slot, target, target_fingerprint, decided_at, decided_by"
)


def _approval(row: tuple[Any, ...]) -> SecretApproval:
    return SecretApproval(
        id=row[0],
        op=row[1],
        status=row[2],
        created_at=row[3],
        requested_by=row[4],
        ref=row[5],
        destination_kind=row[6],
        destination_uid=row[7],
        destination_label=row[8],
        slot=row[9],
        target=row[10],
        target_fingerprint=row[11],
        decided_at=row[12],
        decided_by=row[13],
    )


def _binding(row: tuple[Any, ...]) -> SecretBinding:
    return SecretBinding(
        ref=row[0],
        destination_kind=row[1],
        destination_uid=row[2],
        slot=row[3],
        target_fingerprint=row[4],
        approved_at=row[5],
        approval_id=row[6],
    )


_BINDING_COLUMNS = (
    "ref, destination_kind, destination_uid, slot, target_fingerprint, approved_at, approval_id"
)


class SqliteBoundaryStore:
    """Bindings, approvals and switches in the coffer DB."""

    def __init__(self, db_path: pathlib.Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    # --- bindings -----------------------------------------------------------

    def get_binding(self, ref: str, kind: str, uid: str, slot: str) -> SecretBinding | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_BINDING_COLUMNS} FROM secret_bindings WHERE ref = ? "
                "AND destination_kind = ? AND destination_uid = ? AND slot = ?",
                (ref, kind, uid, slot),
            ).fetchone()
        return _binding(row) if row else None

    def bindings(self, ref: str | None = None) -> list[SecretBinding]:
        sql = f"SELECT {_BINDING_COLUMNS} FROM secret_bindings"
        args: tuple[Any, ...] = ()
        if ref is not None:
            sql += " WHERE ref = ?"
            args = (ref,)
        with closing(self._connect()) as conn:
            return [_binding(r) for r in conn.execute(sql + " ORDER BY ref, slot", args)]

    def has_any_binding(self, ref: str) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT 1 FROM secret_bindings WHERE ref = ?", (ref,)).fetchone()
        return row is not None

    def put_binding(self, binding: SecretBinding) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO secret_bindings "
                f"({_BINDING_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(ref, destination_kind, destination_uid, slot) DO UPDATE SET "
                "target_fingerprint = excluded.target_fingerprint, "
                "approved_at = excluded.approved_at, approval_id = excluded.approval_id",
                (
                    binding.ref,
                    binding.destination_kind,
                    binding.destination_uid,
                    binding.slot,
                    binding.target_fingerprint,
                    binding.approved_at,
                    binding.approval_id,
                ),
            )

    def delete_bindings(self, ref: str) -> None:
        """Forget every binding of a ref — only when the ref itself is deleted."""
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM secret_bindings WHERE ref = ?", (ref,))

    # --- approvals ----------------------------------------------------------

    def create_approval(self, approval: SecretApproval, ciphertext: bytes | None = None) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"INSERT INTO secret_approvals ({_APPROVAL_COLUMNS}, pending_ciphertext) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    approval.id,
                    approval.op,
                    approval.status,
                    approval.created_at,
                    approval.requested_by,
                    approval.ref,
                    approval.destination_kind,
                    approval.destination_uid,
                    approval.destination_label,
                    approval.slot,
                    approval.target,
                    approval.target_fingerprint,
                    approval.decided_at,
                    approval.decided_by,
                    ciphertext,
                ),
            )

    def get_approval(self, approval_id: str) -> SecretApproval | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_APPROVAL_COLUMNS} FROM secret_approvals WHERE id = ?",
                (approval_id,),
            ).fetchone()
        return _approval(row) if row else None

    def pending_ciphertext(self, approval_id: str) -> bytes | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT pending_ciphertext FROM secret_approvals WHERE id = ?", (approval_id,)
            ).fetchone()
        return bytes(row[0]) if row and row[0] is not None else None

    def find_open_bind(
        self, ref: str, kind: str, uid: str, slot: str, target_fingerprint: str
    ) -> SecretApproval | None:
        """The pending — or refused — approval for exactly this binding and target."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"SELECT {_APPROVAL_COLUMNS} FROM secret_approvals "
                "WHERE status IN ('pending', 'rejected') AND op = 'bind' AND ref = ? "
                "AND destination_kind = ? AND destination_uid = ? AND slot = ? "
                "AND target_fingerprint = ? ORDER BY created_at DESC LIMIT 1",
                (ref, kind, uid, slot, target_fingerprint),
            ).fetchone()
        return _approval(row) if row else None

    def pending_of_op(self, op: str, ref: str | None = None) -> list[SecretApproval]:
        sql = (
            f"SELECT {_APPROVAL_COLUMNS} FROM secret_approvals WHERE status = 'pending' AND op = ?"
        )
        args: tuple[Any, ...] = (op,)
        if ref is not None:
            sql += " AND ref = ?"
            args = (op, ref)
        with closing(self._connect()) as conn:
            return [_approval(r) for r in conn.execute(sql, args)]

    def list_approvals(
        self, *, status: str | None = None, destination_uid: str | None = None, limit: int = 200
    ) -> list[SecretApproval]:
        clauses: list[str] = []
        args: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            args.append(status)
        if destination_uid is not None:
            clauses.append("destination_uid = ?")
            args.append(destination_uid)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT {_APPROVAL_COLUMNS} FROM secret_approvals{where} "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (*args, limit),
            ).fetchall()
        return [_approval(r) for r in rows]

    def decide(self, approval_id: str, status: str, *, by: str, at: str) -> bool:
        """Move a PENDING approval to ``status``; False when it was not pending.

        Compare-and-set on the status, so two answers to one approval cannot
        both take effect. A decided approval drops any value it held.
        """
        with closing(self._connect()) as conn, conn:
            cur = conn.execute(
                "UPDATE secret_approvals SET status = ?, decided_at = ?, decided_by = ?, "
                "pending_ciphertext = NULL WHERE id = ? AND status = 'pending'",
                (status, at, by, approval_id),
            )
            return cur.rowcount > 0

    # --- switches -----------------------------------------------------------

    def get_setting(self, key: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT value FROM secret_boundary_settings WHERE key = ?", (key,)
            ).fetchone()
        return str(row[0]) if row else None

    def set_setting(self, key: str, value: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO secret_boundary_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
