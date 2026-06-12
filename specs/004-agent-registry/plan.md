# Implementation Plan: 004 — Agent Registry

**Feature Branch**: `feature/004-agent-registry`
**Date**: 2026-05-22
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

Add the `agent` Resource kind to Coffer: a registry of locally-installed AI agents. v1 supports two types — **Claude Code** (`claude_code`) and **OpenAI Codex** (`codex`) — each covering both the CLI and the app/IDE form of the product, which share one config directory. Discovery is read-only: a scan reports installed-but-unregistered agents as candidates and the user confirms which to add — nothing is auto-registered (including on startup). Users can also add, edit, and remove agents manually.

On top of the registry, the feature adds two capabilities:

1. **Config-file view + edit** — each agent type exposes a curated allowlist of its own config files (Claude Code: `settings.json`, `settings.local.json`, `~/.claude.json`, `CLAUDE.md`; Codex: `config.toml`, `AGENTS.md`). Users read and save them as raw text; saves are validated per format, atomic, and keep a `.bak`. The same atomic-write + `.bak` machinery also backs the Coffer-MCP install/uninstall.
2. **One-click Coffer-MCP install** — write/remove a `coffer` stdio MCP-server entry (pointing at `coffer-mcp-shim`) into the agent's MCP config, with status/idempotency.

The kind exposes an `on_delete` hook that the 005-skill-manager spec wires for skill-binding cleanup. Ships with REST routes, CLI subcommands, and a desktop Agents page.

This spec lays the second consumer of the kind-agnostic Resource framework introduced in spec 001, validating the framework's portability.

## Technical Context

| Dimension                    | Value                                                                                                                                                                                                                                     |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Language / Version**       | Python 3.12+, TypeScript 5.x                                                                                                                                                                                                              |
| **New runtime dependencies** | `tomlkit` (MIT) — format-preserving TOML edit for Codex `config.toml` MCP install.                                                                                                                                                        |
| **Storage**                  | SQLite at `~/.coffer/coffer.db`. No new table — agents are rows in the generic `resources` table (head migration stays at 0004). Config files + MCP-install state are NOT persisted — agent config files on disk are the source of truth. |
| **Testing**                  | 4-tier (unit / integration / contract / e2e); acceptance markers tie to scenarios.                                                                                                                                                        |
| **Target Platforms**         | macOS arm64+x64, Windows x64, Linux x64+arm64                                                                                                                                                                                             |
| **Performance Goals**        | Discovery scan ≤ 200 ms cold. CRUD operations ≤ 50 ms each.                                                                                                                                                                               |
| **Constraints**              | Local-first 127.0.0.1 only; layered architecture preserved; no new credential storage.                                                                                                                                                    |
| **Scale**                    | ≤ 8 registered agents per user.                                                                                                                                                                                                           |

## Constitution Check

| Clause                                | Compliance | Notes                                                                                           |
| ------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------- |
| I. Local-First (NON-NEGOTIABLE)       | ✅         | Pure local registry; no network calls.                                                          |
| II. Spec-as-Truth                     | ✅         | This plan implements `spec.md`; spec committed before code.                                     |
| III. Open-Source-Readiness            | ✅         | One new dep `tomlkit` — MIT, open-source; noted in PR description per governance.               |
| Languages                             | ✅         | Python + TypeScript only.                                                                       |
| Architecture: layered                 | ✅         | New code follows `surfaces → application → domain → infrastructure`. No domain → infra imports. |
| Persistence: SQLite for control plane | ✅         | Registry in SQLite.                                                                             |
| Credentials                           | ✅         | None.                                                                                           |
| Network defaults                      | ✅         | Loopback-only HTTP. Discovery reads the local filesystem only.                                  |

## Project Structure

### Documentation

```
specs/004-agent-registry/
  spec.md
  plan.md              (this file)
  data-model.md
  contracts/api.openapi.yaml
  quickstart.md
```

### New backend modules

