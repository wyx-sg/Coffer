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
    # spec mcp-gateway "Forward tools, resources and prompts": tools pinned into
    # the listing, left to search, or handed back to the usage ranking.
    TOOL_EXPOSURE_CHANGED = "tool_exposure_changed"
    TOKEN_ROTATED = "token_rotated"
    # spec daemon "Change residency from the settings page or the command line":
    # autostart installed or removed
    DAEMON_RESIDENCY_UPDATED = "daemon_residency_updated"
    # spec daemon "Restart itself on request": the web UI asked the daemon to
    # start its successor and exit
    DAEMON_RESTARTED = "daemon_restarted"
    RETENTION_UPDATED = "retention_updated"
    # spec web-ui "Let the user ignore any item on Overview": a
    # "needs you" item ignored on this machine, or no longer.
    ATTENTION_IGNORED = "attention_ignored"
    ATTENTION_UNIGNORED = "attention_unignored"
    # Settings > Data "Rebuildable cache": the memory tree and the transcript
    # summary cache were cleared, to be rebuilt by the next memory update.
    STORAGE_CACHE_CLEARED = "storage_cache_cleared"
    INTERNAL_ENGINE_MODEL_SET = "internal_engine_model_set"
    SECRET_SET = "secret_set"
    SECRET_DELETED = "secret_deleted"
    SECRET_NOTES_UPDATED = "secret_notes_updated"
    MASTER_KEY_RELOCATED = "master_key_relocated"
    # The secret boundary (ADR only-a-present-human-sees-a-secret-or-sends-it-
    # somewhere-new): a value shown to a present human in the desktop app, a
    # standalone secret resolved into one `coffer run` child, the approvals a
    # new destination waits on, and plaintext secret files moved into the store.
    SECRET_REVEALED = "secret_revealed"
    SECRET_RESOLVED = "secret_resolved"
    SECRET_IMPORTED = "secret_imported"
    SECRET_PLAINTEXT_IGNORED = "secret_plaintext_ignored"
    SECRET_PLAINTEXT_UNIGNORED = "secret_plaintext_unignored"
    SECRET_APPROVAL_REQUESTED = "secret_approval_requested"
    SECRET_APPROVAL_APPROVED = "secret_approval_approved"
    SECRET_APPROVAL_REJECTED = "secret_approval_rejected"
    SECRET_PROTECTION_ENABLED = "secret_protection_enabled"
    # A standalone secret's local-process grant (`coffer run`) withdrawn.
    SECRET_LOCAL_ACCESS_REVOKED = "secret_local_access_revoked"
    # spec agent-registry
    # no longer emitted; kept so recorded events still read
    AGENT_CONFIG_FILE_WRITTEN = "agent_config_file_written"
    AGENT_MCP_INSTALLED = "agent_mcp_installed"
    AGENT_MCP_UNINSTALLED = "agent_mcp_uninstalled"
    # agent workspace (spec agent-registry, amended)
    # no longer emitted; kept so recorded events still read
    AGENT_CONFIG_FILE_DELETED = "agent_config_file_deleted"
    AGENT_MCP_ENTRY_REMOVED = "agent_mcp_entry_removed"
    AGENT_MCP_ENTRY_ADOPTED = "agent_mcp_entry_adopted"
    AGENT_PLUGIN_TOGGLED = "agent_plugin_toggled"
    AGENT_PLUGIN_UNINSTALLED = "agent_plugin_uninstalled"
    # spec skill-manager
    SKILL_IMPORTED = "skill_imported"
    SKILL_UPDATED = "skill_updated"
    #: The pin moved to an upstream commit merged into local edits by hand;
    #: the master's files were not touched.
    SKILL_UPDATE_MERGED = "skill_update_merged"
    SKILL_BOUND = "skill_bound"
    SKILL_UNBOUND = "skill_unbound"
    SKILL_RELINKED = "skill_relinked"
    SKILL_DRIFT_REMEDIATED = "skill_drift_remediated"
    SKILL_ADOPTED = "skill_adopted"
    SKILL_UNMANAGED_DELETED = "skill_unmanaged_deleted"
    # spec skill-manager "Declare the commands a skill requires"
    CLI_TOOL_ADDED = "cli_tool_added"
    CLI_TOOL_EDITED = "cli_tool_edited"
    CLI_TOOL_REMOVED = "cli_tool_removed"
    # spec knowledge
    KNOWLEDGE_WRITTEN = "knowledge_written"
    KNOWLEDGE_DELETED = "knowledge_deleted"
    KNOWLEDGE_EDITED = "knowledge_edited"
    # No longer emitted: kept so a row written by an earlier build keeps its name.
    KNOWLEDGE_CURATED = "knowledge_curated"
    # spec memory
    MEMORY_AGGREGATED = "memory_aggregated"
    MEMORY_DELIVERY_FIRED = "memory_delivery_fired"
    MEMORY_DELIVERY_INSTALLED = "memory_delivery_installed"
    MEMORY_DELIVERY_REMOVED = "memory_delivery_removed"
    MEMORY_DISTILLED = "memory_distilled"
    # no longer emitted; kept so recorded events still read
    MEMORY_NOTE_EDITED = "memory_note_edited"
    MEMORY_NOTE_DELETED = "memory_note_deleted"
    # spec channels
    CHANNEL_PAIRING_ISSUED = "channel_pairing_issued"
    CHANNEL_PAIRED = "channel_paired"
    CHANNEL_PERSON_REMOVED = "channel_person_removed"
    CHANNEL_REPLY_WITHDRAWN = "channel_reply_withdrawn"
    # spec vault-storage: a person's edit found on disk and committed as a
    # ``disk`` write, and a version of a vault file or folder put back.
    VAULT_FILE_EDITED = "vault_file_edited"
    VAULT_FILE_RESTORED = "vault_file_restored"
    # spec vault-sync
    MASTER_KEY_EXPORTED = "master_key_exported"
    MASTER_KEY_IMPORTED = "master_key_imported"
    SYNC_RUN = "sync_run"
    SYNC_CONFIRMED = "sync_confirmed"
    SYNC_REJECTED = "sync_rejected"
    SYNC_ROLLED_BACK = "sync_rolled_back"
    SYNC_MACHINE_REMOVED = "sync_machine_removed"
    SYNC_PLAINTEXT_PUSHED = "sync_plaintext_pushed"
    # spec provider-switching
    PROVIDER_SWITCHED = "provider_switched"
    # No longer emitted: kept so a row written by an earlier build keeps its name.
    PROVIDER_INTERNAL_DEFAULT_SET = "provider_internal_default_set"
    PROVIDER_TRANSCRIBE_DEFAULT_SET = "provider_transcribe_default_set"
    # A projection write refused because the agent's native config file changed
    # on disk between Coffer's read and its write (optimistic concurrency).
    PROVIDER_PROJECTION_REFUSED = "provider_projection_refused"
    # The reconciler rewrote, or removed, an agent's projection whose keys no
    # longer matched the connection the registry marks active.
    PROVIDER_PROJECTION_REPAIRED = "provider_projection_repaired"


@dataclass
class AuditEntry:
    """One row in the audit_log table."""

    id: int | None
    timestamp: datetime
    event_type: str
    actor: str
    #: The resource this happened TO, by its uid. It is what makes a trail
    #: survive a rename: the kind+name below are the LABEL the resource carried
    #: AT THE TIME, so old rows keep saying what was true then instead of being
    #: rewritten to the new name. All three are ``None`` for an event that
    #: names no resource, and the uid is ``None`` for rows written before the
    #: trail was keyed on identity.
    resource_uid: str | None = None
    resource_kind: str | None = None
    resource_name: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    #: The correlation ids bound when the row was written: the
    #: HTTP request's or the turn's ``trace_id`` — the key that joins this row to
    #: the MCP invocations and the daemon log lines of the same request or turn —
    #: and, for a row a chat or channel turn wrote, its conversation and turn.
    trace_id: str | None = None
    conversation_id: str | None = None
    turn_id: str | None = None
