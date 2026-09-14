"""Revision 0076: scope's machine axis is resolved away, never merely dropped.

The trap this migration exists for is that deleting the ``machines`` key
WIDENS. ``{"agents": null, "machines": ["x"]}`` reached exactly one machine;
drop the key and it reaches every agent on every machine — a resource silently
exposed where the user had kept it out. Narrowing is visible and one click
undoes it; widening is neither.

So what is asserted here is the never-widen property, row shape by row shape:
a restricted scope stays restricted, a dormant one stays dormant, a row whose
machine list does NOT name this machine comes out dormant rather than open,
and a row whose list DOES name this machine keeps its agent axis verbatim —
still restricted, not widened. Plus the two properties that make it safe to run
twice: ``NULL`` is untouched, and a second pass changes nothing.

Assertions read the raw stored JSON rather than going through ``Scope``: the
question is what is in the database, not what the current domain model would
make of it.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts, like the 0048/0049/0071 tests do.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)

#: The id this machine's cache claims, when a test writes one.
_THIS_MACHINE = "M-THIS"
#: An id that is never this machine's, so a list naming it is a list this
#: machine was not on.
_OTHER_MACHINE = "M-OTHER"


def _at_0075(tmp_path, monkeypatch, db_name: str, *, machine_id: str | None = None):
    """Bring a throwaway vault to the revision just below 0076.

    ``machine_id`` writes the daemon's cache beside the database — the same
    file, in the same place, that the running daemon reads to evaluate scope.
    Omitting it is the vault of a machine that never cached an id.
    """
    db_path = tmp_path / db_name
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    if machine_id is not None:
        (tmp_path / "daemon-config.json").write_text(
            json.dumps({"version": 1, "port": 8000, "machine_id": machine_id})
        )
    cfg = _alembic_config()
    command.upgrade(cfg, "0075")
    return db_path, cfg


def _seed(db_path: pathlib.Path, name: str, scope: object) -> None:
    """Insert one scoped resource. ``scope`` of ``None`` stores SQL NULL."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO resources "
            "(kind, name, config_json, scope_json, enabled, created_at, updated_at) "
            "VALUES ('mcp_server', ?, '{}', ?, 1, '2026-09-01', '2026-09-01')",
            (name, None if scope is None else json.dumps(scope)),
        )
        conn.commit()


def _scopes(db_path: pathlib.Path) -> dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        return {
            name: (json.loads(raw) if raw is not None else None)
            for name, raw in conn.execute(
                "SELECT name, scope_json FROM resources WHERE kind = 'mcp_server'"
            ).fetchall()
        }


def test_0076_keeps_an_unrestricted_machine_axis_exactly(tmp_path, monkeypatch):
    """``machines: null`` excluded no machine, so the agent axis survives
    verbatim — restricted stays restricted, dormant stays dormant, and open
    stays open. No row's activation changes on any machine."""
    db_path, cfg = _at_0075(tmp_path, monkeypatch, "unrestricted.db", machine_id=_THIS_MACHINE)
    _seed(db_path, "listed", {"agents": ["claude-code"], "machines": None})
    _seed(db_path, "dormant", {"agents": [], "machines": None})
    _seed(db_path, "open", {"agents": None, "machines": None})

    command.upgrade(cfg, "0076")

    scopes = _scopes(db_path)
    assert scopes["listed"] == {"agents": ["claude-code"]}
    assert scopes["dormant"] == {"agents": []}
    assert scopes["open"] == {"agents": None}