```
backend/coffer/domain/agent/
  __init__.py
  types.py             # AgentType StrEnum (claude_code, codex) + default_config_dir + detect markers
  config.py            # AgentConfig (Pydantic)
  config_files.py      # ConfigFileFormat, ConfigFileSpec, config_files_for(), validate_content, spec_for
  mcp_install.py       # apply_install / apply_uninstall / is_installed (pure text transform, tomlkit for TOML)

backend/coffer/application/agent/
  __init__.py
  service.py             # AgentService (register [name optional] / update / remove)
  auto_detect.py         # AutoDetectService.discover() -> list[AgentCandidate] (read-only scan, returns candidates, no suppress list, not run on startup)
  config_file_service.py # AgentConfigFileService (list/read) + ConfigFileStorePort
  mcp_service.py         # AgentMcpService (status/install/uninstall) + ShimResolver
  kind.py                # make_agent_kind(on_delete_hook) -> Kind

backend/coffer/application/fs/
  __init__.py
  browse_service.py      # BrowseService.browse(path) -> immediate subdirs (read-only folder browse)

backend/coffer/infrastructure/agent/
  __init__.py
  config_file_store.py    # ConfigFileStore: read_text / stat; write_text_atomic (+ .bak) for config-file saves and the Coffer-MCP install

backend/coffer/surfaces/http/agent_routes.py         # GET/POST /agents, GET/PATCH/DELETE /agents/{name}, GET /agents/candidates
backend/coffer/surfaces/http/agent_config_routes.py  # GET /agents/{name}/config-files[/{key}], GET/POST/DELETE /agents/{name}/mcp-install
backend/coffer/surfaces/http/fs_routes.py            # GET /fs/browse (read-only folder browser backing the web folder picker)
backend/coffer/surfaces/cli/agent_cmd.py             # coffer agent {add, list, edit, rm, detect, config ls|cat, mcp status|install|uninstall}
```

### New frontend modules

```
frontend/src/pages/AgentsPage.tsx                 # existing list page
frontend/src/components/agents/
  AgentAddForm.tsx / AgentEditForm.tsx / AgentTable.tsx   # existing
  FolderPicker.tsx         # config-dir folder picker (OS-native dialog on desktop; GET /fs/browse folder browser on web)
  AgentConfigPanel.tsx     # per-agent config-file list + editor (file list + editable content view with save, find/replace, format label)
  AgentMcpInstall.tsx      # one-click install/uninstall toggle + status badge
frontend/src/lib/api/agents.ts                     # extend with config-file + mcp-install calls
frontend/src/lib/hooks/useAgents.ts                # add useAgentConfigFiles / useAgentConfigFile / useAgentMcpInstall
frontend/src/i18n/locales/{en,zh}.json             # agents.config.* / agents.mcp.* strings
```

The agent detail page (`/agents/:name`) is a simple **Overview + Config files**
detail page: an Overview tab summarising the agent's registered config and a
Config files tab rendering its known config files in an editable viewer with a
save control and an in-editor find / replace convenience.

## Phasing

### Phase 0 — Research (closed in conversation)

