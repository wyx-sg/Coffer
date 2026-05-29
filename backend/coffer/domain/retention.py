"""Retention-policy domain entity (kind-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RetentionPolicy:
    """One row in the retention_policies table.

    `retention_days`:
        - None → keep forever (no auto-prune)
        - positive int → keep N days, prune older entries
        - 0 is forbidden at the application layer; CHECK constraint in
          the migration also rejects it.
    """

    table_name: str
    retention_days: int | None
    last_pruned_at: datetime | None
    last_pruned_rows: int
    updated_at: datetime
