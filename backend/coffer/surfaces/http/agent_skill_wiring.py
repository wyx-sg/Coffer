"""Composition-root helper that wires the agent + skill kinds into the app.

Extracted from `app.py` to keep that file under the size limit. The
cross-kind on_delete hook (deleting an agent cascades into skill binding
cleanup) is bound here because this module is allowed to import both kind
subpackages — they cannot import each other (Contract 5).
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.application.agent.auto_detect import AutoDetectService
from coffer.application.agent.config_file_service import AgentConfigFileService
from coffer.application.agent.hooks_service import AgentHooksService
from coffer.application.agent.kind import make_agent_kind
from coffer.application.agent.mcp_entry_service import AgentMcpEntryService
from coffer.application.agent.mcp_reconcile import McpEntryTarget
from coffer.application.agent.mcp_service import AgentMcpService, default_shim_resolver
from coffer.application.agent.native_memory_service import AgentNativeMemoryService
from coffer.application.agent.plugin_service import AgentPluginService
from coffer.application.agent.plugin_sync_state import AgentPluginSyncState
from coffer.application.agent.service import AgentService
from coffer.application.agent.sync_reconcile import AgentImportGate
from coffer.application.agent.transcript_service import AgentTranscriptService
from coffer.application.audit_service import AuditService
from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.platform_port import PlatformPort
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.resource_service import ResourceService
from coffer.application.skill.builtin_seed import BuiltinSkillSeed
from coffer.application.skill.kind import make_skill_kind
from coffer.application.skill.link_reconcile import TARGET as SKILL_LINK_TARGET
from coffer.application.skill.link_reconcile import SkillLinkTarget
from coffer.application.skill.service import SkillService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.agent.facets import AgentCatalog
from coffer.domain.agent.scan import scan_locations
from coffer.domain.reconcile import PassReport, Trigger
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.agent.native_memory_store import FileNativeMemoryScanner
from coffer.infrastructure.agent.plugin_bundle import FsPluginDetailReader
from coffer.infrastructure.agent.plugin_cli import ClaudePluginCli
from coffer.infrastructure.agent.transcript_reader import FileTranscriptReader
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.infrastructure.skill.master_store import MasterStore
from coffer.infrastructure.skill.persistence import SkillBindingRepo
from coffer.infrastructure.skill.sync_engine import SyncEngine
from coffer.infrastructure.skill.workspace_scan import WorkspaceScan
from coffer.surfaces.http.agent_dependencies import (
    set_agent_config_file_service,
    set_agent_service,
    set_auto_detect_service,
)
from coffer.surfaces.http.cli_wiring import wire_cli_requirements
from coffer.surfaces.http.skill_dependencies import set_skill_service
from coffer.surfaces.http.sync_contributions import SyncContributions
from coffer.surfaces.http.workspace_dependencies import (
    set_agent_hooks_service,
    set_agent_mcp_entry_service,
    set_agent_native_memory_service,
    set_agent_plugin_service,
    set_agent_transcript_service,
)

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentSkillWiring:
    """What the agent + skill kinds hand back to the lifespan: the two services
    later kinds project into / deliver through, and the builtin skill seed."""

    agent_service: AgentService
    skill_service: SkillService
    #: Writes Coffer's own generated skill into the master store. Paired
    #: with a renderer by ``guide_wiring`` — the skill kind cannot reach the
    #: knowledge layer that produces the text, so the pairing is the
    #: composition root's to make.
    builtin_seed: BuiltinSkillSeed
    #: The one reader the Conversations listing uses. Handed back rather than
    #: kept here, because the boot-time warm pass must warm THIS instance — a
    #: second one would fill a second cache and leave the listing's as cold as
    #: it found it.
    transcript_reader: FileTranscriptReader
    #: Installs Coffer's gateway entry — the first part of an agent's Coffer
    #: connection, which ``agent_connection_wiring`` composes once the memory
    #: kind (the other part's owner) is wired too.
    mcp_service: AgentMcpService


def wire_agent_and_skill_kinds(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker[AsyncSession],
    builtin_tools: BuiltinToolRegistry,
    credential_store: EncryptedCredentialStore,
    sync: SyncContributions,
    platform: PlatformPort,
    agent_catalog: AgentCatalog,
    reconciler: Reconciler,
) -> AgentSkillWiring:
    """Wire the agent + skill kinds (specs agent-registry and skill-manager) into a running app.

    Mirrors the `wire_mcp_kind` pattern. Both kinds are wired in lockstep so
    the cross-kind on_delete hook (deleting an agent cascades into skill
    binding cleanup) can reference both services.
    """
    binding_repo = SkillBindingRepo(sm)
    master_store = MasterStore()
    master_store.ensure_root()
    sync_engine = SyncEngine()

    # Cross-kind resolvers: the skill service needs the agent's effective
    # skill_dir and its scan locations (spec skill-manager "List unmanaged
    # skills in an agent's skill locations") but cannot import agent-kind
    # code itself (Contract 5) — only this composition root may bridge the two
    # kinds. Delivery itself needs nothing from the agent's config: the whole
    # rule lives on the skill resource (``enabled`` + ``scope``).

    def _agent_skill_dir(r: Resource):  # type: ignore[no-untyped-def]
        cfg = AgentConfig.model_validate(r.config)
        return cfg.resolved_skill_dir()

    def _agent_scan_locations(r: Resource) -> list[pathlib.Path]:
        cfg = AgentConfig.model_validate(r.config)
        return scan_locations(cfg.type, cfg.resolved_config_dir())

    # Skill delivery is one reconcile target (ADR
    # one-level-triggered-reconciler-compares-parameters): every front door that
    # changes what an agent should hold asks for a pass over it, synchronously,
    # so the link is in place when the user's write returns.
    async def _deliver_skills() -> PassReport:
        return await reconciler.run(targets=[SKILL_LINK_TARGET], trigger=Trigger.CHANGE)

    skill_svc = SkillService(
        resource_service=resource_svc,
        audit=audit,
        binding_repo=binding_repo,
        master_store=master_store,
        sync_engine=sync_engine,
        agent_skill_dir_resolver=_agent_skill_dir,
        workspace_scan=WorkspaceScan(),
        agent_scan_locations_resolver=_agent_scan_locations,
        reconcile_delivery=_deliver_skills,
    )
    reconciler.register(SkillLinkTarget(service=skill_svc))

    # Agent kind (spec agent-registry). Detection is discovery-only (no
    # auto-registration): AutoDetectService reports installed-but-unregistered
    # agents as candidates the user confirms on the Agents page.
    #
    # Registering an agent, moving its config dir, switching it and editing a
    # skill's ``enabled`` / ``scope`` each change what some agent should hold
    # (spec skill-manager "Reconcile deliveries from state on every pass"):
    # each asks for the same pass, which judges every agent at once.
    async def _agent_delivery_changed(_agent_uid: str) -> None:
        await _deliver_skills()

    async def _skill_delivery_changed(_resource: Resource) -> None:
        await _deliver_skills()

    # Config-file view/edit + one-click Coffer-MCP install (spec agent-registry).
    config_file_store = ConfigFileStore()

    agent_svc = AgentService(
        resource_service=resource_svc,
        audit=audit,
        platform=platform,
        on_config_dir_changed=_agent_delivery_changed,
        reconcile_skill_delivery=_agent_delivery_changed,
        config_file_store=config_file_store,
    )
    # Two-signal detection: the agents' dependency probe facets + the dirs.
    auto_detect_svc = AutoDetectService(agent_service=agent_svc, catalog=agent_catalog)
    agent_config_file_svc = AgentConfigFileService(
        agent_service=agent_svc, audit=audit, store=config_file_store
    )
    agent_mcp_svc = AgentMcpService(agent_service=agent_svc, audit=audit, store=config_file_store)
    # Coffer's own MCP entry, judged by its shim path and --agent-uid on every
    # pass (ADR one-level-triggered-reconciler-compares-parameters); this is
    # also what moves an entry an older build left in another agent's file.
    reconciler.register(
        McpEntryTarget(
            agents=agent_svc, store=config_file_store, shim_resolver=default_shim_resolver
        )
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

    # Read-only listing of every hook in the agent's native config, Coffer's
    # own marked with its health (the delivery hook of the projection facet).
    agent_hooks_svc = AgentHooksService(
        agent_service=agent_svc,
        store=config_file_store,
        plugins=agent_plugin_svc,
        audit=audit,
        catalog=agent_catalog,
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
    transcript_reader = FileTranscriptReader()
    agent_transcript_svc = AgentTranscriptService(
        reader=transcript_reader,
        agent_service=agent_svc,
    )

    # The plugin inventory travels in an export bundle. Codex on a new machine
    # cannot know which plugins the old one had — that list exists only where
    # they are installed — so carrying it is a thing no single agent can do for
    # itself. Import stores the list and writes no agent config (see
    # ``plugin_sync_state``).
    sync.state_providers.append(AgentPluginSyncState(resource_svc, agent_plugin_svc))

    async def _agent_on_delete(agent: Resource) -> None:
        # Awaited by ResourceService.delete BEFORE the agent row is removed,
        # so binding-row lookups inside ``cleanup_bindings_for_agent`` still
        # resolve and every per-agent symlink is torn down. A fire-and-forget
        # implementation would race the row delete and find nothing to clean.
        await skill_svc.cleanup_bindings_for_agent(agent)

    agent_kind = make_agent_kind(
        on_delete=_agent_on_delete,
        # Disabling an agent reclaims its delivered skills; enabling it puts
        # back whatever the skills' own ``enabled`` + ``scope`` grant.
        on_enabled_changed=_skill_delivery_changed,
    )
    skill_kind = make_skill_kind(
        skill_svc.cleanup_bindings_for_skill,
        on_scope_changed=_skill_delivery_changed,
        on_enabled_changed=_skill_delivery_changed,
    )

    app.state.kinds["agent"] = agent_kind
    app.state.kinds["skill"] = skill_kind

    # Import reconciliation (spec vault-sync): an agent doc only imports where the
    # agent is installed (gate → quarantine otherwise). Skill delivery after an
    # import is the reconciler's import pass (``reconcile_wiring``).
    sync.import_gates.append(AgentImportGate(platform))

    set_agent_service(agent_svc)
    set_auto_detect_service(auto_detect_svc)
    set_agent_config_file_service(agent_config_file_svc)
    set_agent_mcp_entry_service(agent_mcp_entry_svc)
    set_agent_native_memory_service(agent_native_memory_svc)
    set_agent_plugin_service(agent_plugin_svc)
    set_agent_hooks_service(agent_hooks_svc)
    set_agent_transcript_service(agent_transcript_svc)
    set_skill_service(skill_svc)
    wire_cli_requirements(skill_svc, audit)

    return AgentSkillWiring(
        agent_service=agent_svc,
        skill_service=skill_svc,
        builtin_seed=BuiltinSkillSeed(skill_service=skill_svc),
        transcript_reader=transcript_reader,
        mcp_service=agent_mcp_svc,
    )
