"""Composition-root helper that wires the agent + skill kinds into the app.

Extracted from `app.py` to keep that file under the size limit. The
cross-kind on_delete hook (deleting an agent cascades into skill binding
cleanup) is bound here because this module is allowed to import both kind
subpackages — they cannot import each other (Contract 5).
"""

from __future__ import annotations

import pathlib
import platform
from typing import TYPE_CHECKING, Any

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.config_file_service import AgentConfigFileService
from coffer.application.agent.hook_service import AgentHookService
from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.mcp_entry_service import AgentMcpEntryService
from coffer.application.agent.mcp_service import AgentMcpService
from coffer.application.agent.native_memory_service import AgentNativeMemoryService
from coffer.application.agent.plugin_service import AgentPluginService
from coffer.application.agent.service import AgentService
from coffer.application.agent.sync_reconcile import AgentImportGate, AgentSideEffectsReconcile
from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.resource_service import ResourceService
from coffer.application.skill.builtin_tools import register_skill_builtin_tools
from coffer.application.skill.kind import make_skill_kind
from coffer.application.skill.service import SkillService
from coffer.application.sync.identity import MachineIdentityService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.scan import scan_locations
from coffer.domain.resource import Resource, ResourceRef
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.agent.hook_resolver import default_hook_resolver
from coffer.infrastructure.agent.native_memory_store import FileNativeMemoryScanner
from coffer.infrastructure.agent.plugin_bundle import FsPluginDetailReader
from coffer.infrastructure.agent.plugin_cli import ClaudePluginCli
from coffer.infrastructure.knowledge.ids import new_ulid
from coffer.infrastructure.skill.master_store import MasterStore
from coffer.infrastructure.skill.persistence import SkillBindingRepo
from coffer.infrastructure.skill.sync_engine import SyncEngine
from coffer.infrastructure.skill.workspace_scan import WorkspaceScan
from coffer.infrastructure.sync.persistence import SqlAlchemyMachineIdentityRepo
from coffer.surfaces.http.dependencies import (
    set_agent_config_file_service,
    set_agent_hook_service,
    set_agent_mcp_service,
    set_agent_native_memory_service,
    set_agent_service,
    set_auto_detect_service,
    set_skill_service,
)
from coffer.surfaces.http.workspace_dependencies import (
    set_agent_mcp_entry_service,
    set_agent_plugin_service,
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
    """Wire the agent + skill kinds (specs 004, 005) into a running app.

    Mirrors the `wire_mcp_kind` pattern. Both kinds are wired in lockstep so
    the cross-kind on_delete hook (deleting an agent cascades into skill
    binding cleanup) can reference both services.
    """
    binding_repo = SkillBindingRepo(sm)  # type: ignore[arg-type]
    master_store = MasterStore()
    master_store.ensure_root()
    sync_engine = SyncEngine()

    # Cross-kind resolvers: skill service needs the agent's effective
    # skill_dir, scan locations (FR-022) and follow policy (FR-025) but
    # cannot import agent-kind code itself (Contract 5) — only this
    # composition root may bridge the two kinds.

    def _agent_skill_dir(r: Resource):  # type: ignore[no-untyped-def]
        cfg = AgentConfig.model_validate(r.config)
        return cfg.resolved_skill_dir()

    def _agent_scan_locations(r: Resource) -> list[pathlib.Path]:
        cfg = AgentConfig.model_validate(r.config)
        return scan_locations(cfg.type, cfg.resolved_config_dir())

    def _agent_skill_policy(r: Resource) -> tuple[bool, list[str]]:
        cfg = AgentConfig.model_validate(r.config)
        return (cfg.follow_all_skills, cfg.skill_exclusions)

    def _agent_skill_delivery(r: Resource) -> str:
        # Plain str (the SkillDeliveryMode value), never the enum, so the skill
        # service stays free of agent-kind imports (Contract 5). Only this
        # composition root may read the agent's capability descriptor.
        return descriptor_for(AgentConfig.model_validate(r.config).type).skill_delivery_mode.value

    # ADR-045 machine axis (Task 11): this daemon's stable sync identity,
    # built exactly as channel_wiring.py does, so skill delivery/reclaim
    # gates on the same machine id as every other scope-aware subsystem.
    identity = MachineIdentityService(
        SqlAlchemyMachineIdentityRepo(sm),  # type: ignore[arg-type]
        audit,
        new_id=new_ulid,
        default_name=lambda: platform.node() or "coffer",
    )

    async def _local_machine_id() -> str:
        return (await identity.get()).machine_id

    skill_svc = SkillService(
        resource_service=resource_svc,
        audit=audit,
        binding_repo=binding_repo,
        master_store=master_store,
        sync_engine=sync_engine,
        agent_skill_dir_resolver=_agent_skill_dir,
        workspace_scan=WorkspaceScan(),
        agent_scan_locations_resolver=_agent_scan_locations,
        agent_skill_policy_resolver=_agent_skill_policy,
        agent_skill_delivery_resolver=_agent_skill_delivery,
        machine_id=_local_machine_id,
    )

    # Agent kind (spec 004-agent-registry). Detection is discovery-only (no
    # auto-registration): AutoDetectService reports installed-but-unregistered
    # agents as candidates the user confirms on the Agents page.
    #
    # `on_config_dir_changed` re-delivers the agent's skills when its config
    # dir moves (skill_svc is constructed above, so the callback is available).
    async def _agent_on_config_dir_changed(agent_name: str) -> None:
        await skill_svc.relink_for_agent(agent_name)

    # `on_skill_policy_changed` reconciles deliveries with the agent's
    # follow-master-library policy (FR-025) after registration or a policy
    # update (flag flip / exclusion edit).
    async def _agent_on_skill_policy_changed(agent_name: str) -> None:
        await skill_svc.apply_follow_for_agent(agent_name, actor="system")

    # Config-file view/edit + one-click Coffer-MCP install (spec 004 v2). The
    # AgentService needs it too (Slice 6 disable_native_memory writes the on-disk
    # transform alongside the persisted field).
    config_file_store = ConfigFileStore()

    agent_svc = AgentService(
        resource_service=resource_svc,
        audit=audit,
        on_config_dir_changed=_agent_on_config_dir_changed,
        on_skill_policy_changed=_agent_on_skill_policy_changed,
        config_file_store=config_file_store,
    )
    auto_detect_svc = AutoDetectService(agent_service=agent_svc)
    agent_config_file_svc = AgentConfigFileService(
        agent_service=agent_svc, audit=audit, store=config_file_store
    )
    agent_mcp_svc = AgentMcpService(agent_service=agent_svc, audit=audit, store=config_file_store)

    # The INSTRUCTIONS_BLOCK payload (ADR-042): the FR-044 rules bundle at
    # global scope. Resolved lazily via the dependencies getter because the
    # memory service is wired after this module runs.
    async def _session_context_payload() -> str:
        from coffer.surfaces.http.dependencies import get_memory_service

        payload: str = await get_memory_service().assemble_session_context(cwd=None)
        return payload

    # Coffer's lifecycle-hook install (Slice 6 SessionStart/SessionEnd).
    # The hook-binary resolver lives in infrastructure; only this composition
    # root (which may import infra) injects it, keeping the application service
    # free of an application↛infrastructure import.
    agent_hook_svc = AgentHookService(
        agent_service=agent_svc,
        audit=audit,
        store=config_file_store,
        hook_resolver=default_hook_resolver,
        session_context=_session_context_payload,
    )

    # Read-only listing of an agent's OWN native per-project memory stores
    # (Claude Code's projects/<slug>/memory). Same agent lookup as above.
    agent_native_memory_svc = AgentNativeMemoryService(
        agent_service=agent_svc, scanner=FileNativeMemoryScanner()
    )

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

    async def _agent_on_delete(ref: ResourceRef) -> None:
        # Awaited by ResourceService.delete BEFORE the agent row is removed,
        # so binding-row lookups inside ``cleanup_bindings_for_agent`` still
        # resolve and every per-agent symlink is torn down. A fire-and-forget
        # implementation would race the row delete and find nothing to clean.
        await skill_svc.cleanup_bindings_for_agent(ref)

    agent_kind = make_agent_kind(on_delete=_agent_on_delete)
    skill_kind = make_skill_kind(skill_svc.cleanup_bindings_for_skill)

    app.state.kinds["agent"] = agent_kind
    app.state.kinds["skill"] = skill_kind

    # Import reconciliation (spec 010): an agent doc only imports where the
    # agent is installed (gate → quarantine otherwise), and imported rows
    # re-apply their on-disk side-effects (native-memory transform, skill
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

    # actor="sync": delivery failures surface in the run's errors (retried on
    # every import) instead of growing the audit log unboundedly.
    async def _sync_skill_reconcile(agent_name: str) -> list[str]:
        return await skill_svc.apply_follow_for_agent(agent_name, actor="sync")

    hooks.append(
        AgentSideEffectsReconcile(
            agent_svc,
            config_file_store,
            on_skill_policy_changed=_sync_skill_reconcile,
        )
    )

    set_agent_service(agent_svc)
    set_auto_detect_service(auto_detect_svc)
    set_agent_config_file_service(agent_config_file_svc)
    set_agent_mcp_service(agent_mcp_svc)
    set_agent_hook_service(agent_hook_svc)
    set_agent_native_memory_service(agent_native_memory_svc)
    set_agent_mcp_entry_service(agent_mcp_entry_svc)
    set_agent_plugin_service(agent_plugin_svc)
    set_skill_service(skill_svc)

    if builtin_tools is not None:
        register_skill_builtin_tools(builtin_tools, resources=resource_svc, skill_service=skill_svc)
