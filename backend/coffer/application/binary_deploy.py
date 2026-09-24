"""Deploy a frozen build's sibling binaries into ``~/.coffer/bin`` (spec daemon "Deploy
frozen sibling binaries and back up the vault before migrating").

The daemon owns the job because it is the one process every frozen install
starts, whichever tier it came from, and ``coffer-mcp-shim`` must be able to
find ``coffer-daemon`` as a sibling so an MCP client can auto-spawn a daemon
after a reboot (ADR daemon-detect-or-spawn).

Only frozen builds need this. A source install has already been handled by
``pip install``, which puts the console scripts on PATH (spec daemon "Install the console
scripts from source") — so :func:`deploy_frozen_sidecars` is a no-op outside a
PyInstaller bundle rather than something the caller has to guard.

Layout — each build lands in its own directory and the public names are
symlinks into it::

    ~/.coffer/bin/coffer-daemon  ->  0.2.0/coffer-daemon
    ~/.coffer/bin/0.2.0/coffer-daemon         (+ .coffer-daemon.version sentinel)
    ~/.coffer/bin/0.1.1/coffer-daemon         (the previous build, kept)

The paths callers use (``~/.coffer/bin/<name>``) do not change. What changes is
that a deploy never overwrites the binary a user may be running or may need to
go back to: the new build is copied beside the old one and the symlink is
flipped atomically, so a bad build is undone by pointing the link back at the
previous directory. The last :data:`KEEP_VERSIONS` directories survive; older
ones are pruned once a newer deploy lands. A public name this build no longer
ships — ``coffer-callback`` after the webhook listener was deleted — has its
symlink removed, so it stops resolving to an old build on the user's ``PATH``.

Staleness is two signals — byte size and a version sentinel written after the
copy completes. mtime is deliberately not one: a build's mtime says when it was
extracted, not what it contains, and comparing it re-copied binaries on every
start after a reinstall of the same release.
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
# included so the shim's detect-or-spawn sibling probe resolves after a reboot,
# and
# `coffer` so the user has the CLI on PATH once ~/.coffer/bin is added to it.
DEPLOYED_BINARIES: tuple[str, ...] = (
    "coffer",
    "coffer-daemon",
    "coffer-mcp-shim",
)

#: Version directories kept under ``~/.coffer/bin``: the current one and the
#: previous, so the last upgrade can always be undone by hand.
KEEP_VERSIONS = 2


def user_bin_dir() -> Path:
    """Where deployed binaries land — ``~/.coffer/bin``."""
    return Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "bin"


def versioned_target(link: Path, version: str) -> Path:
    """Where ``link``'s binary for ``version`` lives: ``<bin>/<version>/<name>``."""
    return link.parent / version / link.name


def _sentinel_for(target: Path) -> Path:
    return target.with_name(f".{target.name}.version")


def needs_deploy(link: Path, source: Path, version: str) -> bool:
    """True when ``source`` must be deployed for ``version`` behind ``link``.

    Deploys when the versioned copy is missing, differs in size, lacks its
    sentinel (a copy that never completed), or when the public name does not
    yet point at it — a fresh install, a legacy in-place file, or a link left
    on an older version after a manual rollback the user has since undone.
    """
    target = versioned_target(link, version)
    try:
        if target.stat().st_size != source.stat().st_size:
            return True
        if _sentinel_for(target).read_text().strip() != version:
            return True
        return not (link.is_symlink() and link.resolve() == target.resolve())
    except OSError:
        return True


