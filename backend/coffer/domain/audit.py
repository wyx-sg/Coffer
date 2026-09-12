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
    # A resource moved to a new name: its identity, not its config, changed.
    RESOURCE_RENAMED = "resource_renamed"
    # Per-Agent Resource Scope: framework-level machine x agent activation scope
    RESOURCE_SCOPE_UPDATED = "resource_scope_updated"
    CAPABILITY_ENABLED = "capability_enabled"
    CAPABILITY_DISABLED = "capability_disabled"
    TOKEN_ROTATED = "token_rotated"
    RETENTION_UPDATED = "retention_updated"
    EMBEDDING_CONFIG_UPDATED = "embedding_config_updated"
    INTERNAL_ENGINE_MODEL_SET = "internal_engine_model_set"
    CREDENTIAL_SET = "credential_set"
    CREDENTIAL_READ = "credential_read"
    CREDENTIAL_DELETED = "credential_deleted"
    CREDENTIAL_MIGRATED = "credential_migrated"
    MASTER_KEY_RELOCATED = "master_key_relocated"
    # spec agent-registry
    AGENT_CONFIG_FILE_WRITTEN = "agent_config_file_written"
    AGENT_MCP_INSTALLED = "agent_mcp_installed"
    AGENT_MCP_UNINSTALLED = "agent_mcp_uninstalled"
    # agent workspace (specs agent-registry/005 amendment)
    AGENT_CONFIG_FILE_DELETED = "agent_config_file_deleted"
    AGENT_MCP_ENTRY_REMOVED = "agent_mcp_entry_removed"
    AGENT_MCP_ENTRY_ADOPTED = "agent_mcp_entry_adopted"
    # spec skill-manager
    SKILL_IMPORTED = "skill_imported"
    SKILL_UPDATED = "skill_updated"
    SKILL_BOUND = "skill_bound"
    SKILL_UNBOUND = "skill_unbound"
    SKILL_RELINKED = "skill_relinked"
    SKILL_DRIFT_REMEDIATED = "skill_drift_remediated"
    SKILL_ADOPTED = "skill_adopted"
    SKILL_UNMANAGED_DELETED = "skill_unmanaged_deleted"
    # spec knowledge
    KNOWLEDGE_WRITTEN = "knowledge_written"
    KNOWLEDGE_DELETED = "knowledge_deleted"
    KNOWLEDGE_TIDIED = "knowledge_tidied"
    # spec channels
    CHANNEL_PAIRING_ISSUED = "channel_pairing_issued"
    CHANNEL_PAIRED = "channel_paired"
    # spec vault-export-import
    MASTER_KEY_EXPORTED = "master_key_exported"
    MASTER_KEY_IMPORTED = "master_key_imported"
    VAULT_BACKED_UP = "vault_backed_up"
    # spec mcp-gateway FR-028
    DAEMON_PORT_SET = "daemon_port_set"
    # spec provider-switching
    PROVIDER_SWITCHED = "provider_switched"
    PROVIDER_INTERNAL_DEFAULT_SET = "provider_internal_default_set"


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
