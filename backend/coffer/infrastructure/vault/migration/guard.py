"""What the daemon checks before it opens anything: whether this home has
taken the one-time upgrade (``coffer migrate``).

Kept apart from the upgrade itself so the daemon's migration runner imports
only this — never the exporters, which read every kind's tables.
"""

from __future__ import annotations

import os
from pathlib import Path

from coffer.infrastructure.vault.migration.errors import MigrationOnHold, MigrationRequired
from coffer.infrastructure.vault.migration.places import HOLD_MARKER, LEGACY_DB, RUNS_DB, at


def refuse_unmigrated_home(home: Path | None = None) -> None:
    """A rolled-back home waits for ``coffer migrate --resume``; a home with
    only ``coffer.db`` waits for ``coffer migrate``. The daemon upgrades
    neither itself."""
    marker = at(home or Path(os.environ.get("HOME", "~")).expanduser(), HOLD_MARKER)
    base = marker.parent
    if marker.exists():
        raise MigrationOnHold(marker)
    if (base / LEGACY_DB).is_file() and not (base / RUNS_DB).exists():
        raise MigrationRequired(base / LEGACY_DB)


__all__ = ["refuse_unmigrated_home"]
