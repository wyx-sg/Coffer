# Feature Specification: Agent Registry

**Status**: Accepted
**Input**: User description: "Manage which locally-installed AI agents Coffer knows about, so later features (skills, memory, knowledge bases) can deliver assets to them. Each agent is a Resource of kind `agent` in the kind-agnostic Resource framework introduced by spec mcp-gateway. v1 supports two agent types: Claude Code and OpenAI Codex — each covering both its CLI and its desktop/IDE form, which share one on-disk config. Beyond registering agents, the user can view and edit each agent's known config files, or open them in an external editor, install Coffer's own MCP server into an agent with one click, and see which models that agent can be put on."

> **Note on agent types.** Supported products: **Claude Code** (`claude_code`) and **OpenAI Codex** (`codex`). Each spans its CLI _and_ its app/IDE form because they read one shared config directory. This spec holds what the two share. Everything that differs by type — where the config directory is, which files are allowlisted, the MCP entry shape, the plugin inventory, the model catalogue's sources, the native-memory layout, the transcript location — lives in a child spec: [`agent-registry/claude-code`](claude-code/spec.md) and [`agent-registry/codex`](codex/spec.md). Each child is the reading of one `AGENT_DESCRIPTORS` record, the single per-type table in the code. Adding a product is one enum value, one descriptor record, and one child spec. The separate **Claude Desktop** chat app (its own `~/Library/Application Support/Claude/` config) is out of scope.

> **Workspace amendment.** Stories 9–12 extend the registry into the agent's real on-disk workspace: the MCP servers actually configured in the agent's own files, the agent's installed plugins, and directory-type config entries. The guiding principle is **ingest → hub → deliver**: anything shareable found in an agent's workspace can be adopted into Coffer's hub (the MCP gateway, the master skill store of spec skill-manager) and delivered back to any agent, instead of living as per-agent one-off config. All writes go through each agent's documented configuration paths only; internal state files are read, never written.

> **Note on the built-in agent ([Built-in Agent Is Internal](../../../docs/decisions/builtin-agent-is-internal-capability.md)).** This registry holds only **managed** agents — locally-installed external coding agents that Coffer delivers assets to. The former `builtin` "Coffer Assistant" is **not** a registered agent here: that decision retires it as a chat persona and recasts its local model as an internal Coffer capability reached only through `coffer__*` MCP tools.

## User Scenarios & Testing

### User Story 1 — Discover installed agents and choose which to add (Priority: P1)

A developer opens the Agents page (or runs `coffer agent detect`); Coffer scans each supported type's install marker and presents what it finds and has not registered as **candidates**. The developer confirms which to add — Coffer never registers an agent silently.

**Independent Test**: On a machine with both types installed, run detection, observe both offered as candidates, confirm them, observe both registered.

### User Story 2 — Manually register an agent with a custom path (Priority: P1)

Some users install agents in non-default locations or have several installs (work vs personal). They add an agent by type, optionally overriding the config directory. The name is optional — when omitted Coffer derives a stable per-type default. When choosing a custom path the web UI offers a folder picker — the host's native directory dialog, opened through the local daemon — so the user picks a real directory instead of typing it.

**Independent Test**: Register a `codex` agent named `codex-work` with `--config-dir /custom/path`; list agents; observe the manually-registered entry. From the web form, add an agent with no name and observe the per-type default name.

### User Story 3 — Edit or remove an agent (Priority: P1)

Installed agents change over time. The user updates the config_dir or description, or deletes the agent. (Agents have no enable/disable concept — a registered agent is simply present.)

**Independent Test**: Register an agent, update its config_dir, then remove it; verify each state is persisted and audited.

### User Story 4 — Manage agents through the web UI (Priority: P2)

The user opens an "Agents" page listing every registered agent with type, name, and config_dir, and can add or edit from a form.

**Independent Test**: Agents → add Codex with its default path → observe in list → open it → change config_dir → save → list updates.

### User Story 5 — Same operations from the command line (Priority: P2)

The user scripts registry setup (dotfiles, CI machines). Everything available in the UI is available as `coffer agent ...` subcommands with `--json` output.

**Independent Test**: A bash script registers two agents, lists them in JSON, edits one, removes one — all without touching the GUI.

### User Story 6 — Audit registry changes (Priority: P3)

Every add / edit / remove is recorded with timestamp and actor, queryable from CLI and UI.

**Independent Test**: Make several changes; view the audit log; observe one row per change with actor and event type.

### User Story 7 — View an agent's config files and open them in an external editor (Priority: P2)

The user wants to see that agent's own configuration files inside Coffer, without leaving the app to hunt for dotfiles. Coffer shows the type's curated set, lets the user open one, read it and **edit it in place**. Saving validates against the file's format first, then writes atomically keeping a `.bak`, so a bad edit is both refused early and recoverable. Because these files are also edited outside Coffer, a save carries the fingerprint of the content it started from and is refused rather than applied when the file changed underneath it (FR-029). For each file Coffer also offers open-in-external-editor and reveal-in-file-manager.

**Independent Test**: Register an agent; list its config files; open one, observe the response surfaces the file's `path`, containing-folder `folder_path` and a content `fingerprint`; edit and save it, and observe the new content reads back; open a not-yet-created file and observe it reads as empty without being created.

### User Story 8 — Install Coffer's MCP into an agent in one click (Priority: P2)

From the agent's management view the user clicks "Install Coffer MCP", and Coffer writes its own MCP-server entry into that agent's MCP config — a `coffer` stdio entry pointing at the `coffer-mcp-shim` binary. A status indicator shows whether Coffer is currently installed, and the user can uninstall to remove the entry.

**Independent Test**: Register an agent with Coffer not yet installed; check status (not installed); install; observe the entry written with an absolute `command` path to the shim; check status (installed); install again (no duplicate); uninstall; observe the entry removed.

### User Story 9 — See and manage the agent's real MCP servers (Priority: P2)

The user wants to see what their agent **actually** has configured: every MCP server entry in the agent's own config files. Each entry shows its transport (stdio command or HTTP URL), which file it came from, and its enabled state where the format defines one. From the same table the user can **remove** an entry — one that duplicates something already in Coffer, or one that simply should not be there — written through the same atomic + `.bak` machinery adoption uses. What Coffer does not offer is editing an entry in place. Coffer's own `coffer` entry is rendered specially and managed by Story 8's actions.

**Independent Test**: Register an agent whose config carries several MCP entries; open the MCP tab; observe exactly those entries with transports and source files; remove one and observe it gone from the file, with a `.bak` of the prior content kept.

### User Story 10 — Adopt a direct MCP server into Coffer (Priority: P2)

