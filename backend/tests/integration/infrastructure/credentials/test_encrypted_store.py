"""EncryptedCredentialStore — Fernet ciphertext as one file per ref (ADR
storage-is-five-classes-by-nature)."""

from __future__ import annotations

import pathlib
import threading

import pytest
from cryptography.fernet import Fernet

from coffer.domain.errors import CredentialUnreadable
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore


@pytest.fixture
def store(tmp_path: pathlib.Path) -> EncryptedCredentialStore:
    return EncryptedCredentialStore(Fernet.generate_key(), home=tmp_path)


def test_set_get_roundtrip(store: EncryptedCredentialStore) -> None:
    store.set("github-token", "fake-token-value-123")
    assert store.get("github-token") == "fake-token-value-123"


def test_get_missing_returns_none(store: EncryptedCredentialStore) -> None:
    assert store.get("nope") is None


def test_set_overwrites(store: EncryptedCredentialStore) -> None:
    store.set("ref", "v1")
    store.set("ref", "v2")
    assert store.get("ref") == "v2"


def test_delete_is_idempotent(store: EncryptedCredentialStore) -> None:
    store.set("ref", "v")
    store.delete("ref")
    store.delete("ref")
    assert store.get("ref") is None


def test_remove_reports_whether_a_file_was_removed(store: EncryptedCredentialStore) -> None:
    store.set("ref", "v")
    store.set("other", "w")
    assert store.remove("ref") is True
    assert store.get("ref") is None
    assert store.remove("ref") is False
    assert store.get("other") == "w"
    assert store.count() == 1


def test_count(store: EncryptedCredentialStore) -> None:
    assert store.count() == 0
    store.set("a", "1")
    store.set("b/c", "2")
    store.set("proxy-token/agent", "3")
    assert store.count() == 3


def test_list_refs_names_every_ref_never_a_value(store: EncryptedCredentialStore) -> None:
    store.set("b/two", "second-secret")
    store.set("a", "first-secret")
    store.set("proxy-token/x", "third-secret")
    listed = store.list_refs()
    assert [ref for ref, _c, _u in listed] == ["a", "b/two", "proxy-token/x"]
    assert not any("secret" in created + updated for _r, created, updated in listed)


@pytest.mark.acceptance(spec="credentials", scenario="an unreadable ciphertext names its ref")
def test_wrong_key_raises_credential_unreadable(tmp_path: pathlib.Path) -> None:
    EncryptedCredentialStore(Fernet.generate_key(), home=tmp_path).set("ref", "v")
    other = EncryptedCredentialStore(Fernet.generate_key(), home=tmp_path)
    with pytest.raises(CredentialUnreadable):
        other.get("ref")


def test_exists_true_for_present(store: EncryptedCredentialStore) -> None:
    store.set("ref", "v")
    assert store.exists("ref") is True


def test_exists_false_for_missing(store: EncryptedCredentialStore) -> None:
    assert store.exists("nope") is False


def test_exists_does_not_decrypt_a_foreign_ciphertext(tmp_path: pathlib.Path) -> None:
    # A file written under one key is undecryptable under another: exists()
    # must report present (no decrypt) while get() raises CredentialUnreadable.
    EncryptedCredentialStore(Fernet.generate_key(), home=tmp_path).set("ref", "v")
    other = EncryptedCredentialStore(Fernet.generate_key(), home=tmp_path)
    assert other.exists("ref") is True
    with pytest.raises(CredentialUnreadable):
        other.get("ref")


def test_created_at_is_this_machines_first_store_and_survives_a_rewrite(
    store: EncryptedCredentialStore,
) -> None:
    store.set("ref", "v1")
    first = store.created_at("ref")
    assert first is not None
    store.set("ref", "v2")
    assert store.created_at("ref") == first
    store.remove("ref")
    assert store.created_at("ref") is None


def test_a_ref_that_arrived_from_elsewhere_has_no_created_at(tmp_path: pathlib.Path) -> None:
    """A ciphertext file this machine did not write (a sync round, the
    migration) was never supplied here, so the secret boundary must not count
    it as freshly supplied (spec credentials "Hold a secret for a new
    destination until a person approves it")."""
    key = Fernet.generate_key()
    here = EncryptedCredentialStore(key, home=tmp_path)
    arrived = here.path_of("gh/token")
    arrived.parent.mkdir(parents=True)
    arrived.write_bytes(Fernet(key).encrypt(b"v") + b"\n")

    assert here.get("gh/token") == "v"
    assert here.created_at("gh/token") is None
    [(ref, created, updated)] = here.list_refs()
    assert ref == "gh/token"
    assert created == updated  # the listing shows the encryption time instead


# --------------------------------------------------------------------------- #
# async facade: the same calls, off the event loop                             #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_async_facade_roundtrips_through_the_same_files(
    store: EncryptedCredentialStore,
) -> None:
    await store.aset("svc/key", "s3cret")
    assert await store.aexists("svc/key") is True
    assert await store.aget("svc/key") == "s3cret"
    assert store.get("svc/key") == "s3cret", "the sync API sees the async write"
    await store.adelete("svc/key")
    assert await store.aget("svc/key") is None
    assert await store.aexists("svc/key") is False


@pytest.mark.asyncio
async def test_async_facade_runs_the_blocking_call_off_the_loop_thread(
    tmp_path: pathlib.Path,
) -> None:
    """The point of the facade: file IO and a vault commit must not run on
    the loop thread."""
    seen: list[int] = []

    class _Recording(EncryptedCredentialStore):
        def get(self, ref: str) -> str | None:
            seen.append(threading.get_ident())
            return super().get(ref)

        def exists(self, ref: str) -> bool:
            seen.append(threading.get_ident())
            return super().exists(ref)

    store = _Recording(Fernet.generate_key(), home=tmp_path)
    await store.aget("nope")
    await store.aexists("nope")
    assert len(seen) == 2
    assert all(ident != threading.get_ident() for ident in seen)
