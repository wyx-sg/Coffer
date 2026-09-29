## MODIFIED Requirements

### Requirement: Discover installed agents as candidates without registering them
The system MUST provide a read-only discovery operation that scans each supported type's install marker — named in that type's child spec — and reports installed types that are not already registered as **candidates** (each carrying `type`, `display_name`, `config_dir`, `default_skill_dir`, and `suggested_name`). Candidates are derived at scan time and never stored. Discovery MUST NOT register anything automatically — the user reviews candidates and confirms which to add. The daemon MUST NOT auto-register agents on startup.

On the command line, candidates are rows of kind `agent` in `coffer scan`, the one listing of everything agents hold that Coffer does not manage yet (see [resource-framework](../resource-framework/spec.md), the requirement that defines `coffer scan`, `coffer adopt` and `coffer discard`). Confirming a candidate is `coffer adopt agent <type>`, which registers that type under its suggested name and default config directory through the ordinary registration of "Manage the agent lifecycle". A candidate MUST NOT be discardable: nothing of Coffer's put the agent there, so `coffer discard agent` is refused and removes nothing.

#### Scenario: discover installed agents as candidates
- **GIVEN** a Coffer install with a supported agent's install marker present and no agent registered
- **WHEN** the user runs discovery
- **THEN** Coffer reports that type as a candidate (type, display name, default config dir, suggested name) and registers nothing — discovery is read-only

#### Scenario: skip already-registered types on subsequent scan
- **GIVEN** a `codex` agent is already registered
- **WHEN** the user runs discovery again
- **THEN** `codex` is not offered as a candidate

#### Scenario: adopt a discovered agent from the command line
- **GIVEN** a `codex` install marker is present and no `codex` agent is registered
- **WHEN** the user runs `coffer scan`, then `coffer adopt agent codex`
- **THEN** the scan lists a row of kind `agent` for `codex` and registers nothing
- **AND** the adopt registers a `codex` agent under the candidate's suggested name and default config directory, audited as `resource_created`
- **AND** `coffer discard agent codex` is refused and changes nothing

### Requirement: Manage the agent lifecycle
Users MUST be able to register, list, view, update (config_dir, description, title, name), and remove agents. An agent also carries the kind-agnostic `enabled` flag every Resource has; switching it is "Switch an agent off with the kind-agnostic enabled flag", not a field of the agent's own update. The agent name is optional at registration — when omitted, the system MUST derive a stable per-type default (underscores become hyphens, e.g. `claude_code` → `claude-code`). An agent's name stays renamable, because it appears only on Coffer's own surfaces; like every resource it also carries an optional, editable `title` that surfaces show in place of the name when it is set. Skill bindings between an agent and a skill belong to skill-manager; this registry defines no skill operations beyond exposing an `on_delete` hook for cascade cleanup and an `on_enabled_changed` hook for the reclaim of "Switch an agent off with the kind-agnostic enabled flag".

On the command line the lifecycle is the `coffer agent` group's uniform verbs — `list`, `show`, `add <type>`, `edit <name>` (with `--name`, `--title`, `--description`, `--config-dir` and the model options of "Carry the model binding on the agent record"), `rm`, `enable` and `disable`. The `agent` kind has no `scope` verb, because it declares no scope. `coffer agent show <name>` MUST print the agent's record together with two derived states: `coffer_mcp`, whether Coffer's MCP entry is installed (see "Keep the Coffer MCP install idempotent and report its status"), and `memory_delivery`, whether memory's session-start delivery is installed ([memory](../memory/spec.md) "Show delivery state on the agent's own page").

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

#### Scenario: give an agent a title from the command line
- **GIVEN** a registered agent named `claude-code` with no title
- **WHEN** the user runs `coffer agent edit claude-code --title "Work laptop Claude"`
- **THEN** `coffer agent list` and `coffer agent show claude-code` show the title
- **AND** the agent is still addressed by the name `claude-code` and keeps its uid

