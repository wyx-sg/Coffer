"""Tests for the keyring adapter using keyring's in-memory test backend."""

from __future__ import annotations

import keyring
import keyring.core
from keyring.backends.fail import Keyring as FailBackend


class InMemoryKeyring(keyring.backend.KeyringBackend):
    """Trivial in-memory backend for tests; mirrors keyring.testing.backend approach."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._data.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._data[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._data.pop((service, username), None)


def _with_in_memory(monkeypatch):
    backend = InMemoryKeyring()
    monkeypatch.setattr(keyring.core, "_keyring_backend", backend)
    return backend


def test_set_and_get_round_trip(monkeypatch):
    _with_in_memory(monkeypatch)
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

    adapter = KeyringAdapter()
    adapter.set("github_pat_main", "ghp_topsecret")
    assert adapter.get("github_pat_main") == "ghp_topsecret"


def test_get_missing_returns_none(monkeypatch):
    _with_in_memory(monkeypatch)
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

    adapter = KeyringAdapter()
    assert adapter.get("does_not_exist") is None


def test_delete(monkeypatch):
    _with_in_memory(monkeypatch)
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

    import pytest

    adapter = KeyringAdapter()
    with pytest.raises(CredentialLocked):
        adapter.get("anything")


def test_keyring_set_under_locked_raises_credential_locked(monkeypatch):
    """KeyringAdapter.set must raise CredentialLocked when the backend is locked."""
    import pytest
    from keyring.errors import KeyringLocked

    from coffer.domain.errors import CredentialLocked
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

    class _LockedBackend(keyring.backend.KeyringBackend):
        """A backend whose set_password always raises KeyringLocked."""

        priority = 1  # type: ignore[assignment]

        def get_password(self, service: str, username: str) -> str | None:
            return None

        def set_password(self, service: str, username: str, password: str) -> None:
            raise KeyringLocked("keyring is locked")

        def delete_password(self, service: str, username: str) -> None:
            pass

    monkeypatch.setattr(keyring.core, "_keyring_backend", _LockedBackend())

    adapter = KeyringAdapter()
    with pytest.raises(CredentialLocked):
        adapter.set("my_ref", "secret_value")