A direct MCP entry in one agent benefits that agent alone. The user clicks "Adopt into Coffer": Coffer registers it as an `mcp_server` resource (so it is served to **every** agent through the gateway) and removes the now-redundant direct entry. If the entry's environment carries secret-looking values, Coffer routes them into the OS keychain and stores references only. If an equivalent resource already exists, Coffer offers to just remove the duplicate direct entry.

**Independent Test**: With an agent carrying a direct stdio entry, adopt it; observe a new `mcp_server` resource registered, the direct entry removed, and the gateway serving the upstream's tools to all agents.

### User Story 11 — Manage the agent's plugins (Priority: P2)

Every installed plugin appears in a single table — the marketplace it came from is a column, not a per-marketplace section — with its enabled state and whether its on-disk cache is present. Each row expands to reveal the plugin's manifest detail and the skills, commands, and MCP servers it bundles, read read-only from the plugin's install directory. Because those components belong to the plugin, they surface here rather than on the agent's Skill / MCP pages, which list only the agent's own standalone resources. The facet is generalised through the capability manifest — each agent record carries a `PluginCapability` (a plugin-model discriminator, the write-surface allowlist key, and `can_toggle`/`can_uninstall` flags), so the service dispatches on data rather than per-agent branches. Installing new plugins and managing marketplaces stay with the agent's own tooling.

**Independent Test**: Register an agent with plugins configured; open the Plugins tab; observe the plugins with their marketplace and enabled state; disable one and observe only the documented location written; uninstall one and observe it gone.

### User Story 12 — Manage directory-type config entries (Priority: P2)

Some agent configuration is a directory of prose files, not a single file. The user expands such an entry in the config-files tab and sees its files, opening one to read and edit it (with open-in-external-editor / reveal for the child file and its folder). Creating, writing, and deleting individual files is available through the in-app editor and the REST API / `coffer agent` CLI — with the same validation, atomic-write, and `.bak` safety net as single-file entries.

**Independent Test**: List a directory entry's files; create one; delete one; observe each reflected in the next listing and audited.

### User Story 13 — See which models an agent can be put on (Priority: P2)

A model is a field of the AGENT, not of the connection that serves it, so the agent record carries the model binding and the agent's page is where the choices are read back. Coffer names no model of its own: the list comes from the installed agent — its own catalogue, its own reasoning-effort levels — so a model released after Coffer shipped is offered the day the agent knows about it, with no Coffer release at all.

**Independent Test**: With an agent installed and registered, read its model catalogue; observe the entries the installed agent reports with their labels and effort levels; make one source unavailable and observe the catalogue lose exactly that source's entries rather than failing.

### Edge Cases

- **Discovery on a second scan**: Already-registered types are not offered as candidates; discovery never duplicates existing entries.
- **User deletes an agent**: A removal is not permanent. The next scan re-surfaces that agent as a candidate; Coffer keeps no suppression list.
- **Agent type not in the supported list**: Registration rejected with a clear message and the supported-type list.
- **`config_dir` path doesn't exist or isn't writable**: Registration rejected; no partial state.
- **`config_dir` points to a privileged path** (`/etc`, `/usr`, etc.): Registration rejected.
- **Duplicate name within `agent` kind**: Rejected by the kind-agnostic Resource framework.
- **Config-file key not in the type's allowlist**: Read rejected with `not_found` (404); no filesystem access for an unknown key.
- **Config file does not exist yet**: Listed and readable as `exists=false` with empty content; the read never creates the file.
- **Coffer MCP install when already installed**: Idempotent — the `coffer` entry is updated in place, never duplicated; status remains `installed`.
- **Coffer MCP uninstall when not installed**: No-op success; status reports `not_installed`.
- **`coffer-mcp-shim` binary cannot be resolved**: Install rejected with a clear error naming the missing binary; nothing is written to the agent's config.
- **Agent config file fails to parse**: The affected facet (MCP entries, plugins) shows an explicit parse-error state and degrades to read-only; other facets and tabs are unaffected. Writes against the broken file are rejected until it parses again.
- **Coffer's own `coffer` MCP entry**: Never adoptable, never listed as a plain direct entry — it is the gateway's install state, managed by Story 8's install/uninstall.
- **Adoption requested for an entry equivalent to an existing resource**: Coffer reports the match (`matches_resource`) and offers removing the redundant direct entry instead of creating a duplicate resource.
- **Plugin configured but cache directory missing**: Listed with `cache_present=false` so the user sees the drift; Coffer does not attempt repair — reinstalling, like every other plugin write Coffer does not own, is the agent's own tooling.
- **The agent's own process rewrites a config file between Coffer's read and write**: The write is rejected as stale (fingerprint mismatch, 409); the user re-reads and retries. The `.bak` of every Coffer write keeps the prior content recoverable in the reverse race.
- **Instructions file contains a leftover memory-projection managed block**: Nothing writes that block any more — native projection was retired and its table dropped — so the editor annotates it as a leftover that is safe to delete rather than as something another feature will rewrite.
- **A model-catalogue source is unavailable** (its CLI is not installed, its layout changed, the agent is unauthenticated or wedged): that source contributes nothing and the catalogue still answers with what the others found. An unknown `agent_key` is a 404.

## Acceptance Scenarios

Per `.agents/sdd.md` and `.agents/testing.md`, every scenario in this section is referenced by at least one test marked `@pytest.mark.acceptance(spec="agent-registry", scenario="…")` (Python) or `acceptance("agent-registry", "…", …)` (TypeScript). Scenarios that assert something only one agent type can do live in that type's child spec and carry the child's spec id.

### Scenario: discover installed agents as candidates

- **Given** a Coffer install with a supported agent's install marker present and no agent registered,
- **When** the user runs discovery,
- **Then** Coffer reports that type as a candidate (type, display name, default config dir, suggested name) and registers nothing — discovery is read-only.

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

### Scenario: read an existing config file

- **Given** a registered agent whose `settings.json` exists,
- **When** the user reads that config-file key,
- **Then** Coffer returns the file's current text content, its format (`json`), and `exists=true`.

### Scenario: read a not-yet-created config file

- **Given** a registered agent whose instructions file does not exist on disk,
- **When** the user reads that config-file key,
- **Then** Coffer returns empty content with `exists=false` and does not create the file.

### Scenario: reject config-file key outside the allowlist

- **Given** a registered agent,
- **When** the user references a config-file key not in that agent type's curated allowlist,
- **Then** Coffer responds `not_found` (404) and performs no filesystem read.

### Scenario: save a config file with valid content

- **Given** a registered agent whose `settings.json` exists,
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

- **Given** a registered agent whose own config files define several MCP server entries including `coffer`,
- **When** the user lists the agent's MCP entries,
- **Then** Coffer returns every entry with its name, source file, transport (stdio command or HTTP URL), and the `enabled` flag where that format defines one, marks the `coffer` entry `is_coffer=true`, and stores nothing — the listing is derived from the file at read time.

