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
from coffer.application.agent.instructions_service import AgentInstructionsService
from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.mcp_entry_service import AgentMcpEntryService
from coffer.application.agent.mcp_service import AgentMcpService
from coffer.application.agent.plugin_service import AgentPluginService
from coffer.application.agent.service import AgentService
from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.resource_service import ResourceService
from coffer.application.skill.builtin_tools import register_skill_builtin_tools
from coffer.application.skill.kind import make_skill_kind
from coffer.application.skill.service import SkillService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.descriptor import descriptor_for
from coffer.domain.agent.scan import scan_locations
from coffer.domain.agent.skill_delivery import SkillDeliveryMode
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.skill.external_dir import ExternalDirRegistration
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.agent.plugin_bundle import FsPluginDetailReader
from coffer.infrastructure.agent.plugin_cli import ClaudePluginCli
from coffer.infrastructure.skill.external_dir_registrar import YamlExternalDirRegistrar
from coffer.infrastructure.skill.master_store import MasterStore
from coffer.infrastructure.skill.persistence import SkillBindingRepo
from coffer.infrastructure.skill.sync_engine import SyncEngine
from coffer.infrastructure.skill.workspace_scan import WorkspaceScan
from coffer.surfaces.http.agent_instructions_routes import set_agent_instructions_service
from coffer.surfaces.http.dependencies import (
    set_agent_config_file_service,
    set_agent_mcp_service,
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
    # EXTERNAL_DIR agents (Hermes) don't receive skills in their own config dir;
    # Coffer folder-delivers into an agent-named directory it owns and registers
    # that dir in the agent's config. Keep it beside the master store.
    external_skill_base = master_store.root.parent / "agent-skills"

    def _agent_skill_dir(r: Resource):  # type: ignore[no-untyped-def]
        cfg = AgentConfig.model_validate(r.config)
        if descriptor_for(cfg.type).skill_delivery_mode is SkillDeliveryMode.EXTERNAL_DIR:
            return external_skill_base / r.name
        return cfg.resolved_skill_dir()

    def _agent_external_registration(r: Resource) -> ExternalDirRegistration | None:
        cfg = AgentConfig.model_validate(r.config)
        desc = descriptor_for(cfg.type)
        if desc.skill_delivery_mode is not SkillDeliveryMode.EXTERNAL_DIR:
            return None
        # Hermes scans dirs listed under ``skills.external_dirs`` in its
        # ``config.yaml``. Resolve the config file from the manifest so a custom
        # config dir is honoured; fall back to the conventional name.
        config_dir = cfg.resolved_config_dir()
        config_file = next(
            (s.path for s in desc.config_files(config_dir) if s.key == "config"),
            config_dir / "config.yaml",
        )
        return ExternalDirRegistration(
            config_path=config_file,
            external_dir=external_skill_base / r.name,
            container_keys=("skills", "external_dirs"),
        )

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
        external_dir_registrar=YamlExternalDirRegistrar(),
        agent_external_registration_resolver=_agent_external_registration,
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

    agent_svc = AgentService(
        resource_service=resource_svc,
        audit=audit,
        on_config_dir_changed=_agent_on_config_dir_changed,
        on_skill_policy_changed=_agent_on_skill_policy_changed,
    )
    auto_detect_svc = AutoDetectService(agent_service=agent_svc)

    # Config-file view/edit + one-click Coffer-MCP install (spec 004 v2).
    config_file_store = ConfigFileStore()
    agent_config_file_svc = AgentConfigFileService(
        agent_service=agent_svc, audit=audit, store=config_file_store
    )
    agent_mcp_svc = AgentMcpService(agent_service=agent_svc, audit=audit, store=config_file_store)
    agent_instructions_svc = AgentInstructionsService(
        agent_service=agent_svc, audit=audit, store=config_file_store
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

    set_agent_service(agent_svc)
    set_auto_detect_service(auto_detect_svc)
    set_agent_config_file_service(agent_config_file_svc)
    set_agent_mcp_service(agent_mcp_svc)
    set_agent_instructions_service(agent_instructions_svc)
    set_agent_mcp_entry_service(agent_mcp_entry_svc)
    set_agent_plugin_service(agent_plugin_svc)
    set_skill_service(skill_svc)

    if builtin_tools is not None:
        register_skill_builtin_tools(builtin_tools, resources=resource_svc, skill_service=skill_svc)
