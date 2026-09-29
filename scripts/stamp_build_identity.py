#!/usr/bin/env python3
"""Stamp Coffer's Keychain access group into a signed release build.

    python scripts/stamp_build_identity.py <TEAM_ID>

Rewrites ``KEYCHAIN_ACCESS_GROUP`` in
``backend/coffer/infrastructure/credentials/build_identity.py`` to
``<TEAM_ID>.coffer``. The release workflow runs it only when it holds a
Developer ID (``APPLE_TEAM_ID`` and the certificate secrets are set), before
PyInstaller freezes the module, and signs the binaries with the
``keychain-access-groups`` entitlement for the same group
(``desktop/entitlements/coffer.entitlements.in``); the desktop shell reads the
same value at compile time from ``COFFER_KEYCHAIN_ACCESS_GROUP``. An unsigned
build is never stamped and keeps the development fallback (spec credentials
"Keep the master key behind a storage port chosen by the build"). Stdlib only;
the edit is anchored on the one assignment.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = _REPO_ROOT / "backend" / "coffer" / "infrastructure" / "credentials" / "build_identity.py"

# An Apple Team ID: ten upper-case letters and digits.
_TEAM_ID = re.compile(r"^[A-Z0-9]{10}$")
_ANCHOR = re.compile(
    r'^KEYCHAIN_ACCESS_GROUP: str \| None = (?:None|"[A-Z0-9]{10}\.coffer")$', re.MULTILINE
)


def access_group(team_id: str) -> str:
    """The access group a Team ID keeps the master key in."""
    if not _TEAM_ID.match(team_id):
        raise SystemExit(f"stamp_build_identity: {team_id!r} is not an Apple Team ID (ten A-Z/0-9)")
    return f"{team_id}.coffer"


def stamp(text: str, team_id: str) -> str:
    """``text`` with its ``KEYCHAIN_ACCESS_GROUP`` set to ``<team_id>.coffer``."""
    group = access_group(team_id)
    new, count = _ANCHOR.subn(f'KEYCHAIN_ACCESS_GROUP: str | None = "{group}"', text, count=1)
    if count != 1:
        raise SystemExit(f"stamp_build_identity: no KEYCHAIN_ACCESS_GROUP assignment in {TARGET}")
    return new


def main(argv: list[str] | None = None, *, target: Path = TARGET) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("team_id")
    args = parser.parse_args(argv)
    target.write_text(stamp(target.read_text(), args.team_id))
    print(f"stamp_build_identity: {target.name} → {access_group(args.team_id)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
