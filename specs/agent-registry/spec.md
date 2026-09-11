# Feature Specification: Agent Registry

**Feature Branch**: `feature/agent-registry`
**Created**: 2026-05-22
**Status**: Accepted
**Input**: User description: "Manage which locally-installed AI agents Coffer knows about, so later features (skills, memory, knowledge bases) can deliver assets to them. Each agent is a Resource of kind `agent` in the kind-agnostic Resource framework introduced by spec mcp-gateway. v1 supports two agent types: Claude Code and OpenAI Codex — each covering both its CLI and its desktop/IDE form, which share one on-disk config. Beyond registering agents, the user can view and edit each agent's known config files, or open them in an external editor, and install Coffer's own MCP server into an agent with one click."

> **Note on agent types.** Supported products: **Claude Code** (`claude_code`, `~/.claude/`) and **OpenAI Codex** (`codex`, `~/.codex/`). Each spans its CLI _and_ its app/IDE form because they read one shared config directory. Per-type behaviour lives in the capability manifest (`AGENT_DESCRIPTORS`) — adding a product is one enum value + one descriptor record (config-file allowlist, MCP injection shape, etc.). The separate **Claude Desktop** chat app (its own `~/Library/Application Support/Claude/` config) is out of scope.

> **Workspace amendment.** Stories 9–12 extend the registry into the agent's real on-disk workspace: the MCP servers actually configured in the agent's own files, the agent's installed plugins, and directory-type config entries. The guiding principle is **ingest → hub → deliver**: anything shareable found in an agent's workspace can be adopted into Coffer's hub (the MCP gateway, the master skill store of spec skill-manager) and delivered back to any agent, instead of living as per-agent one-off config. All writes go through each agent's documented configuration paths only; internal state files are read, never written.

> **Note on the built-in agent ([Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.md)).** This registry holds only **managed** agents — locally-installed external coding agents (Claude Code, Codex, …) that Coffer delivers assets to. The former `builtin` "Coffer Assistant" is **not** a registered agent here: [Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.md) retires it as a chat persona and recasts its local model as an internal Coffer capability reached only through `coffer__*` MCP tools. (The separate chat agent-provider registry of the retired Agent Chat spec likewise drops the `builtin` provider and lists managed agents only.)

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

Some users install agents in non-default locations or have multiple installs (work vs personal). They need to add an agent by type, optionally overriding the config directory. The name is optional — when omitted Coffer derives a stable per-type default. When choosing a custom path, the web UI offers a folder picker — the host's native directory dialog, opened through the local daemon — so the user picks a real directory instead of typing it.

**Why this priority**: Discovery covers the common case; manual register covers the long tail. Without it the registry is incomplete.

**Independent Test**: From the command line, register a `codex` agent named `codex-work` with `--config-dir /custom/path`; list agents; observe the manually-registered entry. From the web UI form, add an agent with no name and observe it registered under the per-type default name.

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

### User Story 4 — Manage agents through the web UI (Priority: P2)

The user opens Coffer's web UI, sees an "Agents" page listing every registered agent with type, name, and config_dir, and can add or edit from a form.

**Why this priority**: Non-CLI users need a visual surface to make sense of the registry.

**Independent Test**: Open the web UI → Agents → add Codex with default path → observe in list → click into it → change config_dir → save → list updates.

**Covering scenarios**:

- agents page lists all registered agents
- add an agent through the web UI form
- edit an agent through the web UI form
- remove an agent through the web UI confirmation

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

### User Story 7 — View an agent's config files and open them in an external editor (Priority: P2)

After an agent is registered, the user wants to see that agent's own configuration files (e.g. Claude Code's `settings.json`, Codex's `config.toml`) directly inside Coffer, without leaving the app to hunt for dotfiles. Coffer shows the agent type's curated set of known config files and lets the user open one, read its current content and **edit it in place**. Saving validates against the file's format first, then writes atomically keeping a `.bak`, so a bad edit is both refused early and recoverable. Because these files are also edited outside Coffer, a save carries the fingerprint of the content it started from and is refused rather than applied when the file changed underneath it (FR-036). For each file Coffer also offers open-in-external-editor and reveal-in-file-manager, for the edits that want a real editor.

**Why this priority**: Locating agent config by hand means remembering where each file lives and what format it uses. Surfacing the curated set in one place — viewable at a glance, one click from the user's own editor — is the first feature that makes the registry useful beyond bookkeeping.

**Independent Test**: Register a `claude_code` agent; list its config files; open `settings.json`, observe the response surfaces the file's `path`, containing-folder `folder_path` (backing open/reveal) and a content `fingerprint`; edit and save it, and observe the new content reads back; open a not-yet-created file (e.g. `CLAUDE.md`) and observe it reads as empty without being created.

**Covering scenarios**:

- list an agent's curated config files with existence + size metadata
- read the content of an existing config file
- read a not-yet-created config file as empty
- reject reading a key outside the agent type's allowlist

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

### User Story 9 — See the agent's real MCP servers (Priority: P2)

