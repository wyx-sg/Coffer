from datetime import UTC, datetime

from coffer.domain.retention import RetentionPolicy


def test_retention_policy_with_days():
    p = RetentionPolicy(
        table_name="audit_log",
        retention_days=365,
        last_pruned_at=None,
        last_pruned_rows=0,
        updated_at=datetime(2026, 5, 20, tzinfo=UTC),
    )
    assert p.retention_days == 365
    assert p.last_pruned_at is None
    assert p.last_pruned_rows == 0


def test_retention_policy_forever():
    """retention_days = None means keep forever."""
    p = RetentionPolicy(
        table_name="audit_log",
        retention_days=None,
        last_pruned_at=None,
        last_pruned_rows=0,
        updated_at=datetime(2026, 5, 20, tzinfo=UTC),
    )
    assert p.retention_days is None


def test_retention_policy_with_pruned_state():
    p = RetentionPolicy(
        table_name="mcp_invocations",
        retention_days=30,
        last_pruned_at=datetime(2026, 5, 19, tzinfo=UTC),
        last_pruned_rows=1247,
        updated_at=datetime(2026, 5, 20, tzinfo=UTC),
    )
    assert p.last_pruned_rows == 1247
    assert p.last_pruned_at == datetime(2026, 5, 19, tzinfo=UTC)