### Requirement: Install Coffer's MCP server into an agent in one action
Users MUST be able to install Coffer's own MCP server into an agent in one action — the Install action on the agent's page, the REST install route, or `coffer agent connect <name>` on the command line. The install writes a `coffer` stdio MCP-server entry into the agent's MCP config, using the shape declared by that agent's manifest `McpInjectionSpec` and named by that type's child spec.

- `command` is the absolute path of the `coffer-mcp-shim` binary, resolved on `PATH`, then the running interpreter's scripts directory — so a venv-installed shim is found even when the daemon's `PATH` lacks the venv — then the bundled binary; a `COFFER_MCP_SHIM_PATH` environment override takes precedence over all.
- The install additionally writes `--agent-uid <uid>` in the entry shape's argument slot — the agent's immutable uid, never its mutable name, because the entry is written once into a file Coffer does not otherwise revisit and a name would go stale on the first rename — so the gateway can attribute the session to this agent for per-agent scope enforcement ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)).
- If the shim cannot be resolved, install is rejected with an error naming the missing binary and nothing is written.

#### Scenario: refuse the Coffer MCP install when the shim cannot be resolved
- **GIVEN** a registered agent and no resolvable `coffer-mcp-shim` binary
- **WHEN** the user installs Coffer's MCP
- **THEN** the install is rejected with an error naming the missing binary
- **AND** the agent's MCP config file is not written

#### Scenario: connect an agent to Coffer from the command line
- **GIVEN** a registered agent whose MCP config has no `coffer` entry and a resolvable `coffer-mcp-shim` binary
- **WHEN** the user runs `coffer agent connect <name>`
- **THEN** the agent's MCP config carries a `coffer` entry whose arguments name the agent's uid
- **AND** an `agent_mcp_installed` audit entry is recorded

### Requirement: Keep the Coffer MCP install idempotent and report its status
Install MUST be idempotent — re-installing updates the existing `coffer` entry in place and never creates a duplicate. The system MUST expose a status operation reporting whether Coffer's MCP is currently installed for the agent; the status is derived from the agent's MCP config file, never stored. On the command line the status is the `coffer_mcp` field of `coffer agent show <name>`, in its plain and its `--json` output.

#### Scenario: report Coffer-MCP install status
- **GIVEN** a registered agent whose MCP config does not contain a `coffer` server entry
- **WHEN** the user checks Coffer-MCP install status
- **THEN** Coffer reports `installed=false`

#### Scenario: install Coffer's MCP is idempotent
- **GIVEN** an agent that already has Coffer's MCP installed
- **WHEN** the user installs again
- **THEN** the existing `coffer` entry is updated in place (never duplicated) and status still reports `installed=true`

#### Scenario: agent show reports the Coffer MCP status
- **GIVEN** one registered agent with Coffer's MCP installed and one without
- **WHEN** the user runs `coffer agent show <name> --json` for each
- **THEN** the first carries `coffer_mcp` reporting installed and the second `coffer_mcp` reporting not installed

### Requirement: Uninstall Coffer's MCP server from an agent
Users MUST be able to uninstall Coffer's MCP, removing the `coffer` entry from the agent's MCP config — from the agent's page, the REST uninstall route, or `coffer agent disconnect <name>` on the command line. Uninstalling when not installed is a no-op success and status then reports not installed.

#### Scenario: uninstall Coffer's MCP when it is not installed
- **GIVEN** a registered agent whose MCP config has no `coffer` entry
- **WHEN** the user uninstalls Coffer's MCP
- **THEN** the operation succeeds without changing the agent's MCP config
- **AND** status reports `installed=false`

#### Scenario: disconnect an agent from Coffer on the command line
- **GIVEN** an agent that has Coffer's MCP installed
- **WHEN** the user runs `coffer agent disconnect <name>`
- **THEN** the `coffer` entry is gone from the agent's MCP config
- **AND** `coffer agent show <name>` reports `coffer_mcp` as not installed

