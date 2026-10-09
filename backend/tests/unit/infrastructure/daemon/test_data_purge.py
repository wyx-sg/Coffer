"""Deleting Coffer's data on uninstall (spec daemon "Uninstall Coffer from this
machine"; design D4)."""

from __future__ import annotations

import pathlib

from coffer.infrastructure.daemon.data_purge import purge_data
from coffer.infrastructure.secret.master_key_backends import KeychainAccessGroupBackend


def test_the_home_goes_and_a_moved_vault_is_left_in_place(tmp_path: pathlib.Path) -> None:
    home = tmp_path / "home"
    moved = tmp_path / "Sync" / "coffer-vault"
    moved.mkdir(parents=True)
    (moved / "skills").mkdir()
    root = home / ".coffer"
    (root / "logs").mkdir(parents=True)
    (root / "master.key").write_text("k")
    (root / "vault").symlink_to(moved)
    result = purge_data(home, keychain=False)
    assert not root.exists()
    assert result.removed == [str(root)]
    assert result.kept == [str(moved.resolve())]
    assert (moved / "skills").exists()
    assert result.errors == []


def test_nothing_to_delete_is_not_an_error(tmp_path: pathlib.Path) -> None:
    result = purge_data(tmp_path, keychain=False)
    assert result.removed == [] and result.errors == []


class _Api:
    def __init__(self) -> None:
        self.deleted: list[dict[str, object]] = []

    def copy_matching(self, query: dict[str, object]) -> tuple[int, bytes | None]:
        return -25300, None

    def add(self, attributes: dict[str, object]) -> int:
        return 0

    def update(self, query: dict[str, object], changes: dict[str, object]) -> int:
        return 0

    def delete(self, query: dict[str, object]) -> int:
        self.deleted.append(query)
        return 0


def test_every_keychain_item_of_coffers_goes_in_one_delete_without_an_account() -> None:
    api = _Api()
    KeychainAccessGroupBackend("TEAM.coffer", api).delete_all()
    assert len(api.deleted) == 1
    query = api.deleted[0]
    assert "kSecAttrAccount" not in query
    assert query["kSecAttrService"] == "coffer"
    assert query["kSecAttrAccessGroup"] == "TEAM.coffer"
