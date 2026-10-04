"""Revision 0146 removes ``add_secret`` and ``replace_value`` approvals from the boundary's file.

A secret's value is stored at once now, so a pending approval of either kind
(and the sealed value it carries) has nothing to apply. Every other approval
stays. Idempotent, and a home without the file is left alone.
"""

from __future__ import annotations

import json
import pathlib

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)


def _home(tmp_path: pathlib.Path, monkeypatch) -> pathlib.Path:
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'runs.db'}")
    return tmp_path / "local" / "secret-boundary" / "approvals.json"


def test_value_holding_rows_are_dropped_and_other_approvals_kept(tmp_path, monkeypatch) -> None:
    file = _home(tmp_path, monkeypatch)
    file.parent.mkdir(parents=True)
    rows = [
        {"id": "a", "op": "add_secret", "status": "pending", "pending_ciphertext": "x"},
        {"id": "b", "op": "replace_value", "status": "pending", "pending_ciphertext": "y"},
        {"id": "c", "op": "bind", "status": "approved"},
        {"id": "d", "op": "add_secret", "status": "rejected"},
        {"id": "e", "op": "disable_protection", "status": "pending"},
    ]
    file.write_text(json.dumps({"approvals": rows}))
    cfg = _alembic_config()
    command.upgrade(cfg, "0145")

    command.upgrade(cfg, "0146")
    command.downgrade(cfg, "0145")
    command.upgrade(cfg, "0146")

    kept = json.loads(file.read_text())["approvals"]
    assert [r["id"] for r in kept] == ["c", "e"]


def test_a_home_without_the_file_is_left_alone(tmp_path, monkeypatch) -> None:
    file = _home(tmp_path, monkeypatch)
    command.upgrade(_alembic_config(), "0146")
    assert not file.exists()
