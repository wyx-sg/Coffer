"""What the encrypted store itself promises on disk (spec secret; ADR
storage-is-five-classes-by-nature, secrets-cross-machines-only-as-ciphertext).

Real files, a real vault repository, a real Fernet key and the store's own
code — the tests read the ciphertext files and the vault's git history back
directly, so they see exactly what is persisted, not what the store returns.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import stat
import subprocess
import threading
import time
from typing import Any

import pytest
from cryptography.fernet import Fernet

from coffer.domain.vault.fernet_time import encrypted_at
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.infrastructure.vault.home import local_root, vault_root
from coffer.infrastructure.vault.instance import vault_repository


def _git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


def _mode(path: pathlib.Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.mark.acceptance(spec="secret", scenario="a stored secret is only ciphertext in its file")
@pytest.mark.acceptance(spec="vault-storage", scenario="a secret is only ciphertext in its file")
def test_a_stored_secret_is_only_ciphertext_in_its_file(tmp_path: pathlib.Path) -> None:
    key = Fernet.generate_key()
    store = EncryptedSecretStore(key, home=tmp_path)
    secret = "sk-plaintext-must-not-persist"

    store.set("svc/key", secret)

    path = vault_root(tmp_path) / "secret" / "svc" / "key.enc"
    data = path.read_bytes()
    assert data.endswith(b"\n") and data.count(b"\n") == 1
    assert secret.encode() not in data
    assert Fernet(key).decrypt(data.strip()).decode() == secret
    # Nothing anywhere under ~/.coffer spells it either.
    for found in (tmp_path / ".coffer").rglob("*"):
        if found.is_file():
            assert secret.encode() not in found.read_bytes(), found


@pytest.mark.acceptance(spec="secret", scenario="writing an existing ref re-encrypts it in place")
def test_writing_an_existing_ref_re_encrypts_it_in_place(tmp_path: pathlib.Path) -> None:
    key = Fernet.generate_key()
    store = EncryptedSecretStore(key, home=tmp_path)

    store.set("svc/key", "first-value")
    path = store.path_of("svc/key")
    first_cipher = path.read_bytes()
    created = store.created_at("svc/key")
    time.sleep(1.05)  # the token's timestamp has one-second resolution
    store.set("svc/key", "second-value")

    cipher = path.read_bytes()
    assert cipher != first_cipher
    assert Fernet(key).decrypt(cipher.strip()).decode() == "second-value"
    assert store.get("svc/key") == "second-value"
    assert store.created_at("svc/key") == created
    [(ref, _created, updated)] = store.list_refs()
    assert ref == "svc/key"
    assert updated > _created
    assert encrypted_at(cipher) is not None
    assert encrypted_at(cipher) > encrypted_at(first_cipher)  # type: ignore[operator]


@pytest.mark.acceptance(
    spec="secret", scenario="an async caller reaches the store through its async facade"
)
async def test_an_async_caller_reaches_the_store_through_its_async_facade(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)
    loop_thread = threading.get_ident()
    seen: list[int] = []

    def recording(name: str) -> None:
        real = getattr(store, name)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            seen.append(threading.get_ident())
            return real(*args, **kwargs)

        monkeypatch.setattr(store, name, wrapper)

    for name in ("path_of", "_write_vault", "_delete_vault"):
        recording(name)
    assert asyncio.get_running_loop() is not None

    await store.aset("svc/key", "async-value")
    assert await store.aget("svc/key") == "async-value"
    assert await store.aexists("svc/key") is True
    await store.adelete("svc/key")
    assert await store.aexists("svc/key") is False
    assert await store.aget("svc/key") is None

    # Every blocking file or git call ran — and none of them on the loop's thread.
    assert len(seen) >= 6
    assert all(ident != loop_thread for ident in seen)


def test_files_are_0600_and_their_directories_0700(tmp_path: pathlib.Path) -> None:
    store = EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)
    store.set("channel/seatalk/app-secret", "v")
    store.set("proxy-token/agent-1", "t")

    vault_file = vault_root(tmp_path) / "secret" / "channel" / "seatalk" / "app-secret.enc"
    local_file = local_root(tmp_path) / "secret" / "proxy-token" / "agent-1.enc"
    assert _mode(vault_file) == 0o600
    assert _mode(local_file) == 0o600
    for directory in (
        vault_root(tmp_path) / "secret",
        vault_file.parent,
        vault_file.parent.parent,
        local_root(tmp_path) / "secret",
        local_file.parent,
    ):
        assert _mode(directory) == 0o700, directory


@pytest.mark.acceptance(spec="vault-storage", scenario="a proxy token stays machine-local")
def test_proxy_tokens_live_under_local_and_never_under_the_vault(tmp_path: pathlib.Path) -> None:
    """A proxy token unlocks only this machine's loopback model proxy, so it
    is machine-local state and has no file the vault could ever commit."""
    store = EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)
    vault_repository(vault_root(tmp_path)).set_carry_secret(True)
    store.set("proxy-token/agent-1", "loopback-token")

    assert (local_root(tmp_path) / "secret" / "proxy-token" / "agent-1.enc").is_file()
    assert not list((tmp_path / ".coffer" / "vault").rglob("agent-1.enc"))
    assert store.get("proxy-token/agent-1") == "loopback-token"
    assert store.remove("proxy-token/agent-1") is True
    assert not (local_root(tmp_path) / "secret" / "proxy-token").exists()


def test_a_set_is_a_vault_commit_when_the_repository_carries_secret(
    tmp_path: pathlib.Path,
) -> None:
    store = EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)
    root = vault_root(tmp_path)
    vault_repository(root).set_carry_secret(True)

    store.set("gh/token", "v1")
    body = _git(root, "log", "-1", "--format=%an%n%B")
    assert body.startswith("Coffer (daemon)\n")
    assert "Stored secret gh/token" in body
    assert "Coffer-Writer: daemon" in body
    assert "Coffer-Operation: secret-set" in body
    assert "v1" not in body
    assert _git(root, "ls-files", "secret").split() == ["secret/gh/token.enc"]

    store.remove("gh/token")
    body = _git(root, "log", "-1", "--format=%B")
    assert "Coffer-Operation: secret-delete" in body
    assert _git(root, "ls-files", "secret") == ""


def test_a_set_is_no_commit_while_the_repository_does_not_carry_secret(
    tmp_path: pathlib.Path,
) -> None:
    store = EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)
    root = vault_root(tmp_path)

    store.set("gh/token", "v1")
    store.set("gh/token", "v2")
    store.remove("gh/token")
    store.set("gh/other", "v3")

    assert (root / "secret" / "gh" / "other.enc").is_file()
    assert _git(root, "rev-list", "--count", "HEAD").strip() == "1"  # the baseline only
    assert _git(root, "ls-files", "secret") == ""
    assert _git(root, "status", "--porcelain") == ""


def test_odd_refs_are_stored_under_their_encoded_names(tmp_path: pathlib.Path) -> None:
    store = EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)
    store.set("team one/.git/ключ", "v")
    creds = vault_root(tmp_path) / "secret"
    expected = creds / "team%20one" / "%2Egit" / "%D0%BA%D0%BB%D1%8E%D1%87.enc"
    assert expected.is_file()
    assert [ref for ref, _c, _u in store.list_refs()] == ["team one/.git/ключ"]


@pytest.mark.parametrize("ref", ["", "a//b", "../x", "a/..", "/abs", "trailing/", "./a"])
def test_a_ref_that_would_leave_its_directory_is_refused(tmp_path: pathlib.Path, ref: str) -> None:
    store = EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)
    with pytest.raises(ValueError):
        store.set(ref, "v")
    assert not (tmp_path / ".coffer" / "vault" / "secret").exists()
