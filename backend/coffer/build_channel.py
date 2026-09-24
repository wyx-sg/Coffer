"""The release channel this build carries.

``dev`` in the repository, so every build is ``dev`` — a source run, ``make
desktop``, the owner's own frozen testing build. The release workflow runs
``scripts/stamp_channel.py stable`` before PyInstaller, so only a tagged
release is ``stable`` (spec experimental-features "Stamp every build with a
release channel"). ``sys.frozen`` is not the signal: the owner's testing build
is frozen too.

Rewritten by that script; keep the assignment on one line.
"""

from __future__ import annotations

from typing import Literal

CHANNEL: Literal["stable", "dev"] = "dev"