### Scenario: degrade to read-only when MCP config is unparseable

- **Given** a registered agent whose MCP-bearing config file contains invalid JSON/TOML,
- **When** the user lists the agent's MCP entries,
- **Then** Coffer reports a parse-error state naming the file and the parser error instead of failing the request, and rejects entry-level writes against that file until it parses again.

### Scenario: remove a direct MCP entry

- **Given** a registered agent with a direct (non-Coffer) MCP entry,
- **When** the user removes that entry (carrying the source file where the type's entries may come from more than one),
- **Then** the entry is deleted from exactly its source file via an atomic write with a `.bak` of the prior content, an `agent_mcp_entry_removed` audit entry is recorded, and the next listing no longer shows it.

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

- **Given** a registered agent whose documented plugin surface defines marketplaces and plugins with their cache directories present,
- **When** the user lists the agent's plugins,
- **Then** Coffer returns every plugin with its `<name>@<marketplace>` id, enabled state, marketplace grouping, and `cache_present=true`, deriving everything from the documented files at read time.

### Scenario: flag a plugin whose cache is missing

- **Given** a registered agent whose plugin inventory references a plugin with no cache directory on disk,
- **When** the user lists the agent's plugins,
- **Then** that plugin is listed with `cache_present=false` and no repair is attempted.

### Scenario: toggle a plugin's enabled state

- **Given** a registered agent with an enabled plugin,
- **When** the user disables it,
- **Then** only that type's documented location is written, the agent's internal plugin state files are byte-identical before and after, and an `agent_plugin_toggled` audit entry is recorded.

### Scenario: browse an agent's transcript history with title, search, and sort

- **Given** a registered agent with several local transcript sessions across more than one project,
- **When** the agent's transcripts are listed with a search query, a project filter, and a sort key (`started_at`, `last_activity_at` or `message_count`),
- **Then** each returned session summary carries a derived title, message count, `started_at`, `last_activity_at`, and the session file's absolute source path; only sessions whose title or project path matches the search and whose project matches the filter are returned, ordered by the requested sort key and direction, and paged by `limit`/`offset` alongside the matched total — read-only, emitting no audit event and writing nothing.

### Scenario: read one of the agent's conversations

- **Given** a registered agent with a local transcript session listed by FR-040, whose turns include one carrying a pasted API key,
- **When** the user opens that session by the absolute source path the listing gave, with a turn window smaller than the session,
- **Then** Coffer returns the session's summary fields plus that window of turns with roles, text and timestamps — the pasted key redacted, an over-long turn cut to its start and flagged, and the whole file's turn count reported alongside the window — while a path outside the agent's own transcript directory is rejected as `not_found` (404), the same answer as a transcript that is gone; read-only, emitting no audit event and writing nothing.

### Scenario: browse one native memory store's files

- **Given** a registered agent with a native memory store listed by FR-039, holding Markdown files in the store directory and a subdirectory,
- **When** the user opens that store by the `memory_dir` the listing gave and then reads one file in it,
- **Then** Coffer returns the store directory as a tree (directories before files, paths relative to the store) and the file's contents with the absolute path that backs open / reveal, while a directory that is not one of this agent's stores — its sibling project directory included — and a path escaping the store are both rejected as `not_found` (404); read-only, emitting no audit event and writing nothing.

### Scenario: list a directory config entry's files

- **Given** a registered agent whose directory config entry contains Markdown files (possibly nested),
- **When** the user lists that config entry,
- **Then** Coffer returns the entry with `kind=directory` and its files (entry-relative path, size, modified time); a missing directory lists as `exists=false` with no files and is not created by the read.

### Scenario: create a file inside a directory entry

- **Given** a registered agent with a directory config entry,
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

- **FR-001**: System MUST register each known local agent as a Resource of kind `agent`, identified by the immutable `uid` the resource framework mints for it ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)). Its name is a mutable label, unique within the kind, and every reference another kind holds to an agent — a resource `scope`'s agent list, a channel's `default_agent`, the `--agent-uid` the shim reports — holds the uid, so renaming an agent breaks nothing.
- **FR-002**: System MUST validate agent configuration against a kind-specific schema with fields `type` (enum) and `config_dir` (path, optional absolute-path override; when omitted it defaults to the type's standard location, which that type's child spec names). Skills are delivered to `<config_dir>/skills`.
- **FR-003**: System MUST support the agent types `claude_code` and `codex`; registering any type outside the manifest (e.g. the `claude_desktop` chat app, a Gemini CLI) is rejected with `unprocessable_entity` (422). Per-type behaviour is defined by the capability manifest (`AGENT_DESCRIPTORS`), so adding a type is one enum value, one descriptor record and one child spec (plus, where the product's wire protocol is new, one chat-provider adapter). Each supported type covers both the CLI and the app/IDE form of that product, which share one config directory.

**How each facet is realised, per type.** The per-facet *capability matrix* is retired: it existed to say which of six products supported which facet, and with two products that both support every facet there is nothing left to answer. What a facet looks like for one type is that type's child spec, which is a reading of `AGENT_DESCRIPTORS` — the one per-type table in the code. There is no per-facet "not supported" state on the agent surface and no capability booleans on the wire; a facet a type could not support would be a reason not to add that type. (The `PluginCapability` flags of FR-025/FR-026 are the one exception, and they are per-facet *runtime availability* — whether the agent's own uninstall command is on `PATH` — not a per-type support claim.)

**Why only these two.** The registry briefly carried four more products — `opencode`, `hermes`, `cursor`, `openclaw`. They are removed. None of them was installed on the maintainer's own machine, so every facet was written against upstream documentation and one-off probes and could never be regression-tested locally: each change to a core mechanism meant blind-editing six code paths at once. A product Coffer cannot actually exercise costs more to carry than it returns. Their removal also removed the per-facet capability matrix the four types made necessary. Re-adding a product is one enum value, one descriptor record and one child spec — worth doing when that product is genuinely in use, not before.

**Discovery (detection = discovery + confirm)**

- **FR-004**: System MUST provide a read-only discovery operation that scans each supported type's install marker — named in that type's child spec — and reports installed types that are not already registered as **candidates** (each carrying `type`, `display_name`, `config_dir`, `default_skill_dir`, and `suggested_name`). Discovery MUST NOT register anything automatically — the user reviews candidates and confirms which to add. The daemon MUST NOT auto-register agents on startup.
- **FR-005**: A removed agent MUST re-appear as a discovery candidate on subsequent scans while its install marker is present — a removal is not permanent (it may be accidental). System MUST NOT keep a "suppressed types" list.

**Lifecycle**

