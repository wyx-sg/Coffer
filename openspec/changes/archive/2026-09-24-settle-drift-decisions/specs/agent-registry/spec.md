## RENAMED Requirements

- FROM: `### Requirement: Manage the agent lifecycle without an enable state`
- TO: `### Requirement: Manage the agent lifecycle`

## MODIFIED Requirements

### Requirement: Manage the agent lifecycle
Users MUST be able to register, list, view, update (config_dir, description), and remove agents. An agent also carries the kind-agnostic `enabled` flag every Resource has; switching it is "Switch an agent off with the kind-agnostic enabled flag", not a field of the agent's own update. The agent name is optional at registration — when omitted, the system MUST derive a stable per-type default (underscores become hyphens, e.g. `claude_code` → `claude-code`). Skill bindings between an agent and a skill belong to skill-manager; this registry defines no skill operations beyond exposing an `on_delete` hook for cascade cleanup and an `on_enabled_changed` hook for the reclaim of "Switch an agent off with the kind-agnostic enabled flag".

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

### Requirement: Reject stale config-file writes by fingerprint
Config-file reads (single files and directory children) MUST return a content fingerprint. A write MAY carry that fingerprint back; a write that carries one MUST be rejected with `conflict` (409, `CONFIG_FILE_STALE`) when the on-disk content changed since the read, leaving the file untouched. A write that carries none is applied as sent, for scripted REST use. `coffer agent config edit` MUST always send the fingerprint of the read it opened the editor on, because it holds the file open for as long as the user edits — exactly the window another writer lands in — and the in-app editor sends it too. The agent's own process may rewrite a file between Coffer's read and write; the user then re-reads and retries, and the `.bak` of every Coffer write keeps the prior content recoverable in the reverse race.

#### Scenario: reject stale config-file writes
- **GIVEN** a config file (or directory child) read by the user, then modified on disk by another process
- **WHEN** the user writes back content carrying the fingerprint from the earlier read
- **THEN** the write is rejected with `conflict` (409) and the on-disk file is unchanged; re-reading yields a fresh fingerprint that allows the write

### Requirement: Carry the model binding on the agent record
The agent record MUST carry the model binding the rest of Coffer reads — `model`, `fast_model` and `wire_api` — because the model is chosen at the point of USE and an agent is where it is used, not on the connection that serves it. That binding MUST be settable without the web UI: `PATCH /api/v1/agents/{uid}` carries `model` / `fast_model` / `wire_api`, and `coffer agent edit` exposes them as `--model` / `--fast-model` / `--wire-api`, with `--clear-fast-model` for the explicit null that unbinds the fast slot — options on the verb that edits the agent rather than a command of their own, because they are fields of the agent. A field the request omits is unchanged. Only `fast_model` clears on an explicit null; `model` and `wire_api` have no null that unbinds them, so an explicit null for either is treated as omitted. Projecting a binding into the agent's native config is provider-switching's; validating a bound value against what one type accepts is that type's child spec (see [agent-registry/codex](codex/spec.md) "Accept only responses as Codex's wire_api" for `wire_api`).

#### Scenario: bind a model to an agent from the command line
- **GIVEN** a registered agent
- **WHEN** the user runs `coffer agent edit` with `--model` and `--fast-model`, then again with `--clear-fast-model`
- **THEN** the agent record reports the bound `model` and `fast_model` after the first edit
- **AND** after the second edit `fast_model` is null while `model` is unchanged

### Requirement: Read one native memory store's files read-only
The system MUST expose a read-only **native-memory store read** that returns one store's directory as a file tree (each entry's name, store-relative path, type and size) and one file inside it as text (its contents, its absolute path for the open / reveal affordances, and whether it was truncated or is binary). A store is addressed by the `memory_dir` the native-memory scan handed out, which MUST be exactly a directory that type's layout would have listed — and not merely some path under the agent's config dir, which also holds its transcripts, settings and plugin cache. A directory that is not one of the agent's stores, a file path escaping the store, and a file that does not exist are all `not_found` (404); whether a directory is one of the agent's stores is decided by its shape alone, so the answer cannot be used to probe the filesystem. A store that has that shape but no longer exists on disk reads as an empty tree (200), not a 404. Reads are capped in size and the walk is depth-bounded, with both facts reported rather than silently applied. Read-only: Coffer never writes an agent's own memory, so the surface previews and offers open / reveal instead of an editor, and emits no audit event.

