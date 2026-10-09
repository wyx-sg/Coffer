"""Delete ``~/.coffer`` (spec daemon "Uninstall Coffer from this machine").

The file half of a data purge, kept apart from the Keychain half
(``data_purge.py``) so ``coffer uninstall --delete-data`` can run it: the
command line never touches the Keychain, which only the daemon owns. Run only
once the daemon has stopped serving, because ``~/.coffer`` holds the open
history database and the logs. A vault moved elsewhere (``~/.coffer/vault`` is
then a symlink) is not followed: the folder it points at may be shared or
synced, so it is left in place and named in the result.
"""

from __future__ import annotations

import contextlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from coffer.infrastructure.vault.home import coffer_home, vault_root


@dataclass
class PurgeResult:
    removed: list[str] = field(default_factory=list)
    #: A moved vault's folder, left in place.
    kept: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def purge_files(home: Path | None = None, result: PurgeResult | None = None) -> PurgeResult:
    """Delete ``~/.coffer``; failures are collected, never raised."""
    result = result if result is not None else PurgeResult()
    root = coffer_home(home)
    vault = vault_root(home)
    if vault.is_symlink():
        with contextlib.suppress(OSError):
            result.kept.append(str(vault.resolve()))
    if root.exists():
        errors: list[str] = []
        shutil.rmtree(root, onexc=lambda _fn, path, exc: errors.append(f"{path}: {exc}"))
        result.errors.extend(errors)
        if not root.exists():
            result.removed.append(str(root))
    return result


__all__ = ["PurgeResult", "purge_files"]
