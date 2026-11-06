"""The master key's routes belong to the secret store, not to sync (spec secret
"Import a master key after showing whose key it is").

Settings > Security shows the key's fingerprint and offers the import whether
or not the experimental ``sync`` feature is on, so the routes behind them must
answer the same either way. Installing a key stays presence-gated: the command
line has no way to get the desktop app's grant, so the import route
without one is refused and the key is unchanged.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from typer.testing import CliRunner

from coffer.infrastructure.daemon import config as daemon_config
from coffer.infrastructure.secret import key_backup
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.secret_composition import get_master_key_manager
from tests.support.boundary_daemon import (
    BoundaryDaemon,
    point_cli_at,
    prepare_home,
    running_daemon,
)

KEY = "/api/v1/secrets/key"
_runner = CliRunner()


@pytest.fixture(params=["on", "off"], ids=["sync-on", "sync-off"])
def daemon(
    request: pytest.FixtureRequest, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[BoundaryDaemon]:
    monkeypatch.setenv(
        daemon_config.FEATURES_ENV, f"knowledge=on,memory=on,sync={request.param},models=on"
    )
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        point_cli_at(d, monkeypatch)
        yield d


def _fingerprint() -> str:
    return key_backup.key_fingerprint(get_master_key_manager().current or b"")


@pytest.mark.acceptance(
    spec="secret", scenario="the master key routes answer whether or not sync is on"
)
def test_the_key_routes_answer_whatever_the_sync_switch(daemon: BoundaryDaemon) -> None:
    fingerprint = daemon.client.get(f"{KEY}/fingerprint")
    assert fingerprint.status_code == 200, fingerprint.text
    assert fingerprint.json() == {"fingerprint": _fingerprint()}

    other = Fernet.generate_key()
    preview = daemon.client.post(f"{KEY}/import/preview", json={"material": other.decode()})
    assert preview.status_code == 200, preview.text
    assert preview.json()["fingerprint"] == key_backup.key_fingerprint(other)
    assert preview.json()["current_fingerprint"] == _fingerprint()
    assert preview.json()["same"] is False
    # The old sync-prefixed paths are gone.
    assert daemon.client.get("/api/v1/sync/key/fingerprint").status_code == 404


@pytest.mark.acceptance(
    spec="secret", scenario="a key install without the app's grant changes nothing"
)
def test_a_key_install_without_the_apps_grant_changes_nothing(daemon: BoundaryDaemon) -> None:
    before = get_master_key_manager().current
    material = Fernet.generate_key().decode()

    missing = daemon.client.post(f"{KEY}/import", json={"material": material})
    forged = daemon.client.post(
        f"{KEY}/import",
        json={"material": material, "nonce": "x" * 16, "signature": "0" * 64},
    )
    assert missing.status_code == 422, missing.text
    assert "PRESENCE_GRANT_INVALID" in forged.text

    assert get_master_key_manager().current == before
    shown = _runner.invoke(cli_app, ["secret", "key-fingerprint", "--json"])
    assert shown.exit_code == 0, shown.output
    assert _fingerprint() in shown.output
    assert material not in shown.output + missing.text + forged.text
    assert daemon.audit("master_key_imported") == []

    listed = _runner.invoke(cli_app, ["secret", "--help"])
    assert "key-install" not in listed.output
    assert _runner.invoke(cli_app, ["secret", "key-install", "--help"]).exit_code != 0
