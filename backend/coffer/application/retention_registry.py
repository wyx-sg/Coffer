"""Prunable-table registry (application layer).

Pure value types and an in-memory registry of log-style tables that can be
pruned by the retention worker. No infrastructure or framework dependencies
— application code (specifically ``RetentionService``) imports from here so
the layered-architecture contract holds (CODE-005).

The infrastructure layer registers concrete tables at composition root by
constructing :class:`PrunableTable` instances and calling
:meth:`PrunableRegistry.register`. The infrastructure module
``coffer.infrastructure.persistence.retention`` re-exports these names for
backward compatibility with existing call sites.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.errors import CofferError


class UnknownPrunableTable(CofferError):  # noqa: N818
    """Raised when get(name) is called with an unregistered table."""

    code = "UNKNOWN_PRUNABLE_TABLE"


@dataclass(frozen=True)
class PrunableTable:
    """Declarative registration of a log-style table that can be pruned."""

    name: str
    timestamp_column: str
    default_retention_days: int | None
    display_name: str
    description: str


class PrunableRegistry:
    """Process-local registry of prunable tables.

    Populated at composition root (one register() call per kind that
    owns log tables). Read-only after startup; concrete services keep
    a reference to this registry rather than to the underlying dict.
    """

    def __init__(self) -> None:
        self._tables: dict[str, PrunableTable] = {}
        self._order: list[str] = []

    def register(self, table: PrunableTable) -> None:
        if table.name in self._tables:
            raise ValueError(f"duplicate prunable table: {table.name!r}")
        self._tables[table.name] = table
        self._order.append(table.name)

    def get(self, name: str) -> PrunableTable:
        if name not in self._tables:
            raise UnknownPrunableTable(name)
        return self._tables[name]

    def all(self) -> list[PrunableTable]:
        return [self._tables[n] for n in self._order]
