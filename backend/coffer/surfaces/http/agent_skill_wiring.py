"""Composition-root helper that wires the agent + skill kinds into the app.

Extracted from `app.py` to keep that file under the size limit. The
cross-kind on_delete hook (deleting an agent cascades into skill binding
cleanup) is bound here because this module is allowed to import both kind
subpackages — they cannot import each other (Contract 5).
"""

from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING, Any

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.config_file_service import AgentConfigFileService
from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.mcp_entry_service import AgentMcpEntryService
from coffer.application.agent.mcp_service import AgentMcpService
from coffer.application.agent.native_memory_service import AgentNativeMemoryService
from coffer.application.agent.plugin_service import AgentPluginService
from coffer.application.agent.plugin_sync_state import AgentPluginSyncState
from coffer.application.agent.service import AgentService
from coffer.application.agent.sync_reconcile import AgentImportGate, AgentSideEffectsReconcile
from coffer.application.agent.transcript_service import AgentTranscriptService
from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.resource_service import ResourceService
from coffer.application.skill.builtin_tools import register_skill_builtin_tools
from coffer.application.skill.kind import make_skill_kind
from coffer.application.skill.service import SkillService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.scan import scan_locations
from coffer.domain.resource import Resource, ResourceRef
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.agent.native_memory_store import FileNativeMemoryScanner
from coffer.infrastructure.agent.plugin_bundle import FsPluginDetailReader
from coffer.infrastructure.agent.plugin_cli import ClaudePluginCli
from coffer.infrastructure.agent.transcript_reader import FileTranscriptReader
from coffer.infrastructure.skill.master_store import MasterStore
from coffer.infrastructure.skill.persistence import SkillBindingRepo
from coffer.infrastructure.skill.sync_engine import SyncEngine
from coffer.infrastructure.skill.workspace_scan import WorkspaceScan
from coffer.surfaces.http.dependencies import (
    set_agent_config_file_service,
    set_agent_mcp_service,
    set_agent_service,
    set_auto_detect_service,
    set_skill_service,
)
from coffer.surfaces.http.workspace_dependencies import (
    set_agent_mcp_entry_service,
    set_agent_native_memory_service,
    set_agent_plugin_service,
    set_agent_transcript_service,
)

if TYPE_CHECKING:
    from fastapi import FastAPI


