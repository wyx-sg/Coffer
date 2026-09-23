# Agent Registry

## Purpose
The agent registry decides which locally-installed AI coding agents Coffer knows about, so that later features — skills, memory, knowledge, channels, chat — can deliver assets to them. Each agent is a Resource of kind `agent` in the kind-agnostic Resource framework. The supported products are **Claude Code** (`claude_code`) and **OpenAI Codex** (`codex`); each spans its CLI and its app/IDE form, because both forms read one shared config directory, so Coffer manages one config set per agent. The separate **Claude Desktop** chat app (its own `~/Library/Application Support/Claude/` config) and web-only agents such as claude.ai are not agents here. The registry holds only **managed** agents — external coding agents Coffer delivers to; the former built-in "Coffer Assistant" is not a registered agent ([Built-in Agent Is Internal](../../../docs/decisions/builtin-agent-is-internal-capability.md)).

This spec holds what the two types share. Everything that differs by type — where the config directory is, which files are allowlisted, the MCP entry shape, the plugin inventory, the model catalogue's sources, the native-memory layout, the transcript location — lives in a child spec: [`agent-registry/claude-code`](claude-code/spec.md) and [`agent-registry/codex`](codex/spec.md), each the reading of one `AGENT_DESCRIPTORS` record, the single per-type table in the code. Adding a product is one enum value, one descriptor record and one child spec.

Beyond registering agents, the user views and edits each agent's known config files (or opens them in an external editor), installs Coffer's own MCP server into an agent with one click, and sees which models that agent can be put on. The registry also reaches into the agent's real on-disk workspace — the MCP servers configured in its own files, its installed plugins, directory-type config entries, its own native memory and its session transcripts — following **ingest → hub → deliver**: anything shareable found in an agent's workspace can be adopted into Coffer's hub (the MCP gateway; the master skill store of skill-manager) and delivered back to any agent, instead of living as per-agent one-off config. All writes go through each agent's documented configuration paths only; the agents' internal state files are read as inputs where needed and never written. Config files are surfaced as raw text with a validate + atomic-write + `.bak` safety net on every save; open-in-external-editor stays alongside as the escape hatch for the long tail, and recurring structured needs graduate into facets.

The user runs Coffer on their own machine; there is no multi-tenant or remote-access requirement. The registry relies on the Resource framework, audit log and immutable-`uid` identity of resource-framework, and renders inside the web-ui application shell. A `coffer-hook` binary with a session-context rules route and a `disable_native_memory` switch once lived here and was removed because it was never installed; session-start delivery is now memory's own, marker-scoped install, which this registry only supports by supplying the agent record, its config directory, its allowlisted settings file and the atomic-write machinery.

## Requirements

### Requirement: Register each agent as an agent resource identified by its uid
The system MUST register each known local agent as a Resource of kind `agent`, identified by the immutable `uid` the resource framework mints for it ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)). Its name is a mutable label, unique within the kind, and every reference another kind holds to an agent — a resource `scope`'s agent list, a channel's `default_agent`, the `--agent-uid` the shim reports — holds the uid, so renaming an agent breaks nothing.

#### Scenario: keep an agent's uid across a rename
- **GIVEN** a registered agent with uid `U` and name `before`
- **WHEN** the user renames it to `after`
- **THEN** the agent is still read back at `/api/v1/agents/U` with uid `U`, name `after` and its config dir unchanged
- **AND** neither `before` nor `after` addresses the agent as a path segment

### Requirement: Validate agent configuration against the agent schema
The system MUST validate agent configuration against a kind-specific schema with fields `type` (enum) and `config_dir` (path, optional absolute-path override; when omitted it defaults to the type's standard location, which that type's child spec names), plus the model binding of "Carry the model binding on the agent record". Skills are delivered to `<config_dir>/skills`. The `agent` kind declares no `scope`: a non-null value is rejected at validation (422) — an agent resource is what other kinds' scopes name, never itself a scope target ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)).

#### Scenario: an agent cannot be given a scope
- **GIVEN** a registered agent
- **WHEN** a scope naming another agent is set on it through the kind-agnostic scope route
- **THEN** the request is rejected as `unprocessable_entity` (422) and the agent still has no scope

