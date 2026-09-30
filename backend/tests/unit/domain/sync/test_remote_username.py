"""The username an HTTPS token is sent with (spec vault-sync "Allow at most
one user-owned sync remote"): optional, "coffer" by default, and handed to
git only through the credential helper's environment."""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.domain.sync.remote import DEFAULT_USERNAME, SyncRemote, SyncRemoteInvalid
from coffer.infrastructure.vault import git


def test_a_remote_sends_coffer_unless_told_otherwise() -> None:
    assert (
        SyncRemote(url="https://gitlab.com/me/vault.git").username == DEFAULT_USERNAME == "coffer"
    )
    assert SyncRemote(url="https://bitbucket.org/me/v.git", username="x-token-auth").username == (
        "x-token-auth"
    )


@pytest.mark.parametrize("bad", ["", "   ", "a b", "a:b", "me@host", "a/b"])
def test_a_username_git_cannot_send_is_refused(bad: str) -> None:
    with pytest.raises(SyncRemoteInvalid):
        SyncRemote(url="https://example.com/v.git", username=bad)


def test_the_helper_reads_the_username_and_token_from_its_environment() -> None:
    env = git._env(Path("/v"), None, "tok", "x-token-auth")
    assert env["COFFER_GIT_USERNAME"] == "x-token-auth"
    assert env["COFFER_GIT_TOKEN"] == "tok"
    assert "COFFER_GIT_USERNAME" in git._CREDENTIAL_HELPER
    assert "x-token-auth" not in git._CREDENTIAL_HELPER
    assert git._env(Path("/v"), None, "tok")["COFFER_GIT_USERNAME"] == "coffer"
    assert "COFFER_GIT_USERNAME" not in git._env(Path("/v"), None, None)
