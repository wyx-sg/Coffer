"""Audit log domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class AuditEventType(StrEnum):
    """Enumerates every lifecycle event coffer records in audit_log."""

    RESOURCE_CREATED = "resource_created"
    RESOURCE_UPDATED = "resource_updated"
    RESOURCE_ENABLED = "resource_enabled"
    RESOURCE_DISABLED = "resource_disabled"
    RESOURCE_DELETED = "resource_deleted"
    CAPABILITY_FIRST_SEEN = "capability_first_seen"
    CAPABILITY_ENABLED = "capability_enabled"
    CAPABILITY_DISABLED = "capability_disabled"
    DAEMON_STARTED = "daemon_started"
    DAEMON_STOPPED = "daemon_stopped"
    TOKEN_ROTATED = "token_rotated"
    RETENTION_UPDATED = "retention_updated"
    BACKUP_CREATED = "backup_created"
    KEYCHAIN_SET = "keychain_set"
    KEYCHAIN_DELETED = "keychain_deleted"
    # spec 004-agent-registry
    AGENT_AUTO_REGISTERED = "agent_auto_registered"
    AGENT_TYPE_SUPPRESSED = "agent_type_suppressed"
    # spec 005-skill-manager
    SKILL_IMPORTED = "skill_imported"
    SKILL_FETCHED = "skill_fetched"
    SKILL_UPDATED = "skill_updated"
    SKILL_UPDATE_NOOP = "skill_update_noop"
    SKILL_RENAMED = "skill_renamed"
    SKILL_BOUND = "skill_bound"
    SKILL_UNBOUND = "skill_unbound"
    SKILL_DRIFT_DETECTED = "skill_drift_detected"
    # spec 006-knowledge-base
    KB_DOCUMENT_INGESTED = "kb_document_ingested"
    KB_DOCUMENT_DELETED = "kb_document_deleted"


@dataclass
class AuditEntry:
    """One row in the audit_log table."""

    id: int | None
    timestamp: datetime
    event_type: str
    resource_kind: str | None
    resource_name: str | None
    actor: str
    details: dict[str, Any] = field(default_factory=dict)
