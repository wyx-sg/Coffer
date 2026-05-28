"""Cross-platform directory link helper.

POSIX:  os.symlink(target, link, target_is_directory=True)
Windows: try os.symlink first; on failure fall back to a directory junction
         via `mklink /J` (which does not require admin/dev-mode for the
         current user on NTFS).

If both fail (FAT32 on Windows, networked drives without reparse support),
fall back to copying the directory tree wholesale. Callers can detect this
via the returned `LinkMode`.

This module touches the OS heavily and lives in infrastructure. The DB
sits one layer up (in application).
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
from dataclasses import dataclass

from coffer.domain.skill.binding import LinkMode
from coffer.domain.skill.drift import DriftKind


@dataclass(frozen=True)
class TargetStatus:
    """Result of inspecting a binding's on-disk target."""

    drift: DriftKind | None  # None = OK
    target_path: str


def make_directory_link(*, target: pathlib.Path, link: pathlib.Path) -> LinkMode:
    """Create `link` pointing to `target` (a directory).

    The link's parent directory is created if missing. If the link path
    already exists, the caller must remove it first — this helper refuses
    to overwrite.
    """
    if not target.is_dir():
        raise FileNotFoundError(f"target directory does not exist: {target}")
    if link.exists() or link.is_symlink():
        raise FileExistsError(f"link path already exists: {link}")
    link.parent.mkdir(parents=True, exist_ok=True)

    target_resolved = target.resolve()

    if sys.platform == "win32":
        try:
            os.symlink(target_resolved, link, target_is_directory=True)
            return LinkMode.SYMLINK
        except OSError:
            # Fall back to a directory junction (no admin needed on NTFS).
            try:
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(target_resolved)],
                    check=True,
                    capture_output=True,
                )
                return LinkMode.JUNCTION
            except (FileNotFoundError, subprocess.CalledProcessError):
                # Filesystem doesn't support reparse points (FAT32, some
                # network shares) — fall back to a copy.
                shutil.copytree(target_resolved, link)
                return LinkMode.COPY_FALLBACK
    else:
        os.symlink(target_resolved, link, target_is_directory=True)
        return LinkMode.SYMLINK


def remove_directory_link(link: pathlib.Path, *, link_mode: LinkMode | None = None) -> None:
    """Remove a link/junction/copy-fallback at `link`. No-op if absent.

    `link_mode` is the mode recorded on the binding. It is the safety gate
    for the real-directory case: a plain directory at `link` is destroyed
    **only** when Coffer itself created it as a ``COPY_FALLBACK`` (a real
    copy of the master, on filesystems without reparse-point support). A
    real directory under any other mode is user content that *replaced* our
    link (``REPLACED_WITH_REGULAR`` drift) — we must never ``rmtree`` it,
    or disable/remove/agent-delete would silently delete the user's files.
    """
    if not link.exists() and not link.is_symlink():
        return
    if link.is_symlink():
        link.unlink()
        return
    if sys.platform == "win32" and link.is_dir():
        # Could be a junction. Try rmdir first (works for junctions; only
        # removes the link, not the target).
        try:
            os.rmdir(link)
            return
        except OSError:
            pass
    if link.is_dir():
        # Real directory. Only ours to delete if it is a recorded copy-fallback.
        if link_mode is LinkMode.COPY_FALLBACK:
            shutil.rmtree(link)
        return
    link.unlink()


def classify_target(
    *,
    link: pathlib.Path,
    expected_master: pathlib.Path,
    link_mode: LinkMode | None = None,
) -> TargetStatus:
    """Compare an expected-link path against on-disk reality.

    `None` drift means the on-disk state matches expectations.

    `link_mode` is the mode recorded on the binding (if any). It matters
    for `COPY_FALLBACK` bindings: those are realised as a *real directory*
    (a copy of the master) on filesystems without reparse-point support,
    so a plain directory at the target is expected — not drift.
    """
    if not expected_master.is_dir():
        return TargetStatus(drift=DriftKind.MISSING_MASTER, target_path=str(link))

    if not link.exists() and not link.is_symlink():
        return TargetStatus(drift=DriftKind.MISSING_LINK, target_path=str(link))

    if link.is_symlink():
        try:
            resolved = link.resolve(strict=False)
        except OSError:
            return TargetStatus(drift=DriftKind.TAMPERED_LINK, target_path=str(link))
        if resolved == expected_master.resolve():
            return TargetStatus(drift=None, target_path=str(link))
        return TargetStatus(drift=DriftKind.TAMPERED_LINK, target_path=str(link))

    if sys.platform == "win32" and link.is_dir() and _looks_like_junction(link):
        # Best-effort junction target inspection.
        try:
            resolved = pathlib.Path(os.readlink(link)).resolve()
        except OSError:
            return TargetStatus(drift=DriftKind.TAMPERED_LINK, target_path=str(link))
        if resolved == expected_master.resolve():
            return TargetStatus(drift=None, target_path=str(link))
        return TargetStatus(drift=DriftKind.TAMPERED_LINK, target_path=str(link))

    if link_mode is LinkMode.COPY_FALLBACK and link.is_dir():
        # Copy-fallback bindings are real directories by design. A plain
        # directory carrying the skill's SKILL.md is the expected state.
        if (link / "SKILL.md").is_file():
            return TargetStatus(drift=None, target_path=str(link))
        return TargetStatus(drift=DriftKind.TAMPERED_LINK, target_path=str(link))

    return TargetStatus(drift=DriftKind.REPLACED_WITH_REGULAR, target_path=str(link))


def _looks_like_junction(path: pathlib.Path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        st = os.lstat(path)
    except OSError:
        return False
    # File attribute reparse point (0x400)
    attr = getattr(st, "st_file_attributes", 0)
    return bool(attr & 0x400)


class SyncEngine:
    """Adapter bundling the three free sync-engine functions behind a single
    object so application code can inject it as a port (Contract 2).
    """

    def make_directory_link(self, *, target: pathlib.Path, link: pathlib.Path) -> LinkMode:
        return make_directory_link(target=target, link=link)

    def remove_directory_link(
        self, link: pathlib.Path, *, link_mode: LinkMode | None = None
    ) -> None:
        return remove_directory_link(link, link_mode=link_mode)

    def classify_target(
        self,
        *,
        link: pathlib.Path,
        expected_master: pathlib.Path,
        link_mode: LinkMode | None,
    ) -> TargetStatus:
        return classify_target(link=link, expected_master=expected_master, link_mode=link_mode)