- **FR-006**: Users MUST be able to register, list, view, update (config_dir, description), and remove agents. Agents have **no enable/disable concept** — a registered agent is simply present; there is no enabled/disabled state on the agent surface. The agent name is optional at registration — when omitted, System MUST derive a stable per-type default (underscores become hyphens, e.g. `claude_code` → `claude-code`).
- **FR-007**: At registration System MUST auto-create the `<config_dir>/skills` subdirectory, then validate that the resolved `config_dir` exists, is a directory, is writable, and is not a privileged system path before accepting the value.
- **FR-008**: System MUST reject registration that would create a duplicate agent name (409 `conflict`, as for any kind — the label is unique within its kind even though it is not the identity), and MUST reject registering more than one agent for the same config directory. `config_dir` is derived from the agent type, so each supported type — and thus each on-disk config directory — may be registered at most once; a second attempt is rejected with `conflict` (409) and nothing is persisted.

**Config files**

- **FR-009**: Each supported agent type MUST define a curated allowlist of config files in its capability-manifest record, enumerated by that type's child spec, each entry carrying a stable `key`, a display name, a resolved absolute path, and a `format` (`json`, `toml`, `markdown`, or `text`). Each type's human-authored instructions file carries the key `instructions` — those files are instructions a person wrote, distinct from agent-written memory (spec memory's domain).
- **FR-010**: Users MUST be able to list an agent's config files with, for each, its key, display name, path, the containing-folder absolute path (`folder_path`), format, and existence (plus size and modified time when the file exists). The `path`/`folder_path` pair feeds the UI's open-in-external-editor / reveal-in-file-manager affordances (FR-047).
- **FR-011**: Users MUST be able to read the content of any allowlisted config file. A file that does not exist reads as empty content with `exists=false` and is not created by the read.
- **FR-012**: The system MUST expose a write (save) for the content of any allowlisted config file through the in-app editor, the REST API and the `coffer agent` CLI — one endpoint serving all three. The content MUST be validated against the file's `format` before any write; malformed `json`/`toml` MUST be rejected (`unprocessable_entity`, 422) and the on-disk file left unchanged. `markdown`/`text` files accept any content.
- **FR-013**: Writes MUST be atomic (temp file + rename) and MUST keep a `.bak` copy of the prior content so a bad edit is recoverable; each successful write MUST record an `agent_config_file_written` audit entry. The Coffer-MCP install/uninstall operations (FR-018) reuse the same atomic-write + `.bak` machinery.
- **FR-014**: Config-file read and write MUST be addressable only by allowlisted `key` (never by caller-supplied path); an unknown key returns `not_found` (404) and performs no filesystem access.

**Coffer MCP install**

- **FR-015**: Users MUST be able to install Coffer's own MCP server into an agent in one action. The install writes a `coffer` stdio MCP-server entry into the agent's MCP config, using the shape declared by that agent's manifest `McpInjectionSpec` and named by that type's child spec. `command` is the absolute path of the `coffer-mcp-shim` binary (resolved on `PATH`, then the running interpreter's scripts directory — so a venv-installed shim is found even when the daemon's `PATH` lacks the venv — then the bundled binary; a `COFFER_MCP_SHIM_PATH` environment override takes precedence over all). The install additionally writes `--agent-uid <uid>` (the agent's immutable uid, never its mutable name — the entry is written once into a file Coffer does not otherwise revisit, and a name would go stale on the first rename) in the entry shape's argument slot, so the gateway can attribute the session to this agent for per-agent scope enforcement ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)). If the shim cannot be resolved, install is rejected and nothing is written.
- **FR-016**: Install MUST be idempotent — re-installing updates the existing `coffer` entry in place and never creates a duplicate. System MUST expose a status operation reporting whether Coffer's MCP is currently installed for the agent.
- **FR-017**: Users MUST be able to uninstall Coffer's MCP, removing the `coffer` entry from the agent's MCP config. Uninstalling when not installed is a no-op success.
- **FR-018**: Install and uninstall MUST reuse the atomic-write + `.bak` machinery from FR-013 and record an audit entry (`agent_mcp_installed` / `agent_mcp_uninstalled`).

**Agent MCP entries (workspace amendment)**

- **FR-019**: System MUST parse and list the MCP server entries configured in the agent's own files, reading the source files that type's child spec names and labelling each entry with the file it came from. Each entry carries name, source, transport (stdio command or HTTP URL), the `enabled` flag where the format defines one, `is_coffer` for Coffer's own gateway entry, and `matches_resource` naming an equivalent registered `mcp_server` resource when one exists. Entries are derived at read time, never stored.
- **FR-020**: Users MUST be able to remove a direct MCP entry. Removal edits only the entry's source file, reuses the FR-013 atomic-write + `.bak` machinery, and records an `agent_mcp_entry_removed` audit entry. The `coffer` entry is not removable through this operation — it is managed by FR-015/FR-017.
- **FR-021**: Users MUST be able to adopt a direct MCP entry into Coffer. Adoption (a) registers the entry as an `mcp_server` resource through the standard resource flow (schema validation + audit), (b) verifies the resource reads back, then (c) removes the source entry per FR-020 — strictly in that order. Any failure stops the operation, rolls back a created resource, and leaves the agent's config byte-identical; audited as `agent_mcp_entry_adopted` on success. A name collision with an existing resource is rejected with `conflict` (409) carrying a suggested alternative; an entry equivalent to an existing resource is reported via `matches_resource` so the user can remove the duplicate instead. The `coffer` entry is never adoptable.
- **FR-022**: Adoption MUST NOT persist secret values into resource config. When an entry's environment carries values under secret-like keys (`TOKEN`, `KEY`, `SECRET`, `PASSWORD` patterns), the adopt request MUST supply a keychain mapping for each flagged key or be rejected with the unresolved keys listed. Mapped values are stored in the OS keychain through the daemon (per the credentials invariant); the resource config carries references only.
- **FR-023**: When an agent config file cannot be parsed, the affected facet MUST degrade to an explicit parse-error state (file path + parser error) without failing the surrounding view, and entry-level writes against that file MUST be rejected until it parses again.

**Not provided: toggling an entry's `enabled` flag.** Coffer once offered a per-entry enable toggle beside the listing. It is gone. For a format with no per-entry flag it was never anything but a 422, and for one that has it the toggle duplicated a switch the agent's own UI already owns while hand-writing another tool's private config format in place. Removal (FR-020) and adoption (FR-021) stay because they are the writes Coffer alone has a reason to make: taking a server out of the agent's private config, and pulling one into the hub with its secrets mapped into the vault. Each owns its write end-to-end and rolls it back when anything fails.

**Plugins (workspace amendment)**

