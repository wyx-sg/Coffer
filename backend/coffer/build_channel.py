"""The release channel this build carries, and the commit it was built from.

The channel decides one thing: whether the development environment switches
(``COFFER_ALLOWED_HOSTS``, ``COFFER_CORS_ORIGINS``, ``COFFER_DEV_CORS``) are
read. It is ``dev`` in the repository; the release workflow runs
``scripts/stamp_channel.py stable`` before PyInstaller, so a tagged release
ignores them (no environment variable may weaken the protections). It changes
nothing a person sees: experimental features are off by default in every
build. ``sys.frozen`` is not the signal: the owner's testing build is frozen
too.

The same script stamps ``COMMIT``, the short hash of the commit the release was
built from, which the Settings About tab shows beside the version; a build from
source keeps ``None``.

Rewritten by that script; keep each assignment on one line.
"""

from __future__ import annotations

from typing import Literal

CHANNEL: Literal["stable", "dev"] = "dev"
COMMIT: str | None = None
