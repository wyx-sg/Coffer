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


def test_get_raises_keyring_locked(monkeypatch):
    """When the underlying keyring is locked (fail backend), the adapter raises CredentialLocked."""
    from coffer.domain.errors import CredentialLocked
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

    monkeypatch.setattr(keyring.core, "_keyring_backend", FailBackend())

    adapter = KeyringAdapter()
    with pytest.raises(CredentialLocked):
        adapter.get("anything")


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
