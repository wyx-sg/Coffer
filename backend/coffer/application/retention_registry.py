"""Prunable-table registry (application layer).

Pure value types and an in-memory registry of log-style tables that can be
pruned by the retention worker. No infrastructure or framework dependencies
— application code (specifically ``RetentionService``) imports from here so
the layered-architecture contract holds.

The infrastructure layer registers concrete tables at composition root by
constructing :class:`PrunableTable` instances and calling
:meth:`PrunableRegistry.register`.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.errors import CofferError


class UnknownPrunableTable(CofferError):  # noqa: N818
    """Raised when get(name) is called with an unregistered table."""

    code = "UNKNOWN_PRUNABLE_TABLE"


@dataclass(frozen=True)
class PrunableTable:
    """Declarative registration of a table the retention worker sweeps.

    Most entries ``delete`` rows older than the policy window. A few model a
    two-stage lifecycle instead: an ``archive`` action stamps ``archive_set_column``
    with the current time on rows older than the window (e.g. auto-archiving idle
    chat threads), and a sibling ``delete`` entry keyed on that stamp removes them
    later. ``name`` is the policy key (one ``retention_policies`` row); ``target_table``
    is the SQL table acted on, which differs from ``name`` only for an archive entry
    that shares a table with its delete sibling.

    ``policy_name`` makes a table a FOLLOWER of another entry's policy: it has no
    ``retention_policies`` row of its own (never seeded, never listed, never
    set), and it is pruned with the named policy's window whenever that policy
    is — the per-request usage detail follows the MCP-calls window this way.
    """

    name: str
    timestamp_column: str
    default_retention_days: int | None
    display_name: str
    description: str
    action: str = "delete"  # "delete" | "archive"
    target_table: str | None = None
    archive_set_column: str | None = None
    policy_name: str | None = None

    @property
    def policy_key(self) -> str:
        """The ``retention_policies`` row whose window governs this table."""
        return self.policy_name or self.name

    @property
    def owns_policy(self) -> bool:
        """Whether this entry has a policy row of its own (not a follower)."""
        return self.policy_name is None

    @property
    def sql_table(self) -> str:
        """The actual SQL table this policy acts on (``name`` unless overridden)."""
        return self.target_table or self.name


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
        if table.policy_name is not None:
            leader = self._tables.get(table.policy_name)
            if leader is None or not leader.owns_policy:
                raise ValueError(
                    f"{table.name!r} follows {table.policy_name!r}, which is not a "
                    "registered policy (register the leader first)"
                )
        self._tables[table.name] = table
        self._order.append(table.name)

    def get(self, name: str) -> PrunableTable:
        if name not in self._tables:
            raise UnknownPrunableTable(name)
        return self._tables[name]

    def all(self) -> list[PrunableTable]:
        return [self._tables[n] for n in self._order]

    def policies(self) -> list[PrunableTable]:
        """The entries that own a policy row — what is seeded and listed."""
        return [t for t in self.all() if t.owns_policy]

    def followers(self, policy: str) -> list[PrunableTable]:
        """The entries pruned with ``policy``'s window but owning no row."""
        return [t for t in self.all() if t.policy_name == policy]