def test_0076_does_not_widen_a_row_that_named_another_machine(tmp_path, monkeypatch):
    """THE trap. ``{"agents": null, "machines": ["M-OTHER"]}`` was active on one
    machine that is not this one — i.e. dormant here. The careless strip makes
    it ``{"agents": null}``: active for EVERY agent, everywhere. It must come
    out ``{"agents": []}`` instead."""
    db_path, cfg = _at_0075(tmp_path, monkeypatch, "widen.db", machine_id=_THIS_MACHINE)
    _seed(db_path, "elsewhere-open", {"agents": None, "machines": [_OTHER_MACHINE]})
    _seed(db_path, "elsewhere-listed", {"agents": ["claude-code"], "machines": [_OTHER_MACHINE]})

    command.upgrade(cfg, "0076")

    scopes = _scopes(db_path)
    assert scopes["elsewhere-open"] == {"agents": []}
    assert scopes["elsewhere-open"] != {"agents": None}  # the widened value, spelled out
    # An agent restriction is no defence either: the row was dormant here, and
    # keeping ["claude-code"] would wake it up for that agent on this machine.
    assert scopes["elsewhere-listed"] == {"agents": []}


def test_0076_empty_machine_list_stays_dormant(tmp_path, monkeypatch):
    """An empty machine list matched no machine at all. It is the most dormant
    a row can be, and the resolution must not read it as "no restriction"."""
    db_path, cfg = _at_0075(tmp_path, monkeypatch, "empty_list.db", machine_id=_THIS_MACHINE)
    _seed(db_path, "nowhere", {"agents": None, "machines": []})
    _seed(db_path, "nowhere-listed", {"agents": ["codex"], "machines": []})

    command.upgrade(cfg, "0076")

    scopes = _scopes(db_path)
    assert scopes["nowhere"] == {"agents": []}
    assert scopes["nowhere-listed"] == {"agents": []}


def test_0076_keeps_a_row_that_named_this_machine(tmp_path, monkeypatch):
    """With the daemon's cache naming this machine, a list containing that id
    was active here subject only to its agent axis — so that axis alone says
    exactly the same thing. Preserved, and still restricted: the agent list is
    NOT replaced by ``null``."""
    db_path, cfg = _at_0075(tmp_path, monkeypatch, "here.db", machine_id=_THIS_MACHINE)
    _seed(db_path, "here-listed", {"agents": ["claude-code"], "machines": [_THIS_MACHINE]})
    _seed(db_path, "here-open", {"agents": None, "machines": [_OTHER_MACHINE, _THIS_MACHINE]})
    _seed(db_path, "here-dormant", {"agents": [], "machines": [_THIS_MACHINE]})

    command.upgrade(cfg, "0076")

    scopes = _scopes(db_path)
    assert scopes["here-listed"] == {"agents": ["claude-code"]}
    assert scopes["here-listed"] != {"agents": None}  # still restricted, not widened
    assert scopes["here-open"] == {"agents": None}
    assert scopes["here-dormant"] == {"agents": []}


def test_0076_without_a_cached_id_every_machine_list_is_dormant(tmp_path, monkeypatch):
    """No ``daemon-config.json`` at all: the script cannot say which machine it
    is, so it cannot claim membership of any allow-list. It takes the dormant
    branch rather than failing, and rather than guessing itself onto the list.

    The unrestricted axis is unaffected — that one needs no id to resolve.
    """
    db_path, cfg = _at_0075(tmp_path, monkeypatch, "no_cache.db")
    assert not (tmp_path / "daemon-config.json").exists()
    _seed(db_path, "listed-here", {"agents": ["claude-code"], "machines": [_THIS_MACHINE]})
    _seed(db_path, "unrestricted", {"agents": ["claude-code"], "machines": None})

    command.upgrade(cfg, "0076")

    scopes = _scopes(db_path)
    assert scopes["listed-here"] == {"agents": []}  # narrowed, never widened
    assert scopes["unrestricted"] == {"agents": ["claude-code"]}