#### Scenario: browse one native memory store's files
- **GIVEN** a registered agent with a native memory store listed by "Scan an agent's own native memory stores read-only", holding Markdown files in the store directory and a subdirectory
- **WHEN** the user opens that store by the `memory_dir` the listing gave and then reads one file in it
- **THEN** Coffer returns the store directory as a tree (directories before files, paths relative to the store) and the file's contents with the absolute path that backs open / reveal, while a directory that is not one of this agent's stores — its sibling project directory included — and a path escaping the store are both rejected as `not_found` (404); read-only, emitting no audit event and writing nothing

### Requirement: Expose every agent operation through REST, CLI and the Agents page
Every management operation — register/list/view/update/remove, config-file list/read/write (including directory children), Coffer-MCP install/uninstall/status, MCP entry list/remove/adopt, plugin list/toggle/uninstall, native-memory scan and store-file read, transcript listing and single-session read, and the model catalogue — MUST be available through (a) the REST API and (b) the `coffer agent ...` CLI, each subcommand calling the corresponding REST endpoint. The model catalogue's command is `coffer agent models <agent_type> [--json]`: it takes the agent type the catalogue route is keyed by (`claude_code`, `codex`), not an agent's name, prints one line per offered model with its label and its effort levels (the default level marked), and an unknown type exits non-zero with the route's not-found message.

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

#### Scenario: the command line lists an agent's models
- **GIVEN** the catalogue route offers a `codex` model with reasoning levels and a default among them, and a second model with none
- **WHEN** the user runs `coffer agent models codex`
- **THEN** the command prints one line per model, the first carrying its id, its label and its levels with the default marked
- **AND** `--json` prints the route's response unchanged

### Requirement: Audit every agent lifecycle event
The system MUST record an audit entry, carrying timestamp, actor and the affected agent reference, for every lifecycle event: agent created, updated, removed (via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events); agent enabled/disabled (via the kind-agnostic `resource_enabled` / `resource_disabled` events); config file written/deleted (`agent_config_file_written` / `agent_config_file_deleted`); Coffer MCP installed/uninstalled; MCP entry removed/adopted (`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`); plugin toggled/uninstalled (`agent_plugin_toggled` / `agent_plugin_uninstalled`). Discovery and all workspace listings — MCP entries, plugins, config files, native memory stores, transcript sessions, the model catalogue — are read-only and emit no audit event, the background pass that warms the transcript summary cache included. Reading ONE of the listed items — a single session's turns, a single store's files — is the same act at a smaller scale and audits nothing either. The audit events of the memory-delivery install the Memory tab offers are memory's, not this spec's.

#### Scenario: audit lifecycle events
- **GIVEN** the user has registered, edited, or removed agents
- **WHEN** they view the audit log
- **THEN** every lifecycle change (create, update, remove) appears via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events, each carrying timestamp, actor, and the affected agent reference. (Discovery is read-only and registers nothing, so it emits no audit event of its own.)

## ADDED Requirements

### Requirement: Switch an agent off with the kind-agnostic enabled flag
An agent MUST carry the kind-agnostic `enabled` flag, toggled through the generic `POST /api/v1/resources/{uid}/enable|disable` routes and `coffer resource enable|disable agent <name>`, and audited as `resource_enabled` / `resource_disabled`. A disabled agent is one Coffer does not write into and does not read from: its delivered skills are reclaimed and nothing new is delivered to it ([skill-manager](../skill-manager/spec.md)), its native memory is not aggregated ([memory](../memory/spec.md)), and its native config does not feed the model catalogue of "Serve each agent type's model catalogue" — the catalogue is read as if no agent of that type were registered. Enabling it again puts back whatever the skills' own state grants, so the switch is never a one-way door. The agent's own routes neither carry nor change the flag: `AgentOut` does not report it and `PATCH /api/v1/agents/{uid}` does not set it.

#### Scenario: disabling an agent reclaims its skills and drops it from the catalogue
- **GIVEN** a registered agent holding a delivered skill, whose config dir the model catalogue reads for its type
- **WHEN** the agent is disabled through the kind-agnostic enabled flag
- **THEN** the delivered skill's link is gone from the agent's skills directory and no binding remains enabled for it
- **AND** the catalogue for that type no longer reads the agent's config dir
- **AND** a `resource_disabled` audit entry names the agent
