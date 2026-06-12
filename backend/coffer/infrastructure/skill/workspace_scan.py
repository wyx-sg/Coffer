"""Filesystem scanner for unmanaged-skill discovery (FR-022).

Implements ``WorkspaceScanPort``: walks one agent skill location and builds
``ScanEntry`` values for the pure classifier in
``coffer.domain.skill.scan.classify``. All filesystem I/O for the scan lives
here; the domain classifier never touches disk.
"""

from __future__ import annotations

import pathlib

from coffer.domain.skill.scan import ScanEntry


class WorkspaceScan:
    """Scan a directory into ``ScanEntry`` values (one level deep)."""

    def scan_dir(self, root: pathlib.Path) -> list[ScanEntry]:
        """List *root*'s entries, resolving symlink targets to absolute paths.

        A missing or non-directory *root* yields ``[]`` — agent skill
        locations are allowed not to exist yet.

        Symlink targets are fully resolved (``classify`` requires absolute
        targets). ``Path.resolve()`` with the default ``strict=False`` still
        returns an absolute path when the target does not exist, so a broken
        link surfaces as a foreign link (its resolved target cannot be inside
        the master store). Only when the link itself cannot be read at all
        (``readlink`` raising ``OSError`` — e.g. the entry vanished mid-scan
        or permissions forbid it) is the entry skipped entirely: there is no
        meaningful target to classify and a half-built entry would either
        crash ``classify`` (relative/None ambiguity) or misclassify.
        """
        if not root.is_dir():
            return []
        out: list[ScanEntry] = []
        for p in sorted(root.iterdir()):
            target: pathlib.Path | None = None
            if p.is_symlink():
                try:
                    raw = p.readlink()
                    target = (p.parent / raw).resolve()
                except OSError:
                    continue  # unreadable link — nothing classifiable
            out.append(ScanEntry(name=p.name, path=p, is_dir=p.is_dir(), link_target=target))
        return out
