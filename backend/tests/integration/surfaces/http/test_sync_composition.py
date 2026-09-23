"""Does a registered shared-state area actually converge? (spec vault-sync)

``test_composition_root.py::test_every_synced_state_area_registers_its_provider``
answers the first half — every kind's ``SyncedStatePort`` reaches the
``SyncContributions`` collector, which is where channel pairings were lost for
a release. This module deliberately starts where that one stops: the collector
is read by ``start_sync`` and handed to ``SyncExporter``, and nothing was
asserting that the rest of that path is connected. Here one decision taken
through the daemon's own routes is followed all the way into the tree the vault
converges through.

Two tests asserting the collector's contents would be one test twice, so this
one does not look at it.

It boots the **real** app (``create_app()`` + the Starlette lifespan) with
``HOME`` and the database pinned under ``tmp_path``, so what it exercises is
the wiring the daemon actually performs rather than a re-composition written
here.
"""

from __future__ import annotations

import pathlib
import subprocess

import pytest
from starlette.testclient import TestClient

from coffer.application.engine_settings_sync import AREA as SETTINGS_AREA
from coffer.application.engine_settings_sync import DOC as SETTINGS_DOC
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

pytestmark = pytest.mark.timeout(180)

_TOKEN = "test-token-sync-composition"
_HEADERS = {"X-Coffer-Token": _TOKEN}


@pytest.fixture
def app(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    monkeypatch.setenv("COFFER_SKILLS_ROOT", str(tmp_path / "skills"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59320")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59329")
    return create_app()


def test_a_registered_area_reaches_the_working_tree(
    app,  # type: ignore[no-untyped-def]
    tmp_path: pathlib.Path,
) -> None:
    """One decision over HTTP, one round, and the document is in the tree.

    A provider that reaches the collector but not the serializer would leave
    every page and every test passing while nothing converged — the same
    failure as forgetting to register it, one seam later.
    """
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True
    )

    with TestClient(app) as client:
        set_active_token(_TOKEN)
        # A non-default upkeep setting is a decision this machine publishes;
        # the defaults deliberately publish no document at all. Curation ships
        # ON (spec knowledge FR-032), so switching it OFF is the non-default
        # here — turning it on would say nothing and publish nothing.
        r = client.put(
            "/api/v1/internal-engine-config/upkeep",
            json={"pass": "curate", "enabled": False},
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text

        r = client.put("/api/v1/sync/remote", json={"url": str(remote)}, headers=_HEADERS)
        assert r.status_code == 200, r.text
        # The first round on a machine is its join, and joining is explicit.
        r = client.post("/api/v1/sync/adopt", json={}, headers=_HEADERS)
        assert r.status_code == 200, r.text
        assert r.json()["status"] in ("ok", "no_change"), r.json()
    set_active_token(None)

    doc = tmp_path / ".coffer" / "sync" / "state" / SETTINGS_AREA / f"{SETTINGS_DOC}.yaml"
    assert doc.is_file(), (
        "a decision taken through the daemon's own routes did not reach the tree "
        "the vault converges through"
    )
