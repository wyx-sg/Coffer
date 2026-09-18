# Implementation Plan: Agent Registry

**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

The `agent` Resource kind is a registry of locally-installed AI agents. Two types are wired in the capability manifest — **Claude Code** (`claude_code`) and **OpenAI Codex** (`codex`) — each covering both the CLI and the app/IDE form of the product, which share one config directory. Discovery is read-only: a scan reports installed-but-unregistered agents as candidates and the user confirms which to add — nothing is auto-registered (including on startup). Users can also add, edit, and remove agents manually.

On top of the registry the feature carries the agent's whole workspace:

1. **Config files** — each agent type exposes a curated allowlist of its own config files (Claude Code: `settings.json`, `settings.local.json`, `~/.claude.json`, `CLAUDE.md`, the `agents/` directory entry; Codex: `config.toml`, `AGENTS.md`, `hooks.json`). Every surface — the in-app editor, REST and CLI — can read and write them: a save validates per format, writes atomically, and keeps a `.bak`. The same atomic-write + `.bak` machinery backs the Coffer-MCP install/uninstall.
2. **One-click Coffer-MCP install** — write/remove a `coffer` stdio MCP-server entry (pointing at `coffer-mcp-shim`, carrying `--agent-uid <uid>`) in the agent's MCP config, with status/idempotency.
3. **The agent's own MCP entries** — list what the agent itself has configured, remove one, or adopt it into Coffer's gateway with its secrets routed into the vault.
4. **Plugins** — list them with their marketplace and enabled state, toggle one, uninstall one (by config edit for Codex, by the agent's own CLI for Claude Code).
5. **Read-only views of the agent's own stores** — its native memory and its session transcripts.
6. **The agent's model binding and catalogue** — the `model` / `fast_model` / `wire_api` fields the agent carries, and the read-only catalogue of what the installed agent can be put on, re-derived from the agent on every request and never written down in Coffer.

The type axis is cut into two child specs. Everything above is the contract both
types share; where a type differs — its config directory, its allowlist, its MCP
entry shape, its plugin inventory and uninstall strategy, its catalogue sources
and effort source, its native-memory layout, its transcript location — that is
`agent-registry/claude-code` or `agent-registry/codex`. The facet axis stays in
the parent: cutting it too would produce a child per type per facet, each too
thin to own anything.

The kind exposes an `on_delete` hook that spec skill-manager wires for skill-binding cleanup. Every facet ships through REST routes, CLI subcommands, and the web Agents page.

This spec is the second consumer of the kind-agnostic Resource framework introduced in spec resource-framework, validating the framework's portability.

## Technical Context

| Dimension                    | Value                                                                                                                                                                                                                                     |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**       | Python 3.12+, TypeScript 5.x                                                                                                                                                                                                              |
| **New runtime dependencies** | `tomlkit` (MIT) — format-preserving TOML edit for Codex `config.toml`.                                                                                                                                                                    |
| **Storage**                  | SQLite at `~/.coffer/coffer.db`. No table of its own — agents are rows in the generic `resources` table, so this spec introduces no Alembic revision. Config files, MCP-install state, plugins, native memory and transcripts are NOT persisted — the agent's own files on disk are the source of truth. |
| **Testing**                  | 4-tier (unit / integration / contract / e2e); acceptance markers tie to scenarios.                                                                                                                                                        |
| **Target Platforms**         | macOS arm64 (the one platform the release builds; see spec daemon FR-025). The code paths are POSIX + Windows aware, but only macOS is exercised.                                                                                     |
| **Performance Goals**        | Discovery scan ≤ 200 ms cold. CRUD operations ≤ 50 ms each. The transcript listing pages rather than loading, and warms its derived sidecar off the request path.                                                                          |
| **Constraints**              | Local-first 127.0.0.1 only; layered architecture preserved; no new credential storage of its own (adoption routes secrets into the existing credential store).                                                                             |
| **Scale**                    | ≤ 8 registered agents per user; an agent's transcript directory runs to thousands of files.                                                                                                                                                |

## Constitution Check

| Clause                                | Compliance | Notes                                                                                           |
| ------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------- |
| I. Local-First (NON-NEGOTIABLE)       | ✅         | Pure local registry; no network calls.                                                          |
| II. Spec-as-Truth                     | ✅         | This plan implements `spec.md`; spec committed before code.                                     |
| III. Open-Source-Readiness            | ✅         | One new dep `tomlkit` — MIT, open-source.                                                       |
| Languages                             | ✅         | Python + TypeScript only.                                                                       |
| Architecture: layered                 | ✅         | `surfaces → application → domain`; infrastructure is reached through application-layer ports.   |
| Persistence: SQLite for control plane | ✅         | Registry in SQLite; the agent's own files are never copied into it.                             |
| Credentials                           | ✅         | Agent config carries none. Adoption stores mapped secrets through the credential store and keeps only refs. |
| Network defaults                      | ✅         | Loopback-only HTTP. Discovery reads the local filesystem only.                                  |

## Project Structure

### Documentation

```
specs/agent-registry/
  spec.md
  plan.md              (this file)
  data-model.md
  contracts/api.openapi.yaml
  quickstart.md
  claude-code/spec.md  (child spec — the `claude_code` type's mechanics)
  codex/spec.md        (child spec — the `codex` type's mechanics)
```

Each child carries `spec.md` and nothing else: a child spec is the prose
reading of one `AGENT_DESCRIPTORS` record, so it has no endpoints, no entities
and no plan of its own — the routes, the entities and this plan are the
parent's, and the child says only how one type realises them.

### Backend modules

```
backend/coffer/domain/agent/
  types.py             # AgentType StrEnum (claude_code, codex)
  descriptor.py        # AGENT_DESCRIPTORS — the capability manifest, one record per type
  config.py            # AgentConfig (Pydantic, extra="forbid")
  config_files.py      # ConfigFileFormat/Kind, ConfigFileSpec, config_files_for, spec_for,
                       #   validate_content, validate_child_relpath
  allowlists.py        # the per-type curated config-file tuples
  mcp_injection.py     # McpInjectionSpec / McpEntryStyle — the orthogonal injection axes
  mcp_install.py       # apply_install / apply_uninstall / is_installed (pure text transforms)
  mcp_entries.py       # McpEntry parsing, secret-key detection, removal, adopt transport mapping
  plugin_capability.py # PluginCapability / PluginModel / UninstallStrategy
  plugin_state.py      # Codex/Claude plugin + marketplace parsing and enabled-state transforms
  plugin_bundle.py     # plugin manifest shapes
  native_memory.py     # the per-type native-memory layouts (FR-039)
  codex_memory.py      # the Codex task-group document parser
  transcripts.py       # transcript session summaries + turn shaping (FR-040/FR-042)
  scan.py              # per-type skill-scan locations, for spec skill-manager's unmanaged scan
  model_catalogue.py   # the shape of a discovered model catalogue

backend/coffer/application/agent/
  service.py              # AgentService (register [name optional] / update / remove)
  auto_detect.py          # AutoDetectService.discover() -> candidates (read-only, never on startup)
  config_file_service.py  # AgentConfigFileService (list/read/write, children) + ConfigFileStorePort
  mcp_service.py          # AgentMcpService (status/install/uninstall) + shim resolution
  mcp_entry_service.py    # AgentMcpEntryService (list / remove_entry / adopt)
  plugin_service.py       # AgentPluginService (list / set_enabled / uninstall)
  plugin_uninstall.py     # the two uninstall strategies
  plugin_views.py         # PluginsOut/PluginView + the PluginCliRunner / PluginDetailReader ports
  native_memory_service.py # the read-only store scan + store-file read (FR-039/FR-043)
  transcript_service.py   # the session listing + single-session read (FR-040/FR-042)
  transcript_warm_worker.py # background warm of the derived summary sidecar
  model_catalogue.py      # reads each agent's own model catalogue
  sync_reconcile.py       # re-reconcile delivery after a sync import
  kind.py                 # make_agent_kind(...) -> Kind

backend/coffer/infrastructure/agent/
  config_file_store.py   # read_text / stat / list_dir / write_text_atomic (+ .bak) / delete_with_backup
  plugin_cli.py          # PluginCliRunner impl — the agent's own uninstall command
  plugin_bundle.py       # best-effort manifest detail from the plugin's install path
  native_memory_store.py / native_memory_files.py / codex_memory_store.py
  transcript_reader.py / transcript_parsers.py / transcript_messages.py /
    transcript_records.py / transcript_cache.py   # the disposable derived sidecar
  model_discovery.py / claude_binary_models.py / claude_effort.py / codex_rpc_models.py

backend/coffer/surfaces/http/
  agent_routes.py                # GET/POST /agents, GET/PATCH/DELETE /agents/{uid}, GET /agents/candidates
  agent_config_routes.py         # /agents/{uid}/config-files[/{key}[/files/{relpath}]], /mcp-install
  agent_workspace_routes.py      # /agents/{uid}/mcp-entries*, /agents/{uid}/plugins*
  agent_native_memory_routes.py  # /agents/{uid}/native-memory[/files[/content]]
  agent_transcript_routes.py     # /agents/{uid}/transcripts[/session]
  agent_unmanaged_skill_routes.py # /agents/{uid}/unmanaged-skills* (spec skill-manager's facet)
  agent_skill_wiring.py          # the agent + skill kind wiring (called from kind_wiring.py)

backend/coffer/surfaces/cli/
  agent_cmd.py              # coffer agent {list, add, show, edit, rm, detect} + the config/mcp typers
  agent_workspace_cmd.py    # attaches config {files,write,rm}, mcp {entries,remove-entry,adopt}, plugin *
  agent_native_memory_cmd.py # attaches native-memory, native-memory-files
  agent_transcript_cmd.py   # attaches transcripts, transcript
```

The CLI surface as a whole: `coffer agent list|add|show|edit|rm|detect`, `coffer agent config ls|cat|edit|files|write|rm`, `coffer agent mcp status|install|uninstall|entries|remove-entry|adopt`, `coffer agent plugin list|enable|disable|uninstall`, `coffer agent native-memory|native-memory-files`, `coffer agent transcripts|transcript`.

### Frontend modules

```
frontend/src/pages/AgentsPage.tsx / AgentDetailPage.tsx
frontend/src/components/agents/
  AgentTable.tsx / AgentAddDialog.tsx / AgentManualAddForm.tsx / AgentEditForm.tsx /
    AgentDeleteDialog.tsx / AgentBulkActions.tsx / AgentWelcomePanel.tsx
  FolderPicker.tsx / FolderPickerField.tsx     # native dialog, /fs/browse fallback
  AgentOverviewTab.tsx
  AgentSkillsTab.tsx / AgentUnmanagedSkills.tsx
  AgentMcpServersTab.tsx / AgentGatewayMcpSection.tsx / AgentMcpControls.tsx /
    AgentAdoptMcpDialog.tsx
  AgentPluginsTab.tsx / AgentPluginDetail.tsx
  AgentMemoryTab.tsx / AgentMemoryStoreTree.tsx / AgentMemoryStoreFileViewer.tsx /
    AgentMemoryDelivery.tsx
  AgentConversationsTab.tsx / AgentTranscriptView.tsx / AgentTranscriptOutline.tsx
  AgentConfigFilesEditor.tsx / ConfigFileTree.tsx / ConfigEditorPane.tsx
frontend/src/lib/api/{agents,agents-workspace,agentNativeMemory,agentTranscripts,agentModels}.ts
frontend/src/lib/hooks/{useAgents,useAgentConfig,useConfigEditorState,useAgentNativeMemory,useAgentTranscripts,useAgentModels}.ts
frontend/src/i18n/locales/{en,zh}.json             # agents.* strings
```

The agent detail page (`/agents/:name`) has **seven** tabs — Overview, Skills,
MCP servers, Plugins, Memory, Conversations, Config files (FR-044). Of those,
only Plugins acts on the agent; Memory and Conversations are read-only views of
the agent's own stores; Config files is a two-pane editor whose right pane is
editable behind an explicit Edit, with an unsaved draft guarded three ways
(switching file, switching tab, leaving the page) and open-in-external-editor /
reveal beside it.

## Decisions

- **Agents are a Resource kind, not their own table.** A separate `agents` table was rejected: it would lose the framework's audit, CRUD and UI uniformity, and there would be nothing to hang a future agent-as-peer facet on.
- **Per-type behaviour lives in data, not in branches.** `AGENT_DESCRIPTORS` is the one per-type table; there is no `_DISPLAY` map and no per-type `if`. Adding a product is one enum value plus one descriptor record.
- **Two types only.** The registry briefly carried `opencode`, `hermes`, `cursor` and `openclaw`; they were removed in the narrowing to `claude_code` + `codex` because none was installed on the maintainer's machine and so no facet could be regression-tested locally. The separate `claude_desktop` chat app was never in scope.
- **Discovery is presence of a marker.** The type's `default_config_dir` existing surfaces that type as a candidate; command-on-PATH detection is left to a future spec.
- **Coffer writes only documented surfaces.** An agent's internal state files (`installed_plugins.json`, `auth.json`, session files) are read, never written; where a write must reach internal state, Coffer delegates to the agent's own CLI.
- **Every write is addressable by allowlist key, never by path**, and is atomic with a `.bak`.
- **The `/fs/*` routes are consumed, not owned.** The folder picker, the folder
  browser, open, reveal and the installed-editor enumeration are spec daemon's:
  they are the loopback process's business, and three different specs' surfaces
  call them. This spec calls them and validates what they return.

## Risks / unknowns

- **GUI / venv PATH** — a GUI- or venv-launched daemon does not inherit the shell `PATH` (and its `sys.executable` may be a symlink to the base interpreter), so a bare `coffer-mcp-shim` command may not resolve. Mitigated by resolving to an absolute path at install time (`COFFER_MCP_SHIM_PATH` → `shutil.which` → the interpreter's `sysconfig` scripts dir → bundled fallback), failing loudly when none exists.
- **`~/.claude.json` reserialization** — installing the MCP entry reserializes the whole JSON file (stdlib `json`, `indent=2`), producing a large diff. Acceptable and recoverable via `.bak`; documented.
- **TOML formatting** — Codex `config.toml` edits use `tomlkit` to preserve the user's comments/layout rather than reserializing.
- **Transcript volume** — an agent accumulates thousands of session files; the listing pages, caches per file mtime + size, and keeps its sidecar outside the vault so losing it costs time and nothing else.

## Open items deferred to future specs

- Agent **type** extension beyond the two supported (Claude Desktop chat app, Gemini CLI, GitHub Copilot) — each adds an enum value, a descriptor record, and a config-file allowlist.
- Agent **health check** (is the install still present at the registered path) — separate spec.
- Agent **as MCP peer** (expose another agent as a callable tool through Coffer's MCP gateway) — exploratory.