### Requirement: Support exactly the Claude Code and Codex agent types
The system MUST support the agent types `claude_code` and `codex`; registering any type outside the manifest (e.g. the `claude_desktop` chat app, a Gemini CLI) is rejected with `unprocessable_entity` (422). Per-type behaviour is defined by the capability manifest (`AGENT_DESCRIPTORS`), so adding a type is one enum value, one descriptor record and one child spec (plus, where the product's wire protocol is new, one chat-provider adapter). Each supported type covers both the CLI and the app/IDE form of that product, which share one config directory.

What a facet looks like for one type is that type's child spec. There is no per-facet capability matrix, no per-facet "not supported" state on the agent surface and no capability booleans on the wire; a facet a type could not support would be a reason not to add that type. The `PluginCapability` flags of "Toggle a plugin through the documented location only" and "Uninstall a plugin by the type's own strategy" are the one exception, and they are per-facet *runtime availability* — whether the agent's own uninstall command is on `PATH` — not a per-type support claim. A further product is added only when it is genuinely in use and its facets can be exercised on a real install; `opencode`, `hermes`, `cursor` and `openclaw` were removed for lacking exactly that.

#### Scenario: reject unsupported agent type
- **GIVEN** the daemon is running
- **WHEN** the user attempts to register an agent of a type outside the supported set (e.g. `claude_desktop`, `gemini_cli`, or a garbage value)
- **THEN** registration is rejected with `unprocessable_entity` (422) naming the supported types, and nothing is persisted

### Requirement: Discover installed agents as candidates without registering them
The system MUST provide a read-only discovery operation that scans each supported type's install marker — named in that type's child spec — and reports installed types that are not already registered as **candidates** (each carrying `type`, `display_name`, `config_dir`, `default_skill_dir`, and `suggested_name`). Candidates are derived at scan time and never stored. Discovery MUST NOT register anything automatically — the user reviews candidates and confirms which to add. The daemon MUST NOT auto-register agents on startup.

#### Scenario: discover installed agents as candidates
- **GIVEN** a Coffer install with a supported agent's install marker present and no agent registered
- **WHEN** the user runs discovery
- **THEN** Coffer reports that type as a candidate (type, display name, default config dir, suggested name) and registers nothing — discovery is read-only

#### Scenario: skip already-registered types on subsequent scan
- **GIVEN** a `codex` agent is already registered
- **WHEN** the user runs discovery again
- **THEN** `codex` is not offered as a candidate

### Requirement: Re-offer a removed agent while its install marker remains
A removed agent MUST re-appear as a discovery candidate on subsequent scans while its install marker is present — a removal is not permanent (it may be accidental). The system MUST NOT keep a "suppressed types" list.

#### Scenario: re-surface removed agents on subsequent scan
- **GIVEN** an agent has been removed by the user and its install marker is still present
- **WHEN** the user runs discovery again
- **THEN** that agent is offered as a candidate again (removal is not permanent; no suppression list)

### Requirement: Manage the agent lifecycle without an enable state
Users MUST be able to register, list, view, update (config_dir, description), and remove agents. Agents have **no enable/disable concept** — a registered agent is simply present; there is no enabled/disabled state on the agent surface. The agent name is optional at registration — when omitted, the system MUST derive a stable per-type default (underscores become hyphens, e.g. `claude_code` → `claude-code`). Skill bindings between an agent and a skill belong to skill-manager; this registry defines no skill operations beyond exposing an `on_delete` hook for cascade cleanup.

#### Scenario: register an agent without an explicit name
- **GIVEN** the daemon is running
- **WHEN** the user registers an agent of supported type without supplying a name
- **THEN** the agent is registered under a stable per-type default name (underscores become hyphens, e.g. `claude_code` → `claude-code`)

#### Scenario: update an existing agent
- **GIVEN** a registered agent
- **WHEN** the user updates its `config_dir` to a new writable path
- **THEN** the change persists, an audit entry is recorded, and subsequent operations see the new path

#### Scenario: remove an agent
- **GIVEN** a registered agent (any binding cleanup is handled by the skill-manager spec)
- **WHEN** the user removes it
- **THEN** the agent is deleted, an audit entry is recorded, and `coffer agent list` no longer shows it

### Requirement: Validate the config directory at registration
At registration the system MUST auto-create the `<config_dir>/skills` subdirectory, then validate that the resolved `config_dir` exists, is a directory, is writable, and is not a privileged system path (`/etc`, `/usr`, `/bin`, `/sbin`, `/System`, `C:\Windows`, `C:\Program Files`) before accepting the value. A rejected registration leaves no partial state, and no `config_dir` value may permit writing outside the directory itself.

#### Scenario: reject registration with an invalid config dir
- **GIVEN** the daemon is running
- **WHEN** the user registers an agent whose `config_dir` does not exist, is not a directory, or is not writable
- **THEN** registration is rejected with a message naming the path, and nothing is persisted

#### Scenario: reject registration into privileged system path
- **GIVEN** the daemon is running
- **WHEN** the user attempts to register an agent whose `config_dir` resolves under a privileged location (`/etc`, `/usr`, `/bin`, `/sbin`, `/System`, `C:\Windows`, or `C:\Program Files`)
- **THEN** registration is rejected with `unprocessable_entity` (422) and no resource row, audit event, or filesystem write occurs

#### Scenario: register an agent with a custom config dir
- **GIVEN** the daemon is running
- **WHEN** the user registers an agent of supported type with an explicit, writable `config_dir`
- **THEN** the agent is persisted with that path (and its `<config_dir>/skills` subdirectory auto-created) and appears in `coffer agent list`

### Requirement: Allow one agent per name and per config directory
The system MUST reject registration that would create a duplicate agent name (409 `conflict`, as for any kind — the label is unique within its kind even though it is not the identity), and MUST reject registering more than one agent for the same config directory. `config_dir` is derived from the agent type, so each supported type — and thus each on-disk config directory — may be registered at most once; a second attempt is rejected with `conflict` (409) and nothing is persisted.

#### Scenario: reject duplicate agent name
- **GIVEN** an agent named `codex-work` exists
- **WHEN** the user attempts to register another agent with the same name
- **THEN** registration is rejected with a clear error

#### Scenario: reject a second agent for an already-registered config dir
- **GIVEN** a `codex` agent is already registered (whose config dir is `~/.codex`)
- **WHEN** the user attempts to register another `codex` agent (which resolves to the same config dir), even with a different name and config_dir
- **THEN** registration is rejected with a clear error and nothing is persisted — only one agent may exist per config directory

### Requirement: Define a curated config-file allowlist per type
Each supported agent type MUST define a curated allowlist of config files in its capability-manifest record, enumerated by that type's child spec, each entry carrying a stable `key`, a display name, a resolved absolute path, and a `format` (`json`, `toml`, `markdown`, or `text`). Each type's human-authored instructions file carries the key `instructions` — those files are instructions a person wrote, distinct from agent-written memory (memory's domain). Config files are not persisted in SQLite — the file on disk is the source of truth.

#### Scenario: key each type's instructions file as instructions
- **GIVEN** the capability manifest for every supported agent type
- **WHEN** the type's config-file allowlist is read
- **THEN** every entry carries a key, a display name, an absolute path and a format among `json`, `toml`, `markdown` and `text`
- **AND** exactly one entry per type is keyed `instructions` and has format `markdown`

### Requirement: List an agent's config files with their locations
Users MUST be able to list an agent's config files with, for each, its key, display name, path, the containing-folder absolute path (`folder_path`), format, and existence (plus size and modified time when the file exists). The `path`/`folder_path` pair feeds the UI's open-in-external-editor / reveal-in-file-manager affordances (see "Open config files in an external editor or reveal them").

#### Scenario: report each config file's path, folder and existence
- **GIVEN** a registered agent where one allowlisted file exists and another does not
- **WHEN** the user lists the agent's config files
- **THEN** each entry carries its key, display name, absolute `path`, `folder_path` equal to the path's parent, format and `exists` flag
- **AND** the existing file also carries its size and modified time while the missing one carries neither

### Requirement: Read allowlisted config files without creating them
Users MUST be able to read the content of any allowlisted config file. A file that does not exist reads as empty content with `exists=false` and is not created by the read.

#### Scenario: read an existing config file
- **GIVEN** a registered agent whose `settings.json` exists
- **WHEN** the user reads that config-file key
- **THEN** Coffer returns the file's current text content, its format (`json`), and `exists=true`

#### Scenario: read a not-yet-created config file
- **GIVEN** a registered agent whose instructions file does not exist on disk
- **WHEN** the user reads that config-file key
- **THEN** Coffer returns empty content with `exists=false` and does not create the file

### Requirement: Validate config-file content before saving it
The system MUST expose a write (save) for the content of any allowlisted config file through the in-app editor, the REST API and the `coffer agent` CLI — one endpoint serving all three. The content MUST be validated against the file's `format` before any write; malformed `json`/`toml` MUST be rejected (`unprocessable_entity`, 422) and the on-disk file left unchanged. `markdown`/`text` files accept any content.

#### Scenario: reject malformed config-file content
- **GIVEN** a registered agent whose `settings.json` (a `json` file) exists
- **WHEN** the user writes malformed content (e.g. invalid JSON) to that key through the in-app editor, the REST API or the `coffer agent` CLI
- **THEN** Coffer responds `unprocessable_entity` (422), leaves the on-disk file unchanged, writes no `.bak`, and records no write audit entry

### Requirement: Write config files atomically with a backup and an audit entry
Writes MUST be atomic (temp file + rename) and MUST keep a `.bak` copy of the prior content so a bad edit is recoverable; each successful write MUST record an `agent_config_file_written` audit entry. The Coffer-MCP install/uninstall operations (see "Back up and audit Coffer MCP install and uninstall") reuse the same atomic-write + `.bak` machinery.

#### Scenario: save a config file with valid content
- **GIVEN** a registered agent whose `settings.json` exists
- **WHEN** the user writes new, well-formed content to that config-file key through the in-app editor, the REST API or the `coffer agent` CLI
- **THEN** Coffer validates the content against the file's format, writes it atomically while keeping a `.bak` of the prior version, records an `agent_config_file_written` audit entry, and the new content reads back on the next read

### Requirement: Address config files only by allowlisted key
Config-file read and write MUST be addressable only by allowlisted `key` (never by caller-supplied path); an unknown key returns `not_found` (404) and performs no filesystem access.

#### Scenario: reject config-file key outside the allowlist
- **GIVEN** a registered agent
- **WHEN** the user references a config-file key not in that agent type's curated allowlist
- **THEN** Coffer responds `not_found` (404) and performs no filesystem read

### Requirement: Install Coffer's MCP server into an agent in one action
Users MUST be able to install Coffer's own MCP server into an agent in one action. The install writes a `coffer` stdio MCP-server entry into the agent's MCP config, using the shape declared by that agent's manifest `McpInjectionSpec` and named by that type's child spec.

- `command` is the absolute path of the `coffer-mcp-shim` binary, resolved on `PATH`, then the running interpreter's scripts directory — so a venv-installed shim is found even when the daemon's `PATH` lacks the venv — then the bundled binary; a `COFFER_MCP_SHIM_PATH` environment override takes precedence over all.
- The install additionally writes `--agent-uid <uid>` in the entry shape's argument slot — the agent's immutable uid, never its mutable name, because the entry is written once into a file Coffer does not otherwise revisit and a name would go stale on the first rename — so the gateway can attribute the session to this agent for per-agent scope enforcement ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)).
- If the shim cannot be resolved, install is rejected with an error naming the missing binary and nothing is written.

