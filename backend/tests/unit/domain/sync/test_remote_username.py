"""The username an HTTPS token is sent with (spec vault-sync "Allow at most
one user-owned sync remote"): derived from the remote's host, never stored, and
handed to git only through the credential helper's environment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coffer.domain.sync.remote import SyncRemote, token_username
from coffer.infrastructure.vault import git


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a token is sent with the username the remote names"
)
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/me/vault.git", "coffer"),
        ("https://gitlab.com/me/vault.git", "oauth2"),
        ("https://GitLab.Example.com/me/vault.git", "oauth2"),
        ("https://gitlab.example.com/me/vault.git", "oauth2"),
        ("https://git.gitlab-corp.io/me/vault.git", "oauth2"),
        ("https://bitbucket.org/me/vault.git", "x-token-auth"),
        ("https://dev.azure.com/org/proj/_git/vault", "coffer"),
        ("git@gitlab.com:me/vault.git", "coffer"),
        ("ssh://git@bitbucket.org/me/vault.git", "coffer"),
    ],
)
def test_the_username_follows_the_host(url: str, expected: str) -> None:
    assert token_username(url) == expected
    assert SyncRemote(url=url).username == expected


def test_a_stored_username_from_an_older_version_is_ignored() -> None:
    remote = SyncRemote.from_json(
        {"url": "https://github.com/me/v.git", "username": "someone", "branch": "main"}
    )
    assert remote.username == "coffer"
    assert "username" not in json.dumps(remote.to_json())


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a token is sent with the username the remote names"
)
def test_the_helper_reads_the_username_and_token_from_its_environment() -> None:
    env = git._env(Path("/v"), None, "tok", "x-token-auth")
    assert env["COFFER_GIT_USERNAME"] == "x-token-auth"
    assert env["COFFER_GIT_TOKEN"] == "tok"
    assert "COFFER_GIT_USERNAME" in git._CREDENTIAL_HELPER
    assert "x-token-auth" not in git._CREDENTIAL_HELPER
    assert git._env(Path("/v"), None, "tok")["COFFER_GIT_USERNAME"] == "coffer"
    assert "COFFER_GIT_USERNAME" not in git._env(Path("/v"), None, None)
