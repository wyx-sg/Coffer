"""Tests for the keyring adapter against an in-memory keyring backend."""

from __future__ import annotations

import keyring
import keyring.backend
import keyring.core
import pytest
from keyring.backends.fail import Keyring as FailBackend

from tests.fixtures.keyring import install_in_memory_keyring


def test_set_and_get_round_trip(monkeypatch):
    install_in_memory_keyring(monkeypatch)
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

    adapter = KeyringAdapter()
    adapter.set("github_pat_main", "ghp_topsecret")
    assert adapter.get("github_pat_main") == "ghp_topsecret"


def test_get_missing_returns_none(monkeypatch):
    install_in_memory_keyring(monkeypatch)
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

    adapter = KeyringAdapter()
    assert adapter.get("does_not_exist") is None


def test_delete(monkeypatch):
    install_in_memory_keyring(monkeypatch)
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

    adapter = KeyringAdapter()
    adapter.set("token", "secret")
    adapter.delete("token")
    assert adapter.get("token") is None


class _ReadRaisesKeyringLocked:
    """A keychain that exists but is locked: reads raise ``KeyringLocked``.

    Duck-typed, not a ``KeyringBackend`` subclass, so it never registers as a
    candidate backend for tests that let keyring pick one."""

    def get_password(self, service: str, username: str) -> str | None:
        from keyring.errors import KeyringLocked

        raise KeyringLocked("the keychain is locked")


def test_get_raises_keyring_locked(monkeypatch):
    """A locked keychain may hold the value: the adapter raises CredentialLocked
    rather than answer "absent"."""
    from coffer.domain.errors import CredentialLocked
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

    monkeypatch.setattr(keyring.core, "_keyring_backend", _ReadRaisesKeyringLocked())

    adapter = KeyringAdapter()
    with pytest.raises(CredentialLocked, match="keychain is locked"):
        adapter.get("anything")


def test_get_with_no_keychain_backend_returns_none(monkeypatch):
    """A host with no keychain backend at all (keyring's fail backend) holds
    nothing there, so a read answers None — the one case that is truly absent
    rather than unreadable."""
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

    monkeypatch.setattr(keyring.core, "_keyring_backend", FailBackend())

    assert KeyringAdapter().get("anything") is None


class _SetRaisesKeyringLocked(keyring.backend.KeyringBackend):
    """A backend whose ``set_password`` always raises ``KeyringLocked``.

    Deliberately NOT the shared ``InMemoryKeyring``: this fake exists to fail
    on purpose, and it fails on the write path only (reads succeed, returning
    nothing), which is the shape the macOS keychain presents when it is locked
    for writes. ``keyring.backends.fail.Keyring`` cannot stand in — it raises a
    different error type, on every operation.
    """

    priority = 1  # type: ignore[assignment]

    def get_password(self, service: str, username: str) -> str | None:
        return None

    def set_password(self, service: str, username: str, password: str) -> None:
        from keyring.errors import KeyringLocked

        raise KeyringLocked("keyring is locked")

    def delete_password(self, service: str, username: str) -> None:
        pass


def test_keyring_set_under_locked_raises_credential_locked(monkeypatch):
    """KeyringAdapter.set must raise CredentialLocked when the backend is locked."""
    from coffer.domain.errors import CredentialLocked
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

    monkeypatch.setattr(keyring.core, "_keyring_backend", _SetRaisesKeyringLocked())

    adapter = KeyringAdapter()
    with pytest.raises(CredentialLocked):
        adapter.set("my_ref", "secret_value")