The agent's MCP servers tab today can only say whether Coffer's own shim is installed. The user wants to see what their agent **actually** has configured: every MCP server entry in the agent's own config files — for Claude Code from both `~/.claude.json` `mcpServers` and `settings.json` `mcpServers`, for Codex from `config.toml` `[mcp_servers.*]`. Each entry shows its transport (stdio command or HTTP URL), which file it came from, and (Codex only — the format defines a per-entry flag) its enabled state. The listing is **read-only**: Coffer surfaces what bypasses its gateway, and the one write it offers on these entries is adoption (Story 10). Editing an entry in place — removing it, flipping a Codex `enabled` flag — belongs to the agent's own UI, which already does it; Coffer duplicating it would mean hand-writing another tool's private config format for no capability the user did not already have. Coffer's own `coffer` entry is rendered specially and managed by the existing install/uninstall actions.

**Why this priority**: The current tab shows the same Coffer-global list for every agent, which is misleading. Showing the agent's real configuration is the prerequisite for adoption — the user cannot pull a server into the hub without first seeing that it is outside it.

**Independent Test**: Register a `codex` agent whose `config.toml` carries several `[mcp_servers.*]` entries; open the MCP tab; observe exactly those entries with transports, source files, and enabled flags, and observe that the agent's `config.toml` is byte-identical after the listing.

**Covering scenarios**:

- list an agent's real MCP entries
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

### User Story 11 — See the agent's plugins (Priority: P3)

Agents with a file-backed plugin system expose that inventory to Coffer **read-only**: every installed plugin with the marketplace it came from, its enabled state, and whether its on-disk cache is present, derived from the agent's documented configuration files at read time, plus best-effort detail read from the plugin's own install directory (`installPath`) — its manifest description/version/author and the skills, commands, and MCP servers it bundles. Each agent record's `PluginCapability` (a plugin-model discriminator plus the allowlist key of the file the state is read from) lets the service dispatch on data rather than per-agent branches. Nothing is written: not the documented surface, not the internal state files. Enabling, disabling, uninstalling, installing, and marketplace management all stay with the agent's own tooling.

Per-agent plugin support:

| Agent       | Plugin model                                                                                                      | Read from                                       | List | Write |
| ----------- | ----------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- | ---- | ----- |
| Claude Code | `enabledPlugins` map in `settings.json` (inventory in `installed_plugins.json` / `known_marketplaces.json`)        | `settings.json` + the two inventory files       | yes  | no    |
| Codex       | `[plugins."<name>@<marketplace>"]` tables + cache dir                                                             | `config.toml` + the cache directory             | yes  | no    |

**Why this priority**: Plugins are real, persistent agent configuration, and knowing what is installed is occasionally useful. It is not useful enough to justify writing another tool's private plugin format — see the removal note under the plugin requirements. This story has no web UI: the listing is a REST + CLI read only.

**Independent Test**: Register a `codex` agent with plugins configured; run `coffer agent plugin list <name> --json`; observe every plugin with its marketplace, enabled state, and `cache_present`, and observe every file under `~/.codex/` byte-identical afterwards.

**Covering scenarios**:

- list an agent's plugins with enabled state
- flag a plugin whose cache is missing

---

### User Story 12 — Manage directory-type config entries (Priority: P2)