def _atomic_deploy(source: Path, target: Path, version: str) -> None:
    """Copy ``source`` to ``target`` atomically, executable bit set first,
    then write the sentinel — so a sentinel present means a complete copy."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    shutil.copyfile(source, tmp)
    tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp, target)
    _sentinel_for(target).write_text(f"{version}\n")


def _flip_symlink(link: Path, target: Path) -> None:
    """Point ``link`` at ``target`` atomically (a temp link renamed over it).

    Relative, so the whole ``bin`` directory can be moved as a unit. Replaces
    whatever ``link`` was before — a legacy in-place binary included — in one
    rename, so a concurrent exec sees either the old file or the new one.
    """
    tmp = link.with_name(f".{link.name}.link.tmp")
    tmp.unlink(missing_ok=True)
    os.symlink(os.path.relpath(target, link.parent), tmp)
    os.replace(tmp, link)
    # The legacy layout kept a sentinel beside the in-place binary; it is
    # meaningless next to a symlink and would be read as the link's version.
    _sentinel_for(link).unlink(missing_ok=True)


def _is_version_dir(path: Path) -> bool:
    """A directory this module created: holds a ``.<name>.version`` sentinel."""
    return path.is_dir() and any(path.glob(".*.version"))


def prune_versions(dest_dir: Path, *, keep: int = KEEP_VERSIONS) -> list[str]:
    """Remove version directories beyond the newest ``keep``; return the names.

    A directory any public symlink still resolves into is never removed, no
    matter its age — that is the build in use, or one a rollback restored.
    Only directories this module created (recognised by their sentinels) are
    candidates, so nothing else a user keeps under ``bin`` is touched.
    """
    in_use: set[Path] = set()
    for link in dest_dir.iterdir():
        if link.is_symlink():
            try:
                in_use.add(link.resolve().parent)
            except OSError:
                continue
    candidates = sorted(
        (d for d in dest_dir.iterdir() if _is_version_dir(d)),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    removed: list[str] = []
    for stale in candidates[keep:]:
        if stale.resolve() in in_use:
            continue
        shutil.rmtree(stale, ignore_errors=True)
        removed.append(stale.name)
    return removed


def _points_into_a_version_dir(link: Path, dest_dir: Path) -> bool:
    """Whether ``link`` is one of this module's links: ``<bin>/<version>/<name>``.

    Read from the link's own text rather than by resolving it, so a link whose
    version directory was already pruned — dangling — is still recognised.
    """
    try:
        raw = os.readlink(link)
    except OSError:
        return False
    target = Path(os.path.normpath(dest_dir / raw))
    version_dir = target.parent
    if version_dir.parent != dest_dir or target.name != link.name:
        return False
    return not version_dir.exists() or _is_version_dir(version_dir)


def retire_unshipped_links(
    dest_dir: Path, *, shipped: tuple[str, ...] = DEPLOYED_BINARIES
) -> list[str]:
    """Remove each public symlink into a version directory under a name not shipped.

    Spec daemon "Deploy frozen sibling binaries and back up the vault before
    migrating": a binary a release dropped must stop resolving to an old build
    rather than linger on the user's ``PATH``. Generic by design, so the next
    binary a release drops needs no special case. Anything at such a path that
    is not provably one of these links — a regular file, a link elsewhere — is
    not Coffer's deployment and is left alone. Returns the names removed.
    """
    if not dest_dir.is_dir():
        return []
    removed: list[str] = []
    for entry in sorted(dest_dir.iterdir()):
        name = entry.name
        if name in shipped or name.startswith(".") or not entry.is_symlink():
            continue
        if not _points_into_a_version_dir(entry, dest_dir):
            continue
        try:
            entry.unlink()
        except OSError:
            log.warning("binary_deploy.retire_failed", extra={"binary": name}, exc_info=True)
            continue
        removed.append(name)
    return removed


def deploy_frozen_sidecars(*, version: str | None = None) -> list[str]:
    """Idempotently place this frozen build's siblings in ``~/.coffer/bin``.

    Returns the names actually deployed — empty when everything was already
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

    deployed: list[str] = []
    for name in DEPLOYED_BINARIES:
        source = source_dir / name
        if not source.is_file():
            # A build that legitimately omits a helper (no voice extra, say)
            # is not an error — there is simply nothing to deploy.
            continue
        link = dest_dir / name
        try:
            if link.exists() and link.resolve() == source.resolve():
                continue  # running from ~/.coffer/bin itself: already in place
        except OSError:
            pass
        if not needs_deploy(link, source, resolved_version):
            continue
        try:
            target = versioned_target(link, resolved_version)
            _atomic_deploy(source, target, resolved_version)
            _flip_symlink(link, target)
        except OSError:
            log.warning("binary_deploy.failed", extra={"binary": name}, exc_info=True)
            continue
        deployed.append(name)

    if deployed:
        log.info("binary_deploy.completed", extra={"binaries": deployed, "dest": str(dest_dir)})
    try:
        retired = retire_unshipped_links(dest_dir)
    except OSError:
        log.warning("binary_deploy.retire_failed", exc_info=True)
        retired = []
    if retired:
        log.info("binary_deploy.retired", extra={"binaries": retired})
    if deployed or retired:
        try:
            pruned = prune_versions(dest_dir)
        except OSError:
            log.warning("binary_deploy.prune_failed", exc_info=True)
        else:
            if pruned:
                log.info("binary_deploy.pruned", extra={"versions": pruned})
    return deployed