- Alternative: separate `agents` table outside the Resource framework → rejected (loses audit/CRUD/UI uniformity; no future-proofing for agent-as-peer).
- Alternative: bundle agent into 005 spec → rejected after re-evaluation (split for spec-size clarity; one PR delivers both).
- Discovery heuristic: presence of a known marker directory (the type's `default_config_dir`) surfaces that type as a candidate. Future spec may add command-on-PATH detection.

> The base registry (types/config/service/discovery, REST/CLI/desktop CRUD)
> already shipped on this branch. The phases below cover the v2 increment:
> narrow to two types, config-file view + edit, and one-click Coffer-MCP install.

### Phase 1 — Type narrowing + contracts

- Remove `claude_desktop` and `cursor` from `AgentType` (enum, `_DISPLAY`, `_default_config_dir`); rename `codex_cli` → `codex` (display "OpenAI Codex"). Update OpenAPI enum, data-model, quickstart, frontend type dropdown, and all tests referencing the dropped/renamed types.
- Add `tomlkit` to backend runtime deps.

### Phase 2 — Config-file domain + backend (TDD)

1. Domain: `agent/config_files.py` — `ConfigFileFormat`, `ConfigFileSpec`, `config_files_for`, `spec_for`, `validate_content`; the allowlist resolves against the agent's `config_dir`. New errors `ConfigFileNotAllowed`, `ConfigFileFormatInvalid`. New audit event `agent_config_file_written`. Unit tests first.
2. Infrastructure: `config_file_store.py` — read, stat; atomic write + `.bak` for config-file saves and the Coffer-MCP install. Integration tests with a tmp dir.
3. Application: `AgentConfigFileService` (`list/read`) over `ConfigFileStorePort`. Integration tests: list/read/missing/unknown-key.
4. Surfaces: `agent_config_routes.py` (HTTP GET), `coffer agent config ls|cat` (CLI), composition wiring. Contract + CLI tests.

### Phase 3 — Coffer-MCP install (TDD)

1. Domain: `agent/mcp_install.py` — `apply_install`/`apply_uninstall`/`is_installed` for `json` (`~/.claude.json`) and `toml` (`config.toml` via `tomlkit`). Pure-text unit tests for both formats incl. idempotency.
2. Application: `AgentMcpService` (`status/install/uninstall`) + shim-path resolver (`COFFER_MCP_SHIM_PATH` → `shutil.which` → interpreter scripts dir → bundled fallback → `ShimNotFound`). New audit events `agent_mcp_installed`/`agent_mcp_uninstalled`. Integration tests incl. install-twice, uninstall-absent, shim-not-found.
3. Surfaces: HTTP GET/POST/DELETE `…/mcp-install`, `coffer agent mcp status|install|uninstall`. Contract + CLI tests.

### Phase 4 — Frontend

- `AgentConfigPanel` — list config files and open one in an editable content view with a save control, inline validation errors, and an in-editor find / replace (with a format label). `AgentMcpInstall` — status badge + install/uninstall toggle.
- The agent detail page is a simple Overview + Config files detail page.
- `FolderPicker` — pick a custom `config_dir` without typing a path: the OS-native directory dialog in the packaged desktop app, the daemon-backed `GET /fs/browse` folder browser on the web. The add/edit forms make the agent name optional (server derives the per-type default when omitted).
- Hooks via TanStack Query + openapi-fetch; i18n strings in English + Simplified Chinese (`agents.config.*`, `agents.mcp.*`).
- e2e (`e2e/web/specs/shell_agents.spec.ts`): view a config file; install Coffer MCP and observe the status flip.

### Phase 5 — Acceptance + verify

- Every acceptance scenario in `spec.md` has at least one test with `@pytest.mark.acceptance(spec="004-agent-registry", scenario="…")`.
- `make verify` (and `make verify-all` for e2e) green on macOS + Linux.

## Risks / unknowns

- **GUI / venv PATH** — a desktop- or venv-launched daemon does not inherit the shell `PATH` (and its `sys.executable` may be a symlink to the base interpreter), so a bare `coffer-mcp-shim` command may not resolve. Mitigation: resolve to an absolute path at install time (`shutil.which` → the interpreter's `sysconfig` scripts dir → bundled `dist/` fallback), fail loudly if none exist.
- **`~/.claude.json` reserialization** — installing the MCP entry reserializes the whole JSON file (stdlib `json`, `indent=2`), producing a large diff. Acceptable and recoverable via `.bak`; documented.
- **TOML formatting** — Codex `config.toml` edits use `tomlkit` to preserve the user's comments/layout rather than reserializing.

## Workspace amendment (delivered on `feature/agent-workspace`)

The spec.md workspace amendment (FR-025..FR-037) turned the agent detail page
into a full workspace. New modules per layer:

- **Domain**: `agent/mcp_entries.py` (parse/remove/toggle MCP entries + secret-key detection + adopt transport mapping), `agent/plugin_state.py` (Codex/Claude plugin + marketplace parsing, documented-surface-only writes), `agent/scan.py` (per-type skill scan locations for spec 005's unmanaged scan), and `config_files.py` v2 (`ConfigFileKind` directory entries, `instructions` rename, `subagents`/`hooks` entries, `validate_child_relpath`).
- **Application**: `agent/mcp_entry_service.py` (list/toggle/remove/adopt with keychain-routed secrets and registration-first rollback), `agent/plugin_service.py` (list/toggle/Codex-uninstall + cache handling), `config_file_service.py` v2 (directory children read/write/delete, content fingerprints with `ConfigFileStale` → 409, memory-block notice).
- **Surfaces**: `http/agent_workspace_routes.py` (`/agents/{name}/mcp-entries*`, `/agents/{name}/plugins*`), `agent_config_routes.py` v2 (`/config-files/{key}/files/{relpath}` GET/PUT/DELETE + fingerprint fields), `agent_routes.py` (AgentPatch/AgentOut follow-policy fields); CLI `cli/agent_workspace_cmd.py` attached onto `agent_cmd.py`'s typers (`coffer agent mcp entries|remove-entry|toggle-entry|adopt`, `coffer agent plugin list|enable|disable|uninstall`, `coffer agent config files|write|rm`, `coffer agent follow`).
- **Frontend**: agent detail tabs `AgentMcpServersTab` (gateway + direct entries, adopt dialog), `AgentPluginsTab`, and `AgentConfigFilesEditor` v2 (directory children, stale-write guard, memory-block notice).

New audit events: `agent_config_file_deleted`, `agent_mcp_entry_removed`,
`agent_mcp_entry_adopted`, `agent_plugin_toggled`, `agent_plugin_uninstalled`.
No storage changes — every workspace facet is derived from the agent's own
files at read time.

## Open items deferred to future specs

- Agent **type** extension beyond v1's two (Claude Desktop chat app, Cursor, Gemini CLI, GitHub Copilot) — each adds an enum value, scanner, and config-file allowlist.
- Agent **health check** (is the install still present at the registered path) — separate spec.
- Agent **as MCP peer** (expose another agent as a callable tool through Coffer's MCP gateway) — exploratory.
