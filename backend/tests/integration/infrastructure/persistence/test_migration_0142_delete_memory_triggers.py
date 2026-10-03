"""Revision 0142 deletes ``vault/memory-triggers/`` and nothing else.

Memory triggers are gone, so the authored guards a person kept in the vault
decide nothing. The migration removes the directory beside the database; every
other vault file stays where it is, and a home without the directory is left
alone. Idempotent: a second run finds nothing.
"""

from __future__ import annotations

import pathlib

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)


def _home(tmp_path: pathlib.Path, monkeypatch, *, with_triggers: bool) -> pathlib.Path:
    db = tmp_path / "runs.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db}")
    vault = tmp_path / "vault"
    (vault / "knowledge" / "notes").mkdir(parents=True)
    (vault / "knowledge" / "notes" / "k.md").write_text("kept\n")
    if with_triggers:
        (vault / "memory-triggers").mkdir()
        (vault / "memory-triggers" / "rm-rf.md").write_text("---\nid: rm-rf\n---\nNo.\n")
    return vault


def test_the_triggers_directory_is_deleted_and_the_rest_of_the_vault_is_not(
    tmp_path, monkeypatch
) -> None:
    vault = _home(tmp_path, monkeypatch, with_triggers=True)
    cfg = _alembic_config()
    command.upgrade(cfg, "0141")
    assert (vault / "memory-triggers" / "rm-rf.md").is_file()

    command.upgrade(cfg, "0142")

    assert not (vault / "memory-triggers").exists()
    assert (vault / "knowledge" / "notes" / "k.md").read_text() == "kept\n"


def test_a_home_without_the_directory_is_left_alone_and_a_second_run_finds_nothing(
    tmp_path, monkeypatch
) -> None:
    vault = _home(tmp_path, monkeypatch, with_triggers=False)
    cfg = _alembic_config()

    command.upgrade(cfg, "0142")
    command.downgrade(cfg, "0141")
    command.upgrade(cfg, "0142")

    assert sorted(p.name for p in vault.iterdir()) == ["knowledge"]
    assert (vault / "knowledge" / "notes" / "k.md").is_file()
