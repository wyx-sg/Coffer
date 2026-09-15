"""Revision 0079: every existing channel keeps running where it already ran.

The trap here is the opposite of 0076's. Nothing widens — the new field can
only ever narrow where a channel runs — so the risk is that it narrows to
NOWHERE: the runtime that arrives with this revision starts an adapter only for
a channel bound to this machine, and every channel in an upgrading vault was
written before the field existed. Leave them alone and the upgrade takes the
user's bots offline, silently, with no message that says why.

The binding this writes is not a guess. Until this revision a channel never
left the machine it was registered on, so the machine holding the row IS the
machine that was running it.

What is asserted: an unbound channel gets this machine's id; a channel that
already names a machine is left exactly as found (so a re-run is a no-op, and a
hand-made binding is never dragged back); other kinds are not touched; a vault
that cannot say which machine it is writes nothing at all; and the downgrade
takes the key back off.

Assertions read the raw stored JSON rather than going through the Pydantic
model: the question is what is in the database.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)

_THIS_MACHINE = "M-THIS"
_ANOTHER_MACHINE = "M-OTHER"


def _at_0078(tmp_path, monkeypatch, db_name: str, *, machine_id: str | None = None):
    """A throwaway vault at the revision just below 0079.

    ``machine_id`` writes the daemon's own cache beside the database — the same
    file the running daemon reads for its identity. Omitting it is the vault of
    a machine that has never cached one.
    """
    db_path = tmp_path / db_name
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    if machine_id is not None:
        (tmp_path / "daemon-config.json").write_text(
            json.dumps({"version": 1, "port": 8000, "machine_id": machine_id})
        )
    cfg = _alembic_config()
    command.upgrade(cfg, "0078")
    return db_path, cfg


def _seed(db_path: pathlib.Path, kind: str, name: str, config: dict[str, object]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO resources "
            "(kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, '2026-09-01', '2026-09-01')",
            (kind, name, json.dumps(config)),
        )
        conn.commit()


def _configs(db_path: pathlib.Path, kind: str = "channel") -> dict[str, dict]:
    with sqlite3.connect(db_path) as conn:
        return {
            name: json.loads(raw)
            for name, raw in conn.execute(
                "SELECT name, config_json FROM resources WHERE kind = ?", (kind,)
            ).fetchall()
        }


def test_0079_binds_an_existing_channel_to_this_machine(tmp_path, monkeypatch):
    """The whole point: nothing goes dark on upgrade."""
    db_path, cfg = _at_0078(tmp_path, monkeypatch, "bind.db", machine_id=_THIS_MACHINE)
    _seed(db_path, "channel", "tg", {"channel_type": "telegram", "bot_token_ref": "r"})

    command.upgrade(cfg, "0079")

    assert _configs(db_path)["tg"] == {
        "channel_type": "telegram",
        "bot_token_ref": "r",
        "runs_on": _THIS_MACHINE,
    }


def test_0079_leaves_a_channel_that_already_names_a_machine(tmp_path, monkeypatch):
    """Idempotent, and more than idempotent: a channel already bound — by hand,
    or by a previous run — must never be dragged back to this machine, because
    doing so would take a bot off the machine the user put it on."""
    db_path, cfg = _at_0078(tmp_path, monkeypatch, "already.db", machine_id=_THIS_MACHINE)
    _seed(db_path, "channel", "theirs", {"channel_type": "telegram", "runs_on": _ANOTHER_MACHINE})

    command.upgrade(cfg, "0079")
    assert _configs(db_path)["theirs"]["runs_on"] == _ANOTHER_MACHINE


def test_0079_touches_no_other_kind(tmp_path, monkeypatch):
    """A binding on an ``mcp_server`` would be a field that decides nothing —
    and one that then travelled into the shared tree for nobody to read."""
    db_path, cfg = _at_0078(tmp_path, monkeypatch, "other_kinds.db", machine_id=_THIS_MACHINE)
    _seed(db_path, "mcp_server", "files", {"transport": "stdio"})

    command.upgrade(cfg, "0079")
    assert _configs(db_path, "mcp_server")["files"] == {"transport": "stdio"}


def test_0079_writes_nothing_when_the_machine_cannot_be_identified(tmp_path, monkeypatch):
    """A vault that cannot say which machine it is has no business claiming a
    channel. The channel comes out unbound — a state the surfaces report with a
    one-click fix — rather than bound to an invented id, which would be a bot
    silently belonging to a machine that does not exist. And the migration does
    not fail: a missing cache is never a reason to refuse an upgrade.
    """
    db_path, cfg = _at_0078(tmp_path, monkeypatch, "no_cache.db")
    assert not (tmp_path / "daemon-config.json").exists()
    _seed(db_path, "channel", "tg", {"channel_type": "telegram"})

    command.upgrade(cfg, "0079")
    assert "runs_on" not in _configs(db_path)["tg"]


def test_0079_downgrade_strips_the_binding(tmp_path, monkeypatch):
    """The build below this revision has no binding gate, so removing the key
    widens nothing — it only stops a field nothing reads from riding into the
    shared tree."""
    db_path, cfg = _at_0078(tmp_path, monkeypatch, "down.db", machine_id=_THIS_MACHINE)
    _seed(db_path, "channel", "tg", {"channel_type": "telegram", "bot_token_ref": "r"})
    command.upgrade(cfg, "0079")

    command.downgrade(cfg, "0078")

    assert _configs(db_path)["tg"] == {"channel_type": "telegram", "bot_token_ref": "r"}
