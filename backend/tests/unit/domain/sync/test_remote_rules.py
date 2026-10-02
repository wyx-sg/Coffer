"""What a sync remote accepts and how re-setting one keeps what it does not
name (spec vault-sync "Allow at most one user-owned sync remote", "Refuse a
URL or branch git would read as an option", "Pause a configured remote
without forgetting it")."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.domain.sync.remote import SyncRemote, SyncRemoteInvalid
from coffer.surfaces.cli.sync_remote_cmd import remote_body
from coffer.surfaces.http.sync_schemas import SyncRemoteIn

URL = "https://gitlab.com/me/vault.git"


@pytest.mark.acceptance(spec="vault-sync", scenario="an interval under a minute is refused")
def test_an_interval_under_a_minute_is_refused_before_anything_is_stored() -> None:
    with pytest.raises(ValidationError, match="60"):
        SyncRemoteIn(url=URL, interval_seconds=59)
    assert SyncRemoteIn(url=URL, interval_seconds=60).interval_seconds == 60
    # The domain object (which also reads a hand-edited remote file) refuses too.
    with pytest.raises(SyncRemoteInvalid, match="60"):
        SyncRemote(url=URL, interval_seconds=59)


@pytest.mark.acceptance(
    spec="vault-sync",
    scenario="a remote URL or branch that git would read as an option is refused",
)
@pytest.mark.parametrize(
    ("url", "branch"),
    [("--upload-pack=evil", "main"), (URL, "-f"), (URL, "a..b"), (URL, "HEAD")],
)
def test_a_url_or_branch_git_would_misread_is_refused(url: str, branch: str) -> None:
    with pytest.raises(SyncRemoteInvalid):
        SyncRemote(url=url, branch=branch)
    with pytest.raises(ValidationError):
        SyncRemoteIn(url=url, branch=branch)


_STORED = {
    "url": URL,
    "branch": "vault",
    "interval_seconds": 900,
    "include_secret": True,
    "secret_ref": "sync/gitlab-token",
    "username": "oauth2",
    "enabled": False,
}


@pytest.mark.acceptance(spec="vault-sync", scenario="reconfiguring a paused remote keeps it paused")
def test_re_setting_a_paused_remote_keeps_it_paused_and_a_first_one_starts_on() -> None:
    body = remote_body(dict(_STORED), URL, interval_seconds=600)
    assert body["interval_seconds"] == 600 and body["enabled"] is False
    first = remote_body(None, URL)
    assert first["enabled"] is True and first["branch"] == "main"
    assert first["username"] == "coffer" and first["include_secret"] is False


@pytest.mark.acceptance(
    spec="vault-sync", scenario="reconfiguring a remote changes only what it names"
)
def test_re_setting_a_remote_changes_only_what_it_names() -> None:
    body = remote_body(dict(_STORED), URL, interval_seconds=600)
    assert {k: v for k, v in body.items() if k != "interval_seconds"} == {
        k: v for k, v in _STORED.items() if k != "interval_seconds"
    }
    off = remote_body(dict(_STORED), URL, include_secret=False)
    assert off == {**_STORED, "include_secret": False}
