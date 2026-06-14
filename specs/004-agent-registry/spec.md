# Feature Specification: Agent Registry

**Feature Branch**: `feature/004-agent-registry`
**Created**: 2026-05-22
**Status**: Accepted
**Input**: User description: "Manage which locally-installed AI agents Coffer knows about, so later features (skills, memory, knowledge bases) can deliver assets to them. Each agent is a Resource of kind `agent` in the kind-agnostic Resource framework introduced by spec 001-mcp-gateway. v1 supports two agent types: Claude Code and OpenAI Codex — each covering both its CLI and its desktop/IDE form, which share one on-disk config. Beyond registering agents, the user can view and edit each agent's known config files and install Coffer's own MCP server into an agent with one click."

> **Note on agent types.** Supported products: **Claude Code** (`claude_code`, `~/.claude/`), **OpenAI Codex** (`codex`, `~/.codex/`), **Cursor** (`cursor`, `~/.cursor/`), **OpenCode** (`opencode`, `~/.config/opencode/`), **OpenClaw** (`openclaw`, `~/.openclaw/`), and **Hermes** (`hermes`, `~/.hermes/`). Each spans its CLI _and_ its app/IDE form because they read one shared config directory. Per-type behaviour lives in the capability manifest (`AGENT_DESCRIPTORS`) — adding a product is one enum value + one descriptor record (config-file allowlist, MCP injection shape, etc.). The separate **Claude Desktop** chat app (its own `~/Library/Application Support/Claude/` config) is out of scope.

> **Workspace amendment.** Stories 9–12 extend the registry into the agent's real on-disk workspace: the MCP servers actually configured in the agent's own files, the agent's installed plugins, and directory-type config entries. The guiding principle is **ingest → hub → deliver**: anything shareable found in an agent's workspace can be adopted into Coffer's hub (the MCP gateway, the master skill store of spec 005) and delivered back to any agent, instead of living as per-agent one-off config. All writes go through each agent's documented configuration paths only; internal state files are read, never written.

> **Note on the built-in agent ([ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md)).** This registry holds only **managed** agents — locally-installed external coding agents (Claude Code, Codex, …) that Coffer delivers assets to. The former `builtin` "Coffer Assistant" is **not** a registered agent here: [ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md) retires it as a chat persona and recasts its local model as an internal Coffer capability reached only through `coffer__*` MCP tools. (The separate chat agent-provider registry of spec 008 likewise drops the `builtin` provider and lists managed agents only.)

## User Scenarios & Testing

### User Story 1 — Discover installed agents and choose which to add (Priority: P1)

When a developer opens the Agents page (or runs `coffer agent detect`), Coffer scans well-known install paths for each supported agent type and presents the ones it finds that aren't registered yet as **candidates**. The developer reviews them and confirms which to add — Coffer never registers an agent silently.

**Why this priority**: Near-zero-config first impression without surprises. Detection finds agents so the user doesn't have to learn type identifiers and default paths, but the user stays in control of what enters their registry.

**Independent Test**: On a machine with `~/.claude/` and `~/.codex/` present, open the Agents page, run detection, observe both Claude Code and Codex offered as candidates; confirm them and observe both registered.

**Covering scenarios**:

- discover installed agents as candidates
- skip already-registered types on subsequent scan
- re-surface removed agents on subsequent scan

---

### User Story 2 — Manually register an agent with a custom path (Priority: P1)

Some users install agents in non-default locations or have multiple installs (work vs personal). They need to add an agent by type, optionally overriding the config directory. The name is optional — when omitted Coffer derives a stable per-type default. When choosing a custom path, the desktop app offers a folder picker (the OS-native dialog in the packaged app; a daemon-backed folder browser on the web) so the user picks a real directory instead of typing it.

**Why this priority**: Discovery covers the common case; manual register covers the long tail. Without it the registry is incomplete.

**Independent Test**: From the command line, register a `codex` agent named `codex-work` with `--config-dir /custom/path`; list agents; observe the manually-registered entry. From the desktop form, add an agent with no name and observe it registered under the per-type default name.

**Covering scenarios**:

- register an agent with a custom config dir
- register an agent without an explicit name
- reject registration when the config dir is missing or not writable
- reject duplicate agent names
- browse local folders to choose a config dir

---

### User Story 3 — Edit or remove an agent (Priority: P1)

The user's installed agents change over time. They need to update the config_dir path or description, or fully delete the agent. (Agents have no enable/disable concept — a registered agent is simply present.)

**Why this priority**: An immutable registry would be useless within a week.

**Independent Test**: Register an agent, update its config_dir, then remove it; verify each state is persisted and audited.

**Covering scenarios**:

- update config_dir for an existing agent
- remove an agent and observe audit entry

---

### User Story 4 — Manage agents through the desktop app (Priority: P2)

The user opens Coffer's desktop app, sees an "Agents" page listing every registered agent with type, name, and config_dir, and can add or edit from a form.

**Why this priority**: Non-CLI users need a visual surface to make sense of the registry.

**Independent Test**: Open desktop app → Agents → add Codex with default path → observe in list → click into it → change config_dir → save → list updates.

**Covering scenarios**:

- agents page lists all registered agents
- add an agent through the desktop form
- edit an agent through the desktop form
- remove an agent through the desktop confirmation

---

### User Story 5 — Same operations from the command line (Priority: P2)

The user scripts registry setup (dotfiles, CI machines). All operations available in the UI are available as `coffer agent ...` subcommands with `--json` output.

**Why this priority**: Coffer's audience is developers. CLI parity is table stakes.

**Independent Test**: A bash script registers two agents, lists them in JSON, edits one, removes one — all without touching the GUI.

**Covering scenarios**:

- command line covers every visual operation
- machine-readable JSON output

---

### User Story 6 — Audit registry changes (Priority: P3)

Every add / edit / remove / auto-detection is recorded with timestamp and actor, queryable from CLI and UI.

**Why this priority**: Builds trust and helps debug "wait, when did this change?" Not blocking core registry operation.

**Independent Test**: Make several changes; view audit log; observe one row per change with actor and event type.

**Covering scenarios**:

- audit agent lifecycle events

---

### User Story 7 — View and edit an agent's config files (Priority: P2)

After an agent is registered, the user wants to see and adjust that agent's own configuration files (e.g. Claude Code's `settings.json`, Codex's `config.toml`) directly inside Coffer, without leaving the app to hunt for dotfiles. Coffer shows the agent type's curated set of known config files, lets the user open one to read its current content, edit it in place, and save it back. On save, Coffer validates the content against the file's format (malformed JSON/TOML is rejected and the file is left unchanged), writes it atomically, and keeps a `.bak` of the prior version so a bad edit is always recoverable. A dependency-free in-editor find / replace tool is offered as a convenience while editing.

