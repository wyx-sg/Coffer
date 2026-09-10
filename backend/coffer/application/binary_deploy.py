"""Deploy a frozen build's sibling binaries into ``~/.coffer/bin`` (FR-026).

The Tauri shell used to do this on every launch. With the shell gone the daemon
inherits the job, and it is the right owner: ``coffer-callback`` (the channel
webhook listener) is a process the *daemon* spawns at runtime, and
``coffer-mcp-shim`` must be able to find
``coffer-daemon`` as a sibling so an MCP client can auto-spawn a daemon after a
reboot (ADR-006).

Only frozen builds need this. A source install has already been handled by
``pip install``, which puts the console scripts on PATH (spec 001 FR-018) — so
:func:`deploy_frozen_sidecars` is a no-op outside a PyInstaller bundle rather
than something the caller has to guard.

Staleness reuses the shell's three-signal test, which exists because no single
signal is sufficient:

* **size** — cheap, catches almost every content change;
* **mtime** — dev and PR builds change the binary without changing the version;
* **version sentinel** — two releases can produce a same-size binary, and
  size-equality alone would silently keep the old one.

Any signal firing forces a copy, and the copy goes to a sibling temp file
before an atomic rename, so a crash mid-deploy can never leave a half-written
executable on PATH.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# The binaries a frozen daemon deploys beside itself. `coffer-daemon` is
# included so the shim's ADR-006 sibling probe resolves after a reboot, and
# `coffer` so the user has the CLI on PATH once ~/.coffer/bin is added to it.
DEPLOYED_BINARIES: tuple[str, ...] = (
    "coffer",
    "coffer-daemon",
    "coffer-mcp-shim",
    "coffer-callback",
)


def user_bin_dir() -> Path:
    """Where deployed binaries land — ``~/.coffer/bin``."""
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "bin"


def _sentinel_for(target: Path) -> Path:
    return target.with_name(f".{target.name}.version")


def needs_copy(target: Path, source: Path, version: str) -> bool:
    """True when ``target`` must be replaced by ``source``."""
    try:
        t_stat = target.stat()
        s_stat = source.stat()
    except OSError:
        return True

    if t_stat.st_size != s_stat.st_size:
        return True
    if s_stat.st_mtime > t_stat.st_mtime:
        return True

    try:
        return _sentinel_for(target).read_text().strip() != version
    except OSError:
        return True


def _atomic_deploy(source: Path, target: Path, version: str) -> None:
    """Copy ``source`` over ``target`` atomically, executable bit set first."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    shutil.copyfile(source, tmp)
    tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp, target)
    _sentinel_for(target).write_text(f"{version}\n")


def deploy_frozen_sidecars(*, version: str | None = None) -> list[str]:
    """Idempotently place this frozen build's siblings in ``~/.coffer/bin``.

    Returns the names actually copied — empty when everything was already
    current, which is the normal case on every restart after the first.

    No-op (returns ``[]``) when not running frozen. Best-effort throughout: a
    binary that cannot be deployed is logged and skipped, never raised. The
    daemon must start even if ``~/.coffer/bin`` is read-only or a sibling is
    missing from a partial build.
    """
    if not getattr(sys, "frozen", False):
        return []

    from coffer import __version__ as coffer_version

    resolved_version = version or coffer_version
    source_dir = Path(sys.executable).resolve().parent
    dest_dir = user_bin_dir()

    copied: list[str] = []
    for name in DEPLOYED_BINARIES:
        source = source_dir / name
        if not source.is_file():
            # A build that legitimately omits a helper (no voice extra, say)
            # is not an error — there is simply nothing to deploy.
            continue
        target = dest_dir / name
        if target.resolve() == source.resolve():
            continue
        if not needs_copy(target, source, resolved_version):
            continue
        try:
            _atomic_deploy(source, target, resolved_version)
        except OSError:
            log.warning("binary_deploy.failed", extra={"binary": name}, exc_info=True)
            continue
        copied.append(name)

    if copied:
        log.info("binary_deploy.completed", extra={"binaries": copied, "dest": str(dest_dir)})
    return copied
