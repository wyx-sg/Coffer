#!/usr/bin/env python3
"""Stamp the release channel into ``backend/coffer/build_channel.py``.

    python scripts/stamp_channel.py stable [--commit 3909da95]

The release workflow runs this before the binaries are built, so a tagged
release is ``stable`` and every other build keeps the repository's ``dev``
(spec experimental-features "Stamp every build with a release channel").
``--commit`` also stamps the short hash of the commit being built, which
Settings > About shows beside the version. Stdlib only; each edit is anchored
on its one assignment (``CHANNEL``, ``COMMIT``).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = _REPO_ROOT / "backend" / "coffer" / "build_channel.py"
CHANNELS = ("stable", "dev")

_ANCHOR = re.compile(r'^CHANNEL: Literal\["stable", "dev"\] = "(?:stable|dev)"$', re.MULTILINE)
_COMMIT_ANCHOR = re.compile(r"^COMMIT: str \| None = .*$", re.MULTILINE)
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


def stamp(text: str, channel: str) -> str:
    """``text`` with its ``CHANNEL`` assignment set to ``channel``."""
    if channel not in CHANNELS:
        raise SystemExit(f"stamp_channel: channel must be one of {CHANNELS}, got {channel!r}")
    new, count = _ANCHOR.subn(f'CHANNEL: Literal["stable", "dev"] = "{channel}"', text, count=1)
    if count != 1:
        raise SystemExit(f"stamp_channel: no CHANNEL assignment found in {TARGET}")
    return new


def stamp_commit(text: str, commit: str) -> str:
    """``text`` with its ``COMMIT`` assignment set to ``commit`` (a short hash)."""
    if not _COMMIT_RE.match(commit):
        raise SystemExit(f"stamp_channel: --commit must be a hex commit hash, got {commit!r}")
    new, count = _COMMIT_ANCHOR.subn(f'COMMIT: str | None = "{commit[:8]}"', text, count=1)
    if count != 1:
        raise SystemExit(f"stamp_channel: no COMMIT assignment found in {TARGET}")
    return new


def main(argv: list[str] | None = None, *, target: Path = TARGET) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("channel", choices=CHANNELS)
    parser.add_argument("--commit", help="the commit being built, stamped as its short hash")
    args = parser.parse_args(argv)
    text = stamp(target.read_text(), args.channel)
    if args.commit:
        text = stamp_commit(text, args.commit)
    target.write_text(text)
    print(
        f"stamp_channel: {target.name} → {args.channel}"
        + (f" @ {args.commit[:8]}" if args.commit else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