**Why this priority**: Locating agent config by hand means remembering where each file lives and what format it uses. Surfacing the curated set in one place — viewable and editable at a glance, with a safety net for bad edits — is the first feature that makes the registry useful beyond bookkeeping.

**Independent Test**: Register a `claude_code` agent; list its config files; open `settings.json`; edit and save it; observe the new content reads back and a `.bak` was kept; open a not-yet-created file (e.g. `CLAUDE.md`) and observe it reads as empty without being created.

**Covering scenarios**:

- list an agent's curated config files with existence + size metadata
- read the content of an existing config file
- read a not-yet-created config file as empty
- reject reading a key outside the agent type's allowlist
- save a config file with valid content
- reject malformed config-file content

---

### User Story 8 — Install Coffer's MCP into an agent in one click (Priority: P2)

The user wants their agent (Claude Code, Codex) to actually use Coffer. From the agent's management view they click "Install Coffer MCP", and Coffer writes its own MCP-server entry into that agent's MCP config — a `coffer` stdio entry pointing at the `coffer-mcp-shim` binary. A status indicator shows whether Coffer is currently installed, and the user can uninstall to remove the entry.

**Why this priority**: Wiring an MCP server into a client by hand (editing `~/.claude.json` or `~/.codex/config.toml` correctly) is exactly the friction Coffer exists to remove. One click closes the loop between "Coffer knows your agent" and "your agent can use Coffer".

**Independent Test**: Register a `claude_code` agent with Coffer not yet installed; check status (not installed); install; observe a `coffer` entry written to `~/.claude.json` `mcpServers` with an absolute `command` path to the shim; check status (installed); install again (no duplicate); uninstall; observe the entry removed.

**Covering scenarios**:

- report Coffer-MCP install status for an agent
- install Coffer's MCP entry into a Claude Code agent (`~/.claude.json`)
- install Coffer's MCP entry into a Codex agent (`~/.codex/config.toml`)
- install is idempotent — re-installing does not duplicate the entry
- uninstall removes the Coffer entry
- install/uninstall write atomically with a `.bak` backup and emit an audit entry

---

### User Story 9 — See and manage the agent's real MCP servers (Priority: P2)

The agent's MCP servers tab today can only say whether Coffer's own shim is installed. The user wants to see what their agent **actually** has configured: every MCP server entry in the agent's own config files — for Claude Code from both `~/.claude.json` `mcpServers` and `settings.json` `mcpServers`, for Codex from `config.toml` `[mcp_servers.*]`. Each entry shows its transport (stdio command or HTTP URL), which file it came from, and (Codex only — the format defines a per-entry flag) its enabled state. The user can remove an entry or toggle a Codex entry's flag; Coffer's own `coffer` entry is rendered specially and managed by the existing install/uninstall actions.

**Why this priority**: The current tab shows the same Coffer-global list for every agent, which is misleading. Showing the agent's real configuration is the prerequisite for every other MCP-management action.

**Independent Test**: Register a `codex` agent whose `config.toml` carries several `[mcp_servers.*]` entries; open the MCP tab; observe exactly those entries with transports and enabled flags; remove one and observe it gone from the file (with a `.bak` kept); toggle another and observe its `enabled` flag flipped in place.

**Covering scenarios**:

- list an agent's real MCP entries
- remove a direct MCP entry
- toggle a Codex MCP entry's enabled flag
- reject toggling a Claude Code MCP entry
- degrade to read-only when MCP config is unparseable

---

### User Story 10 — Adopt a direct MCP server into Coffer (Priority: P2)

A direct MCP entry in one agent benefits that agent alone. The user clicks "Adopt into Coffer" on a direct entry: Coffer registers it as an `mcp_server` resource (so it is served to **every** agent through the gateway) and removes the now-redundant direct entry from the agent's config. If the entry's environment carries secret-looking values, Coffer routes them into the OS keychain and stores references only. If an equivalent resource already exists, Coffer offers to just remove the duplicate direct entry.

**Why this priority**: This is the ingest half of Coffer's hub-and-spoke model — the single action that turns scattered per-agent config into shared, gateway-served resources.

**Independent Test**: With a `codex` agent carrying a direct stdio entry, adopt it; observe a new `mcp_server` resource registered, the direct entry removed from `config.toml`, and the gateway serving the upstream's tools to all agents.

**Covering scenarios**:

- adopt a direct MCP entry into Coffer
- reject adoption on resource name conflict
- require keychain mapping for secret-like env values
- adoption failure leaves agent config untouched

---

### User Story 11 — Manage the agent's plugins (Priority: P2)

Agents with a file-backed plugin system expose it through the agent's Plugins tab: every installed plugin grouped by marketplace, with its enabled state and whether its on-disk cache is present. The plugin facet is generalised through the capability manifest — each agent record carries a `PluginCapability` (a plugin-model discriminator, the write-surface allowlist key, and `can_toggle`/`can_uninstall` flags), so the service dispatches on data rather than per-agent branches. Each capability maps to the agent's documented configuration surface; internal state files are read, never written. Installing new plugins and managing marketplaces stay with the agent's own tooling.

Per-agent plugin support:

| Agent       | Plugin model                                                                                                      | Write surface    | List  | Toggle | Uninstall             |
| ----------- | ----------------------------------------------------------------------------------------------------------------- | ---------------- | ----- | ------ | --------------------- |
| Claude Code | `enabledPlugins` map in `settings.json` (internal `installed_plugins.json` / `known_marketplaces.json` read-only) | `settings.json`  | yes   | yes    | no (agent tooling)    |
| Codex       | `[plugins."<name>@<marketplace>"]` tables + cache dir                                                             | `config.toml`    | yes   | yes    | yes (entry + cache)   |
| Cursor      | VSIX list from `extensions/extensions.json` (enable/disable in SQLite)                                            | none (read-only) | yes   | no     | no                    |
| OpenCode    | the `plugin` array in `opencode.json`                                                                             | `opencode.json`  | yes   | yes    | yes (drop from array) |
| OpenClaw    | the `plugins{}` block in `openclaw.json`                                                                          | `openclaw.json`  | yes   | yes    | yes                   |
| Hermes      | none — MCP is the plugin mechanism                                                                                | none             | empty | no     | no                    |

**Why this priority**: Plugins are real, persistent agent configuration that today is invisible to Coffer. Visibility plus the cheap, safe writes (toggle, uninstall where supported) cover the recurring needs; installation is left where it already works.

**Independent Test**: Register a `codex` agent with plugins configured; open the Plugins tab; observe the plugins grouped by marketplace with enabled state; disable one and observe `enabled = false` written to `config.toml`; uninstall one and observe its config entry and cache directory gone. For an `opencode` agent, toggle a plugin and observe it removed from the `plugin` array; for a `cursor` agent, list extensions and observe toggle/uninstall rejected.