def wire_agent_and_skill_kinds(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: object,
    builtin_tools: BuiltinToolRegistry | None = None,
    credential_store: Any = None,
) -> None:
    """Wire the agent + skill kinds (specs agent-registry, 005) into a running app.

    Mirrors the `wire_mcp_kind` pattern. Both kinds are wired in lockstep so
    the cross-kind on_delete hook (deleting an agent cascades into skill
    binding cleanup) can reference both services.
    """
    binding_repo = SkillBindingRepo(sm)  # type: ignore[arg-type]
    master_store = MasterStore()
    master_store.ensure_root()
    sync_engine = SyncEngine()

    # Cross-kind resolvers: the skill service needs the agent's effective
    # skill_dir and its scan locations (FR-022) but cannot import agent-kind
    # code itself (Contract 5) — only this composition root may bridge the two
    # kinds. Delivery itself needs nothing from the agent's config: the whole
    # rule lives on the skill resource (``enabled`` + ``scope``).

    def _agent_skill_dir(r: Resource):  # type: ignore[no-untyped-def]
        cfg = AgentConfig.model_validate(r.config)
        return cfg.resolved_skill_dir()

    def _agent_scan_locations(r: Resource) -> list[pathlib.Path]:
        cfg = AgentConfig.model_validate(r.config)
        return scan_locations(cfg.type, cfg.resolved_config_dir())

    skill_svc = SkillService(
        resource_service=resource_svc,
        audit=audit,
        binding_repo=binding_repo,
        master_store=master_store,
        sync_engine=sync_engine,
        agent_skill_dir_resolver=_agent_skill_dir,
        workspace_scan=WorkspaceScan(),
        agent_scan_locations_resolver=_agent_scan_locations,
    )

    # Agent kind (spec agent-registry-agent-registry). Detection is discovery-only (no
    # auto-registration): AutoDetectService reports installed-but-unregistered
    # agents as candidates the user confirms on the Agents page.
    #
    # `on_config_dir_changed` re-delivers the agent's skills when its config
    # dir moves (skill_svc is constructed above, so the callback is available).
    async def _agent_on_config_dir_changed(agent_name: str) -> None:
        await skill_svc.relink_for_agent(agent_name)

    # A newly registered agent gets everything the delivery predicate grants
    # it right now (FR-012a).
    async def _agent_reconcile_skill_delivery(agent_name: str) -> None:
        await skill_svc.apply_scope_for_agent(agent_name, actor="system")

    # actor="sync": delivery failures surface in the run's errors (retried on
    # every import) instead of growing the audit log unboundedly. Reused below
    # by the sync post-import hook AND by both skill-kind hooks — one
    # reconciliation, several triggers.
    async def _sync_skill_reconcile(agent_name: str) -> list[str]:
        return await skill_svc.apply_scope_for_agent(agent_name, actor="sync")

    # The SKILL kind's two post-write hooks (ADR per-agent-resource-scope). The `agent` kind carries
    # no scope of its own, so only a skill's own edit triggers these — and
    # either half of the predicate (``enabled`` or ``scope``) can gain or lose
    # any agent, so every registered agent's delivery is re-reconciled.
    async def _skill_delivery_changed(ref: ResourceRef) -> None:
        for row in await resource_svc.list(kind="agent"):
            await _sync_skill_reconcile(row.name)

    # Config-file view/edit + one-click Coffer-MCP install (spec agent-registry v2).
    config_file_store = ConfigFileStore()

    agent_svc = AgentService(
        resource_service=resource_svc,
        audit=audit,
        on_config_dir_changed=_agent_on_config_dir_changed,
        reconcile_skill_delivery=_agent_reconcile_skill_delivery,
        config_file_store=config_file_store,
    )
    auto_detect_svc = AutoDetectService(agent_service=agent_svc)
    agent_config_file_svc = AgentConfigFileService(
        agent_service=agent_svc, audit=audit, store=config_file_store
    )
    agent_mcp_svc = AgentMcpService(agent_service=agent_svc, audit=audit, store=config_file_store)

    # MCP entries + plugins in the agent's own config files (agent workspace).
    # The keyring is the same stateless adapter the rest of the app constructs
    # ad hoc (see dependencies.get_keyring) — adoption writes secret values
    # into the OS keychain before registering the mcp_server resource.
    agent_mcp_entry_svc = AgentMcpEntryService(
        agent_service=agent_svc,
        audit=audit,
        store=config_file_store,
        resource_service=resource_svc,
        credentials=credential_store,
    )
    agent_plugin_svc = AgentPluginService(
        agent_service=agent_svc,
        audit=audit,
        store=config_file_store,
        detail_reader=FsPluginDetailReader(),
        cli_runner=ClaudePluginCli(),
    )

    # Read-only listing of the agent's OWN native per-project memory stores
    # (Claude Code's projects/<slug>/memory, Codex's global memories/MEMORY.md).
    # Coffer never writes them — the UI only opens/reveals the directory.
    agent_native_memory_svc = AgentNativeMemoryService(
        agent_service=agent_svc,
        scanner=FileNativeMemoryScanner(),
    )

    # Read-only browse over the agent's own conversation transcripts. The reader
    # is a singleton on purpose: its mtime-aware cache is what keeps listing an
    # agent with thousands of past sessions responsive.
    agent_transcript_svc = AgentTranscriptService(
        reader=FileTranscriptReader(),
        agent_service=agent_svc,
    )

    # The plugin inventory travels in an export bundle. Codex on a new machine
    # cannot know which plugins the old one had — that list exists only where
    # they are installed — so carrying it is a thing no single agent can do for
    # itself. Import stores the list and writes no agent config (see
    # ``plugin_sync_state``).
    providers = getattr(app.state, "sync_state_providers", None)
    if providers is None:
        providers = []
        app.state.sync_state_providers = providers
    providers.append(AgentPluginSyncState(resource_svc, agent_plugin_svc))

    async def _agent_on_delete(ref: ResourceRef) -> None:
        # Awaited by ResourceService.delete BEFORE the agent row is removed,
        # so binding-row lookups inside ``cleanup_bindings_for_agent`` still
        # resolve and every per-agent symlink is torn down. A fire-and-forget
        # implementation would race the row delete and find nothing to clean.
        await skill_svc.cleanup_bindings_for_agent(ref)

    async def _agent_enabled_changed(ref: ResourceRef) -> None:
        # Disabling an agent reclaims its delivered skills; enabling it puts
        # back whatever the skills' own ``enabled`` + ``scope`` grant. Same
        # per-agent reconciliation both ways, so the reclaim is reversible.
        await skill_svc.apply_scope_for_agent(agent_name=ref.name, actor="system")

    agent_kind = make_agent_kind(
        on_delete=_agent_on_delete,
        on_enabled_changed=_agent_enabled_changed,
    )
    skill_kind = make_skill_kind(
        skill_svc.cleanup_bindings_for_skill,
        on_scope_changed=_skill_delivery_changed,
        on_enabled_changed=_skill_delivery_changed,
    )

    app.state.kinds["agent"] = agent_kind
    app.state.kinds["skill"] = skill_kind

    # Import reconciliation (spec vault-export-import): an agent doc only imports where the
    # agent is installed (gate → quarantine otherwise), and imported rows
    # re-apply their on-disk side-effects (skill
    # delivery) after every sync import. start_sync reads these registries.
    gates = getattr(app.state, "sync_import_gates", None)
    if gates is None:
        gates = []
        app.state.sync_import_gates = gates
    gates.append(AgentImportGate())
    hooks = getattr(app.state, "sync_post_import_hooks", None)
    if hooks is None:
        hooks = []
        app.state.sync_post_import_hooks = hooks

    hooks.append(
        AgentSideEffectsReconcile(
            agent_svc,
            config_file_store,
            reconcile_skill_delivery=_sync_skill_reconcile,
        )
    )

    set_agent_service(agent_svc)
    set_auto_detect_service(auto_detect_svc)
    set_agent_config_file_service(agent_config_file_svc)
    set_agent_mcp_service(agent_mcp_svc)
    set_agent_mcp_entry_service(agent_mcp_entry_svc)
    set_agent_native_memory_service(agent_native_memory_svc)
    set_agent_plugin_service(agent_plugin_svc)
    set_agent_transcript_service(agent_transcript_svc)
    set_skill_service(skill_svc)

    if builtin_tools is not None:
        register_skill_builtin_tools(builtin_tools, resources=resource_svc, skill_service=skill_svc)