#### Scenario: refuse the Coffer MCP install when the shim cannot be resolved
- **GIVEN** a registered agent and no resolvable `coffer-mcp-shim` binary
- **WHEN** the user installs Coffer's MCP
- **THEN** the install is rejected with an error naming the missing binary
- **AND** the agent's MCP config file is not written

### Requirement: Keep the Coffer MCP install idempotent and report its status
Install MUST be idempotent — re-installing updates the existing `coffer` entry in place and never creates a duplicate. The system MUST expose a status operation reporting whether Coffer's MCP is currently installed for the agent; the status is derived from the agent's MCP config file, never stored.

#### Scenario: report Coffer-MCP install status
- **GIVEN** a registered agent whose MCP config does not contain a `coffer` server entry
- **WHEN** the user checks Coffer-MCP install status
- **THEN** Coffer reports `installed=false`

#### Scenario: install Coffer's MCP is idempotent
- **GIVEN** an agent that already has Coffer's MCP installed
- **WHEN** the user installs again
- **THEN** the existing `coffer` entry is updated in place (never duplicated) and status still reports `installed=true`

### Requirement: Uninstall Coffer's MCP server from an agent
Users MUST be able to uninstall Coffer's MCP, removing the `coffer` entry from the agent's MCP config. Uninstalling when not installed is a no-op success and status then reports not installed.

#### Scenario: uninstall Coffer's MCP when it is not installed
- **GIVEN** a registered agent whose MCP config has no `coffer` entry
- **WHEN** the user uninstalls Coffer's MCP
- **THEN** the operation succeeds without changing the agent's MCP config
- **AND** status reports `installed=false`

### Requirement: Back up and audit Coffer MCP install and uninstall
Install and uninstall MUST reuse the atomic-write + `.bak` machinery of "Write config files atomically with a backup and an audit entry" and record an audit entry (`agent_mcp_installed` / `agent_mcp_uninstalled`).

#### Scenario: uninstall Coffer's MCP from an agent
- **GIVEN** an agent that has Coffer's MCP installed
- **WHEN** the user uninstalls it
- **THEN** the `coffer` entry is removed from the agent's MCP config, the file is backed up to `.bak`, an `agent_mcp_uninstalled` audit entry is recorded, and status reports `installed=false`

### Requirement: List the MCP entries in the agent's own config files
The system MUST parse and list the MCP server entries configured in the agent's own files, reading the source files that type's child spec names and labelling each entry with the file it came from. Each entry carries name, source, transport (stdio command or HTTP URL), the `enabled` flag where the format defines one, `is_coffer` for Coffer's own gateway entry, and `matches_resource` naming an equivalent registered `mcp_server` resource when one exists. Entries are derived at read time, never stored; Coffer keeps no copy. Coffer's own `coffer` entry is rendered specially and managed by the install/uninstall operations, never as a plain direct entry.

Coffer does not offer toggling an entry's `enabled` flag, nor editing an entry in place: for a format with no per-entry flag a toggle could only fail, and for one that has it the toggle would duplicate a switch the agent's own UI already owns while hand-writing another tool's private config format. Removal and adoption are the only entry-level writes, because they are the writes Coffer alone has a reason to make.

#### Scenario: list an agent's real MCP entries
- **GIVEN** a registered agent whose own config files define several MCP server entries including `coffer`
- **WHEN** the user lists the agent's MCP entries
- **THEN** Coffer returns every entry with its name, source file, transport (stdio command or HTTP URL), and the `enabled` flag where that format defines one, marks the `coffer` entry `is_coffer=true`, and stores nothing — the listing is derived from the file at read time

### Requirement: Remove a direct MCP entry from its source file
Users MUST be able to remove a direct MCP entry. Removal edits only the entry's source file, reuses the atomic-write + `.bak` machinery of "Write config files atomically with a backup and an audit entry", and records an `agent_mcp_entry_removed` audit entry. The `coffer` entry is not removable through this operation — it is managed by "Install Coffer's MCP server into an agent in one action" and "Uninstall Coffer's MCP server from an agent".

