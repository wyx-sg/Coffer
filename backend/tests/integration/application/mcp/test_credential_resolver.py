from __future__ import annotations

import pytest

from coffer.application.mcp.credential_resolver import CredentialResolver
from coffer.domain.errors import CredentialMissing
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from tests.fixtures.keyring import install_in_memory_keyring


def _with_in_memory(monkeypatch):
    return install_in_memory_keyring(monkeypatch)


def test_materialize_round_trip(monkeypatch):
    _with_in_memory(monkeypatch)
    adapter = KeyringAdapter()
    adapter.set("github_pat_main", "ghp_topsecret")
    adapter.set("anthropic_api_key", "sk-abc")

    resolver = CredentialResolver(adapter)
    out = resolver.materialize(
        {
            "GITHUB_TOKEN": "github_pat_main",
            "ANTHROPIC_API_KEY": "anthropic_api_key",
        }
    )
    assert out == {
        "GITHUB_TOKEN": "ghp_topsecret",
        "ANTHROPIC_API_KEY": "sk-abc",
    }


def test_missing_credential_raises(monkeypatch):
    _with_in_memory(monkeypatch)
    adapter = KeyringAdapter()
    resolver = CredentialResolver(adapter)
    with pytest.raises(CredentialMissing) as exc:
        resolver.materialize({"GITHUB_TOKEN": "nope"})
    assert exc.value.ref == "nope"


def test_empty_refs_yields_empty_dict(monkeypatch):
    _with_in_memory(monkeypatch)
    adapter = KeyringAdapter()
    resolver = CredentialResolver(adapter)
    assert resolver.materialize({}) == {}
