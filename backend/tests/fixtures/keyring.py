"""Shared in-memory keyring backend for tests.

One dict-backed ``KeyringBackend``, installed over the process-wide active
backend, for every test that needs the keyring to simply work. There are no
local copies of this class; a test that hand-rolls its own backend is doing so
because it needs one that FAILS in a particular way, and says so in its own
docstring. Use via:

    from tests.fixtures.keyring import InMemoryKeyring, install_in_memory_keyring

    backend = install_in_memory_keyring(monkeypatch)
    backend.set_password("coffer", "ref", "secret")
"""

from __future__ import annotations

import keyring
import keyring.backend
import keyring.core
import pytest


class InMemoryKeyring(keyring.backend.KeyringBackend):
    """Minimal KeyringBackend backed by a dict.  Used only in tests."""

    priority = 1.0  # type: ignore[assignment]

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._data.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._data[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._data.pop((service, username), None)


def install_in_memory_keyring(monkeypatch: pytest.MonkeyPatch) -> InMemoryKeyring:
    """Replace the active keyring backend with a fresh InMemoryKeyring.

    Returns the backend so callers can pre-populate it via set_password().
    """
    backend = InMemoryKeyring()
    monkeypatch.setattr(keyring.core, "_keyring_backend", backend)
    return backend
