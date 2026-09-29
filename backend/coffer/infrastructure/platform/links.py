"""Directory links: symlink, NTFS junction, or a copy where neither works.

POSIX:   ``os.symlink(target, link, target_is_directory=True)``.
Windows: try ``os.symlink`` first; on failure fall back to a directory junction
         via ``mklink /J`` (no admin / developer mode needed on NTFS); where
         neither works (FAT32, network shares without reparse points), copy the
         tree wholesale.

Kind-agnostic: the result is a :class:`DirLinkKind`, which a caller maps to its
own vocabulary (the skill kind's ``LinkMode`` has the same values).
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
from enum import StrEnum

from coffer.infrastructure.platform.host import HostOs, host_os

#: ``FILE_ATTRIBUTE_REPARSE_POINT`` — set on an NTFS junction.
_REPARSE_POINT = 0x400


class DirLinkKind(StrEnum):
    """How a directory link was realised on disk."""

    SYMLINK = "symlink"
    JUNCTION = "junction"
    COPY_FALLBACK = "copy_fallback"


def link_directory(*, target: pathlib.Path, link: pathlib.Path) -> DirLinkKind:
    """Make ``link`` point at the existing directory ``target``.

    The caller has checked ``target`` is a directory, ``link`` is free and its
    parent exists; ``target`` is already resolved.
    """
    if host_os() is HostOs.WINDOWS:
        try:
            os.symlink(target, link, target_is_directory=True)
            return DirLinkKind.SYMLINK
        except OSError:
            # Fall back to a directory junction (no admin needed on NTFS).
            try:
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                    check=True,
                    capture_output=True,
                )
                return DirLinkKind.JUNCTION
            except (FileNotFoundError, subprocess.CalledProcessError):
                # Filesystem doesn't support reparse points (FAT32, some
                # network shares) — fall back to a copy.
                shutil.copytree(target, link)
                return DirLinkKind.COPY_FALLBACK
    os.symlink(target, link, target_is_directory=True)
    return DirLinkKind.SYMLINK


def is_junction(path: pathlib.Path) -> bool:
    """True when ``path`` is an NTFS directory junction. Always False off Windows."""
    if host_os() is not HostOs.WINDOWS or not path.is_dir():
        return False
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & _REPARSE_POINT)


def remove_junction(path: pathlib.Path) -> bool:
    """Remove ``path`` if it is a removable junction; True when it was removed.

    ``rmdir`` removes a junction without touching its target. Off Windows this
    is a no-op returning False, and so is a real directory that is not empty.
    """
    if host_os() is not HostOs.WINDOWS or not path.is_dir():
        return False
    try:
        os.rmdir(path)
    except OSError:
        return False
    return True


def infer_dir_link_kind(link: pathlib.Path) -> DirLinkKind:
    """Best-effort: what kind of link is actually on disk at ``link``?"""
    if link.is_symlink():
        return DirLinkKind.SYMLINK
    if is_junction(link):
        return DirLinkKind.JUNCTION
    return DirLinkKind.COPY_FALLBACK
