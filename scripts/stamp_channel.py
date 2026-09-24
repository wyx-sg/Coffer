#!/usr/bin/env python3
"""Stamp the release channel into ``backend/coffer/build_channel.py``.

    python scripts/stamp_channel.py stable

The release workflow runs this before the binaries are built, so a tagged
release is ``stable`` and every other build keeps the repository's ``dev``
(spec experimental-features "Stamp every build with a release channel").
Stdlib only; the edit is anchored on the one ``CHANNEL`` assignment.
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


def stamp(text: str, channel: str) -> str:
    """``text`` with its ``CHANNEL`` assignment set to ``channel``."""
    if channel not in CHANNELS:
        raise SystemExit(f"stamp_channel: channel must be one of {CHANNELS}, got {channel!r}")
    new, count = _ANCHOR.subn(f'CHANNEL: Literal["stable", "dev"] = "{channel}"', text, count=1)
    if count != 1:
        raise SystemExit(f"stamp_channel: no CHANNEL assignment found in {TARGET}")
    return new


def main(argv: list[str] | None = None, *, target: Path = TARGET) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("channel", choices=CHANNELS)
    args = parser.parse_args(argv)
    target.write_text(stamp(target.read_text(), args.channel))
    print(f"stamp_channel: {target.name} → {args.channel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
