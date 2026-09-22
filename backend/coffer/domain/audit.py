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
    # Per-Agent Resource Scope: framework-level per-agent activation scope
    RESOURCE_SCOPE_UPDATED = "resource_scope_updated"
    CAPABILITY_ENABLED = "capability_enabled"
    CAPABILITY_DISABLED = "capability_disabled"
    TOKEN_ROTATED = "token_rotated"
    # spec daemon FR-028/FR-029: autostart installed or removed, idle window changed
    DAEMON_RESIDENCY_UPDATED = "daemon_residency_updated"
    RETENTION_UPDATED = "retention_updated"
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
    # agent workspace (spec agent-registry, amended)
    AGENT_CONFIG_FILE_DELETED = "agent_config_file_deleted"
    AGENT_MCP_ENTRY_REMOVED = "agent_mcp_entry_removed"
    AGENT_MCP_ENTRY_ADOPTED = "agent_mcp_entry_adopted"
    AGENT_PLUGIN_TOGGLED = "agent_plugin_toggled"
    AGENT_PLUGIN_UNINSTALLED = "agent_plugin_uninstalled"
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
    KNOWLEDGE_CURATED = "knowledge_curated"
    # spec memory
    MEMORY_AGGREGATED = "memory_aggregated"
    MEMORY_DELIVERY_FIRED = "memory_delivery_fired"
    MEMORY_DELIVERY_INSTALLED = "memory_delivery_installed"
    MEMORY_DELIVERY_REMOVED = "memory_delivery_removed"
    MEMORY_DISTILLED = "memory_distilled"
    # spec channels
    CHANNEL_PAIRING_ISSUED = "channel_pairing_issued"
    CHANNEL_PAIRED = "channel_paired"
    # spec vault-sync
    MASTER_KEY_EXPORTED = "master_key_exported"
    MASTER_KEY_IMPORTED = "master_key_imported"
    SYNC_RUN = "sync_run"
    SYNC_CONFIRMED = "sync_confirmed"
    SYNC_REJECTED = "sync_rejected"
    SYNC_ROLLED_BACK = "sync_rolled_back"
    SYNC_MACHINE_REMOVED = "sync_machine_removed"
    # spec provider-switching
    PROVIDER_SWITCHED = "provider_switched"
    PROVIDER_INTERNAL_DEFAULT_SET = "provider_internal_default_set"
    PROVIDER_TRANSCRIBE_DEFAULT_SET = "provider_transcribe_default_set"
    # A projection write refused because the agent's native config file changed
    # on disk between Coffer's read and its write (optimistic concurrency).
    PROVIDER_PROJECTION_REFUSED = "provider_projection_refused"


@dataclass
class AuditEntry:
    """One row in the audit_log table."""

    id: int | None
    timestamp: datetime
    event_type: str
    actor: str
    #: The resource this happened TO, by its stable row id. It is what makes a
    #: trail survive a rename: the kind+name below are the LABEL the resource
    #: carried AT THE TIME, so old rows keep saying what was true then instead
    #: of being rewritten to the new name. All three are ``None`` for an event
    #: that names no resource, and the id is ``None`` for rows written before
    #: the column existed.
    resource_id: int | None = None
    resource_kind: str | None = None
    resource_name: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