- **FR-024**: System MUST list an agent's installed plugins with their enabled state and the marketplace each came from (a column of the listing, not a grouping of it), deriving the inventory from the documented sources that type's child spec names. The listing itself writes nothing — not the documented surface, not any internal state file; the writes are FR-025 and FR-026. A plugin configured without its cache is flagged `cache_present=false`; no repair is attempted.
- **FR-025**: Users MUST be able to enable/disable a plugin. Writes touch only that type's documented location and MUST never write the agents' internal state files. Audited as `agent_plugin_toggled`.
- **FR-026**: Users MUST be able to uninstall a plugin, by the per-agent strategy its child spec defines. Where the install state lives in a file Coffer must not hand-write, Coffer delegates to the agent's own CLI; when that CLI is unavailable the operation is rejected with `unprocessable_entity` (422) and error code `PLUGIN_UNINSTALL_UNSUPPORTED`, the in-app uninstall affordance is hidden (the listing reports `can_uninstall=false`), and a CLI error surfaces as `PLUGIN_UNINSTALL_FAILED` (422). Every successful path is audited as `agent_plugin_uninstalled`. Plugin installation and marketplace management are not provided by Coffer; both remain with the agent's own tooling.

**Directory config entries (workspace amendment)**

- **FR-027**: A config-file allowlist entry MAY be a **directory entry** (`kind=directory`): it resolves to a directory and lists its files (entry-relative path, size, modified time) instead of carrying content. A missing directory lists as `exists=false` with no files; the read never creates it. Which allowlist entries are directory entries is per type, and each child spec names its own.
- **FR-028**: Users MUST be able to read individual files inside a directory entry; this read backs the UI's editor. Write (create-on-write) and delete of individual files are available through the in-app editor, the REST API and the `coffer agent` CLI. Child paths are validated server-side before any filesystem access: they MUST resolve inside the entry's directory (no `..`, no absolute paths, no symlink escape) and carry the `.md` extension. Writes reuse FR-013's machinery; deletion preserves the prior content as `.bak`. Audited as `agent_config_file_written` / `agent_config_file_deleted`.
- **FR-029**: Config-file reads (single files and directory children) MUST return a content fingerprint; writes MUST carry it back and are rejected with `conflict` (409) when the on-disk content changed since the read, leaving the file untouched.
- **FR-030**: When an instructions file still contains the **legacy** memory-projection managed block, the editor MUST annotate it as a leftover that is safe to delete. Coffer no longer writes or parses that block: native projection was retired ([Aggregate Agent Memory, Never Write It](../../../docs/decisions/aggregate-agent-memory-never-write-it.md)), the table behind it was dropped, and spec memory FR-037 forbids reintroducing it. Detection is by marker prefix only — the block's content is never read. No live feature owns a managed block in these files, so there is no second block to annotate.

**The agent's model binding**

- **FR-031**: The agent record MUST carry the model binding the rest of Coffer reads — `model`, `fast_model` and `wire_api` — because the model is chosen at the point of USE and an agent is where it is used, not on the connection that serves it. That binding MUST be settable without the web UI: `PATCH /api/v1/agents/{uid}` carries `model` / `fast_model` / `wire_api`, and `coffer agent edit` exposes them as `--model` / `--fast-model` / `--wire-api`, with `--clear-fast-model` for the explicit null that unbinds the fast slot — options on the verb that edits the agent rather than a command of their own, because they are fields of the agent. Projecting a binding into the agent's native config is spec provider-switching's; validating a bound value against what one type accepts is that type's child spec (see agent-registry/codex FR-011 for `wire_api`).

**The model catalogue**

- **FR-032**: `GET /api/v1/agent-providers/{agent_key}/models` MUST answer, per agent type, which models that agent can be put on, read back from the installed agent and never written down in Coffer. Each entry MUST carry `id`, `label`, `description`, the reasoning `efforts` its runtime reports and the `default_effort` it would use, keeping a reported default only when it is one of the offered levels. An unknown `agent_key` MUST be a 404.
- **FR-033**: The catalogue MUST be one backend service answering per agent, and every entry — id, label, description — MUST be read back from the installed agent rather than written into Coffer, because a list written down here goes stale on the next CLI release. Each type's child spec names its sources, and the order those sources answer in is the order of the picker. Every source MUST degrade to nothing on its own: a missing CLI, a changed bundle layout, an unauthenticated or wedged agent costs the models that source would have added and nothing else.
- **FR-034**: There MUST be exactly one source of truth. No Coffer surface may keep a model list of its own: the agent's catalogue is FR-032's answer, and what a picker is OFFERED — which narrows to an active connection's curated set where there is one — is spec provider-switching FR-032's answer, served over the wire from that one backend rather than reassembled by any client. Nothing in Coffer curates an agent's models; two attempts to have someone curate them, first on the agent and then on the channel, were both removed. The accepted cost is that a model the agent's own catalogue does not name cannot be PICKED from a Coffer surface — it stays typeable wherever the CLI accepts a name. The benefit is that a newly released model reaches every surface with no Coffer release at all.
- **FR-035**: Each type's own native config MUST contribute the local model choices only it knows, alongside whatever its runtime reports. The key each type reads is named in that type's child spec, and it is read, never written.

**Reasoning effort levels**

- **FR-036**: A reasoning-effort level MUST travel BESIDE the model id, never inside it. `AgentModel` carries `efforts: tuple[str, ...]` — the levels the agent reported, in the order it reported them, empty for an agent that takes no such setting — and `default_effort`, the level it would use when none is chosen; FR-032's route exposes both. Beside, because that is what the protocols do: the effort is its own field on a turn, so folding levels into the name would multiply one model into several entries under names Coffer invented. A reported default is kept only when it is one of the offered levels, and nothing is invented for a model that reports none. The stakes are not cosmetic: the same prompt on the same model reported 53 reasoning output tokens at the lowest level and 2569 at the highest.
- **FR-037**: The levels MUST come from the agent's RUNTIME, not from the model, read from the source that type's child spec names. A runtime that declares none yields an empty tuple: the effort controls hide themselves and turns are unchanged.
- **FR-038**: No default level MAY be reported unless the runtime publishes one machine-readably. Prose documentation naming one level is not a machine-readable fact, and a picker naming the wrong default is worse than one naming none.

**The agent's own native memory (workspace amendment)**

This requirement extends the registry to the coding agent's OWN native memory — distinct from the `instructions` config files of FR-009 (those are human-authored instructions; this is the agent's self-written store). Coffer only ever READS it. The scan is a listing, like the MCP-entry and plugin listings beside it, and it exists so the user can see, from the agent's page, what memory that agent has been keeping and open it on disk. What Coffer does with the agents' own stores beyond showing them is spec memory's.

