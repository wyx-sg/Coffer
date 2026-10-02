"""Skill delivery links on disk: create, remove, classify drift.

How a directory link is made per OS — a symlink on POSIX; on Windows a
symlink, else an NTFS junction, else a copy of the tree — is
``coffer.infrastructure.platform.links``'s business. This module adds what the
skill kind means by a link: its refusal to overwrite, the copy-fallback safety
gate on removal, and drift classification. Callers learn which way a link was
realised from the returned ``LinkMode``.

The DB sits one layer up (in application).
"""

from __future__ import annotations

import os
import pathlib
import shutil
from dataclasses import dataclass

from coffer.domain.skill.binding import LinkMode
from coffer.domain.skill.content_hash import folder_content_hash
from coffer.domain.skill.drift import DriftKind
from coffer.infrastructure.platform.links import (
    infer_dir_link_kind,
    is_junction,
    link_directory,
    remove_junction,
)


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
    return LinkMode(link_directory(target=target_resolved, link=link).value)


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
    # Could be a junction (Windows). rmdir removes only the link, not the
    # target; off Windows this is a no-op.
    if remove_junction(link):
        return
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

    if is_junction(link):
        # Best-effort junction target inspection.
        try:
            resolved = pathlib.Path(os.readlink(link)).resolve()
        except OSError:
            return TargetStatus(drift=DriftKind.TAMPERED_LINK, target_path=str(link))
        if resolved == expected_master.resolve():
            return TargetStatus(drift=None, target_path=str(link))
        return TargetStatus(drift=DriftKind.TAMPERED_LINK, target_path=str(link))

    if link_mode is LinkMode.COPY_FALLBACK and link.is_dir():
        # Copy-fallback bindings are real directories by design, but a copy
        # does not follow the master: one whose content no longer matches it
        # (master edited since, or the copy edited) is replaced from master by
        # the tampered-link repair, the old copy kept in the backup folder.
        in_step = (link / "SKILL.md").is_file() and folder_content_hash(
            link
        ) == folder_content_hash(expected_master)
        return TargetStatus(
            drift=None if in_step else DriftKind.TAMPERED_LINK, target_path=str(link)
        )

    return TargetStatus(drift=DriftKind.REPLACED_WITH_REGULAR, target_path=str(link))


def infer_link_mode(link: pathlib.Path) -> LinkMode:
    """Best-effort: what kind of link is actually on disk at ``link``?

    Used when a target is already correctly linked but no prior binding row
    recorded the mode, so a junction/copy-fallback isn't mislabelled SYMLINK.
    """
    return LinkMode(infer_dir_link_kind(link).value)


class SyncEngine:
    """Adapter bundling the free sync-engine functions behind a single
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

    def infer_link_mode(self, link: pathlib.Path) -> LinkMode:
        return infer_link_mode(link)
