"""A key backup's desktop request outlives a prompt's (spec secret "Approve
from the command line with the person's own presence check"): the person types
a passphrase and picks a folder in the dialog the request keeps open."""

from __future__ import annotations

from coffer.application.secret.desktop_requests import (
    BACKUP_TTL_SECONDS,
    REQUEST_TTL_SECONDS,
    DesktopRequests,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_backup_request_waits_longer_than_a_prompt() -> None:
    clock = _Clock()
    requests = DesktopRequests(clock=clock)
    backup = requests.create("export_master_key")
    reveal = requests.create("reveal", ref="r")
    assert requests.claim() is backup
    clock.now = REQUEST_TTL_SECONDS + 1
    assert requests.get(reveal.id).status == "expired"
    assert requests.get(backup.id).status == "claimed"
    done = requests.finish(backup.id, "done", "written", {"path": "/p", "fingerprint": "f"})
    assert done.status == "done" and done.result == {"path": "/p", "fingerprint": "f"}
    late = requests.create("export_master_key")
    clock.now += BACKUP_TTL_SECONDS + 1
    assert requests.get(late.id).status == "expired"