- **FR-039**: System MUST expose a read-only **native-memory scan** that lists an agent type's own native memory stores, in the layout that type's child spec defines. Each row carries a `project` label and `path` that are the REAL project directory, the real `memory_dir`, and an `item_count`. An agent type with no native memory layout, or one whose layout is absent on disk, returns an empty list. The scan is read-only, derives everything from disk at read time (nothing stored), and — consistent with FR-048's "every workspace listing is read-only and emits no audit event" — emits NO audit event. It never writes the agent's store.

**Not provided: importing a native memory store into Coffer.** A retired requirement once read a store's facts and wrote them into a Coffer inbox lane, handing them to an organizer. It is not restored, and the machinery is gone with it. The knowledge layer is now a directory of markdown files that the user and agents write deliberately ([Knowledge Is Plain Files](../../../docs/decisions/knowledge-is-plain-files.md)); a bulk copy of another tool's store into it produces material nobody chose to keep, in a place they must then curate. Reading the store, and opening it where it lives, is the whole of what this facet offers.

**The agent's own chat history (workspace amendment)**

An agent writes a transcript of every session into its own config directory, at the location that type's child spec names. The registry lists them so the user can find a past session from the agent's page and open it where it lives. This is a browse surface and nothing more: Coffer parses the files to derive a summary, and never writes them, never stores their content, and never sends them anywhere.

- **FR-040**: System MUST expose a read-only listing of an agent's local transcript sessions. Each session summary carries its `session_id`, a derived `title` (the session's first *real* user turn, secret-scrubbed — a turn whose text is nothing but an injected markup block was written by the harness, not by a person, and is not a candidate), `project_path`, `message_count`, `started_at`, `last_activity_at`, and the transcript file's absolute `source_path` — the last feeding the FR-047 open / reveal affordances. The listing MUST support a case-insensitive substring search over title and project path, an exact `project` filter, sorting by `started_at`, `last_activity_at` (default) or `message_count` in either direction, and `limit`/`offset` paging alongside the matched `total`, because an agent accumulates thousands of sessions and the surface cannot load them all. Parsing is per-file and cached by the file's modification time **and size**; a file that fails to parse is skipped rather than failing the listing. Message text is not carried on the wire by THIS listing and is not retained by it — a body travels only through FR-042's single-session read, for the one session a reader opened.
- **FR-041**: The listing MAY keep a **disposable derived sidecar** of those summaries so a cold parse is not repeated on every daemon restart — an agent's transcripts run to thousands of files and gigabytes, and re-deriving them is seconds of blocking I/O. The sidecar holds no message text, lives **outside the vault and outside `coffer.db`** at one path the user may delete at any moment, and no export or backup carries it. It MUST never change an answer, only the time to reach one: a summary is served from it only while its file's modification time and size still match, and with the sidecar missing, empty, corrupt or mid-write the listing MUST still be correct — merely slower. The system MAY warm it in the background, off the request path, so the first visit after an install is not the one that pays. Everything the listing returns is still derived from the agent's own files on disk: nothing about a session is a stored truth. Like the other workspace listings (FR-048), neither the listing nor the warm pass emits an audit event.

**Not provided: distilling a transcript into memory.** Coffer once read these same files to distil durable facts into a journal lane. That path, its ledger, its background sweep and the lane it wrote to are gone; this listing does not resurrect them. The agent's own memory is spec memory's domain, and spec memory FR-037 forbids reintroducing a path that writes back into it. What remains is the part that needed no model and could not corrupt anything: showing the user what sessions exist and opening one.

**Not provided: the `coffer-hook` binary and the session-context route**

Three requirements were removed together. One installed a `coffer-hook` command entry into the agent's hooks file and could uninstall it and report its status. One served that hook a **rules bundle** over `GET /agents/{name}/session-context` — the session's project and global rules plus two seeded built-in rules. One exposed `disable_native_memory`, which turned the agent's own write-side memory off in lockstep with a persisted flag. With them go the `coffer-hook` binary, its PyInstaller target and console script, the `hook-install` and `session-context` routes, the `surfaces/hook/` entry point and the hook service / resolver / install domain, `coffer agent hook …`, the `disable_native_memory` config field, and the four audit events `agent_hook_installed` / `agent_hook_uninstalled` / `agent_native_memory_disabled` / `agent_native_memory_restored`. The reason was that they shipped and were never installed: the built `coffer-hook` binary sat in `~/.coffer/bin/` referenced by nothing.

Session-start delivery itself came back, on spec memory's own terms — an explicit, marker-scoped, auditable install of Coffer's memory-delivery hook into the agent's own settings, specified and owned by spec memory, which also owns the per-agent delivery status the Memory tab renders (FR-044). This registry supplies what that install stands on — the agent record, its config directory, the allowlisted file it writes through, and FR-013's atomic-write machinery — and specifies none of the delivery itself.

**Surfaces**