**Covering scenarios**:

- list an agent's plugins with enabled state
- toggle a plugin's enabled state
- uninstall a Codex plugin
- reject uninstalling a Claude Code plugin
- flag a plugin whose cache is missing
- list, toggle, and uninstall OpenCode and OpenClaw plugins via their documented config surfaces
- list Cursor extensions read-only, rejecting toggle and uninstall
- report an empty plugin listing for Hermes and reject toggle/uninstall

---

### User Story 12 — Manage directory-type config entries (Priority: P2)

Some agent configuration is a directory of prose files, not a single file — Claude Code's `agents/` directory holds one Markdown file per personal subagent, OpenCode keeps both an `agents/` (subagents) and a `commands/` (slash commands) directory, and Hermes keeps a `cron/` directory of scheduled jobs. The user expands such an entry in the config-files tab, sees its files, opens one to edit, creates a new one, or deletes one — with the same validation, atomic-write, and `.bak` safety net as single-file entries. The allowlist also gains Codex's `hooks.json`; the `memory` key is renamed `instructions` (CLAUDE.md / AGENTS.md are human-authored instructions, not agent-written memory); and each agent's instructions/identity surfaces are allowlisted (Cursor's global `.cursorrules` + `AGENTS.md`, Hermes's `SOUL.md` + `USER.md`).

**Why this priority**: Subagent definitions are exactly the kind of shareable prose the hub model wants visible first, adoptable later; today they are invisible.

**Covering scenarios**:

- list a directory config entry's files
- create a file inside a directory entry
- delete a file inside a directory entry
- reject directory file paths outside the entry
- reject stale config-file writes

---

### Edge Cases