### Requirement: List the MCP entries in the agent's own config files
The system MUST parse and list the MCP server entries configured in the agent's own files, reading the source files that type's child spec names and labelling each entry with the file it came from. Each entry carries name, source, transport (stdio command or HTTP URL), the `enabled` flag where the format defines one, `is_coffer` for Coffer's own gateway entry, and `matches_resource` naming an equivalent registered `mcp_server` resource when one exists. Entries are derived at read time, never stored; Coffer keeps no copy. Coffer's own `coffer` entry is rendered specially and managed by the install/uninstall operations, never as a plain direct entry.

On the command line the entries are rows of kind `mcp` in `coffer scan --agent <name>`, each with the reference `<agent>:<entry>` that `coffer adopt mcp` and `coffer discard mcp` take. Coffer's own `coffer` entry is not a scan row, because Coffer already manages it.

Coffer does not offer toggling an entry's `enabled` flag, nor editing an entry in place: for a format with no per-entry flag a toggle could only fail, and for one that has it the toggle would duplicate a switch the agent's own UI already owns while hand-writing another tool's private config format. Removal and adoption are the only entry-level writes, because they are the writes Coffer alone has a reason to make.

#### Scenario: list an agent's real MCP entries
- **GIVEN** a registered agent whose own config files define several MCP server entries including `coffer`
- **WHEN** the user lists the agent's MCP entries
- **THEN** Coffer returns every entry with its name, source file, transport (stdio command or HTTP URL), and the `enabled` flag where that format defines one, marks the `coffer` entry `is_coffer=true`, and stores nothing — the listing is derived from the file at read time

#### Scenario: scan lists an agent's direct MCP entries
- **GIVEN** a registered agent named `claude-code` whose own config defines a direct entry `github` and the `coffer` entry
- **WHEN** the user runs `coffer scan --agent claude-code`
- **THEN** the output carries a row of kind `mcp` with the reference `claude-code:github`
- **AND** no row names the `coffer` entry

### Requirement: Remove a direct MCP entry from its source file
Users MUST be able to remove a direct MCP entry — from the agent's page, the REST route, or `coffer discard mcp <agent>:<entry>` on the command line. Removal edits only the entry's source file, reuses the atomic-write + `.bak` machinery of "Write config files atomically with a backup and an audit entry", and records an `agent_mcp_entry_removed` audit entry. The `coffer` entry is not removable through this operation — it is managed by "Install Coffer's MCP server into an agent in one action" and "Uninstall Coffer's MCP server from an agent".