- **FR-042**: System MUST expose a read-only **single-session read** that returns one transcript's summary fields (as FR-040 lists them) together with a WINDOW of its conversational turns — each turn's role, text and timestamp — plus the `limit`/`offset` that window was taken with. A session is addressed by the absolute `source_path` FR-040 handed out, which MUST resolve inside that agent's own transcript directory; any other path is `not_found` (404), the same answer as a transcript that has since been deleted, so the difference cannot be used to probe the filesystem. This is the ONLY place a transcript body crosses the wire, and everything guarding a body is concentrated here: every turn is secret-scrubbed with the same redaction FR-040's titles get (a prompt is exactly where a pasted key would be), a turn longer than the system's per-turn cap is cut to its start and flagged, and the number of turns returned is bounded — a transcript can be tens of megabytes, so the surface pages through it rather than loading it. The whole file's turn count is returned alongside the window, so a reader is never shown 200 turns and left to assume that is all of them. Read-only: nothing is written, nothing is retained, and no audit event is emitted (FR-048).
- **FR-043**: System MUST expose a read-only **native-memory store read** that returns one store's directory as a file tree (each entry's name, store-relative path, type and size) and one file inside it as text (its contents, its absolute path for FR-047's open / reveal, and whether it was truncated or is binary). A store is addressed by the `memory_dir` FR-039 handed out, which MUST be exactly a directory that type's layout would have listed — and not merely some path under the agent's config dir, which also holds its transcripts, settings and plugin cache. A directory that is not one of the agent's stores, a file path escaping the store, and a file that does not exist are all `not_found` (404). Reads are capped in size and the walk is depth-bounded, with both facts reported rather than silently applied. Read-only: Coffer never writes an agent's own memory, so the surface previews and offers FR-047's open / reveal instead of an editor, and emits no audit event (FR-048).
- **FR-044**: Every management operation — register/list/view/update/remove, config-file list/read/write (including directory children), Coffer-MCP install/uninstall/status, MCP entry list/remove/adopt, plugin list/toggle/uninstall, native-memory scan (FR-039) and store-file read (FR-043), transcript listing (FR-040) and single-session read (FR-042), and the model catalogue (FR-032) — MUST be available through (a) the REST API and (b) the `coffer agent ...` CLI. The Agents page in the web UI MUST expose all of these, config-file content writes included: a config file (and a directory-entry child) opens in a viewer that becomes **editable behind an explicit Edit**, saves through the same FR-012/FR-013 path as REST and the CLI, and guards an unsaved draft three ways — picking another file asks first, leaving the tab asks first, and leaving the page asks first. Open-in-external-editor / reveal-in-file-manager (FR-047) sit beside the content for the edits that want a real editor. The agent detail page has seven tabs — Overview, Skills, MCP servers, Plugins, Memory, Conversations, and Config files. Of those, Plugins acts on the agent (enable / disable / uninstall) and Memory carries one write — installing or removing Coffer's memory-delivery hook, which spec memory specifies and this page mounts; the rest of Memory, and all of Conversations, are read-only views of the agent's own stores. Neither table carries per-row actions: a row OPENS its subject, and the open-in-external-editor / reveal-in-file-manager affordances (FR-047) live on the page it opens, beside the thing they act on. A Conversations row opens that one session rendered as a readable conversation (FR-042), beside a contents list of the session's prompts that scrolls the conversation to any one of them; a Memory row opens that store's directory as a file tree with a read-only preview (FR-043), because a store is a directory and one session is a single file.
- **FR-045**: **Readable means the person's words lead.** A "user turn" in a transcript is not only what the user typed: every harness prepends its own blocks to the same turn — reminders, task notifications, environment dumps. Both surfaces MUST read the turn as the person's, not the harness's: the contents list MUST index a turn by the first line the PERSON wrote and MUST omit a turn they wrote no part of, and the conversation MUST lead with their words, with the prepended blocks folded away rather than dropped — the blocks are part of the record and a view that discarded them would be claiming the turn said less than it did. Identified by SHAPE, not by a list of block names: naming them one at a time never finishes, and prose that merely contains a `<` is not markup.
- **FR-046**: The CLI MUST support `--json` for machine-readable output on every read operation.
- **FR-047**: For each config file (and each directory-entry child) the UI MUST offer **open-in-external-editor** and **reveal-in-file-manager** actions on the file, using the `path` from FR-010/FR-011. Open and reveal perform the real OS action through the daemon's filesystem-action endpoints (`POST /api/v1/fs/open`, `POST /api/v1/fs/reveal`, and the installed-editor enumeration behind the preference — all spec daemon), since the loopback daemon is always on the user's own machine ([Daemon Proxies OS File Actions](../../../docs/decisions/daemon-proxies-os-file-actions.md)). There is no copy-path fallback. The editor used for open-in-external-editor references the user's "preferred external editor" preference defined by spec web-ui (not re-specified here).

**Observability**

- **FR-048**: System MUST record an audit entry for every lifecycle event: agent created, updated, removed; config file written/deleted (`agent_config_file_written` / `agent_config_file_deleted`); Coffer MCP installed/uninstalled; MCP entry removed/adopted (`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`); plugin toggled/uninstalled (`agent_plugin_toggled` / `agent_plugin_uninstalled`). (Agents have no enable/disable concept; discovery and all workspace listings — MCP entries, plugins, config files, native memory stores, transcript sessions, the model catalogue — are read-only and emit no audit event, the background pass that warms FR-040's transcript summary cache included. Reading ONE of the listed items — a single session's turns (FR-042), a single store's files (FR-043) — is the same act at a smaller scale and audits nothing either. The audit events of the memory-delivery install the Memory tab offers are spec memory's, not this spec's.)
- **FR-049**: System MUST expose a read-only discovery operation listing installed-but-unregistered agents as candidates, available from the REST API (`GET /api/v1/agents/candidates`), the `coffer agent detect` CLI, and the Agents page in the web UI.

**Config-directory picker**

- **FR-050**: When choosing a custom `config_dir`, the web UI MUST offer a folder picker rather than requiring the user to type a path. It MUST use the daemon's native directory dialog (`POST /api/v1/fs/pick-folder`, spec daemon), falling back to the daemon-backed folder browser (`GET /api/v1/fs/browse`, spec daemon) only when the host has no native dialog tool. Both yield an absolute path that is then validated per FR-007 before registration.

**Convergence**

- **FR-051**: Deleting the plugin inventory document for an agent (sync state area
  `agent-plugins/<agent>`) MUST drop nothing locally. The inventory has no local
  store beyond the document itself, and there is no uninstall-by-sync path: the
  next export republishes whatever this machine's agent still holds. This is this
  spec's answer to the rule that each state area's provider defines what its own
  document's deletion means (spec vault-sync).

### Key Entities

- **Agent**: A Resource of kind `agent`. Represents one locally-installed AI agent. Config: `type` (supported enum), `config_dir` (optional absolute-path override; defaults to the type's standard location), and the model binding of FR-031 (`model`, `fast_model`, `wire_api`). Skills are delivered to `<config_dir>/skills`. Identified by its immutable `uid`; `name` is a mutable label. The `agent` kind declares no `scope`: a non-null value is rejected at validation (422) — an agent resource is what other kinds' scopes name, never itself a scope target ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)).
- **Agent Type**: An enum value identifying a known agent product (`claude_code`, `codex`). Each value maps to a record in the **capability manifest** (`AGENT_DESCRIPTORS`) carrying its default `config_dir`, display name, install marker, curated **config-file allowlist**, **MCP injection shape**, plugin capability, native-memory layout, transcript location, model-catalogue sources and provider-projection facet — which is exactly what that type's child spec documents. Both supported products carry every facet; a product that could not would be a product not worth adding.
- **Agent Candidate**: A discovered installed-but-unregistered agent — `type`, `display_name`, `config_dir` (the type's default config directory), `default_skill_dir`, and `suggested_name`. Derived at scan time, never stored; the user confirms a candidate to register it.
- **Config File**: A curated, allowlisted file belonging to an agent type, identified by a stable `key`. Carries a display name, a resolved absolute path, its containing-folder absolute path (`folder_path`), a `format` (`json` / `toml` / `markdown` / `text`), and (when present) size and modified time. Surfaced in the UI for reading and editing (and for opening it / its folder in an external editor); read and written by key (in-app editor, REST, CLI), never by arbitrary path. Not persisted in SQLite — the file on disk is the source of truth.
- **Coffer MCP Install Status**: Derived (not stored) state for an agent: whether a `coffer` MCP-server entry is present in that agent's MCP config file.
- **Agent MCP Entry**: A derived (never stored) view of one MCP server configured in the agent's own files — name, source file, transport, `enabled` where the format defines one, `is_coffer`, `matches_resource`. The file is the source of truth; Coffer reads and adopts entries but keeps no copy, and edits an entry only as the removal step of an adoption.
- **Agent Plugin**: A derived (never stored) view of one installed plugin — id (`<name>@<marketplace>`), marketplace, enabled state, `cache_present`, plus best-effort manifest detail read from the plugin's install directory. Every input is read-only: the enabled state Coffer reports is the one that agent's documented config surface declares, and Coffer never writes it back except through FR-025.
- **Agent Model**: A derived (never stored) catalogue entry — `id` (passed to the agent verbatim), `label`, `description`, `efforts` and `default_effort`. Read back from the installed agent on every request; Coffer stores no model list and names no model of its own.
- **Native Memory Store**: A derived (never stored) view of one of the coding agent's OWN native memory stores, in the layout that type's child spec defines. Carries a `project` label and `path` (the REAL project cwd), the real `memory_dir`, and an `item_count`. Read-only: Coffer lists these stores and opens them, and never writes them.
- **Transcript Session**: A derived summary of one of the agent's own session transcript files — `session_id`, a scrubbed derived `title`, `project_path`, `message_count`, `started_at`, `last_activity_at`, and the file's absolute `source_path`. Parsed from the `.jsonl` on disk and cached by that file's modification time and size, both in memory and in the disposable sidecar of FR-041 — which holds no message text, sits outside the vault and outside `coffer.db`, and is a cache of the derivation rather than a record of the session: delete it and the same summaries come back. Message text is never part of a summary and is never retained; FR-042 streams a bounded, scrubbed window of it straight from the file when one session is opened, and keeps nothing.
- **Directory Config Entry**: An allowlisted config entry that resolves to a directory of files rather than a single file. Children are addressed by validated entry-relative paths; the directory on disk is the source of truth.

## Success Criteria

### Measurable Outcomes

- **SC-001**: On a machine with at least two supported agent install paths present, running discovery surfaces exactly those agents as candidates, and the user adds them with a single confirm each — no typing of type identifiers or paths.
- **SC-002**: From a fresh install, a user can register an additional agent with a custom `config_dir` and see it in `coffer agent list --json` within 60 seconds, without consulting documentation more than once.
- **SC-003**: Every Acceptance Scenario in this spec is covered by at least one test marked `acceptance(spec="agent-registry", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios. The same holds for each child spec under its own spec id.
- **SC-004**: The full `make verify` suite passes locally and in CI; `make verify-all` (adding e2e) passes on macOS and Linux.
- **SC-005**: No `config_dir` value ever permits writing outside the directory itself (path-traversal check); validated by a dedicated security test.
- **SC-006**: A user can open an agent's main config file in Coffer, edit it and save it — or open it in their external editor instead; every save validates the content (a malformed save is rejected with the file left unchanged), keeps a `.bak` of the prior version, and is refused if the file changed on disk since it was read.
- **SC-007**: A user can install Coffer's MCP into a freshly-registered agent in one click and, after restarting that agent, the agent lists Coffer's aggregated tools; re-installing never duplicates the entry, and uninstall removes it.
- **SC-008**: The MCP tab lists exactly the entries present in the agent's real config files, and adopting a direct entry completes the full round trip — resource registered, gateway serving it, direct entry gone — in one user action plus at most one confirmation.
- **SC-009**: The plugin listing writes nothing: every file under the agent's config directory is byte-identical before and after a listing, including the agents' internal plugin state files.
- **SC-010**: No directory-entry operation can read or write a path outside its entry's directory; validated by dedicated security tests covering `..` traversal, absolute paths, symlink escape, and disallowed extensions.
- **SC-011**: A model released after Coffer shipped appears in an agent's catalogue with no Coffer release, and making one of that type's catalogue sources unavailable costs exactly that source's entries and nothing else.

## Assumptions

- The user runs Coffer on their own machine; there is no multi-tenant or remote-access requirement.
- Both agent types are wired in the capability manifest (`AGENT_DESCRIPTORS`) — `claude_code` and `codex` — each one `AgentType` enum value plus one record (install marker, config-file allowlist, MCP injection shape, and its facets), documented by that type's child spec. Adding a further product is the same one-record change plus one child spec, plus a chat-provider adapter when its wire protocol is new; a product whose facets Coffer cannot exercise on a real install is not added.
- Each supported agent's CLI and app/IDE form read one shared config directory, so Coffer manages one config set per agent.
- Config files are surfaced as raw text the user can read and edit in place, with the validate + atomic-write + `.bak` safety net on every save, whichever surface issues it. Open-in-external-editor stays alongside as the escape hatch for the long tail; recurring structured needs graduate into facets (MCP entries, plugins) per the workspace amendment.
- The agents' internal state files are read as inputs where needed and never written by the workspace facets; the documented configuration surfaces verified against each vendor's docs are the only write targets. Which files fall on each side of that line is per type, and each child spec names its own.
- The filesystem-action routes this spec's surfaces call — `GET /api/v1/fs/browse`, `POST /api/v1/fs/open`, `POST /api/v1/fs/reveal`, `GET /api/v1/fs/editors`, `POST /api/v1/fs/pick-folder` — belong to spec daemon, which owns the loopback process that performs them. This spec consumes them and specifies none of them.
- Installing and removing Coffer's memory-delivery hook is spec memory's requirement, not this one's. This registry supplies what that install stands on — the agent record, its config directory, its allowlisted settings file and the atomic-write machinery — and renders the resulting status on the Memory tab (FR-044).
- Workspace facets follow the ingest → hub → deliver principle: shareable content found in an agent's workspace is adoptable into Coffer's hub (MCP gateway here; the master skill store via spec skill-manager's companion amendment) rather than managed as per-agent one-offs.
- Agents store their skill libraries on the local filesystem under `<config_dir>/skills`. Web-only agents (e.g. claude.ai) are out of scope for v1 and require a future spec to add API-based sync.
- The kind-agnostic Resource framework, audit log, and immutable-`uid` identity scheme defined by spec resource-framework are in place.
- The application shell from spec web-ui — sidebar IA, layout, routing skeleton, and design system — is in place. The Agents page renders within that shell at `/agents` as a **dedicated top-level nav entry** (a sibling of the Resources and System groups, **not** nested under Resources — agents are consumers of vault assets, not assets themselves). Agent resources do not appear in the kind-agnostic resources/MCP browser, which lists only kinds that register a resource-card UI.
- Skill bindings (i.e. the relationship between an agent and a particular skill) are introduced and managed by spec skill-manager; this spec does not define skill operations beyond exposing an `on_delete` hook for cascade cleanup.
