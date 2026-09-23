"""Removing scope's machine axis narrows rather than widens (spec vault-sync).

Revision 0076 resolves every stored machine list against the machine id the
daemon was actually using — the one cached in ``daemon-config.json`` beside the
database — and writes the answer that machine already saw, taking
``agents: []`` whenever it cannot tell. Drives the real migration script
through the helpers of its own suite.
"""

from __future__ import annotations

import pytest
from alembic import command

from tests.integration.infrastructure.persistence.test_migration_0076 import (
    _at_0075,
    _scopes,
    _seed,
)

_THIS = "M-THIS"
_OTHER = "M-OTHER"


@pytest.mark.acceptance(
    spec="vault-sync", scenario="removing the machine axis narrows rather than widens"
)
def test_the_machine_axis_is_resolved_to_what_this_machine_saw(tmp_path, monkeypatch) -> None:
    db_path, cfg = _at_0075(tmp_path, monkeypatch, "narrows.db", machine_id=_THIS)
    _seed(db_path, "admitted", {"agents": ["uid-claude"], "machines": [_OTHER, _THIS]})
    _seed(db_path, "excluded", {"agents": None, "machines": [_OTHER]})
    # A machine list the migration cannot interpret: it cannot tell whether
    # this machine was on it.
    _seed(db_path, "unreadable", {"agents": None, "machines": "M-THIS"})

    command.upgrade(cfg, "0076")

    scopes = _scopes(db_path)
    assert scopes["admitted"] == {"agents": ["uid-claude"]}
    assert scopes["excluded"] == {"agents": []}
    assert scopes["unreadable"] == {"agents": []}
    # Nothing came out wider than it went in.
    assert {"agents": None} not in scopes.values()


@pytest.mark.acceptance(
    spec="vault-sync", scenario="removing the machine axis narrows rather than widens"
)
def test_a_vault_that_cannot_name_its_machine_goes_dormant(tmp_path, monkeypatch) -> None:
    db_path, cfg = _at_0075(tmp_path, monkeypatch, "unknown.db")
    _seed(db_path, "listed", {"agents": ["uid-claude"], "machines": [_THIS]})

    command.upgrade(cfg, "0076")

    assert _scopes(db_path)["listed"] == {"agents": []}
