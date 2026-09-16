"""File modes on the daemon's token file.

`~/.coffer/daemon.json` holds the daemon's live API token in plaintext — it is
how every CLI invocation and the web UI authenticate. On a shared machine any
other local account that can read the file owns the vault, so the file must
never exist with a mode wider than 0600, not even for the instant between
creating the temp file and renaming it into place.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


def test_the_token_file_is_never_created_wider_than_0600(tmp_path: Path) -> None:
    """The write lands at mode exactly 0600 — not 0644-then-chmod.

    Asserting the final mode is what catches the ordering bug: a temp file
    created at the umask default and chmod'ed afterwards is world-readable for
    a window, and the only way to be sure that window does not exist is for the
    helper to be the single path that creates the file.
    """
    from coffer.surfaces.http.daemon_routes import _atomic_write_0600

    target = tmp_path / "secret.json"
    _atomic_write_0600(target, "{}")
    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"
