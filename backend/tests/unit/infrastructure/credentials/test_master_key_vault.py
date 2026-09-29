"""The master key in a signed build's Keychain access group (spec credentials
"Keep the master key behind a storage port chosen by the build").

The access-group backend is exercised through an injected ``SecItemApi`` fake:
the real Security.framework calls need a Developer-ID-signed binary with the
entitlement, and are never made against the developer's Keychain here.
"""

from __future__ import annotations

import pathlib

import pytest
from cryptography.fernet import Fernet

from coffer.domain.errors import CredentialLocked, MasterKeyConflict
from coffer.infrastructure.credentials.build_identity import keychain_access_group
from coffer.infrastructure.credentials.master_key import KEYCHAIN_REF, MasterKeyManager
from coffer.infrastructure.credentials.master_key_backends import (
    ERR_SEC_DUPLICATE_ITEM,
    ERR_SEC_ITEM_NOT_FOUND,
    ERR_SEC_MISSING_ENTITLEMENT,
    InMemoryMasterKeyBackend,
    KeychainAccessGroupBackend,
)


class _Keyring:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self.store.get(ref)

    def set(self, ref: str, value: str) -> None:
        self.store[ref] = value

    def delete(self, ref: str) -> None:
        self.store.pop(ref, None)


class _FakeSecItem:
    """Records every query; holds items keyed by (group, account)."""

    def __init__(self, status: int | None = None) -> None:
        self.items: dict[tuple[str, str], bytes] = {}
        self.queries: list[dict[str, object]] = []
        self.forced = status

    def _key(self, q: dict[str, object]) -> tuple[str, str]:
        return str(q["kSecAttrAccessGroup"]), str(q["kSecAttrAccount"])

    def copy_matching(self, query: dict[str, object]) -> tuple[int, bytes | None]:
        self.queries.append(query)
        if self.forced is not None:
            return self.forced, None
        data = self.items.get(self._key(query))
        return (0, data) if data is not None else (ERR_SEC_ITEM_NOT_FOUND, None)

    def add(self, attributes: dict[str, object]) -> int:
        self.queries.append(attributes)
        if self._key(attributes) in self.items:
            return ERR_SEC_DUPLICATE_ITEM
        self.items[self._key(attributes)] = bytes(attributes["kSecValueData"])  # type: ignore[arg-type]
        return 0

    def update(self, query: dict[str, object], changes: dict[str, object]) -> int:
        self.queries.append(query)
        self.items[self._key(query)] = bytes(changes["kSecValueData"])  # type: ignore[arg-type]
        return 0

    def delete(self, query: dict[str, object]) -> int:
        self.queries.append(query)
        return 0 if self.items.pop(self._key(query), None) is not None else ERR_SEC_ITEM_NOT_FOUND


@pytest.mark.acceptance(
    spec="credentials", scenario="a signed build moves a file key into its access group"
)
def test_a_signed_build_moves_the_file_key_into_the_vault(tmp_path: pathlib.Path) -> None:
    key_path = tmp_path / "master.key"
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    vault = InMemoryMasterKeyBackend()
    mgr = MasterKeyManager(key_path=key_path, keyring=_Keyring(), vault=vault)

    assert mgr.resolve(allow_create=False) == key
    assert vault.key == key and not key_path.exists()
    assert mgr.location == "keychain_access_group" and not mgr.development
    assert mgr.migrated_from == "file"
    with pytest.raises(CredentialLocked):
        mgr.relocate("file")


def test_a_legacy_keychain_key_moves_too_and_a_fresh_store_creates_in_the_vault(
    tmp_path: pathlib.Path,
) -> None:
    kr = _Keyring()
    key = Fernet.generate_key()
    kr.set(KEYCHAIN_REF, key.decode())
    vault = InMemoryMasterKeyBackend()
    assert MasterKeyManager(tmp_path / "m.key", kr, vault=vault).resolve(allow_create=False) == key
    assert kr.store == {} and vault.key == key

    empty = InMemoryMasterKeyBackend()
    created = MasterKeyManager(tmp_path / "n.key", _Keyring(), vault=empty).resolve(
        allow_create=True
    )
    assert created is not None and empty.key == created
    assert not (tmp_path / "n.key").exists()


def test_two_different_keys_stop_the_start_naming_both(tmp_path: pathlib.Path) -> None:
    key_path = tmp_path / "master.key"
    key_path.write_bytes(Fernet.generate_key())
    vault = InMemoryMasterKeyBackend()
    vault.key = Fernet.generate_key()
    with pytest.raises(MasterKeyConflict, match="two different master keys"):
        MasterKeyManager(key_path, _Keyring(), vault=vault).resolve(allow_create=False)
    assert key_path.exists()


def test_an_import_keeps_the_replaced_key_in_a_second_item(tmp_path: pathlib.Path) -> None:
    vault, backups = InMemoryMasterKeyBackend(), {}
    vault.key = Fernet.generate_key()
    old = vault.key

    def backup(stamp: str) -> InMemoryMasterKeyBackend:
        backups[stamp] = InMemoryMasterKeyBackend()
        return backups[stamp]

    mgr = MasterKeyManager(tmp_path / "m.key", _Keyring(), vault=vault, vault_backup=backup)
    new = Fernet.generate_key()
    mgr.install_key(new)
    assert vault.key == new
    assert [b.key for b in backups.values()] == [old]
    assert not (tmp_path / "m.key").exists()


@pytest.mark.acceptance(
    spec="credentials", scenario="the access-group item carries no presence flag"
)
def test_the_access_group_item_is_data_protection_without_access_control() -> None:
    api = _FakeSecItem()
    backend = KeychainAccessGroupBackend("TEAMID.coffer", api)
    key = Fernet.generate_key()

    assert backend.read() is None
    backend.write(key)
    backend.write(key)  # a second write updates rather than failing
    assert backend.read() == key
    backend.delete()
    assert backend.read() is None

    for q in api.queries:
        assert q["kSecUseDataProtectionKeychain"] is True
        assert q["kSecAttrAccessGroup"] == "TEAMID.coffer"
        assert q["kSecAttrService"] == "coffer" and q["kSecAttrAccount"] == "master-key"
        assert "kSecAttrAccessControl" not in q


def test_an_unsigned_build_is_refused_by_the_keychain_as_locked() -> None:
    backend = KeychainAccessGroupBackend("TEAMID.coffer", _FakeSecItem(ERR_SEC_MISSING_ENTITLEMENT))
    with pytest.raises(CredentialLocked, match="not signed"):
        backend.read()


def test_a_build_from_source_is_a_development_build() -> None:
    assert keychain_access_group() is None
