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
    EMBEDDING_CONFIG_UPDATED = "embedding_config_updated"
    BACKUP_CREATED = "backup_created"
    KEYCHAIN_SET = "keychain_set"
    KEYCHAIN_READ = "keychain_read"
    KEYCHAIN_DELETED = "keychain_deleted"
    # spec 004-agent-registry
    AGENT_CONFIG_FILE_WRITTEN = "agent_config_file_written"
    AGENT_MCP_INSTALLED = "agent_mcp_installed"
    AGENT_MCP_UNINSTALLED = "agent_mcp_uninstalled"
    # spec 005-skill-manager
    SKILL_IMPORTED = "skill_imported"
    SKILL_FETCHED = "skill_fetched"
    SKILL_UPDATED = "skill_updated"
    SKILL_UPDATE_NOOP = "skill_update_noop"
    SKILL_RENAMED = "skill_renamed"
    SKILL_BOUND = "skill_bound"
    SKILL_UNBOUND = "skill_unbound"
    SKILL_AUTOBIND_SKIPPED = "skill_autobind_skipped"
    SKILL_RELINKED = "skill_relinked"
    SKILL_DRIFT_DETECTED = "skill_drift_detected"
    # spec 006-knowledge-base
    KB_DOCUMENT_INGESTED = "kb_document_ingested"
    KB_DOCUMENT_UPDATED = "kb_document_updated"
    KB_DOCUMENT_DELETED = "kb_document_deleted"
    KB_REINDEXED = "kb_reindexed"
    # memory kind (spec 007)
    MEMORY_ADDED = "memory_added"
    MEMORY_UPDATED = "memory_updated"
    MEMORY_DELETED = "memory_deleted"
    MEMORY_CLEARED = "memory_cleared"
    MEMORY_PROJECTED = "memory_projected"
    # spec 008-agent-chat
    CONVERSATION_CREATED = "conversation_created"
    CONVERSATION_DELETED = "conversation_deleted"
    CONVERSATION_ARCHIVED = "conversation_archived"
    CONVERSATION_UNARCHIVED = "conversation_unarchived"
    CHAT_TURN_COMPLETED = "chat_turn_completed"
    MODEL_CREATED = "model_created"
    MODEL_UPDATED = "model_updated"
    MODEL_DELETED = "model_deleted"
    # spec 009-channels
    CHANNEL_PAIRING_ISSUED = "channel_pairing_issued"
    CHANNEL_PAIRED = "channel_paired"
    CHANNEL_NOTIFY_SENT = "channel_notify_sent"


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
