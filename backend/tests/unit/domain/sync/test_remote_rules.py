"""What a sync remote accepts (spec vault-sync "Allow at most one user-owned sync
remote", "Refuse a URL or branch git would read as an option")."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.domain.sync.remote import SyncRemote, SyncRemoteInvalid
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