Some agent configuration is a directory of prose files, not a single file — Claude Code's `agents/` directory holds one Markdown file per personal subagent. The user expands such an entry in the config-files tab and sees its files, opening one to read and edit it (with open-in-external-editor / reveal for the child file and its folder). Creating, writing, and deleting individual files is available through the in-app editor and the REST API / `coffer agent` CLI — with the same validation, atomic-write, and `.bak` safety net as single-file entries. The allowlist also gains Codex's `hooks.json`; the `memory` key is renamed `instructions` (CLAUDE.md / AGENTS.md are human-authored instructions, not agent-written memory).

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
- **Agent type not in the supported list**: Registration rejected with a clear message and the supported-type list (the manifest types — `claude_code`, `codex`).
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
- **Same MCP entry name in both Claude Code source files**: Both entries are listed, each labelled with its source file; an adopt request carries the source so the right one is adopted and removed.
- **Coffer's own `coffer` MCP entry**: Never adoptable, never listed as a plain direct entry — it is the gateway's install state, managed by Story 8's install/uninstall.
- **Adoption requested for an entry equivalent to an existing resource**: Coffer reports the match (`matches_resource`) and offers removing the redundant direct entry instead of creating a duplicate resource.
- **Plugin configured but cache directory missing**: Listed with `cache_present=false` so the user sees the drift; Coffer does not attempt repair (reinstalling — like every other plugin write — is the agent's own tooling).
- **The agent's own process rewrites a config file between Coffer's read and write**: The write is rejected as stale (fingerprint mismatch, 409); the user re-reads and retries. The `.bak` of every Coffer write keeps the prior content recoverable in the reverse race.
- **Instructions file contains the knowledge layer's memory-projection managed block**: The editor annotates that the block is owned by the memory feature, so the user knows an edit to it may be rewritten.
- **`~/.codex/auth.json` and other credential/state files**: Never enter any allowlist or listing; plugin and MCP parsing never reads them.

## Acceptance Scenarios

Per `agents/sdd.md` and `agents/testing.md`, every scenario in this section is referenced by at least one test marked `@pytest.mark.acceptance(spec="agent-registry", scenario="…")` (Python) or `acceptance("agent-registry", "…", …)` (TypeScript).

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

### Scenario: open a managed file via the daemon (web open/reveal)

- **Given** the daemon is running and the editor is showing a managed file,
- **When** the web surface asks the daemon to open an existing absolute path (optionally with a preferred editor) or to reveal it in the file manager,
- **Then** the daemon launches the OS application / file manager for that path and returns success; a relative or non-existent path is rejected without spawning anything.

### Scenario: update an existing agent

- **Given** a registered agent,
- **When** the user updates its `config_dir` to a new writable path,
- **Then** the change persists, an audit entry is recorded, and subsequent operations see the new path.

### Scenario: remove an agent

- **Given** a registered agent (any binding cleanup is handled by the skill-manager spec),
- **When** the user removes it,
- **Then** the agent is deleted, an audit entry is recorded, and `coffer agent list` no longer shows it.

### Scenario: desktop app agents page

- **Given** Coffer's web UI is open and one or more agents are registered,
- **When** the user opens the Agents page,
- **Then** every registered agent appears with type, name, and `config_dir`.

> Story 4 add/edit/remove flows from the web UI form are exercised at the e2e tier; see `e2e/web/specs/shell_agents.spec.ts` for the bundled acceptance coverage.

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
- **Then** Coffer returns the curated set for the type — `settings.json`, `settings.local.json`, `~/.claude.json`, `CLAUDE.md` (key `instructions`), and the `agents/` directory entry — each with its resolved path, its containing-folder absolute path (`folder_path`), format, and an `exists` flag (with size + modified time when present).

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
- **When** the user writes new, well-formed content to that config-file key through the in-app editor, the REST API or the `coffer agent` CLI,
- **Then** Coffer validates the content against the file's format, writes it atomically while keeping a `.bak` of the prior version, records an `agent_config_file_written` audit entry, and the new content reads back on the next read.

### Scenario: reject malformed config-file content

- **Given** a registered agent whose `settings.json` (a `json` file) exists,
- **When** the user writes malformed content (e.g. invalid JSON) to that key through the in-app editor, the REST API or the `coffer agent` CLI,
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
- **When** the user writes content to a new `.md` file path inside the entry through the in-app editor, the REST API or the `coffer agent` CLI,
- **Then** the file is created via the atomic-write machinery, an `agent_config_file_written` audit entry is recorded, and the next listing includes it.

### Scenario: delete a file inside a directory entry

- **Given** a directory entry containing a file,
- **When** the user deletes that file through the REST API or the `coffer agent` CLI,
- **Then** the file is removed with its prior content preserved as `.bak`, an `agent_config_file_deleted` audit entry is recorded, and the next listing no longer shows it.

### Scenario: reject directory file paths outside the entry

- **Given** a registered agent with a directory config entry,
- **When** the user addresses a child path containing `..`, an absolute path, or a non-`.md` extension,
- **Then** the request is rejected before any filesystem access with `not_found` (404) for containment violations or `unprocessable_entity` (422) for a disallowed extension.

### Scenario: reject stale config-file writes

- **Given** a config file (or directory child) read by the user, then modified on disk by another process,
- **When** the user writes back content carrying the fingerprint from the earlier read,
- **Then** the write is rejected with `conflict` (409) and the on-disk file is unchanged; re-reading yields a fresh fingerprint that allows the write.

## Requirements

### Functional Requirements

**Resource model**

- **FR-001**: System MUST register each known local agent as a Resource of kind `agent`, identified by `agent:<name>` per spec mcp-gateway's `<kind>:<name>` convention.
- **FR-002**: System MUST validate agent configuration against a kind-specific schema with fields `type` (enum) and `config_dir` (path, optional absolute-path override; when omitted it defaults to the type's standard location — `~/.claude` for `claude_code`, `~/.codex` for `codex`). Skills are delivered to `<config_dir>/skills`.
- **FR-003**: System MUST support the agent types `claude_code` and `codex`; registering any type outside the manifest (e.g. the `claude_desktop` chat app, a Gemini CLI) is rejected with `unprocessable_entity` (422). Per-type behaviour is defined by the capability manifest (`AGENT_DESCRIPTORS`), so adding a type is adding one enum value + one descriptor record (plus, where the product's wire protocol is new, one chat-provider adapter). Each supported type covers both the CLI and the app/IDE form of that product, which share one config directory.

**Agent capability matrix (FR-003a).** Both supported types support every facet, so the matrix records **how** each facet is realised per product, not whether it exists. There is no per-facet "not supported" state on the agent surface, and no capability booleans on the wire — a facet a type could not support would be a reason not to add that type.

| Agent | config dir | chat provider (spec channels) | Coffer-MCP inject (FR-019) | provider projection (spec provider-switching) |
| --- | --- | --- | --- | --- |
| `claude_code` | `~/.claude/` | Claude Agent SDK | `mcpServers` JSON | `apiKeyHelper` |
| `codex` | `~/.codex/` | `codex app-server` | `[mcp_servers]` TOML | `[model_providers]` env_key |

**Why only these two.** The registry briefly carried four more products — `opencode`, `hermes`, `cursor`, `openclaw`. They are removed. None of them was installed on the maintainer's own machine, so every facet was written against upstream documentation and one-off probes and could never be regression-tested locally: each change to a core mechanism meant blind-editing six code paths at once. A product Coffer cannot actually exercise costs more to carry than it returns. Their removal also removed the per-facet capability matrix the four types made necessary. Re-adding a product is adding one enum value plus one descriptor record — worth doing when that product is genuinely in use, not before.

**Discovery (detection = discovery + confirm)**

- **FR-004**: System MUST provide a read-only discovery operation that scans well-known install markers for each supported agent type and reports installed types that are not already registered as **candidates** (each carrying `type`, `display_name`, `config_dir`, `default_skill_dir`, and `suggested_name`). Discovery MUST NOT register anything automatically — the user reviews candidates and confirms which to add. The daemon MUST NOT auto-register agents on startup.
- **FR-005**: A removed agent MUST re-appear as a discovery candidate on subsequent scans while its install marker is present — a removal is not permanent (it may be accidental). System MUST NOT keep a "suppressed types" list.

**Lifecycle**

- **FR-006**: Users MUST be able to register, list, view, update (config_dir, description), and remove agents. Agents have **no enable/disable concept** — a registered agent is simply present; there is no enabled/disabled state on the agent surface. The agent name is optional at registration — when omitted, System MUST derive a stable per-type default (underscores become hyphens, e.g. `claude_code` → `claude-code`).
- **FR-007**: At registration System MUST auto-create the `<config_dir>/skills` subdirectory, then validate that the resolved `config_dir` exists, is a directory, is writable, and is not a privileged system path before accepting the value. Skills are delivered to `<config_dir>/skills`.
- **FR-008**: System MUST reject registration that would create a duplicate `agent:<name>`, and MUST reject registering more than one agent for the same config directory. `config_dir` is derived from the agent type, so each supported type — and thus each on-disk config directory — may be registered at most once; a second attempt is rejected with `conflict` (409) and nothing is persisted.

**Config files**

- **FR-013**: Each supported agent type MUST define a curated allowlist of config files (in its capability-manifest record), each entry carrying a stable `key`, a display name, a resolved absolute path, and a `format` (`json`, `toml`, `markdown`, or `text`). Claude Code → `settings.json`, `settings.local.json`, `~/.claude.json`, `CLAUDE.md` (key `instructions`), and the `agents/` directory entry (FR-034); Codex → `config.toml`, `AGENTS.md` (key `instructions`), and `hooks.json`. The former `memory` key of Claude Code/Codex is renamed `instructions` — those files are human-authored instructions, distinct from agent-written memory (spec knowledge's domain).
- **FR-014**: Users MUST be able to list an agent's config files with, for each, its key, display name, path, the containing-folder absolute path (`folder_path`), format, and existence (plus size and modified time when the file exists). The `path`/`folder_path` pair feeds the UI's open-in-external-editor / reveal-in-file-manager affordances (FR-038).
- **FR-015**: Users MUST be able to read the content of any allowlisted config file. A file that does not exist reads as empty content with `exists=false` and is not created by the read.
- **FR-016**: The system MUST expose a write (save) for the content of any allowlisted config file through the in-app editor, the REST API and the `coffer agent` CLI — one endpoint serving all three. The content MUST be validated against the file's `format` before any write; malformed `json`/`toml` MUST be rejected (`unprocessable_entity`, 422) and the on-disk file left unchanged. `markdown`/`text` files accept any content.
- **FR-017**: Writes MUST be atomic (temp file + rename) and MUST keep a `.bak` copy of the prior content so a bad edit is recoverable; each successful write MUST record an `agent_config_file_written` audit entry. The Coffer-MCP install/uninstall operations (FR-022) reuse the same atomic-write + `.bak` machinery.
- **FR-018**: Config-file read and write MUST be addressable only by allowlisted `key` (never by caller-supplied path); an unknown key returns `not_found` (404) and performs no filesystem access.

**Coffer MCP install**

- **FR-019**: Users MUST be able to install Coffer's own MCP server into an agent in one action. The install writes a `coffer` stdio MCP-server entry into the agent's MCP config, using the shape declared by that agent's manifest `McpInjectionSpec` — `mcpServers.coffer` in `~/.claude.json` (`claude_code`); `[mcp_servers.coffer]` in `~/.codex/config.toml` (`codex`). `command` is the absolute path of the `coffer-mcp-shim` binary (resolved on `PATH`, then the running interpreter's scripts directory — so a venv-installed shim is found even when the daemon's `PATH` lacks the venv — then the bundled binary; a `COFFER_MCP_SHIM_PATH` environment override takes precedence over all). The install additionally writes `--agent <name>` (the agent's registry name) as an argument of the shim invocation — in the entry shape's argument slot (`args` for command-map entries, appended to the `command` array for typed-array entries) — so the gateway can attribute the session to this agent for per-agent scope enforcement ([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)). If the shim cannot be resolved, install is rejected and nothing is written.
- **FR-020**: Install MUST be idempotent — re-installing updates the existing `coffer` entry in place and never creates a duplicate. System MUST expose a status operation reporting whether Coffer's MCP is currently installed for the agent.
- **FR-021**: Users MUST be able to uninstall Coffer's MCP, removing the `coffer` entry from the agent's MCP config. Uninstalling when not installed is a no-op success.
- **FR-022**: Install and uninstall MUST reuse the atomic-write + `.bak` machinery from FR-017 and record an audit entry (`agent_mcp_installed` / `agent_mcp_uninstalled`).

**Agent MCP entries (workspace amendment)**

- **FR-025**: System MUST parse and list the MCP server entries configured in the agent's own files — for `claude_code` from both `~/.claude.json` `mcpServers` and `settings.json` `mcpServers` (each entry labelled with its source file); for `codex` from `config.toml` `[mcp_servers.*]`. Each entry carries name, source, transport (stdio command or HTTP URL), the `enabled` flag where the format defines one (Codex), `is_coffer` for Coffer's own gateway entry, and `matches_resource` naming an equivalent registered `mcp_server` resource when one exists. Entries are derived at read time, never stored.
- **FR-028**: Users MUST be able to adopt a direct MCP entry into Coffer. Adoption (a) registers the entry as an `mcp_server` resource through the standard resource flow (schema validation + audit), (b) verifies the resource reads back, then (c) removes the entry from its source file — disambiguated by the caller for `claude_code` when both files carry the name, using the FR-017 atomic-write + `.bak` machinery — strictly in that order. Any failure stops the operation, rolls back a created resource, and leaves the agent's config byte-identical; audited as `agent_mcp_entry_adopted` on success. A name collision with an existing resource is rejected with `conflict` (409) carrying a suggested alternative; an entry equivalent to an existing resource is reported via `matches_resource` so the user can remove the duplicate instead. The `coffer` entry is never adoptable.
- **FR-029**: Adoption MUST NOT persist secret values into resource config. When an entry's environment carries values under secret-like keys (`TOKEN`, `KEY`, `SECRET`, `PASSWORD` patterns), the adopt request MUST supply a keychain mapping for each flagged key or be rejected with the unresolved keys listed. Mapped values are stored in the OS keychain through the daemon (per the credentials invariant); the resource config carries references only.
- **FR-030**: When an agent config file cannot be parsed, the affected facet MUST degrade to an explicit parse-error state (file path + parser error) without failing the surrounding view, and entry-level writes against that file MUST be rejected until it parses again.

**Not provided: editing the agent's own MCP entries.** Coffer once offered a standalone remove (`agent_mcp_entry_removed`) and a Codex-only `enabled` toggle. Both are gone; only the listing (FR-025), adoption (FR-028/FR-029), and the parse-error degradation (FR-030) remain. What remains is the half only Coffer offers: surfacing the MCP servers that bypass its gateway, and pulling one into the hub with its secrets mapped into the vault. What went was the half the agent's own UI already does — while performing the most fragile action in this spec, hand-writing another tool's private config format. For `claude_code` the toggle was never anything but a 422: that format has no per-entry flag. Adoption still removes the source entry it adopted; it owns that write end-to-end, and rolls it back with the rest of the operation when anything fails.

**Plugins (workspace amendment)**

- **FR-031**: System MUST list an agent's installed plugins with enabled state, grouped by marketplace. The listing is **read-only** — it writes nothing, to the documented surface or to any internal state file. For `codex` the listing derives from `config.toml` (`[plugins."<name>@<marketplace>"]`, `[marketplaces.*]`) plus presence of the documented cache directory `~/.codex/plugins/cache/<marketplace>/<plugin>/`; for `claude_code` the inventory derives from `~/.claude/plugins/installed_plugins.json` and `known_marketplaces.json`, with enabled state from `settings.json` `enabledPlugins`. A plugin configured without its cache is flagged `cache_present=false`; no repair is attempted. The listing is exposed through the REST API (`GET /api/v1/agents/{name}/plugins`) and the `coffer agent plugin list` CLI **only**: the web UI has no Plugins tab, so this route is a backend data source with no UI on top of it. Plugin installation, enable/disable, uninstall, and marketplace management are not provided by Coffer; all of them remain with the agent's own tooling.

**Not provided: writing plugin state.** Coffer once offered enable/disable (`agent_plugin_toggled`) and uninstall (`agent_plugin_uninstalled`, delegating to `claude plugin uninstall` for `claude_code` and deleting the entry plus its cache directory for `codex`), carried in the manifest as `can_toggle` / `can_uninstall` / `uninstall_strategy`. All of it is gone. Those ~500 lines wrote another tool's private format and wrapped another tool's CLI: an upstream format change would have silently corrupted a user's config, whereas a read-only parse of the same files degrades, at worst, to FR-030's explicit parse-error state. And the operation they replaced is one command — typing the vendor's own `claude plugin disable …` is faster than finding Coffer's proxy of it.

**Directory config entries (workspace amendment)**

- **FR-034**: A config-file allowlist entry MAY be a **directory entry** (`kind=directory`): it resolves to a directory and lists its files (entry-relative path, size, modified time) instead of carrying content. The directory entry for Claude Code is `agents/` (one Markdown file per personal subagent, nested paths allowed). A missing directory lists as `exists=false` with no files; the read never creates it.
- **FR-035**: Users MUST be able to read individual files inside a directory entry; this read backs the UI's editor. Write (create-on-write) and delete of individual files are available through the in-app editor, the REST API and the `coffer agent` CLI. Child paths are validated server-side before any filesystem access: they MUST resolve inside the entry's directory (no `..`, no absolute paths, no symlink escape) and carry the `.md` extension. Writes reuse FR-017's machinery; deletion preserves the prior content as `.bak`. Audited as `agent_config_file_written` / `agent_config_file_deleted`.
- **FR-036**: Config-file reads (single files and directory children) MUST return a content fingerprint; writes MUST carry it back and are rejected with `conflict` (409) when the on-disk content changed since the read, leaving the file untouched.
- **FR-037**: When an instructions file contains a managed block defined by another feature — the knowledge layer's memory-projection block — the editor MUST annotate that the block is owned by that feature. Each block uses its own distinct markers and is rewritten independently; the marker format is owned by the defining feature.

**Not provided: native memory (removed)**

The registry once reached into the coding agent's OWN native per-project memory — distinct from the `instructions` config files of FR-013 (CLAUDE.md / AGENTS.md are human-authored instructions; that was the agent's self-written memory store). FR-040 exposed a read-only scan of those stores (Claude Code's `<config_dir>/projects/<slug>/memory/`; Codex's global task-grouped `<config_dir>/memories/MEMORY.md` sliced by routed cwd) and FR-041 imported one store into the matching Coffer project memory's `knowledge/inbox/` lane, handing the facts to spec knowledge's organizer. Both are gone, with the `/api/v1/agents/{name}/native-memory*` routes, the `coffer agent native-memory` / `coffer agent import-native-memory` commands, the web Memory tab, and the decision record that introduced native-memory scanning.

The reason is use, not design: the feature shipped and was never used. The one artefact that would have shown otherwise — `memory_store_project_roots` — was populated entirely by the ordinary scope resolver, never by an import. Nothing in this spec now reads or writes an agent's native memory store.

**Not provided: lifecycle hooks and session-context injection (removed)**

Three requirements are gone together. FR-043 installed a `coffer-hook` command entry into the agent's hooks file (`settings.json` for `claude_code`, `hooks.json` for `codex`) and could uninstall it and report its status. FR-044 served that hook a **rules bundle** over `GET /agents/{name}/session-context` — the session's project and global rules plus two seeded built-in rules — for the agent to inject as additional context at SessionStart. FR-046 exposed `disable_native_memory`, which turned the agent's own write-side memory off in lockstep with the persisted flag (`autoMemoryEnabled` for Claude Code, `features.memories` for Codex). With them go the `coffer-hook` binary, its PyInstaller target and console script, the `hook-install` and `session-context` routes, the `surfaces/hook/` entry point and the hook service / resolver / install domain, `coffer agent hook …`, the manifest's `ContextInjectionSpec` facet, the `disable_native_memory` config field, and the four audit events `agent_hook_installed` / `agent_hook_uninstalled` / `agent_native_memory_disabled` / `agent_native_memory_restored`. The decision record behind the SessionStart hook and its rules bundle is deleted with them.

The reason is the same as native memory's: it shipped and was never installed. `~/.claude/settings.json` carried only third-party hooks, and the built `coffer-hook` binary sat in `~/.coffer/bin/` referenced by nothing.

**What this costs, stated plainly.** This removes the *delivery* half of cross-agent memory. Knowledge still goes in — `coffer__remember`, the organizer, the knowledge base — but nothing pushes it into a session any more. An agent that wants prior context must call `coffer__recall` (or `coffer__resume`) itself, and an agent that never calls it starts every session cold. That is a real loss, and it is accepted deliberately rather than overlooked: an injection path that no agent on the maintainer's machine had installed was delivering nothing anyway, and a delivery mechanism is worth rebuilding only against a hook that is actually in place.

**Surfaces**

- **FR-009**: Every management operation — register/list/view/update/remove, config-file list/read/write (including directory children), Coffer-MCP install/uninstall/status, MCP entry list/adopt, plugin list — MUST be available through (a) the REST API and (b) the `coffer agent ...` CLI. The Agents page in the web UI MUST expose all of these EXCEPT config-file content writes (single files and directory children) and the plugin listing: in the UI, config files and directory children are **read-only** with open-in-external-editor / reveal-in-file-manager affordances (FR-038), while the REST API and CLI keep the programmatic write/create/delete path; the plugin listing (FR-031) is REST + CLI only and has no UI. The agent detail page has four tabs — Overview, Skills, MCP servers, and Config files.
- **FR-010**: The CLI MUST support `--json` for machine-readable output on every read operation.
- **FR-038**: For each config file (and each directory-entry child) the UI MUST offer **open-in-external-editor** and **reveal-in-file-manager** actions on the file, using the `path` from FR-014/FR-015. Open and reveal perform the real OS action through the daemon filesystem-action endpoints (FR-039), since the loopback daemon is always on the user's own machine (ADR daemon-proxies-os-file-actions). There is no copy-path fallback. The editor used for open-in-external-editor references the user's "preferred external editor" preference defined by spec ui-shell (not re-specified here).

**Observability**

- **FR-011**: System MUST record an audit entry for every lifecycle event: agent created, updated, removed; config file written/deleted (`agent_config_file_written` / `agent_config_file_deleted`); Coffer MCP installed/uninstalled; MCP entry adopted (`agent_mcp_entry_adopted`). (Agents have no enable/disable concept; discovery and all workspace listings — MCP entries, plugins, config files — are read-only and emit no audit event.)
- **FR-012**: System MUST expose a read-only discovery operation listing installed-but-unregistered agents as candidates, available from the REST API (`GET /api/v1/agents/candidates`), the `coffer agent detect` CLI, and the Agents page in the web UI.

**Config-directory picker**

- **FR-023**: When choosing a custom `config_dir`, the web UI MUST offer a folder picker rather than requiring the user to type a path. It MUST use the daemon native directory dialog (FR-042), falling back to the daemon-backed folder browser (FR-024) only when the host has no native dialog tool. Both yield an absolute path that is then validated per FR-007 before registration.
- **FR-024**: System MUST expose a read-only filesystem-browse operation (`GET /api/v1/fs/browse`) that, given a directory path (defaulting to the user's home), returns that path, its parent, and its immediate subdirectories. It MUST NOT return file contents and MUST be guarded by the same loopback + token auth as all other daemon routes.
- **FR-042**: System MUST expose ONE native OS dialog through the loopback daemon — the **folder** picker, `POST /api/v1/fs/pick-folder` — so the web surface opens the host's real directory chooser instead of requiring a typed path. It opens the host's native dialog (macOS `osascript`; Linux `zenity`/`kdialog`), invoked with a fixed argument vector (no shell interpolation), and returns `{ available, path }`: `available=false` when the host has no native dialog tool, `available=true` with `path=null` on cancel, otherwise the chosen absolute path. When `available=false` the caller degrades to the in-app browser (FR-024). It creates nothing and is guarded by the same loopback + token auth as every daemon route.

**Not provided: native open-file and save-file dialogs.** `POST /api/v1/fs/pick-file` and `POST /api/v1/fs/save-file` are removed, and the decision to proxy native open-file and save-file dialogs through the daemon with them. The browser already has both mechanisms natively: `<a download>` saves a file, and `<input type="file">` opens one — and the second is strictly better than a native dialog, because it hands the web surface the file's *contents* rather than a path the daemon must then go and read. A folder is the exception that keeps FR-042 alive: the browser deliberately withholds absolute paths, and registering an agent needs one. The removal also narrows the daemon's attack surface — for these two operations it no longer shells out to `osascript` / `zenity` at all, so its loopback surface executes one less class of local program.

**Filesystem open/reveal**

- **FR-039**: System MUST expose filesystem-action operations that let the web surface perform real open/reveal (FR-038) through the loopback daemon, which is always co-located with the web client on the user's machine (ADR daemon-proxies-os-file-actions): `POST /api/v1/fs/open` (open an existing absolute path in an application — a `with` editor preference, or the OS default) and `POST /api/v1/fs/reveal` (select / reveal an existing absolute path in the OS file manager). Both MUST validate the path is absolute and exists before acting, MUST invoke the OS launcher with a fixed argument vector (no shell interpolation), MUST create nothing, and MUST be guarded by the same loopback + token auth as all other daemon routes. A non-absolute or non-existent path is rejected (`FS_PATH_NOT_OPENABLE`, 400). Where a platform has no portable "select the file" primitive (Linux), reveal degrades to opening the containing folder. System MUST also expose `GET /api/v1/fs/editors`, which enumerates common GUI editors detected as installed on the host (macOS app-bundle names for `open -a`; Linux/Windows commands on PATH) so the spec ui-shell preferred-editor setting can offer a picker rather than a blind text field. It returns each editor's display label and the launcher `value` accepted by `/fs/open`'s `with`, reads nothing but app presence, and is guarded by the same loopback + token auth.

### Key Entities

- **Agent**: A Resource of kind `agent`. Represents one locally-installed AI agent. Config: `type` (supported enum), `config_dir` (optional absolute-path override; defaults to the type's standard location). Skills are delivered to `<config_dir>/skills`. Identified by `agent:<name>`. The `agent` kind declares no `scope`: a non-null value is rejected at validation (422) — an agent resource is what other kinds' scopes name, never itself a scope target ([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)).
- **Agent Type**: An enum value identifying a known agent product (`claude_code`, `codex`). Each value maps to a record in the **capability manifest** (`AGENT_DESCRIPTORS`) carrying its default `config_dir`, display name, install-marker (for discovery), curated **config-file allowlist**, **MCP injection shape**, and its provider-projection facet. Both supported products carry every facet; a product that could not would be a product not worth adding (FR-003a).
- **Agent Candidate**: A discovered installed-but-unregistered agent — `type`, `display_name`, `config_dir` (the type's default config directory), `default_skill_dir`, and `suggested_name`. Derived at scan time, never stored; the user confirms a candidate to register it.
- **Config File**: A curated, allowlisted file belonging to an agent type, identified by a stable `key`. Carries a display name, a resolved absolute path, its containing-folder absolute path (`folder_path`), a `format` (`json` / `toml` / `markdown` / `text`), and (when present) size and modified time. Surfaced in the UI for reading and editing (and for opening it / its folder in an external editor); read and written by key (in-app editor, REST, CLI), never by arbitrary path. Not persisted in SQLite — the file on disk is the source of truth.
- **Coffer MCP Install Status**: Derived (not stored) state for an agent: whether a `coffer` MCP-server entry is present in that agent's MCP config file.
- **Agent MCP Entry**: A derived (never stored) view of one MCP server configured in the agent's own files — name, source file, transport, `enabled` (Codex), `is_coffer`, `matches_resource`. The file is the source of truth; Coffer reads and adopts entries but keeps no copy, and edits an entry only as the removal step of an adoption.
- **Agent Plugin**: A derived (never stored) view of one installed plugin — id (`<name>@<marketplace>`), marketplace, enabled state, `cache_present`, plus best-effort manifest detail read from the plugin's install directory. Every input is read-only: the enabled state Coffer reports is the one each agent's documented config surface declares, and Coffer never writes it back.
- **Directory Config Entry**: An allowlisted config entry that resolves to a directory of files rather than a single file. Children are addressed by validated entry-relative paths; the directory on disk is the source of truth.

## Success Criteria

### Measurable Outcomes

- **SC-001**: On a machine with at least two supported agent install paths present, running discovery surfaces exactly those agents as candidates, and the user adds them with a single confirm each — no typing of type identifiers or paths.
- **SC-002**: From a fresh install, a user can register an additional agent with a custom `config_dir` and see it in `coffer agent list --json` within 60 seconds, without consulting documentation more than once.
- **SC-003**: Every Acceptance Scenario in this spec is covered by at least one test marked `acceptance(spec="agent-registry", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-004**: The full `make verify` suite passes locally and in CI; `make verify-all` (adding e2e) passes on macOS and Linux.
- **SC-005**: No `config_dir` value ever permits writing outside the directory itself (path-traversal check); validated by a dedicated security test.
- **SC-006**: A user can open an agent's `settings.json` (Claude Code) or `config.toml` (Codex) in Coffer, edit it and save it — or open it in their external editor instead; every save validates the content (a malformed save is rejected with the file left unchanged), keeps a `.bak` of the prior version, and is refused if the file changed on disk since it was read.
- **SC-007**: A user can install Coffer's MCP into a freshly-registered agent in one click and, after restarting that agent, the agent lists Coffer's aggregated tools; re-installing never duplicates the entry, and uninstall removes it.
- **SC-008**: The MCP tab lists exactly the entries present in the agent's real config files, and adopting a direct entry completes the full round trip — resource registered, gateway serving it, direct entry gone — in one user action plus at most one confirmation.
- **SC-009**: The plugin listing writes nothing: every file under the agent's config directory is byte-identical before and after a listing, including the agents' internal plugin state files.
- **SC-010**: No directory-entry operation can read or write a path outside its entry's directory; validated by dedicated security tests covering `..` traversal, absolute paths, symlink escape, and disallowed extensions.

## Assumptions

- The user runs Coffer on their own machine; there is no multi-tenant or remote-access requirement.
- Both agent types are wired in the capability manifest (`AGENT_DESCRIPTORS`) — `claude_code` and `codex` — each one `AgentType` enum value plus one record (install marker, config-file allowlist, MCP injection shape, and its facets). Adding a further product is the same one-record change, plus a chat-provider adapter when its wire protocol is new; a product whose facets Coffer cannot exercise on a real install is not added (FR-003a).
- Each supported agent's CLI and app/IDE form read one shared config directory (`~/.claude/` and `~/.codex/`), so Coffer manages one config set per agent.
- Config files are surfaced as raw text the user can read and edit in place, with the validate + atomic-write + `.bak` safety net on every save, whichever surface issues it. Open-in-external-editor stays alongside as the escape hatch for the long tail; recurring structured needs graduate into facets (MCP entries, plugins) per the workspace amendment. The credential/state file `~/.codex/auth.json` is intentionally excluded from the allowlist.
- The agents' internal state files (`~/.claude.json` beyond its `mcpServers` map, `~/.claude/plugins/*.json`, Codex's `[marketplaces.*]` / `[hooks.state.*]` / `[projects.*]` tables) are read as inputs where needed and never written by the workspace facets; the documented configuration surfaces verified against each vendor's docs are the only write targets. In practice (verified on a real machine) user-scope Claude Code MCP servers live in `~/.claude.json` `mcpServers` and may also appear in `settings.json` `mcpServers` — both are parsed.
- Workspace facets follow the ingest → hub → deliver principle: shareable content found in an agent's workspace is adoptable into Coffer's hub (MCP gateway here; the master skill store via spec skill-manager's companion amendment) rather than managed as per-agent one-offs. Cross-machine sharing of the hub itself is a future spec (and constitutional amendment); these facets are designed so their state serializes to declarative manifests when that lands.
- Agents store their skill libraries on the local filesystem under `<config_dir>/skills`. Web-only agents (e.g., claude.ai) are out of scope for v1 and require a future spec to add API-based sync.
- The kind-agnostic Resource framework, audit log, and `<kind>:<name>` identity scheme defined by spec mcp-gateway are in place.
- The application shell from spec ui-shell — sidebar IA, layout, routing skeleton, and design system — is in place. The Agents page renders within that shell at `/agents` as a **dedicated top-level nav entry** (a sibling of the Resources and System groups, **not** nested under Resources — agents are consumers of vault assets, not assets themselves). Agent resources do not appear in the kind-agnostic resources/MCP browser, which lists only kinds that register a resource-card UI.
- Skill bindings (i.e., the relationship between an agent and a particular skill) are introduced and managed by spec skill-manager; spec agent-registry does not define skill operations beyond exposing an `on_delete` hook for cascade cleanup.