#### Scenario: remove a direct MCP entry
- **GIVEN** a registered agent with a direct (non-Coffer) MCP entry
- **WHEN** the user removes that entry (carrying the source file where the type's entries may come from more than one)
- **THEN** the entry is deleted from exactly its source file via an atomic write with a `.bak` of the prior content, an `agent_mcp_entry_removed` audit entry is recorded, and the next listing no longer shows it

### Requirement: Adopt a direct MCP entry into Coffer
Users MUST be able to adopt a direct MCP entry into Coffer, so that it is served to every agent through the gateway instead of benefiting one agent alone. Adoption (a) registers the entry as an `mcp_server` resource through the standard resource flow (schema validation + audit), (b) verifies the resource reads back, then (c) removes the source entry per "Remove a direct MCP entry from its source file" — strictly in that order. Any failure stops the operation, rolls back a created resource, and leaves the agent's config byte-identical, reporting the failure with a specific error code; audited as `agent_mcp_entry_adopted` on success. A name collision with an existing resource is rejected with `conflict` (409) carrying a suggested alternative; an entry equivalent to an existing resource is reported via `matches_resource` so the user can remove the duplicate instead. The `coffer` entry is never adoptable.

#### Scenario: adopt a direct MCP entry into Coffer
- **GIVEN** a registered agent with a direct stdio MCP entry whose name collides with no existing resource
- **WHEN** the user adopts the entry
- **THEN** Coffer first registers an equivalent `mcp_server` resource (schema-validated, audited), verifies it reads back, then removes the direct entry from the agent's config (atomic + `.bak`), records an `agent_mcp_entry_adopted` audit entry, and the upstream is now served to all agents through the gateway

#### Scenario: reject adoption on resource name conflict
- **GIVEN** an `mcp_server` resource already exists with the same name as a direct entry
- **WHEN** the user adopts that entry without renaming
- **THEN** the request is rejected with `conflict` (409) carrying a suggested alternative name, no resource is created, and the agent's config is untouched

#### Scenario: adoption failure leaves agent config untouched
- **GIVEN** an adoption attempt that fails after resource registration (e.g. the config-file write is rejected as stale)
- **WHEN** the operation aborts
- **THEN** the created resource is rolled back, the agent's config file is byte-identical to before the attempt, and the failure is reported with a specific error code

### Requirement: Route secret-like environment values to the credential store on adoption
Adoption MUST NOT persist secret values into resource config. When an entry's environment carries values under secret-like keys (defined below), the adopt request MUST supply a credential mapping for each flagged key or be rejected with the unresolved keys listed. Mapped values are stored as Fernet ciphertext in Coffer's credential store through the daemon (per the credentials invariant); the resource config carries references only. A key is secret-like when its value is non-empty and its name matches `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`/`APIKEY`, `CREDENTIAL` or `AUTHORIZATION`, case-insensitively.

#### Scenario: require a credential mapping for secret-like env values
- **GIVEN** a direct MCP entry whose environment contains a value under a secret-like key (e.g. `API_TOKEN`)
- **WHEN** the user adopts the entry without supplying a credential mapping for that key
- **THEN** the request is rejected with a response listing the unresolved keys; when the mapping is supplied, the secret is stored in the credential store via the daemon and the created resource config carries a reference, never the value

### Requirement: Degrade a facet to a parse-error state when its config file is unparseable
When an agent config file cannot be parsed, the affected facet (MCP entries, plugins) MUST degrade to an explicit parse-error state (file path + parser error) without failing the surrounding view, leaving other facets and tabs unaffected, and entry-level writes against that file MUST be rejected until it parses again.

#### Scenario: degrade to read-only when MCP config is unparseable
- **GIVEN** a registered agent whose MCP-bearing config file contains invalid JSON/TOML
- **WHEN** the user lists the agent's MCP entries
- **THEN** Coffer reports a parse-error state naming the file and the parser error instead of failing the request, and rejects entry-level writes against that file until it parses again

### Requirement: List an agent's installed plugins without writing anything
The system MUST list an agent's installed plugins — each with its `<name>@<marketplace>` id, its enabled state and the marketplace it came from (a column of the listing, not a grouping of it) — deriving the inventory from the documented sources that type's child spec names. Each row carries best-effort manifest detail and the skills, commands and MCP servers the plugin bundles, read read-only from the plugin's install directory; those components belong to the plugin, so they surface here rather than on the agent's Skill or MCP pages, which list only the agent's own standalone resources. The listing itself writes nothing — not the documented surface, not any internal state file; every file under the agent's config directory is byte-identical before and after a listing. The writes are "Toggle a plugin through the documented location only" and "Uninstall a plugin by the type's own strategy". A plugin configured without its cache is flagged `cache_present=false`; no repair is attempted — reinstalling, like plugin installation and marketplace management generally, stays with the agent's own tooling.

#### Scenario: list an agent's plugins with enabled state
- **GIVEN** a registered agent whose documented plugin surface defines marketplaces and plugins with their cache directories present
- **WHEN** the user lists the agent's plugins
- **THEN** Coffer returns every plugin with its `<name>@<marketplace>` id, enabled state, marketplace grouping, and `cache_present=true`, deriving everything from the documented files at read time

#### Scenario: flag a plugin whose cache is missing
- **GIVEN** a registered agent whose plugin inventory references a plugin with no cache directory on disk
- **WHEN** the user lists the agent's plugins
- **THEN** that plugin is listed with `cache_present=false` and no repair is attempted

### Requirement: Toggle a plugin through the documented location only
Users MUST be able to enable/disable a plugin. Writes touch only that type's documented location and MUST never write the agents' internal state files. Audited as `agent_plugin_toggled`. The facet dispatches on the `PluginCapability` each agent record carries — a plugin-model discriminator, the write-surface allowlist key, and `can_toggle`/`can_uninstall` flags — rather than on per-agent branches.

#### Scenario: toggle a plugin's enabled state
- **GIVEN** a registered agent with an enabled plugin
- **WHEN** the user disables it
- **THEN** only that type's documented location is written, the agent's internal plugin state files are byte-identical before and after, and an `agent_plugin_toggled` audit entry is recorded

### Requirement: Uninstall a plugin by the type's own strategy
Users MUST be able to uninstall a plugin, by the per-agent strategy its child spec defines. Where the install state lives in a file Coffer must not hand-write, Coffer delegates to the agent's own CLI; when that CLI is unavailable the operation is rejected with `unprocessable_entity` (422) and error code `PLUGIN_UNINSTALL_UNSUPPORTED`, the in-app uninstall affordance is hidden (the listing reports `can_uninstall=false`), and a CLI error surfaces as `PLUGIN_UNINSTALL_FAILED` (422). Every successful path is audited as `agent_plugin_uninstalled`. Plugin installation and marketplace management are not provided by Coffer; both remain with the agent's own tooling.

#### Scenario: hide the uninstall affordance when the uninstall cannot run
- **GIVEN** a registered agent whose plugin uninstall is delegated to its own CLI, with plugins installed
- **WHEN** the user lists the agent's plugins with that CLI unavailable, and again with it available
- **THEN** the first listing reports `can_uninstall=false` and the second `can_uninstall=true`

### Requirement: List directory config entries
A config-file allowlist entry MAY be a **directory entry** (`kind=directory`): it resolves to a directory and lists its files (entry-relative path, size, modified time) instead of carrying content. A missing directory MUST list as `exists=false` with no files, and the read MUST NOT create it. Which allowlist entries are directory entries is per type, and each child spec names its own. The directory on disk is the source of truth.

#### Scenario: list a directory config entry's files
- **GIVEN** a registered agent whose directory config entry contains Markdown files (possibly nested)
- **WHEN** the user lists that config entry
- **THEN** Coffer returns the entry with `kind=directory` and its files (entry-relative path, size, modified time); a missing directory lists as `exists=false` with no files and is not created by the read

### Requirement: Read, write and delete files inside a directory entry
Users MUST be able to read individual files inside a directory entry; this read backs the UI's editor. Write (create-on-write) and delete of individual files are available through the in-app editor, the REST API and the `coffer agent` CLI. Child paths are validated server-side before any filesystem access: they MUST resolve inside the entry's directory (no `..`, no absolute paths, no symlink escape) and carry the `.md` extension — a containment violation is `not_found` (404) and a disallowed extension `unprocessable_entity` (422). Writes reuse the machinery of "Write config files atomically with a backup and an audit entry"; deletion preserves the prior content as `.bak`. Audited as `agent_config_file_written` / `agent_config_file_deleted`.

#### Scenario: create a file inside a directory entry
- **GIVEN** a registered agent with a directory config entry
- **WHEN** the user writes content to a new `.md` file path inside the entry through the in-app editor, the REST API or the `coffer agent` CLI
- **THEN** the file is created via the atomic-write machinery, an `agent_config_file_written` audit entry is recorded, and the next listing includes it

#### Scenario: delete a file inside a directory entry
- **GIVEN** a directory entry containing a file
- **WHEN** the user deletes that file through the REST API or the `coffer agent` CLI
- **THEN** the file is removed with its prior content preserved as `.bak`, an `agent_config_file_deleted` audit entry is recorded, and the next listing no longer shows it

#### Scenario: reject directory file paths outside the entry
- **GIVEN** a registered agent with a directory config entry
- **WHEN** the user addresses a child path containing `..`, an absolute path, or a non-`.md` extension
- **THEN** the request is rejected before any filesystem access with `not_found` (404) for containment violations or `unprocessable_entity` (422) for a disallowed extension

### Requirement: Reject stale config-file writes by fingerprint
Config-file reads (single files and directory children) MUST return a content fingerprint; writes MUST carry it back and are rejected with `conflict` (409) when the on-disk content changed since the read, leaving the file untouched. The agent's own process may rewrite a file between Coffer's read and write; the user then re-reads and retries, and the `.bak` of every Coffer write keeps the prior content recoverable in the reverse race.

#### Scenario: reject stale config-file writes
- **GIVEN** a config file (or directory child) read by the user, then modified on disk by another process
- **WHEN** the user writes back content carrying the fingerprint from the earlier read
- **THEN** the write is rejected with `conflict` (409) and the on-disk file is unchanged; re-reading yields a fresh fingerprint that allows the write

### Requirement: Annotate a leftover memory-projection block as safe to delete
When an instructions file still contains the **legacy** memory-projection managed block, the editor MUST annotate it as a leftover that is safe to delete. Coffer no longer writes or parses that block: native projection was retired ([Aggregate Agent Memory, Never Write It](../../../docs/decisions/aggregate-agent-memory-never-write-it.md)), the table behind it was dropped, and [memory](../memory/spec.md) "Reintroduce no retired mechanism" forbids reintroducing it. Detection is by marker prefix only — the block's content is never read. No live feature owns a managed block in these files, so there is no second block to annotate.

#### Scenario: annotate a leftover memory block in the instructions file
- **GIVEN** a registered agent whose instructions file still contains the legacy memory-projection block marker
- **WHEN** the user opens that file in the Config files tab
- **THEN** the config-file read reports the block as present
- **AND** the editor shows an annotation that the block is a leftover that is safe to delete

### Requirement: Carry the model binding on the agent record
The agent record MUST carry the model binding the rest of Coffer reads — `model`, `fast_model` and `wire_api` — because the model is chosen at the point of USE and an agent is where it is used, not on the connection that serves it. That binding MUST be settable without the web UI: `PATCH /api/v1/agents/{uid}` carries `model` / `fast_model` / `wire_api`, and `coffer agent edit` exposes them as `--model` / `--fast-model` / `--wire-api`, with `--clear-fast-model` for the explicit null that unbinds the fast slot — options on the verb that edits the agent rather than a command of their own, because they are fields of the agent. Projecting a binding into the agent's native config is provider-switching's; validating a bound value against what one type accepts is that type's child spec (see [agent-registry/codex](codex/spec.md) "Accept only responses as Codex's wire_api" for `wire_api`).

#### Scenario: bind a model to an agent from the command line
- **GIVEN** a registered agent
- **WHEN** the user runs `coffer agent edit` with `--model` and `--fast-model`, then again with `--clear-fast-model`
- **THEN** the agent record reports the bound `model` and `fast_model` after the first edit
- **AND** after the second edit `fast_model` is null while `model` is unchanged

### Requirement: Serve each agent type's model catalogue
`GET /api/v1/agent-providers/{agent_key}/models` MUST answer, per agent type, which models that agent can be put on, read back from the installed agent and never written down in Coffer. Each entry MUST carry `id` (passed to the agent verbatim), `label`, `description`, the reasoning `efforts` its runtime reports and the `default_effort` it would use, keeping a reported default only when it is one of the offered levels. An unknown `agent_key` MUST be a 404.

#### Scenario: list the models an agent can be put on
- **GIVEN** a registered `codex` agent whose own config names a model
- **WHEN** the user requests `GET /api/v1/agent-providers/codex/models`
- **THEN** the response lists that model with `id`, `label`, `description`, `efforts` and `default_effort`
- **AND** the same request for an unknown agent key answers 404

### Requirement: Read the model catalogue back from the installed agent
The catalogue MUST be one backend service answering per agent, and every entry — id, label, description — MUST be read back from the installed agent rather than written into Coffer, because a list written down here goes stale on the next CLI release; a model released after Coffer shipped appears with no Coffer release. Each type's child spec names its sources, and the order those sources answer in is the order of the picker. Every source MUST degrade to nothing on its own: a missing CLI, a changed bundle layout, an unauthenticated or wedged agent costs the models that source would have added and nothing else.

#### Scenario: lose only a failing source's models
- **GIVEN** an agent type with two catalogue sources, the first of which raises
- **WHEN** the catalogue is read
- **THEN** the answer carries exactly the second source's models and the request does not fail

### Requirement: Keep one source of truth for an agent's models
There MUST be exactly one source of truth. No Coffer surface may keep a model list of its own: the agent's catalogue is the answer of "Serve each agent type's model catalogue", and what a picker is OFFERED — which narrows to an active connection's curated set where there is one — is [provider-switching](../provider-switching/spec.md) "Offer only text models to chat pickers"'s answer, served over the wire from that one backend rather than reassembled by any client. Nothing in Coffer curates an agent's models; two attempts to have someone curate them, first on the agent and then on the channel, were both removed. The accepted cost is that a model the agent's own catalogue does not name cannot be PICKED from a Coffer surface — it stays typeable wherever the CLI accepts a name. The benefit is that a newly released model reaches every surface with no Coffer release at all.

#### Scenario: offer the agent's whole catalogue with nothing curated on the agent
- **GIVEN** a registered agent whose installed agent reports several models and no active connection curating a set
- **WHEN** the models offered for that agent are read
- **THEN** every model the agent reports is offered, in the order reported
- **AND** the agent resource carries no model list of its own

### Requirement: Contribute models from the type's native config read-only
Each type's own native config MUST contribute the local model choices only it knows, alongside whatever its runtime reports. The key each type reads is named in that type's child spec, and it is read, never written.

#### Scenario: read native-config models without writing the config
- **GIVEN** a registered agent whose native config names local model choices
- **WHEN** the catalogue's native-config source is read
- **THEN** those models are returned
- **AND** the native config file is byte-identical before and after the read

### Requirement: Carry reasoning-effort levels beside the model id
A reasoning-effort level MUST travel BESIDE the model id, never inside it. `AgentModel` carries `efforts: tuple[str, ...]` — the levels the agent reported, in the order it reported them, empty for an agent that takes no such setting — and `default_effort`, the level it would use when none is chosen; the catalogue route exposes both. Beside, because that is what the protocols do: the effort is its own field on a turn, so folding levels into the name would multiply one model into several entries under names Coffer invented. A reported default is kept only when it is one of the offered levels, and nothing is invented for a model that reports none. The stakes are not cosmetic: the same prompt on the same model reported 53 reasoning output tokens at the lowest level and 2569 at the highest.

#### Scenario: carry effort levels beside the model id
- **GIVEN** an agent runtime that reports one model with several reasoning levels and a default among them
- **WHEN** the catalogue is read
- **THEN** there is exactly one entry for that model, its id carrying no level
- **AND** its `efforts` are the reported levels in reported order and its `default_effort` is the reported default

### Requirement: Read reasoning-effort levels from the agent runtime
The levels MUST come from the agent's RUNTIME, not from the model, read from the source that type's child spec names. A runtime that declares none yields an empty tuple: the effort controls hide themselves and turns are unchanged.

#### Scenario: offer no effort levels when the runtime declares none
- **GIVEN** an agent runtime that declares no reasoning-effort levels
- **WHEN** the levels are read for the catalogue
- **THEN** they are an empty tuple

### Requirement: Report no default effort the runtime does not publish
No default level MAY be reported — the system MUST NOT report one — unless the runtime publishes one machine-readably. Prose documentation naming one level is not a machine-readable fact, and a picker naming the wrong default is worse than one naming none.

#### Scenario: report no default when the runtime publishes none
- **GIVEN** an agent runtime that reports reasoning levels but no machine-readable default
- **WHEN** the catalogue is read
- **THEN** every entry carries its levels and a `default_effort` of null

### Requirement: Scan an agent's own native memory stores read-only
The system MUST expose a read-only **native-memory scan** that lists an agent type's own native memory stores — the agent's self-written store, distinct from the human-authored `instructions` config files — in the layout that type's child spec defines. Each row carries a `project` label and `path` that are the REAL project directory, the real `memory_dir`, and an `item_count`. An agent type with no native memory layout, or one whose layout is absent on disk, returns an empty list. The scan is read-only, derives everything from disk at read time (nothing stored), and — consistent with "Audit every agent lifecycle event" — emits NO audit event. It never writes the agent's store. What Coffer does with the agents' own stores beyond showing them is memory's.

Coffer does not import a native memory store into its own knowledge layer: the knowledge layer is a directory of markdown files the user and agents write deliberately ([Knowledge Is Plain Files](../../../docs/decisions/knowledge-is-plain-files.md)), and a bulk copy of another tool's store would be material nobody chose to keep. Reading the store, and opening it where it lives, is the whole of this facet.

#### Scenario: return an empty scan when the agent has no native memory on disk
- **GIVEN** a registered agent whose native memory layout is absent on disk
- **WHEN** the user scans the agent's native memory
- **THEN** the scan returns an empty list
- **AND** no audit event is recorded

### Requirement: List an agent's transcript sessions read-only
The system MUST expose a read-only listing of an agent's local transcript sessions, found at the location that type's child spec names. Each session summary carries its `session_id`, a derived `title` (the session's first *real* user turn, secret-scrubbed — a turn whose text is nothing but an injected markup block was written by the harness, not by a person, and is not a candidate), `project_path`, `message_count`, `started_at`, `last_activity_at`, and the transcript file's absolute `source_path` — the last feeding the open / reveal affordances of "Open config files in an external editor or reveal them". The listing MUST support a case-insensitive substring search over title and project path, an exact `project` filter, sorting by `started_at`, `last_activity_at` (default) or `message_count` in either direction, and `limit`/`offset` paging alongside the matched `total`, because an agent accumulates thousands of sessions and the surface cannot load them all. Parsing is per-file and cached by the file's modification time **and size**; a file that fails to parse is skipped rather than failing the listing. Message text is not carried on the wire by THIS listing and is not retained by it — a body travels only through "Read one transcript session in bounded windows", for the one session a reader opened.

Coffer never writes the transcript files, never stores their content and never sends them anywhere. It does not distil transcripts into memory: the agent's own memory is memory's domain, and [memory](../memory/spec.md) "Reintroduce no retired mechanism" forbids reintroducing a path that writes back into it.

#### Scenario: browse an agent's transcript history with title, search, and sort
- **GIVEN** a registered agent with several local transcript sessions across more than one project
- **WHEN** the agent's transcripts are listed with a search query, a project filter, and a sort key (`started_at`, `last_activity_at` or `message_count`)
- **THEN** each returned session summary carries a derived title, message count, `started_at`, `last_activity_at`, and the session file's absolute source path; only sessions whose title or project path matches the search and whose project matches the filter are returned, ordered by the requested sort key and direction, and paged by `limit`/`offset` alongside the matched total — read-only, emitting no audit event and writing nothing

### Requirement: Keep the transcript summary sidecar disposable
The listing MAY keep a **disposable derived sidecar** of those summaries so a cold parse is not repeated on every daemon restart — an agent's transcripts run to thousands of files and gigabytes, and re-deriving them is seconds of blocking I/O. The sidecar holds no message text, lives **outside the vault and outside `coffer.db`** at one path the user may delete at any moment, and no export or backup carries it. It MUST never change an answer, only the time to reach one: a summary is served from it only while its file's modification time and size still match, and with the sidecar missing, empty, corrupt or mid-write the listing MUST still be correct — merely slower. The system MAY warm it in the background, off the request path, so the first visit after an install is not the one that pays. Everything the listing returns is still derived from the agent's own files on disk: nothing about a session is a stored truth. Like the other workspace listings, neither the listing nor the warm pass emits an audit event.

#### Scenario: list transcripts correctly with an unusable sidecar
- **GIVEN** an agent with transcript sessions on disk and a summary sidecar that is corrupt
- **WHEN** the transcripts are listed
- **THEN** the listing returns the same sessions it returns with no sidecar at all

### Requirement: Read one transcript session in bounded windows
The system MUST expose a read-only **single-session read** that returns one transcript's summary fields (as "List an agent's transcript sessions read-only" lists them) together with a WINDOW of its conversational turns — each turn's role, text and timestamp — plus the `limit`/`offset` that window was taken with. A session is addressed by the absolute `source_path` the listing handed out, which MUST resolve inside that agent's own transcript directory; any other path is `not_found` (404), the same answer as a transcript that has since been deleted, so the difference cannot be used to probe the filesystem.

This is the ONLY place a transcript body crosses the wire, and everything guarding a body is concentrated here: every turn is secret-scrubbed with the same redaction the listing's titles get (a prompt is exactly where a pasted key would be), a turn longer than the system's per-turn cap is cut to its start and flagged, and the number of turns returned is bounded — a transcript can be tens of megabytes, so the surface pages through it rather than loading it. The whole file's turn count is returned alongside the window, so a reader is never shown 200 turns and left to assume that is all of them. Read-only: nothing is written, nothing is retained, and no audit event is emitted.

#### Scenario: read one of the agent's conversations
- **GIVEN** a registered agent with a local transcript session listed by "List an agent's transcript sessions read-only", whose turns include one carrying a pasted API key
- **WHEN** the user opens that session by the absolute source path the listing gave, with a turn window smaller than the session
- **THEN** Coffer returns the session's summary fields plus that window of turns with roles, text and timestamps — the pasted key redacted, an over-long turn cut to its start and flagged, and the whole file's turn count reported alongside the window — while a path outside the agent's own transcript directory is rejected as `not_found` (404), the same answer as a transcript that is gone; read-only, emitting no audit event and writing nothing

### Requirement: Read one native memory store's files read-only
The system MUST expose a read-only **native-memory store read** that returns one store's directory as a file tree (each entry's name, store-relative path, type and size) and one file inside it as text (its contents, its absolute path for the open / reveal affordances, and whether it was truncated or is binary). A store is addressed by the `memory_dir` the native-memory scan handed out, which MUST be exactly a directory that type's layout would have listed — and not merely some path under the agent's config dir, which also holds its transcripts, settings and plugin cache. A directory that is not one of the agent's stores, a file path escaping the store, and a file that does not exist are all `not_found` (404). Reads are capped in size and the walk is depth-bounded, with both facts reported rather than silently applied. Read-only: Coffer never writes an agent's own memory, so the surface previews and offers open / reveal instead of an editor, and emits no audit event.

#### Scenario: browse one native memory store's files
- **GIVEN** a registered agent with a native memory store listed by "Scan an agent's own native memory stores read-only", holding Markdown files in the store directory and a subdirectory
- **WHEN** the user opens that store by the `memory_dir` the listing gave and then reads one file in it
- **THEN** Coffer returns the store directory as a tree (directories before files, paths relative to the store) and the file's contents with the absolute path that backs open / reveal, while a directory that is not one of this agent's stores — its sibling project directory included — and a path escaping the store are both rejected as `not_found` (404); read-only, emitting no audit event and writing nothing

### Requirement: Expose every agent operation through REST, CLI and the Agents page
Every management operation — register/list/view/update/remove, config-file list/read/write (including directory children), Coffer-MCP install/uninstall/status, MCP entry list/remove/adopt, plugin list/toggle/uninstall, native-memory scan and store-file read, transcript listing and single-session read, and the model catalogue — MUST be available through (a) the REST API and (b) the `coffer agent ...` CLI, each subcommand calling the corresponding REST endpoint.

The Agents page in the web UI MUST expose all of these, config-file content writes included. It renders within the web-ui shell at `/agents` as a **dedicated top-level nav entry** — a sibling of the Resources and System groups, not nested under Resources, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file (and a directory-entry child) opens in a viewer that becomes **editable behind an explicit Edit**, saves through the same path as REST and the CLI ("Validate config-file content before saving it", "Write config files atomically with a backup and an audit entry"), and guards an unsaved draft three ways — picking another file asks first, leaving the tab asks first, and leaving the page asks first. Open-in-external-editor / reveal-in-file-manager sit beside the content for the edits that want a real editor.
- The agent detail page has seven tabs — Overview, Skills, MCP servers, Plugins, Memory, Conversations, and Config files. Plugins acts on the agent (enable / disable / uninstall), and each plugin row expands to its manifest detail and bundled components. Memory carries one write — installing or removing Coffer's memory-delivery hook, which memory specifies (including its audit events and the per-agent delivery status the tab renders) and this page mounts; the rest of Memory, and all of Conversations, are read-only views of the agent's own stores.
- Neither the Memory nor the Conversations table carries per-row actions: a row OPENS its subject, and the open / reveal affordances live on the page it opens, beside the thing they act on. A Conversations row opens that one session rendered as a readable conversation, beside a contents list of the session's prompts that scrolls the conversation to any one of them; a Memory row opens that store's directory as a file tree with a read-only preview, because a store is a directory and one session is a single file.

#### Scenario: desktop app agents page
- **GIVEN** Coffer's web UI is open and one or more agents are registered
- **WHEN** the user opens the Agents page
- **THEN** every registered agent appears with type, name, and `config_dir`

#### Scenario: config-file and MCP operations mirror across surfaces
- **GIVEN** the daemon exposes the config-file and MCP-install routes
- **WHEN** the user invokes the equivalent `coffer agent config …` / `coffer agent mcp …` CLI subcommands
- **THEN** each subcommand calls the corresponding REST endpoint and produces equivalent state, and read subcommands accept `--json`

#### Scenario: CLI surface mirrors REST operations
- **GIVEN** the daemon is running and exposes the REST agent routes
- **WHEN** the user invokes `coffer agent add`, `list`, `edit`, `rm`, or `detect`
- **THEN** each subcommand calls the corresponding REST endpoint and produces equivalent state changes, and every read subcommand additionally accepts `--json` for machine-readable output

### Requirement: Lead a transcript turn with the person's own words
**Readable means the person's words lead.** A "user turn" in a transcript is not only what the user typed: every harness prepends its own blocks to the same turn — reminders, task notifications, environment dumps. Both surfaces — the contents list and the conversation — MUST read the turn as the person's, not the harness's: the contents list MUST index a turn by the first line the PERSON wrote and MUST omit a turn they wrote no part of, and the conversation MUST lead with their words, with the prepended blocks folded away rather than dropped — the blocks are part of the record and a view that discarded them would be claiming the turn said less than it did. Blocks are identified by SHAPE, not by a list of block names: naming them one at a time never finishes, and prose that merely contains a `<` is not markup.

#### Scenario: index a turn by the person's words, not the harness's blocks
- **GIVEN** an opened conversation whose user turns include one led by a harness reminder block before the person's question, and one made only of harness blocks
- **WHEN** the contents list is built from the turns
- **THEN** the first turn is indexed by the person's question
- **AND** the turn made only of harness blocks is left out of the contents list

### Requirement: Offer JSON output on every CLI read
The CLI MUST support `--json` for machine-readable output on every read operation.

#### Scenario: agent reads print JSON with --json
- **GIVEN** a registered agent
- **WHEN** the user runs `coffer agent list --json` and `coffer agent show <name> --json`
- **THEN** each prints only JSON, carrying the agent's name, type and config directory, and `show` also its uid

### Requirement: Open config files in an external editor or reveal them
For each config file (and each directory-entry child) the UI MUST offer **open-in-external-editor** and **reveal-in-file-manager** actions on the file, using the `path` from "List an agent's config files with their locations" and "Read allowlisted config files without creating them". Open and reveal perform the real OS action through the daemon's filesystem-action endpoints (`POST /api/v1/fs/open`, `POST /api/v1/fs/reveal`, and the installed-editor enumeration `GET /api/v1/fs/editors` behind the preference — all owned by the daemon spec, which this spec consumes and does not specify), since the loopback daemon is always on the user's own machine ([Daemon Proxies OS File Actions](../../../docs/decisions/daemon-proxies-os-file-actions.md)). There is no copy-path fallback. The editor used for open-in-external-editor references the user's "preferred external editor" preference defined by web-ui (not re-specified here).

#### Scenario: open a config file and reveal it through the daemon
- **GIVEN** an agent's Config files tab with an existing config file selected
- **WHEN** the user chooses open-in-external-editor and then reveal-in-file-manager on it
- **THEN** the UI asks the daemon to open that file's absolute path and then to reveal it
- **AND** no copy-path affordance is offered

### Requirement: Audit every agent lifecycle event
The system MUST record an audit entry, carrying timestamp, actor and the affected agent reference, for every lifecycle event: agent created, updated, removed (via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events); config file written/deleted (`agent_config_file_written` / `agent_config_file_deleted`); Coffer MCP installed/uninstalled; MCP entry removed/adopted (`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`); plugin toggled/uninstalled (`agent_plugin_toggled` / `agent_plugin_uninstalled`). Agents have no enable/disable concept; discovery and all workspace listings — MCP entries, plugins, config files, native memory stores, transcript sessions, the model catalogue — are read-only and emit no audit event, the background pass that warms the transcript summary cache included. Reading ONE of the listed items — a single session's turns, a single store's files — is the same act at a smaller scale and audits nothing either. The audit events of the memory-delivery install the Memory tab offers are memory's, not this spec's.

#### Scenario: audit lifecycle events
- **GIVEN** the user has registered, edited, or removed agents
- **WHEN** they view the audit log
- **THEN** every lifecycle change (create, update, remove) appears via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events, each carrying timestamp, actor, and the affected agent reference. (Agents have no enable/disable concept; discovery is read-only and registers nothing, so neither emits an audit event of its own.)

### Requirement: Expose agent discovery on every surface
The system MUST expose a read-only discovery operation listing installed-but-unregistered agents as candidates, available from the REST API (`GET /api/v1/agents/candidates`), the `coffer agent detect` CLI, and the Agents page in the web UI, where the user adds each candidate with a single confirm and no typing of type identifiers or paths.

#### Scenario: list discovery candidates from the command line
- **GIVEN** a supported agent's install marker is present and no agent of that type is registered
- **WHEN** the user runs `coffer agent detect`
- **THEN** the command lists that type as a candidate with its default config dir
- **AND** no agent is registered as a result

### Requirement: Offer a folder picker for a custom config directory
When choosing a custom `config_dir`, the web UI MUST offer a folder picker rather than requiring the user to type a path. It MUST use the daemon's native directory dialog (`POST /api/v1/fs/pick-folder`, owned by the daemon spec), falling back to the daemon-backed folder browser (`GET /api/v1/fs/browse`, owned by the daemon spec) only when the host has no native dialog tool. Both yield an absolute path that is then validated per "Validate the config directory at registration" before registration.

#### Scenario: pick a custom config directory with the native dialog
- **GIVEN** the add-agent dialog with its manual form open and the host offering a native directory dialog
- **WHEN** the user browses for the config directory and picks a folder
- **THEN** the picked absolute path fills the config directory field
- **AND** the in-app folder browser is not opened

### Requirement: Drop nothing locally when the plugin inventory document is deleted
Deleting the plugin inventory document for an agent (sync state area `agent-plugins/<agent>`) MUST drop nothing locally. The inventory has no local store beyond the document itself, and there is no uninstall-by-sync path: the next export republishes whatever this machine's agent still holds. This is this spec's answer to the rule that each state area's provider defines what its own document's deletion means (vault-sync).

#### Scenario: keep local plugins when the inventory document is deleted
- **GIVEN** an agent whose plugins are published as an `agent-plugins/<agent>` sync document
- **WHEN** that document is deleted by a sync
- **THEN** no agent and no plugin changes locally
- **AND** the next export republishes the plugins the agent still holds