#### Scenario: remove a direct MCP entry
- **GIVEN** a registered agent with a direct (non-Coffer) MCP entry
- **WHEN** the user removes that entry (carrying the source file where the type's entries may come from more than one)
- **THEN** the entry is deleted from exactly its source file via an atomic write with a `.bak` of the prior content, an `agent_mcp_entry_removed` audit entry is recorded, and the next listing no longer shows it

#### Scenario: discard a direct MCP entry from the command line
- **GIVEN** a registered agent `claude-code` whose own config defines a direct entry `github`
- **WHEN** the user runs `coffer discard mcp claude-code:github`
- **THEN** the entry is gone from its source file, a `.bak` holds the prior content, and an `agent_mcp_entry_removed` audit entry is recorded
- **AND** `coffer discard mcp claude-code:coffer` is refused and leaves the file unchanged

### Requirement: Adopt a direct MCP entry into Coffer
Users MUST be able to adopt a direct MCP entry into Coffer, so that it is served to every agent through the gateway instead of benefiting one agent alone — from the agent's page, the REST route, or `coffer adopt mcp <agent>:<entry> [--name <name>]` on the command line, where `--name` registers the server under a different name than the entry's. Adoption (a) registers the entry as an `mcp_server` resource through the standard resource flow (schema validation + audit), (b) verifies the resource reads back, then (c) removes the source entry per "Remove a direct MCP entry from its source file" — strictly in that order. Any failure stops the operation, rolls back a created resource, and leaves the agent's config byte-identical, reporting the failure with a specific error code; audited as `agent_mcp_entry_adopted` on success. A name collision with an existing resource is rejected with `conflict` (409) carrying a suggested alternative; an entry equivalent to an existing resource is reported via `matches_resource` so the user can remove the duplicate instead. The `coffer` entry is never adoptable.

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

#### Scenario: adopt a direct MCP entry under a new name from the command line
- **GIVEN** an `mcp_server` resource named `github` and an agent `claude-code` whose own config defines a direct entry `github`
- **WHEN** the user runs `coffer adopt mcp claude-code:github --name github-work`
- **THEN** an `mcp_server` resource named `github-work` is registered and the direct entry is gone from the agent's config
- **AND** an `agent_mcp_entry_adopted` audit entry is recorded

### Requirement: Read, write and delete files inside a directory entry
Users MUST be able to read individual files inside a directory entry; this read backs the UI's editor, and on the command line the files are read on disk at the directory that `coffer path agent <name> config` names. Write (create-on-write) and delete of individual files are available through the in-app editor, the REST API and the `coffer agent config` CLI — `coffer agent config edit <name> <key>/<child> [--from-file <file>]` writes one child and `coffer agent config rm <name> <key>/<child>` deletes one. Child paths are validated server-side before any filesystem access: they MUST resolve inside the entry's directory (no `..`, no absolute paths, no symlink escape) and carry the `.md` extension — a containment violation is `not_found` (404) and a disallowed extension `unprocessable_entity` (422). Writes reuse the machinery of "Write config files atomically with a backup and an audit entry"; deletion preserves the prior content as `.bak`. Audited as `agent_config_file_written` / `agent_config_file_deleted`.

#### Scenario: create a file inside a directory entry
- **GIVEN** a registered agent with a directory config entry
- **WHEN** the user writes content to a new `.md` file path inside the entry through the in-app editor, the REST API or `coffer agent config edit <name> <key>/<child> --from-file <file>`
- **THEN** the file is created via the atomic-write machinery, an `agent_config_file_written` audit entry is recorded, and the next listing includes it

#### Scenario: delete a file inside a directory entry
- **GIVEN** a directory entry containing a file
- **WHEN** the user deletes that file through the REST API or `coffer agent config rm <name> <key>/<child>`
- **THEN** the file is removed with its prior content preserved as `.bak`, an `agent_config_file_deleted` audit entry is recorded, and the next listing no longer shows it

#### Scenario: reject directory file paths outside the entry
- **GIVEN** a registered agent with a directory config entry
- **WHEN** the user addresses a child path containing `..`, an absolute path, or a non-`.md` extension
- **THEN** the request is rejected before any filesystem access with `not_found` (404) for containment violations or `unprocessable_entity` (422) for a disallowed extension

### Requirement: Reject stale config-file writes by fingerprint
Config-file reads (single files and directory children) MUST return a content fingerprint. A write MAY carry that fingerprint back; a write that carries one MUST be rejected with `conflict` (409, `CONFIG_FILE_STALE`) when the on-disk content changed since the read, leaving the file untouched. A write that carries none is applied as sent, for scripted REST use. `coffer agent config edit <name> <key>[/<child>]` MUST always send the fingerprint of the read it started from: without `--from-file` that is the read it opened the editor on, because it holds the file open for as long as the user edits — exactly the window another writer lands in; with `--from-file` it is the read it takes before sending the file's content. The in-app editor sends it too. The agent's own process may rewrite a file between Coffer's read and write; the user then re-reads and retries, and the `.bak` of every Coffer write keeps the prior content recoverable in the reverse race.

#### Scenario: reject stale config-file writes
- **GIVEN** a config file (or directory child) read by the user, then modified on disk by another process
- **WHEN** the user writes back content carrying the fingerprint from the earlier read
- **THEN** the write is rejected with `conflict` (409) and the on-disk file is unchanged; re-reading yields a fresh fingerprint that allows the write

#### Scenario: edit a config file from a file on the command line
- **GIVEN** a registered agent with an existing `json` config file under the allowlisted key `<key>`, and a local file holding well-formed JSON
- **WHEN** the user runs `coffer agent config edit <name> <key> --from-file <file>`
- **THEN** the config file holds the local file's content, a `.bak` holds the prior content, and an `agent_config_file_written` audit entry is recorded
- **AND** the same command with malformed JSON exits non-zero and leaves the config file unchanged

### Requirement: Expose every agent operation through REST, CLI and the Agents page
Every management operation — register/list/view/update/remove, config-file write and delete (including directory children), Coffer-MCP install/uninstall/status, MCP entry list/remove/adopt, plugin list/toggle/uninstall, transcript listing and single-session read, and the model catalogue — MUST be available through (a) the REST API and (b) the `coffer` CLI, each command calling the corresponding REST endpoint:

- the lifecycle verbs of "Manage the agent lifecycle" under `coffer agent`;
- `coffer agent config edit` and `coffer agent config rm` for config-file writes and deletes;
- `coffer agent connect` and `coffer agent disconnect` for Coffer's MCP entry, with its status on `coffer agent show`;
- `coffer scan --agent <name>`, `coffer adopt mcp` and `coffer discard mcp` for direct MCP entries;
- `coffer agent plugin list|enable|disable|rm` for plugins, where `rm` is the uninstall of "Uninstall a plugin by the type's own strategy";
- `coffer agent transcript <name>` to list an agent's sessions, with the listing's search, project, sort and paging options, and `coffer agent transcript <name> <id>` to read one session in the bounded windows of "Read one transcript session in bounded windows";
- `coffer agent models` for the model catalogue.

The reads of plain files on disk — an agent's config files and their content, the files of its native memory stores, and the transcript files themselves — are served over REST for the web UI, and on the command line by `coffer path agent <name> config|memory|transcripts`, which prints their absolute locations for the user or an agent to read directly (see [resource-framework](../resource-framework/spec.md), the requirement that defines `coffer path`). The model catalogue's command is `coffer agent models <agent_type> [--json]`: it takes the agent type the catalogue route is keyed by (`claude_code`, `codex`), not an agent's name, prints one line per offered model with its label and its effort levels (the default level marked), and an unknown type exits non-zero with the route's not-found message.

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
- **WHEN** the user invokes `coffer agent config edit`, `coffer agent config rm`, `coffer agent connect` and `coffer agent disconnect`
- **THEN** each command calls the corresponding REST endpoint and produces equivalent state
- **AND** `coffer agent show --json` reports the install status the REST status route reports

#### Scenario: CLI surface mirrors REST operations
- **GIVEN** the daemon is running and exposes the REST agent routes
- **WHEN** the user invokes `coffer agent add`, `list`, `show`, `edit`, `rm`, `enable` or `disable`, or runs `coffer scan`
- **THEN** each command calls the corresponding REST endpoint and produces equivalent state changes, and every read command additionally accepts `--json` for machine-readable output

#### Scenario: the command line names an agent's files by path
- **GIVEN** a registered agent with config files, a native memory store and transcript sessions on disk
- **WHEN** the user runs `coffer path agent <name> config`, `coffer path agent <name> memory` and `coffer path agent <name> transcripts`
- **THEN** each prints the absolute locations that the REST config-file listing, native-memory scan and transcript listing report for that agent
- **AND** nothing is written and no audit event is recorded

#### Scenario: the command line reads one transcript session
- **GIVEN** a registered agent with a transcript session listed by `coffer agent transcript <name>`
- **WHEN** the user runs `coffer agent transcript <name> <id>` with that session's id
- **THEN** the command prints a window of that session's turns with the pasted secrets redacted and the whole session's turn count
- **AND** an id the agent has no session for exits non-zero with the route's not-found message

#### Scenario: the command line lists an agent's models
- **GIVEN** the catalogue route offers a `codex` model with reasoning levels and a default among them, and a second model with none
- **WHEN** the user runs `coffer agent models codex`
- **THEN** the command prints one line per model, the first carrying its id, its label and its levels with the default marked
- **AND** `--json` prints the route's response unchanged

### Requirement: Offer JSON output on every CLI read
The CLI MUST support `--json` for machine-readable output on every read operation.

#### Scenario: agent reads print JSON with --json
- **GIVEN** a registered agent
- **WHEN** the user runs `coffer agent list --json` and `coffer agent show <name> --json`
- **THEN** each prints only JSON, carrying the agent's name, title, type and config directory, and `show` also its uid, its `coffer_mcp` status and its `memory_delivery` status

### Requirement: Expose agent discovery on every surface
The system MUST expose a read-only discovery operation listing installed-but-unregistered agents as candidates, available from the REST API (`GET /api/v1/agents/candidates`), the `coffer scan` CLI (as rows of kind `agent`), and the Agents page in the web UI, where the user adds each candidate with a single confirm and no typing of type identifiers or paths. The command line's single confirm is `coffer adopt agent <type>`.

#### Scenario: list discovery candidates from the command line
- **GIVEN** a supported agent's install marker is present and no agent of that type is registered
- **WHEN** the user runs `coffer scan`
- **THEN** the command lists that type as a row of kind `agent` with its default config dir
- **AND** no agent is registered as a result

### Requirement: Switch an agent off with the kind-agnostic enabled flag
An agent MUST carry the kind-agnostic `enabled` flag, toggled through the generic `POST /api/v1/resources/{uid}/enable|disable` routes and `coffer agent enable|disable <name>`, and audited as `resource_enabled` / `resource_disabled`. A disabled agent is one Coffer does not write into and does not read from: its delivered skills are reclaimed and nothing new is delivered to it ([skill-manager](../skill-manager/spec.md)), its native memory is not aggregated ([memory](../memory/spec.md)), and its native config does not feed the model catalogue of "Serve each agent type's model catalogue" — the catalogue is read as if no agent of that type were registered. Enabling it again puts back whatever the skills' own state grants, so the switch is never a one-way door. The one exception is adoption ([skill-manager](../skill-manager/spec.md) "Adopt an unmanaged skill"): adopting a folder from a disabled agent's skills directory links it in place and records an enabled binding for that agent, the agent's next reconcile reclaims that link and disables the binding, and enabling the agent delivers the skill back whenever the skill's own `enabled` flag and scope grant it. The agent's own routes neither carry nor change the flag: `AgentOut` does not report it and `PATCH /api/v1/agents/{uid}` does not set it.

#### Scenario: disabling an agent reclaims its skills and drops it from the catalogue
- **GIVEN** a registered agent holding a delivered skill, whose config dir the model catalogue reads for its type
- **WHEN** the agent is disabled through the kind-agnostic enabled flag
- **THEN** the delivered skill's link is gone from the agent's skills directory and no binding remains enabled for it
- **AND** the catalogue for that type no longer reads the agent's config dir
- **AND** a `resource_disabled` audit entry names the agent

#### Scenario: switch an agent off and on from the command line
- **GIVEN** a registered, enabled agent named `codex`
- **WHEN** the user runs `coffer agent disable codex`, then `coffer agent enable codex`
- **THEN** the agent's kind-agnostic `enabled` flag is false after the first and true after the second
- **AND** a `resource_disabled` and then a `resource_enabled` audit entry name the agent
