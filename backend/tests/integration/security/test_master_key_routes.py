"""The master key's routes belong to the secret store, not to sync (spec secret
"Import a master key after showing whose key it is").

Settings > Security shows the key's fingerprint and offers the import whether
or not the experimental ``sync`` feature is on, so the routes behind them must
answer the same either way. Installing a key stays presence-gated: the command
line has no way to get the desktop app's grant, so ``coffer secret key-install``
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
    spec="secret", scenario="a key install from the command line without a grant changes nothing"
)
def test_the_cli_cannot_install_a_key_without_the_apps_grant(daemon: BoundaryDaemon) -> None:
    before = get_master_key_manager().current
    material = Fernet.generate_key().decode()

    missing = _runner.invoke(
        cli_app,
        ["secret", "key-install", "--json", "--data", "-"],
        input=f'{{"material": "{material}"}}',
    )
    assert missing.exit_code == 6, missing.output

    forged_body = f'{{"material": "{material}", "nonce": "{"x" * 16}", "signature": "{"0" * 64}"}}'
    forged = _runner.invoke(
        cli_app, ["secret", "key-install", "--json", "--data", "-"], input=forged_body
    )
    assert forged.exit_code == 11, forged.output
    assert "PRESENCE_GRANT_INVALID" in forged.output

    assert get_master_key_manager().current == before
    shown = _runner.invoke(cli_app, ["secret", "key-fingerprint", "--json"])
    assert shown.exit_code == 0, shown.output
    assert _fingerprint() in shown.output
    assert material not in shown.output + missing.output + forged.output
    assert daemon.audit("master_key_imported") == []


def test_the_install_help_names_the_grant_and_the_app_command() -> None:
    result = _runner.invoke(cli_app, ["secret", "key-install", "--help"])
    assert result.exit_code == 0, result.output
    text = " ".join(result.output.split())
    assert "presence grant" in text
    assert "coffer secret import-key" in text