def test_0076_unreadable_cache_is_treated_as_unknown(tmp_path, monkeypatch):
    """A mangled cache must not stop the migration — and must not be read
    optimistically either. Same dormant branch as an absent one."""
    db_path, cfg = _at_0075(tmp_path, monkeypatch, "bad_cache.db")
    (tmp_path / "daemon-config.json").write_text("{not json at all")
    _seed(db_path, "listed-here", {"agents": ["claude-code"], "machines": [_THIS_MACHINE]})

    command.upgrade(cfg, "0076")

    assert _scopes(db_path)["listed-here"] == {"agents": []}


def test_0076_leaves_null_and_non_objects_alone(tmp_path, monkeypatch):
    """``NULL`` (unscoped) has no axis to resolve, and a value that is not an
    object — a stale pre-0072 list, or garbage — is a row the app cannot read
    either. Neither is this script's to touch."""
    db_path, cfg = _at_0075(tmp_path, monkeypatch, "untouched.db", machine_id=_THIS_MACHINE)
    _seed(db_path, "unscoped", None)
    _seed(db_path, "stale-list", ["claude-code"])

    command.upgrade(cfg, "0076")

    scopes = _scopes(db_path)
    assert scopes["unscoped"] is None
    assert scopes["stale-list"] == ["claude-code"]


def test_0076_run_twice_changes_nothing(tmp_path, monkeypatch):
    """Idempotency, and the reason it holds: once ``machines`` is gone the row
    no longer matches, so a second pass has nothing to resolve — and in
    particular cannot re-resolve an already-narrowed row against the id a
    second time, nor widen one whose agent axis is now ``null``.

    The version table is wound back WITHOUT running ``downgrade`` (which would
    restore the key and hide the bug); that is what a hand-run, a stamp, or a
    replayed migration chain does to the data.
    """
    db_path, cfg = _at_0075(tmp_path, monkeypatch, "twice.db", machine_id=_THIS_MACHINE)
    _seed(db_path, "here-listed", {"agents": ["claude-code"], "machines": [_THIS_MACHINE]})
    _seed(db_path, "elsewhere-open", {"agents": None, "machines": [_OTHER_MACHINE]})
    _seed(db_path, "unrestricted", {"agents": None, "machines": None})
    _seed(db_path, "unscoped", None)

    command.upgrade(cfg, "0076")
    after_once = _scopes(db_path)
    assert after_once["here-listed"] == {"agents": ["claude-code"]}
    assert after_once["elsewhere-open"] == {"agents": []}
    assert after_once["unrestricted"] == {"agents": None}

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE alembic_version SET version_num = '0075'")
        conn.commit()
    command.upgrade(cfg, "0076")

    assert _scopes(db_path) == after_once


def test_0076_downgrade_restores_an_unrestricted_machine_axis(tmp_path, monkeypatch):
    """The only honest inverse: the resolved lists are gone, and ``null`` is the
    widening direction on that axis — the direction that cannot make a resource
    vanish from a machine that could still see it. ``NULL`` stays ``NULL``, a
    non-object is left alone, and a re-run of the upgrade afterwards lands on
    the same rows again."""
    db_path, cfg = _at_0075(tmp_path, monkeypatch, "down.db", machine_id=_THIS_MACHINE)
    _seed(db_path, "here-listed", {"agents": ["claude-code"], "machines": [_THIS_MACHINE]})
    _seed(db_path, "elsewhere-open", {"agents": None, "machines": [_OTHER_MACHINE]})
    _seed(db_path, "unscoped", None)
    _seed(db_path, "stale-list", ["claude-code"])

    command.upgrade(cfg, "0076")
    after_up = _scopes(db_path)

    command.downgrade(cfg, "0075")
    down = _scopes(db_path)
    assert down["here-listed"] == {"agents": ["claude-code"], "machines": None}
    assert down["elsewhere-open"] == {"agents": [], "machines": None}
    assert down["unscoped"] is None
    assert down["stale-list"] == ["claude-code"]

    # Up again: the agent axis is already resolved, so it comes back unchanged.
    command.upgrade(cfg, "0076")
    assert _scopes(db_path) == after_up
