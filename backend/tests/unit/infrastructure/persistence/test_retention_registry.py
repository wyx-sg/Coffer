import pytest

from coffer.infrastructure.persistence.retention import (
    PrunableRegistry,
    PrunableTable,
    UnknownPrunableTable,
)


def _table(name: str = "audit_log") -> PrunableTable:
    return PrunableTable(
        name=name,
        timestamp_column="timestamp",
        default_retention_days=365,
        display_name="Audit Log",
        description="Resource lifecycle events.",
    )


def test_register_and_get():
    reg = PrunableRegistry()
    t = _table()
    reg.register(t)
    assert reg.get("audit_log") is t


def test_register_duplicate_rejected():
    reg = PrunableRegistry()
    reg.register(_table())
    with pytest.raises(ValueError):
        reg.register(_table())


def test_get_unknown_raises_unknown_prunable_table():
    reg = PrunableRegistry()
    with pytest.raises(UnknownPrunableTable):
        reg.get("nope")


def test_all_returns_all_in_registration_order():
    reg = PrunableRegistry()
    reg.register(_table("audit_log"))
    reg.register(_table("mcp_invocations"))
    names = [t.name for t in reg.all()]
    assert names == ["audit_log", "mcp_invocations"]


def test_default_retention_can_be_none_for_forever():
    """default_retention_days=None means seed with retention_days=None ('keep forever')."""
    reg = PrunableRegistry()
    reg.register(
        PrunableTable(
            name="audit_log",
            timestamp_column="timestamp",
            default_retention_days=None,
            display_name="Audit Log",
            description="Resource lifecycle events.",
        )
    )
    assert reg.get("audit_log").default_retention_days is None


def test_prunable_table_is_frozen():
    """PrunableTable is a frozen dataclass — registry entries can't be mutated."""
    t = _table()
    with pytest.raises((AttributeError, TypeError)):
        t.name = "x"  # type: ignore[misc]
