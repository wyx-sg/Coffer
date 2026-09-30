"""EncryptedSecretStore — Fernet ciphertext as one file per ref (ADR
storage-is-five-classes-by-nature)."""

from __future__ import annotations

import pathlib
import threading

import pytest
from cryptography.fernet import Fernet

from coffer.domain.errors import SecretUnreadable
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore


@pytest.fixture
def store(tmp_path: pathlib.Path) -> EncryptedSecretStore:
    return EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)


def test_set_get_roundtrip(store: EncryptedSecretStore) -> None:
    store.set("github-token", "fake-token-value-123")
    assert store.get("github-token") == "fake-token-value-123"


def test_get_missing_returns_none(store: EncryptedSecretStore) -> None:
    assert store.get("nope") is None


def test_set_overwrites(store: EncryptedSecretStore) -> None:
    store.set("ref", "v1")
    store.set("ref", "v2")
    assert store.get("ref") == "v2"


def test_delete_is_idempotent(store: EncryptedSecretStore) -> None:
    store.set("ref", "v")
    store.delete("ref")
    store.delete("ref")
    assert store.get("ref") is None


def test_remove_reports_whether_a_file_was_removed(store: EncryptedSecretStore) -> None:
    store.set("ref", "v")
    store.set("other", "w")
    assert store.remove("ref") is True
    assert store.get("ref") is None
    assert store.remove("ref") is False
    assert store.get("other") == "w"
    assert store.count() == 1


def test_count(store: EncryptedSecretStore) -> None:
    assert store.count() == 0
    store.set("a", "1")
    store.set("b/c", "2")
    store.set("proxy-token/agent", "3")
    assert store.count() == 3


def test_list_refs_names_every_ref_never_a_value(store: EncryptedSecretStore) -> None:
    store.set("b/two", "second-secret")
    store.set("a", "first-secret")
    store.set("proxy-token/x", "third-secret")
    listed = store.list_refs()
    assert [ref for ref, _c, _u in listed] == ["a", "b/two", "proxy-token/x"]
    assert not any("secret" in created + updated for _r, created, updated in listed)


@pytest.mark.acceptance(spec="secret", scenario="an unreadable ciphertext names its ref")
def test_wrong_key_raises_secret_unreadable(tmp_path: pathlib.Path) -> None:
    EncryptedSecretStore(Fernet.generate_key(), home=tmp_path).set("ref", "v")
    other = EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)
    with pytest.raises(SecretUnreadable):
        other.get("ref")


def test_exists_true_for_present(store: EncryptedSecretStore) -> None:
    store.set("ref", "v")
    assert store.exists("ref") is True


def test_exists_false_for_missing(store: EncryptedSecretStore) -> None:
    assert store.exists("nope") is False


def test_exists_does_not_decrypt_a_foreign_ciphertext(tmp_path: pathlib.Path) -> None:
    # A file written under one key is undecryptable under another: exists()
    # must report present (no decrypt) while get() raises SecretUnreadable.
    EncryptedSecretStore(Fernet.generate_key(), home=tmp_path).set("ref", "v")
    other = EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)
    assert other.exists("ref") is True
    with pytest.raises(SecretUnreadable):
        other.get("ref")


def test_created_at_is_this_machines_first_store_and_survives_a_rewrite(
    store: EncryptedSecretStore,
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
    it as freshly supplied (spec secret "Hold a secret for a new
    destination until a person approves it")."""
    key = Fernet.generate_key()
    here = EncryptedSecretStore(key, home=tmp_path)
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
    store: EncryptedSecretStore,
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

    class _Recording(EncryptedSecretStore):
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


# --------------------------------------------------------------------------- #
# last used, locked refs, an imported key                                      #
# --------------------------------------------------------------------------- #


def test_a_read_for_a_consumer_is_stamped_and_a_peek_is_not(store: EncryptedSecretStore) -> None:
    """Spec secret "List every stored and cited secret with what uses it": the
    stamp is machine-local, beside the boundary's other files."""
    store.set("svc/key", "v")
    assert store.peek("svc/key") == "v"
    assert store.last_used() == {}
    assert store.get("svc/key") == "v"
    assert set(store.last_used()) == {"svc/key"}
    store.delete("svc/key")
    assert store.last_used() == {}


def test_a_ciphertext_under_another_key_is_unreadable_without_decrypting(
    tmp_path: pathlib.Path,
) -> None:
    other = EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)
    other.set("from/elsewhere", "x")
    store = EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)
    store.set("from/here", "y")
    assert store.unreadable_refs() == ["from/elsewhere"]


def test_an_imported_key_seals_what_is_stored_after_it(tmp_path: pathlib.Path) -> None:
    store = EncryptedSecretStore(Fernet.generate_key(), home=tmp_path)
    imported = Fernet.generate_key()
    store.use_key(imported)
    store.set("after/import", "v")
    assert EncryptedSecretStore(imported, home=tmp_path).peek("after/import") == "v"
