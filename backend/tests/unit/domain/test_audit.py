from datetime import UTC, datetime

from coffer.domain.audit import AuditEntry, AuditEventType


def test_audit_event_type_values():
    assert AuditEventType.RESOURCE_CREATED.value == "resource_created"
    assert AuditEventType.RESOURCE_UPDATED.value == "resource_updated"
    assert AuditEventType.RESOURCE_ENABLED.value == "resource_enabled"
    assert AuditEventType.RESOURCE_DISABLED.value == "resource_disabled"
    assert AuditEventType.RESOURCE_DELETED.value == "resource_deleted"
    assert AuditEventType.CAPABILITY_FIRST_SEEN.value == "capability_first_seen"
    assert AuditEventType.CAPABILITY_ENABLED.value == "capability_enabled"
    assert AuditEventType.CAPABILITY_DISABLED.value == "capability_disabled"
    assert AuditEventType.DAEMON_STARTED.value == "daemon_started"
    assert AuditEventType.DAEMON_STOPPED.value == "daemon_stopped"
    assert AuditEventType.TOKEN_ROTATED.value == "token_rotated"
    assert AuditEventType.RETENTION_UPDATED.value == "retention_updated"
    assert AuditEventType.BACKUP_CREATED.value == "backup_created"


def test_slice6_hook_and_native_memory_event_values():
    assert AuditEventType.AGENT_HOOK_INSTALLED.value == "agent_hook_installed"
    assert AuditEventType.AGENT_HOOK_UNINSTALLED.value == "agent_hook_uninstalled"
    assert AuditEventType.AGENT_NATIVE_MEMORY_DISABLED.value == "agent_native_memory_disabled"
    assert AuditEventType.AGENT_NATIVE_MEMORY_RESTORED.value == "agent_native_memory_restored"


def test_audit_event_type_is_strenum():
    """StrEnum members compare equal to their string value."""
    assert AuditEventType.RESOURCE_CREATED == "resource_created"


def test_audit_entry_minimal():
    e = AuditEntry(
        id=None,
        timestamp=datetime(2026, 5, 20, tzinfo=UTC),
        event_type=AuditEventType.RESOURCE_CREATED.value,
        resource_kind="mcp_server",
        resource_name="filesystem",
        actor="cli",
        details={"config": {}},
    )
    assert e.event_type == "resource_created"
    assert e.id is None  # not yet persisted
    assert e.resource_kind == "mcp_server"
    assert e.details == {"config": {}}


def test_audit_entry_default_details():
    e = AuditEntry(
        id=42,
        timestamp=datetime(2026, 5, 20, tzinfo=UTC),
        event_type="resource_enabled",
        resource_kind="mcp_server",
        resource_name="filesystem",
        actor="api",
    )
    assert e.details == {}


def test_audit_entry_nullable_resource_fields():
    """Daemon-level events have no resource."""
    e = AuditEntry(
        id=None,
        timestamp=datetime(2026, 5, 20, tzinfo=UTC),
        event_type=AuditEventType.DAEMON_STARTED.value,
        resource_kind=None,
        resource_name=None,
        actor="system",
        details={"port": 8000},
    )
    assert e.resource_kind is None
    assert e.resource_name is None
