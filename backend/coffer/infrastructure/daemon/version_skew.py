"""Cross-build attachment: say so when the daemon a caller found is not its build.

The daemon outlives the CLI and shim processes that attach to it, so a freshly
installed Coffer can quietly reuse a daemon from the previous install — every
command then runs against old code while the caller believes it is current
(ADR daemon-detect-or-spawn's version-skew note). A second daemon refuses to
start when one is live, and the caller never used to compare versions, so the
mismatch was silent. Detection, not refusal: the warning names both versions
and the daemon's executable so the user can see which build answered and
restart it themselves.
"""

from __future__ import annotations

from typing import Any

import coffer


def skew_warning(
    status: dict[str, Any] | None,
    *,
    caller: str,
    caller_version: str | None = None,
) -> str | None:
    """A one-line warning when ``status`` (a ``/daemon/status`` body) reports a
    different version than this build, else ``None``.

    ``status`` may be ``None`` or lack the field — an older daemon that
    predates the check, or a body that failed to parse — and both read as
    "cannot tell", never as a mismatch.
    """
    if not status:
        return None
    daemon_version = status.get("version")
    if not isinstance(daemon_version, str):
        return None
    mine = caller_version if caller_version is not None else coffer.__version__
    if daemon_version == mine:
        return None
    where = status.get("executable")
    origin = f" ({where})" if isinstance(where, str) and where else ""
    return (
        f"{caller}: WARNING: attached to a Coffer daemon at version {daemon_version}{origin} "
        f"but this {caller} is {mine}; run `coffer daemon restart` to serve the current build"
    )