- **Discovery on a second scan**: Already-registered types are not offered as candidates; discovery never duplicates existing entries.
- **User deletes an agent**: A removal is not permanent. The next scan re-surfaces that agent as a candidate (the deletion may have been accidental); Coffer keeps no suppression list. The user re-adds with one confirm.
- **Agent type not in the supported list**: Registration rejected with a clear message and the supported-type list (`claude_code`, `codex`, `cursor`, `opencode`, `openclaw`, `hermes`).
- **`config_dir` path doesn't exist or isn't writable**: Registration rejected; no partial state.
- **`config_dir` points to a privileged path** (`/etc`, `/usr`, etc.): Registration rejected.
- **Duplicate name within `agent` kind**: Rejected by the kind-agnostic Resource framework.
- **Config-file key not in the type's allowlist**: Read rejected with `not_found` (404); no filesystem access for an unknown key.
- **Config file does not exist yet**: Listed and readable as `exists=false` with empty content; the read never creates the file.
- **Coffer MCP install when already installed**: Idempotent — the `coffer` entry is updated in place, never duplicated; status remains `installed`.
- **Coffer MCP uninstall when not installed**: No-op success; status reports `not_installed`.
- **`coffer-mcp-shim` binary cannot be resolved**: Install rejected with a clear error naming the missing binary; nothing is written to the agent's config.
- **Folder browse outside the home directory**: The daemon-backed folder browser lists subdirectories of any readable directory the user navigates to; it never returns file contents. An unreadable or non-existent path returns an error, not a partial listing.
- **Agent config file fails to parse**: The affected facet (MCP entries, plugins) shows an explicit parse-error state and degrades to read-only; other facets and tabs are unaffected. Write operations against the broken file are rejected until it parses again.
- **Same MCP entry name in both Claude Code source files**: Both entries are listed, each labelled with its source file; remove/adopt requests carry the source so the right one is edited.
- **Coffer's own `coffer` MCP entry**: Never adoptable, never listed as a plain direct entry — it is the gateway's install state, managed by Story 8's install/uninstall.
- **Adoption requested for an entry equivalent to an existing resource**: Coffer reports the match (`matches_resource`) and offers removing the redundant direct entry instead of creating a duplicate resource.
- **Plugin configured but cache directory missing**: Listed with `cache_present=false` so the user sees the drift; Coffer does not attempt repair (reinstalling is the agent's own tooling).
- **The agent's own process rewrites a config file between Coffer's read and write**: The write is rejected as stale (fingerprint mismatch, 409); the user re-reads and retries. The `.bak` of every Coffer write keeps the prior content recoverable in the reverse race.
- **Instructions file contains the spec-007 memory-projection managed block**: The editor surfaces that the block is owned by the memory feature; editing outside the block is unrestricted.
- **`~/.codex/auth.json` and other credential/state files**: Never enter any allowlist or listing; plugin and MCP parsing never reads them.

## Acceptance Scenarios

Per `agents/sdd.md` and `agents/testing.md`, every scenario in this section is referenced by at least one test marked `@pytest.mark.acceptance(spec="004-agent-registry", scenario="…")` (Python) or `acceptance("004-agent-registry", "…", …)` (TypeScript).

### Scenario: discover installed agents as candidates

- **Given** a Coffer install with `~/.codex/` present and no agent registered,
- **When** the user runs discovery,
- **Then** Coffer reports a `codex` candidate (type, display name, default config dir, suggested name) and registers nothing — discovery is read-only.

### Scenario: skip already-registered types on subsequent scan

- **Given** a `codex` agent is already registered,
- **When** the user runs discovery again,
- **Then** `codex` is not offered as a candidate.

### Scenario: re-surface removed agents on subsequent scan

- **Given** an agent has been removed by the user and its install marker is still present,
- **When** the user runs discovery again,
- **Then** that agent is offered as a candidate again (removal is not permanent; no suppression list).

### Scenario: register an agent with a custom config dir

- **Given** the daemon is running,
- **When** the user registers an agent of supported type with an explicit, writable `config_dir`,
- **Then** the agent is persisted with that path (and its `<config_dir>/skills` subdirectory auto-created) and appears in `coffer agent list`.

### Scenario: reject registration with an invalid config dir

- **Given** the daemon is running,
- **When** the user registers an agent whose `config_dir` does not exist, is not a directory, or is not writable,
- **Then** registration is rejected with a message naming the path, and nothing is persisted.

### Scenario: reject duplicate agent name

- **Given** an agent named `codex-work` exists,
- **When** the user attempts to register another agent with the same name,
- **Then** registration is rejected with a clear error.

### Scenario: reject a second agent for an already-registered config dir

- **Given** a `codex` agent is already registered (whose config dir is `~/.codex`),
- **When** the user attempts to register another `codex` agent (which resolves to the same config dir), even with a different name and config_dir,
- **Then** registration is rejected with a clear error and nothing is persisted — only one agent may exist per config directory.

### Scenario: register an agent without an explicit name

- **Given** the daemon is running,
- **When** the user registers an agent of supported type without supplying a name,
- **Then** the agent is registered under a stable per-type default name (underscores become hyphens, e.g. `claude_code` → `claude-code`).

### Scenario: browse local folders to choose a config dir

- **Given** the daemon is running,
- **When** the web folder browser requests the subdirectories of a readable directory,
- **Then** Coffer returns that directory's path, its parent, and its immediate subdirectories (no file contents); an unreadable or missing path returns an error.

### Scenario: update an existing agent

- **Given** a registered agent,
- **When** the user updates its `config_dir` to a new writable path,
- **Then** the change persists, an audit entry is recorded, and subsequent operations see the new path.

### Scenario: remove an agent

- **Given** a registered agent (any binding cleanup is handled by the 005-skill-manager spec),
- **When** the user removes it,
- **Then** the agent is deleted, an audit entry is recorded, and `coffer agent list` no longer shows it.

### Scenario: desktop app agents page

- **Given** Coffer's desktop app is launched and one or more agents are registered,
- **When** the user opens the Agents page,
- **Then** every registered agent appears with type, name, and `config_dir`.

> Story 4 add/edit/remove flows from the desktop form are exercised at the e2e tier; see `e2e/web/specs/shell_agents.spec.ts` for the bundled acceptance coverage.

### Scenario: CLI surface mirrors REST operations

- **Given** the daemon is running and exposes the REST agent routes,
- **When** the user invokes `coffer agent add`, `list`, `edit`, `rm`, or `detect`,
- **Then** each subcommand calls the corresponding REST endpoint and produces equivalent state changes, and every read subcommand additionally accepts `--json` for machine-readable output.

### Scenario: reject registration into privileged system path

- **Given** the daemon is running,
- **When** the user attempts to register an agent whose `config_dir` resolves under a privileged location (`/etc`, `/usr`, `/bin`, `/sbin`, `/System`, `C:\Windows`, or `C:\Program Files`),
- **Then** registration is rejected with `unprocessable_entity` (422) and no resource row, audit event, or filesystem write occurs.

### Scenario: audit lifecycle events

- **Given** the user has registered, edited, or removed agents,
- **When** they view the audit log,
- **Then** every lifecycle change (create, update, remove) appears via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events, each carrying timestamp, actor, and the affected agent reference. (Agents have no enable/disable concept; discovery is read-only and registers nothing, so neither emits an audit event of its own.)

### Scenario: reject unsupported agent type

- **Given** the daemon is running,
- **When** the user attempts to register an agent of a type outside the supported set (e.g. `claude_desktop`, `gemini_cli`, or a garbage value),
- **Then** registration is rejected with `unprocessable_entity` (422) naming the supported types, and nothing is persisted.

### Scenario: list an agent's config files

- **Given** a registered `claude_code` agent,
- **When** the user lists its config files,
- **Then** Coffer returns the curated set for the type — `settings.json`, `settings.local.json`, `~/.claude.json`, `CLAUDE.md` (key `instructions`), and the `agents/` directory entry — each with its resolved path, format, and an `exists` flag (with size + modified time when present).

### Scenario: read an existing config file

- **Given** a registered agent whose `settings.json` exists,
- **When** the user reads that config-file key,
- **Then** Coffer returns the file's current text content, its format (`json`), and `exists=true`.

### Scenario: read a not-yet-created config file

- **Given** a registered agent whose `CLAUDE.md` does not exist on disk,
- **When** the user reads that config-file key,
- **Then** Coffer returns empty content with `exists=false` and does not create the file.

### Scenario: reject config-file key outside the allowlist

- **Given** a registered agent,
- **When** the user references a config-file key not in that agent type's curated allowlist,
- **Then** Coffer responds `not_found` (404) and performs no filesystem read.

### Scenario: save a config file with valid content

- **Given** a registered `claude_code` agent whose `settings.json` exists,
- **When** the user writes new, well-formed content to that config-file key,
- **Then** Coffer validates the content against the file's format, writes it atomically while keeping a `.bak` of the prior version, records an `agent_config_file_written` audit entry, and the new content reads back on the next read.

### Scenario: reject malformed config-file content

- **Given** a registered agent whose `settings.json` (a `json` file) exists,
- **When** the user writes malformed content (e.g. invalid JSON) to that key,
- **Then** Coffer responds `unprocessable_entity` (422), leaves the on-disk file unchanged, writes no `.bak`, and records no write audit entry.

### Scenario: report Coffer-MCP install status

- **Given** a registered agent whose MCP config does not contain a `coffer` server entry,
- **When** the user checks Coffer-MCP install status,
- **Then** Coffer reports `installed=false`.

### Scenario: install Coffer's MCP into an agent

- **Given** a registered `claude_code` agent and a resolvable `coffer-mcp-shim` binary,
- **When** the user installs Coffer's MCP,
- **Then** a `coffer` entry is written into `~/.claude.json` `mcpServers` with `command` set to the absolute shim path, the prior file is backed up to `.bak`, an `agent_mcp_installed` audit entry is recorded, and install status reports `installed=true`.

### Scenario: install Coffer's MCP is idempotent

- **Given** an agent that already has Coffer's MCP installed,
- **When** the user installs again,
- **Then** the existing `coffer` entry is updated in place (never duplicated) and status still reports `installed=true`.

### Scenario: uninstall Coffer's MCP from an agent

- **Given** an agent that has Coffer's MCP installed,
- **When** the user uninstalls it,
- **Then** the `coffer` entry is removed from the agent's MCP config, the file is backed up to `.bak`, an `agent_mcp_uninstalled` audit entry is recorded, and status reports `installed=false`.

### Scenario: config-file and MCP operations mirror across surfaces

- **Given** the daemon exposes the config-file and MCP-install routes,
- **When** the user invokes the equivalent `coffer agent config …` / `coffer agent mcp …` CLI subcommands,
- **Then** each subcommand calls the corresponding REST endpoint and produces equivalent state, and read subcommands accept `--json`.

### Scenario: list an agent's real MCP entries

- **Given** a registered `codex` agent whose `config.toml` defines several `[mcp_servers.*]` entries including `coffer`,
- **When** the user lists the agent's MCP entries,
- **Then** Coffer returns every entry with its name, source file, transport (stdio command or HTTP URL), and `enabled` flag, marks the `coffer` entry `is_coffer=true`, and stores nothing — the listing is derived from the file at read time.

### Scenario: remove a direct MCP entry

- **Given** a registered agent with a direct (non-Coffer) MCP entry,
- **When** the user removes that entry (carrying the source file for a `claude_code` agent),
- **Then** the entry is deleted from exactly its source file via an atomic write with a `.bak` of the prior content, an `agent_mcp_entry_removed` audit entry is recorded, and the next listing no longer shows it.

### Scenario: toggle a Codex MCP entry's enabled flag

- **Given** a registered `codex` agent with an enabled direct MCP entry,
- **When** the user disables that entry,
- **Then** the entry's `enabled` field is rewritten in place in `config.toml` (atomic + `.bak`), and the listing reflects the new state.

### Scenario: reject toggling a Claude Code MCP entry

- **Given** a registered `claude_code` agent with a direct MCP entry,
- **When** the user attempts to toggle that entry's enabled state,
- **Then** the request is rejected with `unprocessable_entity` (422) and an explanatory error code — the Claude Code format has no per-entry enabled flag — and no file is touched.

### Scenario: degrade to read-only when MCP config is unparseable

- **Given** a registered agent whose MCP-bearing config file contains invalid JSON/TOML,
- **When** the user lists the agent's MCP entries,
- **Then** Coffer reports a parse-error state naming the file and the parser error instead of failing the request, and rejects entry-level writes against that file until it parses again.

### Scenario: adopt a direct MCP entry into Coffer

- **Given** a registered agent with a direct stdio MCP entry whose name collides with no existing resource,
- **When** the user adopts the entry,
- **Then** Coffer first registers an equivalent `mcp_server` resource (schema-validated, audited), verifies it reads back, then removes the direct entry from the agent's config (atomic + `.bak`), records an `agent_mcp_entry_adopted` audit entry, and the upstream is now served to all agents through the gateway.

### Scenario: reject adoption on resource name conflict

- **Given** an `mcp_server` resource already exists with the same name as a direct entry,
- **When** the user adopts that entry without renaming,
- **Then** the request is rejected with `conflict` (409) carrying a suggested alternative name, no resource is created, and the agent's config is untouched.

### Scenario: require keychain mapping for secret-like env values

- **Given** a direct MCP entry whose environment contains a value under a secret-like key (e.g. `API_TOKEN`),
- **When** the user adopts the entry without supplying a keychain mapping for that key,
- **Then** the request is rejected with a response listing the unresolved keys; when the mapping is supplied, the secret is stored in the OS keychain via the daemon and the created resource config carries a reference, never the value.

### Scenario: adoption failure leaves agent config untouched

- **Given** an adoption attempt that fails after resource registration (e.g. the config-file write is rejected as stale),
- **When** the operation aborts,
- **Then** the created resource is rolled back, the agent's config file is byte-identical to before the attempt, and the failure is reported with a specific error code.

### Scenario: list an agent's plugins with enabled state

- **Given** a registered `codex` agent whose `config.toml` defines `[marketplaces.*]` and `[plugins."<name>@<marketplace>"]` entries with cache directories present,
- **When** the user lists the agent's plugins,
- **Then** Coffer returns every plugin with its `<name>@<marketplace>` id, enabled state, marketplace grouping, and `cache_present=true`, deriving everything from the documented files at read time.

### Scenario: toggle a plugin's enabled state

- **Given** a registered agent with an enabled plugin,
- **When** the user disables it,
- **Then** only the documented location is written — the Codex entry's `enabled` field, or the Claude Code `enabledPlugins` map in `settings.json` — internal plugin state files are byte-identical before and after, and an `agent_plugin_toggled` audit entry is recorded.

### Scenario: uninstall a Codex plugin

- **Given** a registered `codex` agent with an installed plugin,
- **When** the user uninstalls it,
- **Then** the `[plugins."…"]` entry is removed from `config.toml` (atomic + `.bak`), the plugin's cache directory under `~/.codex/plugins/cache/` is deleted, and an `agent_plugin_uninstalled` audit entry is recorded.

### Scenario: reject uninstalling a Claude Code plugin

- **Given** a registered `claude_code` agent with an installed plugin,
- **When** the user attempts to uninstall it,
- **Then** the request is rejected with `unprocessable_entity` (422) and error code `PLUGIN_UNINSTALL_UNSUPPORTED`, and nothing is written — full uninstall requires the agent's own tooling.

### Scenario: flag a plugin whose cache is missing

- **Given** a `codex` agent whose `config.toml` references a plugin with no cache directory on disk,
- **When** the user lists the agent's plugins,
- **Then** that plugin is listed with `cache_present=false` and no repair is attempted.

### Scenario: list a directory config entry's files

- **Given** a registered `claude_code` agent whose `agents/` directory contains Markdown subagent files (possibly nested),
- **When** the user lists that config entry,
- **Then** Coffer returns the entry with `kind=directory` and its files (entry-relative path, size, modified time); a missing directory lists as `exists=false` with no files and is not created by the read.

### Scenario: create a file inside a directory entry

- **Given** a registered `claude_code` agent with an `agents/` directory entry,
- **When** the user writes content to a new `.md` file path inside the entry,
- **Then** the file is created via the atomic-write machinery, an `agent_config_file_written` audit entry is recorded, and the next listing includes it.

### Scenario: delete a file inside a directory entry

- **Given** a directory entry containing a file,
- **When** the user deletes that file,
- **Then** the file is removed with its prior content preserved as `.bak`, an `agent_config_file_deleted` audit entry is recorded, and the next listing no longer shows it.

### Scenario: reject directory file paths outside the entry

- **Given** a registered agent with a directory config entry,
- **When** the user addresses a child path containing `..`, an absolute path, or a non-`.md` extension,
- **Then** the request is rejected before any filesystem access with `not_found` (404) for containment violations or `unprocessable_entity` (422) for a disallowed extension.

### Scenario: reject stale config-file writes

- **Given** a config file (or directory child) read by the user, then modified on disk by another process,
- **When** the user writes back content carrying the fingerprint from the earlier read,
- **Then** the write is rejected with `conflict` (409) and the on-disk file is unchanged; re-reading yields a fresh fingerprint that allows the write.

### Scenario: list OpenCode plugins

- **Given** a registered OpenCode agent whose `opencode.json` carries a `plugin` array,
- **When** the user lists its plugins,
- **Then** Coffer returns one entry per array member with no parse errors.

### Scenario: toggle an OpenCode plugin

- **Given** a registered OpenCode agent with a plugin enabled in its `plugin` array,
- **When** the user disables that plugin,
- **Then** the plugin is removed from the `plugin` array while sibling keys in `opencode.json` are preserved.

### Scenario: uninstall an OpenCode plugin

- **Given** a registered OpenCode agent with a plugin in its `plugin` array,
- **When** the user uninstalls that plugin,
- **Then** the plugin is removed from the `plugin` array.

### Scenario: list + toggle OpenClaw plugins

- **Given** a registered OpenClaw agent whose `openclaw.json` carries a `plugins` block with entries, an allow-list, and a deny-list,
- **When** the user lists plugins and then enables a denied one,
- **Then** the listing reflects each plugin's enabled state, and the toggle updates the block so the plugin reads as enabled.

### Scenario: list Cursor extensions read-only

- **Given** a registered Cursor agent with installed extensions,
- **When** the user lists its plugins and then attempts to toggle or uninstall one,
- **Then** the extensions are listed, the toggle is rejected with `unprocessable_entity` (422), the uninstall is rejected with `unprocessable_entity` (422), and the extensions file is never written.

### Scenario: Hermes has no plugin facet

- **Given** a registered Hermes agent (whose plugin mechanism is MCP),
- **When** the user lists plugins and then attempts to toggle or uninstall one,
- **Then** the listing is empty and both the toggle and uninstall are rejected with `unprocessable_entity` (422).

## Requirements

### Functional Requirements

**Resource model**

- **FR-001**: System MUST register each known local agent as a Resource of kind `agent`, identified by `agent:<name>` per spec 001-mcp-gateway's `<kind>:<name>` convention.
- **FR-002**: System MUST validate agent configuration against a kind-specific schema with fields `type` (enum) and `config_dir` (path, optional absolute-path override; when omitted it defaults to the type's standard location — `~/.claude` for `claude_code`, `~/.codex` for `codex`). Skills are delivered to `<config_dir>/skills`.
- **FR-003**: System MUST support the agent types `claude_code`, `codex`, `cursor`, `opencode`, `openclaw`, and `hermes`; registering any other type (e.g. the `claude_desktop` chat app, a Gemini CLI) is rejected with `unprocessable_entity` (422). Per-type behaviour is defined by the capability manifest (`AGENT_DESCRIPTORS`), so adding a type is adding one enum value + one descriptor record. Each supported type covers both the CLI and the app/IDE form of that product, which share one config directory.

**Discovery (detection = discovery + confirm)**

- **FR-004**: System MUST provide a read-only discovery operation that scans well-known install markers for each supported agent type and reports installed types that are not already registered as **candidates** (each carrying `type`, `display_name`, `config_dir`, `default_skill_dir`, and `suggested_name`). Discovery MUST NOT register anything automatically — the user reviews candidates and confirms which to add. The daemon MUST NOT auto-register agents on startup.
- **FR-005**: A removed agent MUST re-appear as a discovery candidate on subsequent scans while its install marker is present — a removal is not permanent (it may be accidental). System MUST NOT keep a "suppressed types" list.

**Lifecycle**

- **FR-006**: Users MUST be able to register, list, view, update (config_dir, description), and remove agents. Agents have **no enable/disable concept** — a registered agent is simply present; there is no enabled/disabled state on the agent surface. The agent name is optional at registration — when omitted, System MUST derive a stable per-type default (underscores become hyphens, e.g. `claude_code` → `claude-code`).
- **FR-007**: At registration System MUST auto-create the `<config_dir>/skills` subdirectory, then validate that the resolved `config_dir` exists, is a directory, is writable, and is not a privileged system path before accepting the value. Skills are delivered to `<config_dir>/skills`.
- **FR-008**: System MUST reject registration that would create a duplicate `agent:<name>`, and MUST reject registering more than one agent for the same config directory. `config_dir` is derived from the agent type, so each supported type — and thus each on-disk config directory — may be registered at most once; a second attempt is rejected with `conflict` (409) and nothing is persisted.

**Config files**

- **FR-013**: Each supported agent type MUST define a curated allowlist of config files (in its capability-manifest record), each entry carrying a stable `key`, a display name, a resolved absolute path, and a `format` (`json`, `toml`, `yaml`, `markdown`, or `text`). Claude Code → `settings.json`, `settings.local.json`, `~/.claude.json`, `CLAUDE.md` (key `instructions`), and the `agents/` directory entry (FR-034); Codex → `config.toml`, `AGENTS.md` (key `instructions`), and `hooks.json`; Cursor → `mcp.json`, `.cursorrules` (key `rules`), `AGENTS.md` (key `instructions`); OpenCode → `opencode.json`, `AGENTS.md`, and the `agents/` (key `subagents`) and `commands/` directory entries (FR-034); OpenClaw → `openclaw.json` (its instructions/identity file is not reliably documented, so none is added until confirmed); Hermes → `config.yaml`, `SOUL.md` (key `instructions`), `USER.md` (key `identity_user`), and the `cron/` directory entry (FR-034). The allowlist for the newer agents covers each agent's config, instructions/identity, and managed directory surfaces, and grows as their other facets land. The former `memory` key is renamed `instructions` — these files are human-authored instructions, distinct from agent-written memory (spec 007's domain).
- **FR-014**: Users MUST be able to list an agent's config files with, for each, its key, display name, path, format, and existence (plus size and modified time when the file exists).
- **FR-015**: Users MUST be able to read the content of any allowlisted config file. A file that does not exist reads as empty content with `exists=false` and is not created by the read.
- **FR-016**: Users MUST be able to write (save) the content of any allowlisted config file. The content MUST be validated against the file's `format` before any write; malformed `json`/`toml` MUST be rejected (`unprocessable_entity`, 422) and the on-disk file left unchanged. `markdown`/`text` files accept any content.
- **FR-017**: Writes MUST be atomic (temp file + rename) and MUST keep a `.bak` copy of the prior content so a bad edit is recoverable; each successful write MUST record an `agent_config_file_written` audit entry. The Coffer-MCP install/uninstall operations (FR-022) reuse the same atomic-write + `.bak` machinery.
- **FR-018**: Config-file read and write MUST be addressable only by allowlisted `key` (never by caller-supplied path); an unknown key returns `not_found` (404) and performs no filesystem access.

**Coffer MCP install**

- **FR-019**: Users MUST be able to install Coffer's own MCP server into an agent in one action. The install writes a `coffer` stdio MCP-server entry into the agent's MCP config, using the shape declared by that agent's manifest `McpInjectionSpec` — `mcpServers.coffer` in `~/.claude.json` (`claude_code`) and `~/.cursor/mcp.json` (`cursor`); `[mcp_servers.coffer]` in `~/.codex/config.toml` (`codex`); `mcp.coffer` in `opencode.json` (`opencode`, as a `{type:"local", command:[shim]}` typed array) and `openclaw.json` (`openclaw`); `mcp_servers.coffer` in `~/.hermes/config.yaml` (`hermes`, YAML). `command` is the absolute path of the `coffer-mcp-shim` binary (resolved on `PATH`, then the running interpreter's scripts directory — so a venv-installed shim is found even when the daemon's `PATH` lacks the venv — then the bundled binary; a `COFFER_MCP_SHIM_PATH` environment override takes precedence over all). If the shim cannot be resolved, install is rejected and nothing is written.
- **FR-020**: Install MUST be idempotent — re-installing updates the existing `coffer` entry in place and never creates a duplicate. System MUST expose a status operation reporting whether Coffer's MCP is currently installed for the agent.
- **FR-021**: Users MUST be able to uninstall Coffer's MCP, removing the `coffer` entry from the agent's MCP config. Uninstalling when not installed is a no-op success.
- **FR-022**: Install and uninstall MUST reuse the atomic-write + `.bak` machinery from FR-017 and record an audit entry (`agent_mcp_installed` / `agent_mcp_uninstalled`).

**Agent MCP entries (workspace amendment)**

- **FR-025**: System MUST parse and list the MCP server entries configured in the agent's own files — for `claude_code` from both `~/.claude.json` `mcpServers` and `settings.json` `mcpServers` (each entry labelled with its source file); for `codex` from `config.toml` `[mcp_servers.*]`. Each entry carries name, source, transport (stdio command or HTTP URL), the `enabled` flag where the format defines one (Codex), `is_coffer` for Coffer's own gateway entry, and `matches_resource` naming an equivalent registered `mcp_server` resource when one exists. Entries are derived at read time, never stored.
- **FR-026**: Users MUST be able to remove a direct MCP entry. Removal edits only the entry's source file (disambiguated by the caller for `claude_code` when both files carry the name), reuses the FR-017 atomic-write + `.bak` machinery, and records an `agent_mcp_entry_removed` audit entry. The `coffer` entry is not removable through this operation — it is managed by FR-019/FR-021.
- **FR-027**: Users MUST be able to toggle a Codex entry's `enabled` flag in place. For `claude_code`, whose format has no per-entry flag, the toggle is rejected with `unprocessable_entity` (422) and an explanatory error code.
- **FR-028**: Users MUST be able to adopt a direct MCP entry into Coffer. Adoption (a) registers the entry as an `mcp_server` resource through the standard resource flow (schema validation + audit), (b) verifies the resource reads back, then (c) removes the source entry per FR-026 — strictly in that order. Any failure stops the operation, rolls back a created resource, and leaves the agent's config byte-identical; audited as `agent_mcp_entry_adopted` on success. A name collision with an existing resource is rejected with `conflict` (409) carrying a suggested alternative; an entry equivalent to an existing resource is reported via `matches_resource` so the user can remove the duplicate instead. The `coffer` entry is never adoptable.
- **FR-029**: Adoption MUST NOT persist secret values into resource config. When an entry's environment carries values under secret-like keys (`TOKEN`, `KEY`, `SECRET`, `PASSWORD` patterns), the adopt request MUST supply a keychain mapping for each flagged key or be rejected with the unresolved keys listed. Mapped values are stored in the OS keychain through the daemon (per the credentials invariant); the resource config carries references only.
- **FR-030**: When an agent config file cannot be parsed, the affected facet MUST degrade to an explicit parse-error state (file path + parser error) without failing the surrounding view, and entry-level writes against that file MUST be rejected until it parses again.

**Plugins (workspace amendment)**

- **FR-031**: System MUST list an agent's installed plugins with enabled state, grouped by marketplace. For `codex` the listing derives from `config.toml` (`[plugins."<name>@<marketplace>"]`, `[marketplaces.*]`) plus presence of the documented cache directory `~/.codex/plugins/cache/<marketplace>/<plugin>/`; for `claude_code` the inventory derives read-only from `~/.claude/plugins/installed_plugins.json` and `known_marketplaces.json`, with enabled state from `settings.json` `enabledPlugins`. A plugin configured without its cache is flagged `cache_present=false`; no repair is attempted.
- **FR-032**: Users MUST be able to enable/disable a plugin. Writes touch only the documented locations — the Codex entry's `enabled` field; the Claude Code `enabledPlugins` map in `settings.json` — and MUST never write the agents' internal state files. Audited as `agent_plugin_toggled`.
- **FR-033**: Users MUST be able to uninstall a `codex` plugin: the `[plugins."…"]` entry is removed from `config.toml` and the plugin's cache directory is deleted; audited as `agent_plugin_uninstalled`. Uninstall for `claude_code` is rejected with `unprocessable_entity` (422) and error code `PLUGIN_UNINSTALL_UNSUPPORTED` — full uninstall requires the agent's own tooling; the UI offers disable plus a hint instead. Plugin installation and marketplace management are not provided by Coffer; both remain with the agent's own tooling.

**Directory config entries (workspace amendment)**

- **FR-034**: A config-file allowlist entry MAY be a **directory entry** (`kind=directory`): it resolves to a directory and lists its files (entry-relative path, size, modified time) instead of carrying content. v1 directory entries: Claude Code `agents/` (one Markdown file per personal subagent, nested paths allowed). A missing directory lists as `exists=false` with no files; the read never creates it.
- **FR-035**: Users MUST be able to read, write (create-on-write), and delete individual files inside a directory entry. Child paths are validated server-side before any filesystem access: they MUST resolve inside the entry's directory (no `..`, no absolute paths, no symlink escape) and carry the `.md` extension. Writes reuse FR-017's machinery; deletion preserves the prior content as `.bak`. Audited as `agent_config_file_written` / `agent_config_file_deleted`.
- **FR-036**: Config-file reads (single files and directory children) MUST return a content fingerprint; writes MUST carry it back and are rejected with `conflict` (409) when the on-disk content changed since the read, leaving the file untouched.
- **FR-037**: When an instructions file contains the managed memory-projection block defined by spec 007, the editor MUST surface that the block is owned by the memory feature. The marker format is defined by spec 007; this spec only requires the notice.

**Surfaces**

- **FR-009**: Every management operation — register/list/view/update/remove, config-file list/read/write (including directory children), Coffer-MCP install/uninstall/status, MCP entry list/remove/toggle/adopt, and plugin list/toggle/uninstall — MUST be available through (a) the REST API, (b) the `coffer agent ...` CLI, and (c) the desktop Agents page.
- **FR-010**: The CLI MUST support `--json` for machine-readable output on every read operation.

**Observability**

- **FR-011**: System MUST record an audit entry for every lifecycle event: agent created, updated, removed; config file written/deleted (`agent_config_file_written` / `agent_config_file_deleted`); Coffer MCP installed/uninstalled; MCP entry removed/adopted (`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`); plugin toggled/uninstalled (`agent_plugin_toggled` / `agent_plugin_uninstalled`). (Agents have no enable/disable concept; discovery and all workspace listings are read-only — none emits an audit event.)
- **FR-012**: System MUST expose a read-only discovery operation listing installed-but-unregistered agents as candidates, available from the REST API (`GET /api/v1/agents/candidates`), the `coffer agent detect` CLI, and the desktop Agents page.

**Config-directory picker**

- **FR-023**: When choosing a custom `config_dir`, the desktop app MUST offer a folder picker rather than requiring the user to type a path. In the packaged desktop app it MUST use the OS-native directory dialog; on the web it MUST use the daemon-backed folder browser (FR-024). Both yield an absolute path that is then validated per FR-007 before registration.
- **FR-024**: System MUST expose a read-only filesystem-browse operation (`GET /api/v1/fs/browse`) that, given a directory path (defaulting to the user's home), returns that path, its parent, and its immediate subdirectories. It MUST NOT return file contents and MUST be guarded by the same loopback + token auth as all other daemon routes.

### Key Entities

- **Agent**: A Resource of kind `agent`. Represents one locally-installed AI agent. Config: `type` (supported enum), `config_dir` (optional absolute-path override; defaults to the type's standard location). Skills are delivered to `<config_dir>/skills`. Identified by `agent:<name>`.
- **Agent Type**: An enum value identifying a known agent product (`claude_code`, `codex`, `cursor`, `opencode`, `openclaw`, `hermes`). Each value maps to a record in the **capability manifest** (`AGENT_DESCRIPTORS`) carrying its default `config_dir`, display name, install-marker (for discovery), curated **config-file allowlist**, and **MCP injection shape**.
- **Agent Candidate**: A discovered installed-but-unregistered agent — `type`, `display_name`, `config_dir` (the type's default config directory), `default_skill_dir`, and `suggested_name`. Derived at scan time, never stored; the user confirms a candidate to register it.
- **Config File**: A curated, allowlisted file belonging to an agent type, identified by a stable `key`. Carries a display name, a resolved absolute path, a `format` (`json` / `toml` / `markdown` / `text`), and (when present) size and modified time. Read/written by key, never by arbitrary path. Not persisted in SQLite — the file on disk is the source of truth.
- **Coffer MCP Install Status**: Derived (not stored) state for an agent: whether a `coffer` MCP-server entry is present in that agent's MCP config file.
- **Agent MCP Entry**: A derived (never stored) view of one MCP server configured in the agent's own files — name, source file, transport, `enabled` (Codex), `is_coffer`, `matches_resource`. The file is the source of truth; Coffer reads, edits, removes, or adopts entries but keeps no copy.
- **Agent Plugin**: A derived (never stored) view of one installed plugin — id (`<name>@<marketplace>`), marketplace, enabled state, `cache_present`. Enabled state lives in each agent's documented config surface; the inventory files of Claude Code are read-only inputs.
- **Directory Config Entry**: An allowlisted config entry that resolves to a directory of files rather than a single file. Children are addressed by validated entry-relative paths; the directory on disk is the source of truth.

## Success Criteria

### Measurable Outcomes

- **SC-001**: On a machine with at least two supported agent install paths present, running discovery surfaces exactly those agents as candidates, and the user adds them with a single confirm each — no typing of type identifiers or paths.
- **SC-002**: From a fresh install, a user can register an additional agent with a custom `config_dir` and see it in `coffer agent list --json` within 60 seconds, without consulting documentation more than once.
- **SC-003**: Every Acceptance Scenario in this spec is covered by at least one test marked `acceptance(spec="004-agent-registry", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-004**: The full `make verify` suite passes locally and in CI; `make verify-all` (adding e2e) passes on macOS and Linux.
- **SC-005**: No `config_dir` value ever permits writing outside the directory itself (path-traversal check); validated by a dedicated security test.
- **SC-006**: A user can open, edit, and save an agent's `settings.json` (Claude Code) or `config.toml` (Codex) from both the desktop app and the CLI; a malformed save is rejected with the file left unchanged, and a `.bak` of the prior version is kept on a successful save.
- **SC-007**: A user can install Coffer's MCP into a freshly-registered agent in one click and, after restarting that agent, the agent lists Coffer's aggregated tools; re-installing never duplicates the entry, and uninstall removes it.
- **SC-008**: The MCP tab lists exactly the entries present in the agent's real config files, and adopting a direct entry completes the full round trip — resource registered, gateway serving it, direct entry gone — in one user action plus at most one confirmation.
- **SC-009**: Plugin toggles change only the documented config surface: a test asserts the agents' internal state files are byte-identical before and after every toggle.
- **SC-010**: No directory-entry operation can read or write a path outside its entry's directory; validated by dedicated security tests covering `..` traversal, absolute paths, symlink escape, and disallowed extensions.

## Assumptions

- The user runs Coffer on their own machine; there is no multi-tenant or remote-access requirement.
- v1's two supported agent types (`claude_code`, `codex`) cover the user's installed agents; adding a new type (e.g. the Claude Desktop chat app, Cursor, Gemini CLI) is a future-spec change that adds another enum value, install-marker scanner, and config-file allowlist.
- Each supported agent's CLI and app/IDE form read one shared config directory (`~/.claude/` for Claude Code, `~/.codex/` for Codex), so Coffer manages one config set per agent.
- Config files are surfaced as raw text the user can edit and save (with a `.bak` safety net); an in-editor find / replace is a UI convenience. The raw editor is the escape hatch for the long tail; recurring structured needs graduate into facets (MCP entries, plugins) per the workspace amendment. The credential/state file `~/.codex/auth.json` is intentionally excluded from the allowlist.
- The agents' internal state files (`~/.claude.json` beyond its `mcpServers` map, `~/.claude/plugins/*.json`, Codex's `[marketplaces.*]` / `[hooks.state.*]` / `[projects.*]` tables) are read as inputs where needed and never written by the workspace facets; the documented configuration surfaces verified against each vendor's docs are the only write targets. In practice (verified on a real machine) user-scope Claude Code MCP servers live in `~/.claude.json` `mcpServers` and may also appear in `settings.json` `mcpServers` — both are parsed.
- Workspace facets follow the ingest → hub → deliver principle: shareable content found in an agent's workspace is adoptable into Coffer's hub (MCP gateway here; the master skill store via spec 005's companion amendment) rather than managed as per-agent one-offs. Cross-machine sharing of the hub itself is a future spec (and constitutional amendment); these facets are designed so their state serializes to declarative manifests when that lands.
- Agents store their skill libraries on the local filesystem under `<config_dir>/skills`. Web-only agents (e.g., claude.ai) are out of scope for v1 and require a future spec to add API-based sync.
- The kind-agnostic Resource framework, audit log, and `<kind>:<name>` identity scheme defined by spec 001-mcp-gateway are in place.
- The application shell from spec 002-ui-shell — sidebar IA, layout, routing skeleton, and design system — is in place. The desktop Agents page renders within that shell at `/agents` as a **dedicated top-level nav entry** (a sibling of the Resources and System groups, **not** nested under Resources — agents are consumers of vault assets, not assets themselves). Agent resources do not appear in the kind-agnostic resources/MCP browser, which lists only kinds that register a resource-card UI.
- Skill bindings (i.e., the relationship between an agent and a particular skill) are introduced and managed by spec 005-skill-manager; spec 004 does not define skill operations beyond exposing an `on_delete` hook for cascade cleanup.
