"""MasterKeyManager — resolve/create/relocate the Fernet master key."""

from __future__ import annotations

import pathlib
import stat

import pytest
from cryptography.fernet import Fernet

from coffer.domain.errors import MasterKeyMissing
from coffer.infrastructure.credentials.master_key import KEYCHAIN_REF, MasterKeyManager


class FakeKeyring:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self.store.get(ref)

    def set(self, ref: str, value: str) -> None:
        self.store[ref] = value

    def delete(self, ref: str) -> None:
        self.store.pop(ref, None)


@pytest.fixture
def key_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "master.key"


def test_creates_key_in_file_when_nothing_exists(key_path: pathlib.Path) -> None:
    mgr = MasterKeyManager(key_path=key_path, keyring=FakeKeyring())
    key = mgr.resolve(allow_create=True)
    assert key is not None
    Fernet(key)  # valid Fernet key
    assert mgr.location == "file"
    assert key_path.read_bytes().strip() == key
    mode = stat.S_IMODE(key_path.stat().st_mode)
    assert mode == 0o600


def test_resolves_existing_file_key(key_path: pathlib.Path) -> None:
    mgr1 = MasterKeyManager(key_path=key_path, keyring=FakeKeyring())
    key = mgr1.resolve(allow_create=True)
    mgr2 = MasterKeyManager(key_path=key_path, keyring=FakeKeyring())
    assert mgr2.resolve(allow_create=False) == key
    assert mgr2.location == "file"


def test_resolves_keychain_key_when_file_absent(key_path: pathlib.Path) -> None:
    kr = FakeKeyring()
    key = Fernet.generate_key()
    kr.set(KEYCHAIN_REF, key.decode())
    mgr = MasterKeyManager(key_path=key_path, keyring=kr)
    assert mgr.resolve(allow_create=False) == key
    assert mgr.location == "keychain"


def test_file_wins_when_both_exist(key_path: pathlib.Path) -> None:
    kr = FakeKeyring()
    kr.set(KEYCHAIN_REF, Fernet.generate_key().decode())
    file_key = Fernet.generate_key()
    key_path.write_bytes(file_key)
    mgr = MasterKeyManager(key_path=key_path, keyring=kr)
    assert mgr.resolve(allow_create=False) == file_key
    assert mgr.location == "file"


def test_returns_none_when_missing_and_create_disallowed(key_path: pathlib.Path) -> None:
    mgr = MasterKeyManager(key_path=key_path, keyring=FakeKeyring())
    assert mgr.resolve(allow_create=False) is None
    assert mgr.location is None


def test_relocate_to_keychain_moves_key(key_path: pathlib.Path) -> None:
    kr = FakeKeyring()
    mgr = MasterKeyManager(key_path=key_path, keyring=kr)
    key = mgr.resolve(allow_create=True)
    mgr.relocate("keychain")
    assert mgr.location == "keychain"
    assert not key_path.exists()
    assert kr.store[KEYCHAIN_REF].encode() == key


def test_relocate_back_to_file(key_path: pathlib.Path) -> None:
    kr = FakeKeyring()
    mgr = MasterKeyManager(key_path=key_path, keyring=kr)
    key = mgr.resolve(allow_create=True)
    mgr.relocate("keychain")
    mgr.relocate("file")
    assert mgr.location == "file"
    assert key_path.read_bytes().strip() == key
    assert KEYCHAIN_REF not in kr.store


def test_relocate_is_noop_when_already_there(key_path: pathlib.Path) -> None:
    kr = FakeKeyring()
    mgr = MasterKeyManager(key_path=key_path, keyring=kr)
    mgr.resolve(allow_create=True)
    mgr.relocate("file")
    assert mgr.location == "file"


def test_relocate_to_file_raises_when_keychain_empty(key_path: pathlib.Path) -> None:
    kr = FakeKeyring()
    mgr = MasterKeyManager(key_path=key_path, keyring=kr)
    mgr.resolve(allow_create=True)
    mgr.relocate("keychain")
    kr.store.clear()  # simulate keychain loss
    with pytest.raises(MasterKeyMissing):
        mgr.relocate("file")


def test_install_key_backs_up_existing_different_key(key_path: pathlib.Path) -> None:
    mgr = MasterKeyManager(key_path=key_path, keyring=FakeKeyring())
    old = mgr.resolve(allow_create=True)
    new = Fernet.generate_key()
    mgr.install_key(new)
    assert key_path.read_bytes().strip() == new
    backups = list(key_path.parent.glob("master.key.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes().strip() == old
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600


def test_install_key_same_key_writes_no_backup(key_path: pathlib.Path) -> None:
    mgr = MasterKeyManager(key_path=key_path, keyring=FakeKeyring())
    old = mgr.resolve(allow_create=True)
    mgr.install_key(bytes(old))
    assert key_path.read_bytes().strip() == old
    assert list(key_path.parent.glob("master.key.bak-*")) == []


def test_install_key_without_existing_key_writes_no_backup(key_path: pathlib.Path) -> None:
    mgr = MasterKeyManager(key_path=key_path, keyring=FakeKeyring())
    new = Fernet.generate_key()
    mgr.install_key(new)
    assert key_path.read_bytes().strip() == new
    assert list(key_path.parent.glob("master.key.bak-*")) == []


def test_install_key_rejects_malformed_key_before_touching_file(key_path: pathlib.Path) -> None:
    mgr = MasterKeyManager(key_path=key_path, keyring=FakeKeyring())
    old = mgr.resolve(allow_create=True)
    with pytest.raises(ValueError):
        mgr.install_key(b"not-a-fernet-key")
    assert key_path.read_bytes().strip() == old
    assert list(key_path.parent.glob("master.key.bak-*")) == []
