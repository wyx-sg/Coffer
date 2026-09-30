"""Startup refuses to run without the key that opens the ciphertext it holds.

spec credentials FR — a master key is never regenerated over live ciphertext,
and a present-but-corrupt key is a named, fatal startup failure rather than a
silent re-key that orphans every stored secret.
"""

from __future__ import annotations

import pathlib

import keyring.backends.fail
import keyring.core
import pytest
from keyring.errors import KeyringLocked

from coffer.domain.errors import CredentialLocked, MasterKeyMissing
from coffer.infrastructure.vault.home import coffer_home, vault_root
from coffer.surfaces.http import credential_composition as cred_comp
from tests.fixtures.keyring import install_in_memory_keyring


def _home_with_ciphertext(tmp_path: pathlib.Path) -> pathlib.Path:
    """A vault holding one ciphertext file — i.e. live ciphertext."""
    path = vault_root(tmp_path) / "secret" / "gh.enc"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"gAAAAA-not-openable-here\n")
    return tmp_path


def _key_path(home: pathlib.Path) -> pathlib.Path:
    return coffer_home(home) / "master.key"


@pytest.fixture(autouse=True)
def _isolate_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    """init_credential_store publishes DI singletons; keep them out of other tests."""
    monkeypatch.setattr(cred_comp, "_credential_store", None, raising=False)
    monkeypatch.setattr(cred_comp, "_master_key_manager", None, raising=False)


@pytest.mark.acceptance(
    spec="credentials",
    scenario="the master key is never regenerated over existing ciphertext",
)
async def test_absent_key_over_ciphertext_refuses_to_start(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_in_memory_keyring(monkeypatch)  # empty: no key in the keychain either
    home = _home_with_ciphertext(tmp_path)
    key_path = _key_path(home)
    assert not key_path.exists()

    with pytest.raises(MasterKeyMissing) as excinfo:
        await cred_comp.init_credential_store(home=home)

    # The failure names the key it expected, and writes no replacement — so
    # restoring the original key restores access to the file above.
    assert str(key_path) in str(excinfo.value)
    assert not key_path.exists()


@pytest.mark.acceptance(
    spec="credentials",
    scenario="a missing master key is a named, fatal startup failure",
)
async def test_corrupt_key_file_is_a_named_fatal_failure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_in_memory_keyring(monkeypatch)
    home = _home_with_ciphertext(tmp_path)
    key_path = _key_path(home)
    key_path.write_bytes(b"not-a-fernet-key")  # present, but opens nothing

    with pytest.raises(MasterKeyMissing) as excinfo:
        await cred_comp.init_credential_store(home=home)

    assert str(key_path) in str(excinfo.value)
    # The corrupt file is left exactly as found rather than replaced.
    assert key_path.read_bytes() == b"not-a-fernet-key"


class _LockedKeyring:
    """A keychain that is there but locked: every read raises KeyringLocked,
    as macOS does while the login keychain is locked or its prompt is dismissed.

    Duck-typed rather than a ``KeyringBackend`` subclass on purpose: every
    subclass registers itself as a candidate backend, and one that always
    raises would be picked up by any later test that lets keyring choose."""

    def get_password(self, service: str, username: str) -> str | None:
        raise KeyringLocked("the keychain is locked")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise KeyringLocked("the keychain is locked")

    def delete_password(self, service: str, username: str) -> None:
        raise KeyringLocked("the keychain is locked")


@pytest.mark.acceptance(
    spec="credentials",
    scenario="a locked keychain at start creates no key",
)
async def test_locked_keychain_with_an_empty_store_refuses_to_start(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The key may be in the locked keychain (opted in earlier). A file key
    created now would win every later start, file-first, and the keychain key
    — the one any synced ciphertext was written under — would never be read."""
    monkeypatch.setattr(keyring.core, "_keyring_backend", _LockedKeyring())
    key_path = _key_path(tmp_path)

    with pytest.raises(CredentialLocked) as excinfo:
        await cred_comp.init_credential_store(home=tmp_path)

    message = str(excinfo.value)
    assert "keychain is locked" in message
    assert "unlock" in message
    assert str(key_path) in message
    assert not key_path.exists()


async def test_no_keychain_backend_at_all_still_creates_the_file_key(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A host with no keychain backend (a bare Linux box) cannot have stored
    the key there, so a first start creates the default file key as before."""
    monkeypatch.setattr(keyring.core, "_keyring_backend", keyring.backends.fail.Keyring())
    key_path = _key_path(tmp_path)
    coffer_home(tmp_path).mkdir(parents=True)

    wiring = await cred_comp.init_credential_store(home=tmp_path)

    assert key_path.exists()
    assert wiring.master_key.location == "file"


async def test_the_key_file_follows_home_not_the_database_url(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The key opens the vault's ciphertext, so it lives in the home the vault
    is in, wherever ``COFFER_DB_URL`` points the history database."""
    monkeypatch.setattr(keyring.core, "_keyring_backend", keyring.backends.fail.Keyring())
    monkeypatch.setenv("HOME", str(tmp_path))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{elsewhere / 'runs.db'}")
    coffer_home().mkdir(parents=True)

    wiring = await cred_comp.init_credential_store()

    assert (tmp_path / ".coffer" / "master.key").is_file()
    assert not (elsewhere / "master.key").exists()
    wiring.store.set("gh/token", "v")
    assert (tmp_path / ".coffer" / "vault" / "secret" / "gh" / "token.enc").is_file()
