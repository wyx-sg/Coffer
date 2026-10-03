"""``POST /sync/vault/move`` over a real vault inside iCloud Drive (spec
vault-sync "Move the vault out of a synchronised folder")."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from coffer.infrastructure.sync.cloud_folder import synchroniser_of
from coffer.infrastructure.sync.vault_move import VaultMover
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.sync_dependencies import set_sync_service

from .conftest import TOKEN, client_for
from .harness import Box


@pytest.fixture(autouse=True)
def _token() -> Iterator[None]:
    set_active_token(TOKEN)
    yield
    set_active_token(None)
    set_sync_service(None)


@pytest.mark.acceptance(
    spec="vault-sync", scenario="the vault is moved out of a synchronised folder"
)
def test_the_vault_leaves_icloud_and_sync_resumes(tmp_path: Path) -> None:
    real = tmp_path / "Library/Mobile Documents/com~apple~CloudDocs/Coffer"
    real.mkdir(parents=True)
    coffer = tmp_path / ".coffer"
    coffer.mkdir()
    (coffer / "vault").symlink_to(real, target_is_directory=True)
    box = Box(
        coffer,
        "mac",
        "Mac",
        "unused",
        cloud=lambda: synchroniser_of(coffer / "vault", home=tmp_path),
    )
    box.put("knowledge/team/on-call.md", "Rotates on Mondays.\n")
    box.service._mover = VaultMover(home=tmp_path)

    with client_for(box) as c:
        status = c.get("/sync/status").json()
        assert status["synchroniser"] == "iCloud Drive"
        assert status["vault_real_path"] == str(real.resolve())
        assert status["default_vault_path"] == str(coffer / "vault")

        # Not inside a synchronised folder, and not somewhere that is taken.
        cloud = tmp_path / "Library/CloudStorage/x"
        cloud.parent.mkdir(parents=True)
        refused = c.post("/sync/vault/move", json={"to": str(cloud)})
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "SYNC_VAULT_TARGET_IN_CLOUD"
        assert c.post("/sync/vault/move", json={"to": "rel"}).json()["error"]["code"] == (
            "SYNC_VAULT_TARGET_INVALID"
        )

        moved = c.post("/sync/vault/move", json={"to": str(coffer / "vault")})
        assert moved.status_code == 200
        assert moved.json() == {
            "from": str(real.resolve()),
            "to": str((coffer / "vault").resolve()),
        }

        after = c.get("/sync/status").json()
        assert after["synchroniser"] is None and after["problem"] is None
    assert box.disk("knowledge/team/on-call.md") == b"Rotates on Mondays.\n"
    assert list(real.iterdir()) == []
    # Writes and rounds go on at the same path.
    box.put("knowledge/team/x.md", "x\n")
    assert box.round() is not None
