"""0080 repairs a ``runs_on`` that cannot be a machine id (spec channels FR-026).

The case that made this necessary was real: a vault carried
``runs_on: 01KX…`` — a ULID written by the retired machine axis (#382) — since
long before the binding existed. 0079 read it as a deliberate binding and
preserved it; the runtime gate read it as another machine's and refused to
start the adapter, so the channel went dark on upgrade without a word.
"""

from __future__ import annotations

from alembic import command

from tests.integration.infrastructure.persistence.test_migration_0079 import (
    _at_0078,
    _configs,
    _seed,
)

#: Shaped like the retired axis's ids: 26 chars of Crockford base32.
_STALE_ULID = "01KX4WYJSDEZQTC61Z4VJJZKEM"
_THIS_MACHINE = "b7a5160dc1ef128f"
_OTHER_MACHINE = "00112233445566aa"


def test_0080_replaces_an_id_that_cannot_be_a_machine(tmp_path, monkeypatch):
    db, cfg = _at_0078(tmp_path, monkeypatch, "stale.db", machine_id=_THIS_MACHINE)
    _seed(db, "channel", "seatalk", {"channel_type": "seatalk", "runs_on": _STALE_ULID})

    command.upgrade(cfg, "0080")

    # The fossil is gone and the channel runs where its row lives, which is
    # what it did the moment before the upgrade.
    assert _configs(db)["seatalk"]["runs_on"] == _THIS_MACHINE


def test_0080_leaves_a_real_binding_to_another_machine_alone(tmp_path, monkeypatch):
    db, cfg = _at_0078(tmp_path, monkeypatch, "other.db", machine_id=_THIS_MACHINE)
    _seed(db, "channel", "tg", {"channel_type": "telegram", "runs_on": _OTHER_MACHINE})

    command.upgrade(cfg, "0080")

    # A well-formed id is somebody's decision — possibly naming a machine this
    # vault has not converged with yet. Guessing here is the overwrite 0079 was
    # right to refuse.
    assert _configs(db)["tg"]["runs_on"] == _OTHER_MACHINE


def test_0080_binds_a_channel_carrying_no_id_at_all(tmp_path, monkeypatch):
    # 0079 already does this; asserted here because 0080 rewrites the same
    # field and must not regress the case 0079 exists for.
    db, cfg = _at_0078(tmp_path, monkeypatch, "bare.db", machine_id=_THIS_MACHINE)
    _seed(db, "channel", "bare", {"channel_type": "telegram"})

    command.upgrade(cfg, "0080")

    assert _configs(db)["bare"]["runs_on"] == _THIS_MACHINE


def test_0080_writes_nothing_when_the_machine_cannot_be_identified(tmp_path, monkeypatch):
    db, cfg = _at_0078(tmp_path, monkeypatch, "nomachine.db")
    _seed(db, "channel", "seatalk", {"channel_type": "seatalk", "runs_on": _STALE_ULID})

    command.upgrade(cfg, "0080")

    # Unbound is a state the surfaces show plainly with a one-click fix; a
    # wrong id is a channel belonging to a machine that does not exist.
    assert _configs(db)["seatalk"]["runs_on"] == _STALE_ULID


def test_0080_touches_no_other_kind(tmp_path, monkeypatch):
    db, cfg = _at_0078(tmp_path, monkeypatch, "kinds.db", machine_id=_THIS_MACHINE)
    _seed(db, "mcp_server", "smart", {"transport": "http", "runs_on": _STALE_ULID})

    command.upgrade(cfg, "0080")

    # `runs_on` means nothing on any other kind, so a value that happens to
    # share the name is not this script's to rewrite.
    assert _configs(db, "mcp_server")["smart"]["runs_on"] == _STALE_ULID
