"""Delete what the retired memory layer kept under ``derived/`` (spec memory
"Remove the memory delivery hook on upgrade"): the notes tree
(``derived/memory/``) and the partition rows (``derived/resources/memory/``).

Both were rebuilt from the agents' own memory, so nothing is lost. Run before
the resource store indexes ``derived/``, so no partition row is ever loaded.
"""

from __future__ import annotations

import logging
import shutil

from coffer.infrastructure.vault.home import derived_root

logger = logging.getLogger(__name__)


def remove_retired_trees() -> list[str]:
    """Delete both directories where they exist; return the ones deleted."""
    removed: list[str] = []
    for root in (derived_root() / "memory", derived_root() / "resources" / "memory"):
        if root.is_symlink():
            root.unlink()
        elif root.is_dir():
            shutil.rmtree(root)
        else:
            continue
        removed.append(str(root))
        logger.info("memory.retired_tree.removed %s", root)
    return removed


__all__ = ["remove_retired_trees"]
