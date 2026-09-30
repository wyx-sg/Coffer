"""Revision 0116: the graduated features' settings leave ``daemon-config.json``.

Sync, knowledge and memory are no longer experimental, so a machine's stored
switch for any of them decides nothing. The revision removes exactly those
three keys from the ``features`` object and nothing else: every other key in
the file and in ``features`` survives, a file without them is not rewritten,
and a missing or unreadable file never fails the upgrade.

Assertions read the file itself: the question is what is on disk.
"""

from __future__ import annotations

import json
import stat

import pytest
from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)


def _at_0115(tmp_path, monkeypatch, config: object | None):
    """A throwaway vault at the revision just below 0116, with ``config``
    written as the daemon config beside it (``None`` writes none)."""
    db_path = tmp_path / "coffer.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    path = tmp_path / "daemon-config.json"
    if config is not None:
        path.write_text(config if isinstance(config, str) else json.dumps(config))
    cfg = _alembic_config()
    command.upgrade(cfg, "0115")
    return path, cfg


@pytest.mark.acceptance(
    spec="experimental-features", scenario="graduating a feature strips its stored setting"
)
def test_0116_strips_the_three_graduated_keys_and_keeps_the_rest(tmp_path, monkeypatch):
    path, cfg = _at_0115(
        tmp_path,
        monkeypatch,
        {
            "port": 8000,
            "machine_id": "M-THIS",
            "features": {
                "vault_sync": False,
                "knowledge": True,
                "memory": False,
                "fake_feature": True,
            },
        },
    )

    command.upgrade(cfg, "0116")

    assert json.loads(path.read_text()) == {
        "port": 8000,
        "machine_id": "M-THIS",
        "features": {"fake_feature": True},
    }
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_0116_leaves_a_file_without_them_untouched(tmp_path, monkeypatch):
    original = '{"port": 8000, "features": {"fake_feature": false}}'
    path, cfg = _at_0115(tmp_path, monkeypatch, original)

    command.upgrade(cfg, "0116")

    assert path.read_text() == original


def test_0116_does_not_fail_without_a_readable_config(tmp_path, monkeypatch):
    path, cfg = _at_0115(tmp_path, monkeypatch, None)
    command.upgrade(cfg, "0116")
    assert not path.exists()

    path.write_text("not json")
    command.downgrade(cfg, "0115")
    command.upgrade(cfg, "0116")
    assert path.read_text() == "not json"


def test_0116_leaves_a_features_value_that_is_not_an_object(tmp_path, monkeypatch):
    path, cfg = _at_0115(tmp_path, monkeypatch, {"features": ["vault_sync"]})

    command.upgrade(cfg, "0116")

    assert json.loads(path.read_text()) == {"features": ["vault_sync"]}
