## MODIFIED Requirements

### Requirement: Re-offer a removed agent while it is still detected
A removed agent MUST re-appear as a discovery candidate on subsequent scans while its program or its config directory remains — a removal is not permanent (it may be accidental). The system MUST NOT keep a "suppressed types" list. Removal is a REST act (`DELETE /api/v1/agents/{uid}`); the web UI offers none, because its list always holds a row for every supported agent and the way to stop Coffer touching one is to disconnect it or turn it off.

#### Scenario: re-surface removed agents on subsequent scan
- **GIVEN** an agent has been removed by the user and its program and config directory are still present
- **WHEN** the user runs discovery again
- **THEN** that agent is offered as a candidate again (removal is not permanent; no suppression list)

### Requirement: Manage the agent lifecycle
Users MUST be able to register, list, view, update (its config directory and the model binding of "Carry the model binding on the agent record") and remove agents. An agent also carries the kind-agnostic `enabled` flag every Resource has; switching it is "Switch an agent off with the kind-agnostic enabled flag", not a field of the agent's own update. Registration takes the type and, optionally, a config directory — the type's standard one when omitted — and the name is the type's ("Keep one agent per type, named by it"); there is no name, title or description to supply or edit. Skill bindings between an agent and a skill belong to skill-manager; this registry defines no skill operations beyond exposing an `on_delete` hook for cascade cleanup and an `on_enabled_changed` hook for the reclaim of "Switch an agent off with the kind-agnostic enabled flag".

Over REST the lifecycle is `POST /api/v1/agents` (the type and, optionally, `config_dir`), `GET /api/v1/agents` and `GET /api/v1/agents/{uid}`, `PATCH /api/v1/agents/{uid}` (with `config_dir` and the model fields of "Carry the model binding on the agent record") and `DELETE /api/v1/agents/{uid}`, where `{uid}` is the agent's uid or the type it is named by ("Keep one agent per type, named by it"); the Agents page reaches the same operations through each row's Connect and ⋯ menu. The `agent` kind has no scope, because it declares none. The agent's Coffer connection, part by part ("Report an agent's Coffer connection part by part"), is read from `GET /api/v1/agents/{uid}/coffer-connection`: its state and, for each applicable part (the gateway MCP entry, and the memory delivery hook while memory is on), whether it is installed.

#### Scenario: register an agent without an explicit name
- **GIVEN** the daemon is running and no `claude_code` agent is registered
- **WHEN** the user registers an agent with `POST /api/v1/agents`, supplying only the type `claude_code`
- **THEN** the agent is registered under the type's name `claude-code` (underscores become hyphens) at the type's standard config directory, audited as `resource_created`

#### Scenario: update an existing agent
- **GIVEN** a registered agent
- **WHEN** the user updates its `config_dir` to a new writable path
- **THEN** the change persists, an audit entry is recorded, and subsequent operations see the new path

#### Scenario: remove an agent
- **GIVEN** a registered agent (any binding cleanup is handled by the skill-manager spec)
- **WHEN** the user removes it
- **THEN** the agent is deleted, an audit entry is recorded, and `GET /api/v1/agents` no longer lists it

#### Scenario: use a different config directory from the command line
- **GIVEN** a registered agent `claude-code` at `~/.claude` and another writable directory
- **WHEN** the user sends `PATCH /api/v1/agents/claude-code` with `config_dir` set to `<dir>`
- **THEN** `GET /api/v1/agents/claude-code` reports `<dir>` as its config directory, with the same uid and name
- **AND** the update route offers no way to change the name, title or description

#### Scenario: give an agent a title from the command line
- **GIVEN** a registered agent named `claude-code`
- **WHEN** the user submits the title `Work laptop Claude` through the kind-agnostic update route
- **THEN** the route refuses the title as a validation error (422)
- **AND** `GET /api/v1/agents/claude-code` still shows the agent as `claude-code`, with its uid and no title

### Requirement: Validate the config directory at registration
At registration the system MUST auto-create the `<config_dir>/skills` subdirectory, then validate that the resolved `config_dir` exists — or, for the standard config directory of a type in state `installed_never_run`, create it first, holding only the entries Coffer needs — is a directory, is writable, and is not a privileged system path before accepting the value. The privileged locations are `/etc`, `/bin`, `/sbin`, `/usr`, `/var`, `/sys`, `/proc`, `/root`, `/boot`, `/dev`, `/System` and `/Library/Application Support/Apple` on POSIX hosts — matched at a path-component boundary, after resolving symlinks and stripping macOS's `/private` firmlink prefix, with the user temp area under `/var/folders/` carved out as usable — and `C:\Windows`, `C:\Program Files` and `C:\Program Files (x86)` on Windows. A rejected registration leaves no partial state, and no `config_dir` value may permit writing outside the directory itself.

#### Scenario: reject registration with an invalid config dir
- **GIVEN** the daemon is running
- **WHEN** the user registers an agent whose `config_dir` does not exist, is not a directory, or is not writable
- **THEN** registration is rejected with a message naming the path, and nothing is persisted

#### Scenario: reject registration into privileged system path
- **GIVEN** the daemon is running
- **WHEN** the user attempts to register an agent whose `config_dir` resolves under a privileged location (e.g. `/etc`, `/usr`, `/var` outside `/var/folders/`, `/System`, `C:\Windows`, or `C:\Program Files`)
- **THEN** registration is rejected with `unprocessable_entity` (422) and no resource row, audit event, or filesystem write occurs

#### Scenario: register an agent with a custom config dir
- **GIVEN** the daemon is running
- **WHEN** the user registers an agent of supported type with an explicit, writable `config_dir`
- **THEN** the agent is persisted with that path (and its `<config_dir>/skills` subdirectory auto-created) and appears in `GET /api/v1/agents`

#### Scenario: register an installed agent whose config directory is not created yet
- **GIVEN** Codex's program is on its `PATH`, `~/.codex` does not exist and no `codex` agent is registered
- **WHEN** the user registers a `codex` agent without a config directory
- **THEN** `~/.codex` is created holding only its `skills` directory, and the agent is registered there
- **AND** registering a type whose program is not installed on a directory that does not exist is still rejected, with nothing created

### Requirement: Validate config-file content before saving it
The system MUST expose a write (save) for the content of any allowlisted config file through the in-app editor and the REST API — one endpoint serving both. The content MUST be validated against the file's `format` before any write; malformed `json`/`toml` MUST be rejected (`unprocessable_entity`, 422) and the on-disk file left unchanged. `markdown` files accept any content.

#### Scenario: reject malformed config-file content
- **GIVEN** a registered agent whose `settings.json` (a `json` file) exists
- **WHEN** the user writes malformed content (e.g. invalid JSON) to that key through the in-app editor or the REST API
- **THEN** Coffer responds `unprocessable_entity` (422), leaves the on-disk file unchanged, writes no `.bak`, and records no write audit entry

### Requirement: Write config files atomically with a backup and an audit entry
Writes MUST be atomic (temp file + rename) and MUST keep a `.bak` copy of the prior content so a bad edit is recoverable; each successful write MUST record an `agent_config_file_written` audit entry. The Coffer-MCP install/uninstall operations (see "Back up and audit Coffer MCP install and uninstall") reuse the same atomic-write + `.bak` machinery.

#### Scenario: save a config file with valid content
- **GIVEN** a registered agent whose `settings.json` exists
- **WHEN** the user writes new, well-formed content to that config-file key through the in-app editor or the REST API
- **THEN** Coffer validates the content against the file's format, writes it atomically while keeping a `.bak` of the prior version, records an `agent_config_file_written` audit entry, and the new content reads back on the next read

### Requirement: Install Coffer's MCP server into an agent in one action
Connecting an agent to Coffer ("Connect an agent to Coffer in one action") MUST install Coffer's own MCP server into it as the connection's `mcp` part. The install writes a `coffer` stdio MCP-server entry into the agent's MCP config, using the shape declared by that agent's manifest `McpInjectionSpec` and named by that type's child spec.

- `command` is the absolute path of the `coffer-mcp-shim` binary, resolved on `PATH`, then the running interpreter's scripts directory — so a venv-installed shim is found even when the daemon's `PATH` lacks the venv — then the bundled binary; a `COFFER_MCP_SHIM_PATH` environment override takes precedence over all.
- The install additionally writes `--agent-uid <uid>` in the entry shape's argument slot — the agent's immutable uid, never its mutable name, because the entry is written once into a file Coffer does not otherwise revisit and a name would go stale on the first rename — so the gateway can attribute the session to this agent for per-agent scope enforcement ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)).
- If the shim cannot be resolved, the connect is rejected with `SHIM_NOT_FOUND`, an error naming the missing binary, and nothing is written. Finding or reinstalling the shim depends on how Coffer got onto this machine, so the refusal MUST carry, in its details as `handoff.prompt`, a hand-off prompt (see [skill-manager](../skill-manager/spec.md) "Hand a required command to an agent with a prompt" for the shape every hand-off takes) asking the person's agent to find or reinstall `coffer-mcp-shim` so it resolves at `~/.coffer/bin/coffer-mcp-shim` or one of the places Coffer looks, naming every place it looked, then to have the person choose Connect again. The web UI's Connect review MUST offer that prompt through **Copy prompt** (and **Ask an agent** while a managed agent is available) beside Retry, and its refusal copy MUST name no environment variable or command.

#### Scenario: refuse the Coffer MCP install when the shim cannot be resolved
- **GIVEN** a registered agent and no resolvable `coffer-mcp-shim` binary
- **WHEN** the user connects the agent to Coffer
- **THEN** the connect is rejected with an error naming the missing binary
- **AND** the agent's MCP config file is not written

#### Scenario: a missing shim is refused with a prompt that hands finding it to an agent
- **GIVEN** no `coffer-mcp-shim` at the override `COFFER_MCP_SHIM_PATH` names, on the daemon's `PATH`, in the interpreter's scripts directory or beside the running executable
- **WHEN** the shim is resolved for a connect
- **THEN** the refusal carries a hand-off prompt asking to find or reinstall `coffer-mcp-shim` so it resolves at `~/.coffer/bin/coffer-mcp-shim`
- **AND** the prompt names every place Coffer looked and ends by asking the person to choose Connect again

#### Scenario: connect an agent to Coffer from the command line
- **GIVEN** a registered agent whose MCP config has no `coffer` entry and a resolvable `coffer-mcp-shim` binary
- **WHEN** the user connects the agent with `POST /api/v1/agents/{uid}/coffer-connection`
- **THEN** the agent's MCP config carries a `coffer` entry whose arguments name the agent's uid
- **AND** an `agent_mcp_installed` audit entry is recorded
- **AND** the response lists each part of the connection and whether it is installed

### Requirement: Keep the Coffer MCP install idempotent and report its status
Installing the `mcp` part MUST be idempotent — re-installing updates the existing `coffer` entry in place and never creates a duplicate. Whether it is installed MUST be reported as that part of the agent's Coffer connection ("Report an agent's Coffer connection part by part"), derived from the agent's MCP config file, never stored. An installed entry MUST also be judged by its parameters — the shim path in `command` and the `--agent-uid` in `args` — against what an install would write now, by the MCP-entry target of the unified reconciler ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"): on every pass a stale entry is rewritten in place, backed up and audited as an install, and an entry that carries another registered agent's uid in a file that agent does not read is moved into that agent's own file. The target never adds an entry to an agent that holds none — connecting is the user's act — and while the shim cannot be found the drift is reported as blocked and nothing is written.

#### Scenario: report Coffer-MCP install status
- **GIVEN** a registered agent whose MCP config does not contain a `coffer` server entry
- **WHEN** the user checks the agent's Coffer connection
- **THEN** the `mcp` part reports `installed=false`

#### Scenario: install Coffer's MCP is idempotent
- **GIVEN** an agent that already has Coffer's MCP installed
- **WHEN** the user connects it again
- **THEN** the existing `coffer` entry is updated in place (never duplicated) and the `mcp` part still reports `installed=true`

#### Scenario: agent show reports the Coffer MCP status
- **GIVEN** one registered agent with Coffer's MCP installed and one without
- **WHEN** the user reads `GET /api/v1/agents/{uid}/coffer-connection` for each
- **THEN** the first's `mcp` part reports installed and the second's state is `disconnected`
- **AND** each response lists the parts the agent's type has, with whether each is installed

#### Scenario: a stale Coffer MCP entry is repaired with its current parameters
- **GIVEN** a registered agent whose `coffer` entry names a shim path this build no longer installs, or an `--agent-uid` that is not the agent's
- **WHEN** a reconcile pass runs
- **THEN** the entry is rewritten with the current shim path and the agent's uid, every other entry in the file is left as it was, and an `agent_mcp_installed` audit entry is recorded with actor `system`
- **AND** an agent with no `coffer` entry is not given one

### Requirement: Uninstall Coffer's MCP server from an agent
Disconnecting an agent from Coffer ("Disconnect an agent from Coffer") MUST uninstall Coffer's MCP, removing the `coffer` entry from the agent's MCP config. Uninstalling when not installed is a no-op success and the `mcp` part then reports not installed.

#### Scenario: uninstall Coffer's MCP when it is not installed
- **GIVEN** a registered agent whose MCP config has no `coffer` entry
- **WHEN** the user disconnects the agent from Coffer
- **THEN** the operation succeeds without changing the agent's MCP config
- **AND** the `mcp` part reports `installed=false`

#### Scenario: disconnect an agent from Coffer on the command line
- **GIVEN** an agent that has Coffer's MCP installed
- **WHEN** the user disconnects the agent with `DELETE /api/v1/agents/{uid}/coffer-connection`
- **THEN** the `coffer` entry is gone from the agent's MCP config
- **AND** `GET /api/v1/agents/{uid}/coffer-connection` reports the state as `disconnected`

### Requirement: List the MCP entries in the agent's own config files
The system MUST parse and list the MCP server entries configured in the agent's own files, reading the source files that type's child spec names and labelling each entry with the file it came from. Each entry carries name, source, transport (stdio command or HTTP URL), the `enabled` flag where the format defines one, `is_coffer` for Coffer's own gateway entry, and `matches_resource` naming an equivalent registered `mcp_server` resource when one exists. Entries are derived at read time, never stored; Coffer keeps no copy. Coffer's own `coffer` entry is rendered specially and managed by the install/uninstall operations, never as a plain direct entry.

Over REST the entries are `GET /api/v1/agents/{uid}/mcp-entries`; each is addressed by its name — plus its source file where the type's entries may come from more than one — by the routes of the requirements that follow.

Coffer does not offer toggling an entry's `enabled` flag, nor editing an entry in place: for a format with no per-entry flag a toggle could only fail, and for one that has it the toggle would duplicate a switch the agent's own UI already owns while hand-writing another tool's private config format. Removal and adoption are the only entry-level writes, because they are the writes Coffer alone has a reason to make.

#### Scenario: list an agent's real MCP entries
- **GIVEN** a registered agent whose own config files define several MCP server entries including `coffer`
- **WHEN** the user lists the agent's MCP entries
- **THEN** Coffer returns every entry with its name, source file, transport (stdio command or HTTP URL), and the `enabled` flag where that format defines one, marks the `coffer` entry `is_coffer=true`, and stores nothing — the listing is derived from the file at read time

#### Scenario: scan lists an agent's direct MCP entries
- **GIVEN** a registered agent named `claude-code` whose own config defines a direct entry `github` and the `coffer` entry
- **WHEN** the user lists the agent's MCP entries with `GET /api/v1/agents/claude-code/mcp-entries`
- **THEN** the response carries the direct entry `github`, not marked as Coffer's
- **AND** the `coffer` entry is the one marked `is_coffer=true`, and it offers no removal or adoption

### Requirement: Show one direct MCP entry's full configuration without its secrets
Users MUST be able to open one direct MCP entry and see everything the agent's own config file holds for it, read-only: its transport, its command and arguments (or its URL), its working directory, its per-entry `enabled` flag where the format has one, the names of its environment variables and HTTP headers, every other key the entry carries, which config file it lives in (the resolved absolute path, with open-in-editor and reveal-in-file-manager beside it), and `matches_resource` when an equivalent `mcp_server` resource is already registered. The read is addressed like removal and adoption — the entry's name, plus the source file where the type's entries may come from more than one — and is derived from the file at read time; Coffer stores nothing and starts nothing, so an unmanaged server is never spawned to be looked at.

No secret value crosses the API. Environment and header values are never returned — only their names, with the secret-like ones flagged by the pattern of "Route secret-like environment values to the secret store on adoption". Any other key whose name matches that pattern with a non-empty value, or whose value nests such a key at any depth, has its value withheld by the daemon and is reported as masked.

The detail is available from the REST API (`GET /agents/{uid}/mcp-entries/{entry}`) and in the web UI as the dialog a direct server's name opens on the agent's MCP servers tab: the entry's JSON as the agent's own file holds it, with secret values masked, over the list, because one entry is too little for a page of its own. The dialog's footer offers the row's two writes — removing it from its file behind the same confirm, and adopting it into Coffer — around Close.

#### Scenario: read one direct MCP entry with its secrets withheld
- **GIVEN** a registered agent whose config file defines a stdio MCP entry with arguments, a working directory, an environment carrying a secret-like and a plain value, a secret-like extra key and a table that nests one
- **WHEN** the user reads that entry
- **THEN** Coffer returns its transport, command, arguments, working directory, the environment key names with the secret-like one flagged, every other key sorted by name with plain values shown as text, and the absolute path of the file it came from
- **AND** the secret-like extra key and the table nesting one are reported masked with no value, and no environment, header or masked value appears anywhere in the response

#### Scenario: open a direct MCP entry's JSON from the agent
- **GIVEN** the agent's MCP servers tab lists a direct server
- **WHEN** the user clicks the server's name
- **THEN** a read-only dialog opens with the entry as its config file holds it — command, arguments, working directory, file and variable names — marking secret-looking names and masked fields as hidden without showing any value
- **AND** its footer offers Remove and Adopt around Close, and closing it leaves the user on the MCP servers tab

### Requirement: Remove a direct MCP entry from its source file
Users MUST be able to remove a direct MCP entry — from the agent's page or the REST route (`DELETE /api/v1/agents/{uid}/mcp-entries/{entry}`). Removal edits only the entry's source file, reuses the atomic-write + `.bak` machinery of "Write config files atomically with a backup and an audit entry", and records an `agent_mcp_entry_removed` audit entry. The `coffer` entry is not removable through this operation — it is managed by "Install Coffer's MCP server into an agent in one action" and "Uninstall Coffer's MCP server from an agent".

#### Scenario: remove a direct MCP entry
- **GIVEN** a registered agent with a direct (non-Coffer) MCP entry
- **WHEN** the user removes that entry (carrying the source file where the type's entries may come from more than one)
- **THEN** the entry is deleted from exactly its source file via an atomic write with a `.bak` of the prior content, an `agent_mcp_entry_removed` audit entry is recorded, and the next listing no longer shows it

#### Scenario: discard a direct MCP entry from the command line
- **GIVEN** a registered agent `claude-code` whose own config defines a direct entry `github`
- **WHEN** the user sends `DELETE /api/v1/agents/claude-code/mcp-entries/github`
- **THEN** the entry is gone from its source file, a `.bak` holds the prior content, and an `agent_mcp_entry_removed` audit entry is recorded
- **AND** `DELETE /api/v1/agents/claude-code/mcp-entries/coffer` is refused and leaves the file unchanged

### Requirement: Adopt a direct MCP entry into Coffer
Users MUST be able to adopt a direct MCP entry into Coffer, so that it is served to every agent through the gateway instead of benefiting one agent alone — from the agent's page or the REST route (`POST /api/v1/agents/{uid}/mcp-entries/{entry}/adopt`), whose `new_name` registers the server under a different name than the entry's. Adoption (a) registers the entry as an `mcp_server` resource through the standard resource flow (schema validation + audit), (b) verifies the resource reads back, then (c) removes the source entry per "Remove a direct MCP entry from its source file" — strictly in that order. Any failure stops the operation, rolls back a created resource, and leaves the agent's config byte-identical, reporting the failure with a specific error code; audited as `agent_mcp_entry_adopted` on success. A name collision with an existing resource is rejected with `conflict` (409) carrying a suggested alternative; an entry equivalent to an existing resource is reported via `matches_resource` so the user can remove the duplicate instead. The `coffer` entry is never adoptable.

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
- **WHEN** the user adopts the entry with `POST /api/v1/agents/claude-code/mcp-entries/github/adopt` carrying `new_name` `github-work`
- **THEN** an `mcp_server` resource named `github-work` is registered and the direct entry is gone from the agent's config
- **AND** an `agent_mcp_entry_adopted` audit entry is recorded

### Requirement: Read, write and delete files inside a directory entry
Users MUST be able to read individual files inside a directory entry; this read backs the UI's editor, . Write (create-on-write) and delete of individual files are available through the in-app editor and the REST API (`PUT` and `DELETE /api/v1/agents/{uid}/config-files/{key}/files/{relpath}`). Child paths are validated server-side before any filesystem access: they MUST resolve inside the entry's directory (no `..`, no absolute paths, no symlink escape) and carry the `.md` extension — a containment violation is `not_found` (404) and a disallowed extension `unprocessable_entity` (422). Writes reuse the machinery of "Write config files atomically with a backup and an audit entry"; deletion preserves the prior content as `.bak`. Audited as `agent_config_file_written` / `agent_config_file_deleted`.

#### Scenario: create a file inside a directory entry
- **GIVEN** a registered agent with a directory config entry
- **WHEN** the user writes content to a new `.md` file path inside the entry through the in-app editor or the REST API
- **THEN** the file is created via the atomic-write machinery, an `agent_config_file_written` audit entry is recorded, and the next listing includes it

#### Scenario: delete a file inside a directory entry
- **GIVEN** a directory entry containing a file
- **WHEN** the user deletes that file through the REST API
- **THEN** the file is removed with its prior content preserved as `.bak`, an `agent_config_file_deleted` audit entry is recorded, and the next listing no longer shows it

#### Scenario: reject directory file paths outside the entry
- **GIVEN** a registered agent with a directory config entry
- **WHEN** the user addresses a child path containing `..`, an absolute path, or a non-`.md` extension
- **THEN** the request is rejected before any filesystem access with `not_found` (404) for containment violations or `unprocessable_entity` (422) for a disallowed extension

### Requirement: Reject stale config-file writes by fingerprint
Config-file reads (single files and directory children) MUST return a content fingerprint. A write MAY carry that fingerprint back; a write that carries one MUST be rejected with `conflict` (409, `CONFIG_FILE_STALE`) when the on-disk content changed since the read, leaving the file untouched. A write that carries none is applied as sent, for scripted REST use. The in-app editor MUST always send the fingerprint of the read it started from, because it holds the file open for as long as the user edits — exactly the window another writer lands in. The agent's own process may rewrite a file between Coffer's read and write; the user then re-reads and retries, and the `.bak` of every Coffer write keeps the prior content recoverable in the reverse race.

#### Scenario: reject stale config-file writes
- **GIVEN** a config file (or directory child) read by the user, then modified on disk by another process
- **WHEN** the user writes back content carrying the fingerprint from the earlier read
- **THEN** the write is rejected with `conflict` (409) and the on-disk file is unchanged; re-reading yields a fresh fingerprint that allows the write

#### Scenario: edit a config file from a file on the command line
- **GIVEN** a registered agent with an existing `json` config file under the allowlisted key `<key>`, and well-formed JSON content to write
- **WHEN** the user writes that content with `PUT /api/v1/agents/{uid}/config-files/<key>`
- **THEN** the config file holds the written content, a `.bak` holds the prior content, and an `agent_config_file_written` audit entry is recorded
- **AND** the same request with malformed JSON is refused with `unprocessable_entity` (422) and leaves the config file unchanged

### Requirement: Carry the model binding on the agent record
The agent record MUST carry the model binding the rest of Coffer reads — `model`, `effort`, `tier_models` (Claude Code only: the model for each of `opus`, `sonnet`, `haiku` and `fable`) — because the model is chosen at the point of USE and an agent is where it is used, not on the connection that serves it. That binding MUST be settable over REST as well as in the web UI: `PATCH /api/v1/agents/{uid}` carries `model` / `effort` / `tier_models`, with an explicit null to unbind `effort` or `tier_models`. A field the request omits is unchanged; `tier_models`, when sent, replaces the whole mapping. Only `effort` and `tier_models` clear on an explicit null; `model` has no null that unbinds it, so an explicit null for it is treated as omitted. A tier other than the four is refused. The binding carries no `fast_model`: Claude Code's background model is its Haiku tier, and the migration that removed the field moved each Claude Code agent's fast model into `tier_models.haiku`. Projecting a binding into the agent's native config is provider-switching's.

#### Scenario: bind a model to an agent from the command line
- **GIVEN** a registered agent
- **WHEN** the user sends `PATCH /api/v1/agents/{uid}` with a `model`, `effort` `high` and `tier_models` `{"haiku": "<model>"}`, then again with `tier_models` null
- **THEN** the agent record reports the bound `model`, `effort` and `tier_models` after the first edit, and carries no `fast_model`
- **AND** after the second edit `tier_models` is null while `model` and `effort` are unchanged

#### Scenario: an earlier fast model becomes the Haiku tier
- **GIVEN** a vault whose Claude Code agent was bound with a `fast_model`
- **WHEN** the daemon migrates the vault
- **THEN** the agent's `tier_models.haiku` names that model, unless a Haiku pin was already there, and no agent row carries `fast_model`

### Requirement: Detect an agent by its program and its config directory
The system MUST detect an agent from two signals: its program on the agent's real `PATH` — the user's login-shell `PATH` merged with the daemon's inherited one, asked through the platform layer — together with the version that program reports, and its config directory on disk. The version MUST be read with the program's own version flag under a bounded timeout, and detection MUST NOT run anything that needs a login, a network call or the agent's config. The two signals MUST be named as one state: `installed_active` (program and directory), `installed_never_run` (program, no directory yet), `config_only` (directory, program missing) and `missing` (neither). Discovery candidates, the per-type listing of "Report every supported type's detection state" and every registered agent read (`GET /api/v1/agents`, `GET /api/v1/agents/{uid}`) MUST carry the state and the version, read at request time and never stored. An `installed_never_run` agent can be added: its program works and the directory it has not created yet is created by the registration (see "Validate the config directory at registration"). A `config_only` agent is shown as config left behind with its program not found — not as not installed — because a directory of its own is still on disk and the fix is to reinstall the program; `missing` is shown as not installed.

#### Scenario: read the installed program's version
- **GIVEN** the agent's program is on the agent's `PATH` and answers its version flag with `2.1.281 (Claude Code)`
- **WHEN** the agent is detected
- **THEN** the program is found and its version is `2.1.281`
- **AND** a program that does not answer within the bound is still found, with no version

#### Scenario: offer an installed agent that has never run
- **GIVEN** a supported agent's program is on its `PATH` and its standard config directory does not exist
- **WHEN** the user runs discovery
- **THEN** that type is a candidate in state `installed_never_run`, with its version and its standard config directory marked as not created, and is offered for adding

#### Scenario: show a leftover config directory as config left behind
- **GIVEN** a supported agent's standard config directory exists and its program is not on its `PATH`
- **WHEN** the user runs discovery
- **THEN** that type is a candidate in state `config_only`, with no version, shown as config left behind with its program not found, and is not offered for adding

#### Scenario: offer the directory named by the agent's environment variable
- **GIVEN** the daemon's environment sets `CLAUDE_CONFIG_DIR` to an existing directory other than `~/.claude`, `~/.claude` exists, and Claude Code's program is installed
- **WHEN** the user runs discovery
- **THEN** Claude Code is one candidate at `~/.claude` whose `other_config_dir` is the variable's directory
- **AND** when `~/.claude` does not exist the candidate is the variable's directory, and a variable naming the standard directory adds nothing

#### Scenario: report a registered agent's detection state
- **GIVEN** a registered agent whose program is installed and whose config directory exists
- **WHEN** the agent is read
- **THEN** it carries state `installed_active` and the program's version
- **AND** an agent whose program and directory are both gone reads `missing`

### Requirement: Keep one agent per type, named by it
A machine MUST hold at most one agent of each supported type, and that agent's `name` MUST be its type's name — `claude-code` for `claude_code`, `codex` for `codex` — derived from the type at registration, never chosen by a person. The name is fixed: a changed name MUST be refused with `NAME_IMMUTABLE` (409) whose message says the name is the agent's type. An agent MUST carry no `title` and no `description`: a non-empty title is refused as a validation error (422) on every surface, and neither registration nor update takes a description. Its config directory is the one per-agent setting besides the type and the model binding of "Carry the model binding on the agent record". Registering a type that already has an agent MUST be refused with `AGENT_TYPE_REGISTERED` (409) and nothing persisted; using a different directory is an edit of the one agent.

Because a type names exactly one agent, every `/api/v1/agents/{uid}/…` route MUST also accept the type — its name (`claude-code`) or its value (`claude_code`) — in place of the uid, and answer exactly as it does for the uid; a type with no agent registered reads as not found.

A database holding several agents of one type from before this rule MUST be collapsed on upgrade to one: the one whose own Coffer MCP entry names its uid, else an enabled one, else the most recently used, else the one on the type's standard directory, else the oldest. Every reach list and channel `default_agent` that named a dropped agent MUST be re-pointed at the kept one — a reach list never widened to every agent by it — the kept agent renamed to its type with its title and description cleared, and each dropped agent reported in the daemon log with its type, name, uid, config directory and the uid kept in its place. Nothing is written into a dropped agent's config directory.

#### Scenario: register a second agent of a registered type
- **GIVEN** a `codex` agent is registered at `~/.codex`
- **WHEN** the user registers another `codex` agent, on `~/.codex` or on any other writable directory
- **THEN** the registration is refused with `AGENT_TYPE_REGISTERED` (409) and nothing is persisted or created on disk
- **AND** the registered agent is still named `codex` and keeps its uid

#### Scenario: address an agent by its type
- **GIVEN** a registered `claude_code` agent with uid `U`
- **WHEN** the user requests `/api/v1/agents/claude-code`, `/api/v1/agents/claude_code/config-files` and `/api/v1/agents/U`
- **THEN** each answers for the same agent, with name `claude-code` and uid `U`
- **AND** `/api/v1/agents/codex` answers not found while no `codex` agent is registered

#### Scenario: an agent's name, title and description cannot be set
- **GIVEN** a registered `claude-code` agent
- **WHEN** the user submits a new name, then a title, through the kind-agnostic update route
- **THEN** the name is refused with `NAME_IMMUTABLE` (409) saying the name is the agent's type, and the title is refused as a validation error (422)
- **AND** registering an agent under any name other than its type's is refused as a validation error

#### Scenario: collapse duplicate agents to one per type on upgrade
- **GIVEN** a database from before this rule with two `claude_code` agents — one enabled, one disabled but touched more recently — a skill whose reach names both, an MCP server whose reach names only the disabled one, and a channel whose default agent is the disabled one
- **WHEN** the database is upgraded
- **THEN** only the enabled agent remains, named `claude-code` with no title or description, and the skill's reach names it once, the MCP server's reach names it, and the channel's default agent is it
- **AND** the daemon log reports the dropped agent's name, uid and config directory beside the uid kept in its place

### Requirement: Connect an agent to Coffer in one action
Users MUST be able to connect an agent to Coffer in one action, from the REST API (`POST /api/v1/agents/{uid}/coffer-connection`) and the web UI. Connecting MUST install every **part** Coffer writes into the agent's own configuration for that agent's type:

- `mcp` — the gateway MCP entry of "Install Coffer's MCP server into an agent in one action", for every agent type;
- `memory_hook` — the memory delivery hook of [memory](../memory/spec.md) "Install delivery hooks explicitly and removably", for every agent type with a hook adapter.

The gateway entry MUST be installed first, so that a connect refused for want of a shim writes nothing. Every part MUST be installed through its own atomic write with a `.bak` and record its own audit event, as it does when installed alone. Connecting MUST be idempotent: connecting a connected agent rewrites each entry in place and never duplicates one.

#### Scenario: connect installs every part that applies
- **GIVEN** a registered Claude Code agent with neither the gateway entry nor the memory hook
- **WHEN** the user connects it to Coffer
- **THEN** the agent's `.claude.json` carries the `coffer` MCP entry and its `settings.json` carries Coffer's marked hook entry
- **AND** one `agent_mcp_installed` and one `memory_delivery_installed` audit entry name the user as actor, and the connection reports `connected` with both parts installed

### Requirement: Report an agent's Coffer connection part by part
The system MUST report an agent's Coffer connection (`GET /api/v1/agents/{uid}/coffer-connection`) as the list of parts its type has — each with its key, whether it is installed, and the installed command when it is — and a state: `connected` when every listed part is installed, `disconnected` when none is, and `partial` otherwise. The report MUST be read from the agent's own configuration files on demand, never stored, and MUST write nothing and record no audit event.

#### Scenario: report a partly installed connection
- **GIVEN** a registered agent carrying the gateway entry but not the memory hook
- **WHEN** the user reads its Coffer connection
- **THEN** the state is `partial`, the `mcp` part is installed with its shim command and the `memory_hook` part is not installed
- **AND** connecting again installs the missing hook and the state becomes `connected`

### Requirement: Disconnect an agent from Coffer
Users MUST be able to disconnect an agent from Coffer in one action (`DELETE /api/v1/agents/{uid}/coffer-connection`, the web UI). Disconnecting MUST remove every part the agent type has, taking out only Coffer's own marked entries and leaving every other entry, key and hook in those files as it was. A part that is absent MUST be a no-op that writes no file and records no audit event.

#### Scenario: disconnect removes only Coffer's entries
- **GIVEN** a connected Claude Code agent whose `.claude.json` also carries another MCP server and whose `settings.json` also carries a foreign hook on the same event
- **WHEN** the user disconnects it from Coffer
- **THEN** the `coffer` MCP entry and Coffer's hook entry are gone, the other MCP server and the foreign hook are untouched, and the connection reports `disconnected`
- **AND** disconnecting again writes no file and records no audit entry

### Requirement: Hand installing an agent's program to an agent
While an agent type's program is not found on the agent's real `PATH` — detection reads `config_only` or `missing` (see "Detect an agent by its program and its config directory") — the system MUST offer a hand-off prompt (see [skill-manager](../skill-manager/spec.md) "Hand a required command to an agent with a prompt" for the shape every hand-off takes) that asks the person's agent to install that type's program, or to reinstall it when an agent of the type is registered or its config directory is still there. The prompt MUST name the agent and this machine's OS and architecture; say that an existing config directory is kept with everything in it; name the program Coffer looks for and the `PATH` it looks on, and ask that the program be found there and confirmed with `<program> --version`; ask the person to come back and choose Check again; and leave signing in to the agent to the person. It MUST name no installer, package manager or install command. The prompt MUST be carried as `install_handoff` on each row of `GET /api/v1/agents/types` and on the agent record (`GET /api/v1/agents`, `GET /api/v1/agents/{uid}`), `null` while the program is found; the Overview attention item for a registered agent whose program is missing MUST carry the same prompt, with a reason sentence that names no command.

#### Scenario: a type that is not installed carries its install prompt
- **GIVEN** Codex's program is not on the agent's `PATH` and no Codex agent is registered
- **WHEN** the prompt for the Codex type is built
- **THEN** it asks to install OpenAI Codex on this machine, naming the machine, the `PATH` Coffer looks on, the program `codex` and `codex --version` to confirm, and ends with Check again and signing in left to the person
- **AND** it names no installer or package manager

#### Scenario: an agent whose program is gone carries a reinstall prompt that keeps its folder
- **GIVEN** a registered Claude Code agent whose config directory is still there and whose program is not on its `PATH`
- **WHEN** the prompt for it is built
- **THEN** it asks to reinstall Claude Code and to keep its config directory and everything in it, confirming with `claude --version`
- **AND** a registered agent whose directory is gone too gets a reinstall prompt saying so, and a found program gets no prompt

#### Scenario: an attention item for a missing program carries the reinstall prompt
- **GIVEN** an enabled registered agent whose program is not found
- **WHEN** the Overview attention list is read
- **THEN** its `agent_program_missing` item carries the reinstall prompt for that agent's type and config directory
- **AND** the item's reason names no command

#### Scenario: the command line prints an agent's install prompt
- **GIVEN** Claude Code's program is not found and Codex's is
- **WHEN** the user reads `GET /api/v1/agents/types`
- **THEN** the Claude Code row carries the install prompt as `install_handoff`
- **AND** the Codex row carries `install_handoff` null

### Requirement: Expose every agent operation through REST, CLI and the Agents page
Every management operation — register/list/view/update/remove, config-file write and delete (including directory children), Coffer connect/disconnect/connection status, MCP entry list/view/remove/adopt, plugin list/detail/toggle/uninstall, the hooks listing, transcript listing and single-session read, and the model catalogue — MUST be available through (a) the REST API and (b) the Agents page in the web UI. The command line carries none of them: it has no `agent` command group.

- the lifecycle of "Manage the agent lifecycle" under `/api/v1/agents`;
- config-file reads, writes and deletes of directory children under `/api/v1/agents/{uid}/config-files`;
- the agent's Coffer connection under `/api/v1/agents/{uid}/coffer-connection` ("Connect an agent to Coffer in one action");
- direct MCP entries under `/api/v1/agents/{uid}/mcp-entries`;
- plugins under `/api/v1/agents/{uid}/plugins`, where `DELETE` is the uninstall of "Uninstall a plugin by the type's own strategy";
- the hooks of "List every hook in the agent's native config" at `GET /api/v1/agents/{uid}/hooks`;
- transcript sessions at `GET /api/v1/agents/{uid}/transcripts`, and one session in the bounded windows of "Read one transcript session in bounded windows" at `GET /api/v1/agents/{uid}/transcripts/session`;
- the model catalogue at `GET /api/v1/agent-providers/{agent_key}/models`.

The reads of plain files on disk — an agent's config files and their content, the files of its native memory stores, and the transcript files themselves — are served over REST for the web UI, and the Overview's Details names the config directory for anyone who wants the files themselves. The model catalogue's route takes the agent type it is keyed by (`claude_code`, `codex`), not an agent's name, and an unknown type is its not-found.

The Agents page in the web UI MUST expose all of these, config-file content writes included. It renders within the web-ui shell at `/agents` as the first entry of the sidebar's Agents group ([web-ui](../web-ui/spec.md) "Group the sidebar by what the user comes to do"), never among the Capabilities or Context entries, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file (and a directory-entry child) opens in a viewer that becomes **editable behind an explicit Edit**, saves through the same path as REST ("Validate config-file content before saving it", "Write config files atomically with a backup and an audit entry"), and guards an unsaved draft three ways — picking another file asks first, leaving the tab asks first, and leaving the page asks first. Open-in-external-editor / reveal-in-file-manager sit beside the content for the edits that want a real editor. Every place the page shows a file the agent holds — Config files, a native memory store, an unmanaged skill's folder, a session — uses the same file tree and the same viewer toolbar, so a file reads the same wherever it is opened.
- The agent detail page's **header** carries the agent's mark, its name, one status pill, **New conversation** and a **⋯** menu, and nothing under the name: the version and the config directory are on the Overview. The pill reads Connected, Not connected, Needs repair, Hook not approved, Off or Config left behind. The header never turns into a fix button — Connect, Repair, Turn on and Check again sit on the Overview's Connection section — and an agent whose program is not on this machine, which has nothing to converse with, shows ⋯ only. **Rotate proxy token** is in ⋯ only while the agent routes through Coffer's proxy ([provider-switching](../provider-switching/spec.md) "Authenticate each agent to the proxy with its own local token").
- The detail page has eight tabs, none carrying a count: six in the strip — **Overview**, **Skills**, **MCP servers**, **Hooks**, **Config files** and **Sessions** — and, behind a **More** menu, **Plugins** and **Memory**, the least used. Each is addressable by its own path (`/agents/<type>` for Overview, then `/agents/<type>/skills`, `/mcp-servers`, `/hooks`, `/config`, `/sessions`, `/plugins` and `/memory`), so a page opened from a tab returns to it. While the open tab is one of the two in More, the More trigger reads that tab's name and carries the underline; a tab in More that needs attention puts a warning dot on More. There is **no Model tab**: an agent's model is a section of the Overview, and `/agents/<type>/model` is not a page.
  - **Overview** stacks, top to bottom, **Connection**, **What this agent can use**, **Model** and **Details**. Connection says what the connection is in one line, lists the `coffer` MCP entry and the memory delivery hook with where each lives and its health, and carries the one fix the state calls for at its title's right — **Connect**, **Repair** or **Turn on** as a solid button, **Check again** as an outline one — and none while the agent is healthy. What this agent can use is six tiles, three by two — MCP servers, Skills, Config files, Plugins, Hooks and Memory — each with its count, one fact and, when something of the agent's own waits for a look, a warning "N to review"; a tile opens its tab. Model reads **Provider**, **Model**, **Effort** and **Route** (through Coffer's proxy, with **Test**, or direct) and carries **Change…**, which opens the Change model dialog of [provider-switching](../provider-switching/spec.md) "Review a model change before writing it"; opening the page with `?change-model=1` opens that dialog on arrival. With the `models` feature off the section is read-only and shows no Provider row and no Change. Details reads **Version**, **Config directory**, **UID** and **Registered**, with no Title, Name or Type, because an agent's name is fixed to its type.
  - **Skills** and **MCP servers** open with Coffer's part and then the agent's own, per "Show what Coffer manages for an agent in one row". **Plugins** lists the agent's installed plugins — all its own, since Coffer installs none — with a search, an enabled switch and a ⋯ menu whose only item is Uninstall…, and a plugin's name opens an information dialog.
  - **Hooks** opens with **Coffer's memory hook**, then **the agent's own hooks**, per "List every hook in the agent's native config". The tab is read only apart from Repair and Check again on Coffer's hook.
  - **Config files** lists every allowlisted config file of "Define a curated config-file allowlist per type" in one file tree — the settings files and the human-authored instructions files (`CLAUDE.md`, `AGENTS.md`) alike, because an instructions file is configuration the person wrote, not something installed.
  - **Memory** leads with **Coffer's memory** — Coffer's memory hook for this agent, when it last fired and what it delivers, with a link to the Memory page and a Repair when the hook is out of date or missing — only while the `memory` feature is on, and then lists **the agent's own memory stores**, read-only ([web-ui](../web-ui/spec.md) "Show memory delivery on the Memory page"). **Sessions** — the agent's own CLI session history, not Coffer's conversations — is one list beside a read-only reader; a failure to load a session shows inside the reader with a Retry.
- A direct server's name on the MCP servers tab opens that entry's read-only JSON in a dialog ("Show one direct MCP entry's full configuration without its secrets"), whose footer carries the row's two writes — remove it from its file (Remove, or Remove duplicate when Coffer already serves it) and adopt it into Coffer — around Close.
- Neither the Memory nor the Sessions list carries per-row actions: a row OPENS its subject, and the open / reveal affordances live on the page it opens, beside the thing they act on. A Sessions row opens that one session rendered as a readable conversation; a Memory row opens that store's directory as a file tree with a read-only preview, because a store is a directory and one session is a single file.

#### Scenario: desktop app agents page
- **GIVEN** Coffer's web UI is open with a Claude Code agent registered and connected and Codex installed but not yet connected
- **WHEN** the user opens the Agents page
- **THEN** it shows exactly two rows, Claude Code and Codex, the first with its `config_dir` and Connected and no button of its own, and the second reading Not connected with a Connect action

#### Scenario: config-file and MCP operations mirror across surfaces
- **GIVEN** the daemon exposes the config-file and Coffer-connection routes
- **WHEN** the user saves a config file, then disconnects and connects the agent, on the Agents page
- **THEN** each action calls the corresponding REST endpoint and produces the same state as calling that endpoint directly
- **AND** the Agents page shows, for the Coffer connection, the state `GET /api/v1/agents/{uid}/coffer-connection` reports

#### Scenario: CLI surface mirrors REST operations
- **GIVEN** the daemon is running and exposes the REST agent routes
- **WHEN** the user registers, views, updates, switches off and on, or edits the model of an agent from the Agents page
- **THEN** each action calls the corresponding REST endpoint and produces equivalent state changes

#### Scenario: the command line names an agent's files by path
- **GIVEN** a registered agent with config files, a native memory store and transcript sessions on disk
- **WHEN** the user reads the agent's config-file listing, native-memory scan and transcript listing over REST
- **THEN** each reports the absolute locations of the files for that agent
- **AND** nothing is written and no audit event is recorded

#### Scenario: the command line reads one transcript session
- **GIVEN** a registered agent with a transcript session listed by `GET /api/v1/agents/{uid}/transcripts`
- **WHEN** the user reads `GET /api/v1/agents/{uid}/transcripts/session` with that session's `source_path`
- **THEN** the response carries a window of that session's turns with the pasted secrets redacted and the whole session's turn count
- **AND** a path the agent has no session for is `not_found` (404)

#### Scenario: the command line lists an agent's models
- **GIVEN** the catalogue route offers a `codex` model with reasoning levels and a default among them, and a second model with none
- **WHEN** the user reads `GET /api/v1/agent-providers/codex/models`
- **THEN** the first model carries its id, its label and its efforts with the default marked, and the second carries none
- **AND** an unknown agent type is `not_found` (404)

#### Scenario: open a plugin's detail page from the Plugins tab
- **GIVEN** an agent with an installed plugin whose package contributes skills and commands
- **WHEN** the user clicks the plugin's name on the agent's Plugins tab
- **THEN** an information dialog opens over the list with the plugin's metadata, install directory and the components it contributes, each section with its count, and the Plugins tab offers no row expansion
- **AND** closing the dialog leaves the user on the Plugins tab

#### Scenario: the agent detail page carries six tabs and a More menu
- **GIVEN** a registered Claude Code agent with a managed skill, a direct MCP entry, an installed plugin and a `CLAUDE.md` instructions file
- **WHEN** the user opens `/agents/claude_code`
- **THEN** the strip reads Overview, Skills, MCP servers, Hooks, Config files and Sessions with no counts, followed by More holding Plugins and Memory, and opening `/agents/claude_code/skills` selects Skills
- **AND** opening Memory from More makes the trigger read Memory with the underline, and a Plugins tab whose files are gone puts a warning dot on More
- **AND** there is no Model tab, and `/agents/claude_code/model` opens the Overview
- **AND** Overview shows no Title or Name field, and its tiles for MCP servers, Skills and Plugins each open their tab; Config files lists the instructions file beside the settings files

#### Scenario: the header carries one status pill and a fixed action pair
- **GIVEN** an agent that is not connected, one that is connected, one that needs repair and one switched off
- **WHEN** each agent's page renders
- **THEN** the header shows the agent's name with one pill reading Not connected, Connected, Needs repair or Off, and New conversation beside the ⋯ menu
- **AND** no header carries a Connect, Repair, Turn on or Check again button, because those sit on the Overview's Connection section

### Requirement: Expose agent discovery on every surface
The system MUST expose a read-only discovery operation listing the supported types seen on this machine that have no agent registered, as candidates — at most one per type — available from the REST API (`GET /api/v1/agents/candidates`, rows shaped as "Report every supported type's detection state" describes), and the Agents page in the web UI, where a candidate is a row of the list that is not added (see "List the supported agents as fixed rows on the Agents page"). Detection is automatic: the page reads the candidates each time it loads and offers no Detect action. The user connects an addable candidate — `installed_active`, or `installed_never_run`, whose standard directory registration creates — with the row's **Connect**, which registers it and connects it after a preview of what it will write, with no typing of type identifiers, names or paths; a `config_only` candidate is shown as config left behind with its program not found, with the daemon's prompt that hands reinstalling it to an agent and no Add action.

#### Scenario: list discovery candidates from the command line
- **GIVEN** a supported agent is installed with its standard config directory present and no agent of that type is registered
- **WHEN** the user reads `GET /api/v1/agents/candidates`
- **THEN** the response lists that type as a candidate with its config dir, its state and its version
- **AND** no agent is registered as a result

#### Scenario: the agents page detects candidates without a detect action
- **GIVEN** Codex installed and run once (state `installed_active`) and no `codex` agent registered
- **WHEN** the user opens the Agents page
- **THEN** the Codex row reads Not connected with a Connect action, and the page carries no Detect agents button and no Add agent dialog

### Requirement: Switch an agent off with the kind-agnostic enabled flag
An agent MUST carry the kind-agnostic `enabled` flag, toggled through the generic `POST /api/v1/resources/{uid}/enable|disable` routes, and audited as `resource_enabled` / `resource_disabled`. A disabled agent is one Coffer does not write into and does not read from: its delivered skills are reclaimed and nothing new is delivered to it ([skill-manager](../skill-manager/spec.md)), its native memory is not aggregated ([memory](../memory/spec.md)), and its native config does not feed the model catalogue of "Serve each agent type's model catalogue from its one agent" — the catalogue is read as if no agent of that type were registered. Enabling it again puts back whatever the skills' own state grants, so the switch is never a one-way door. The one exception is adoption ([skill-manager](../skill-manager/spec.md) "Adopt an unmanaged skill"): adopting a folder from a disabled agent's skills directory links it in place and records an enabled binding for that agent, the agent's next reconcile reclaims that link and disables the binding, and enabling the agent delivers the skill back whenever the skill's own `enabled` flag and scope grant it. The agent's own routes neither carry nor change the flag: `AgentOut` does not report it and `PATCH /api/v1/agents/{uid}` does not set it.

#### Scenario: disabling an agent reclaims its skills and drops it from the catalogue
- **GIVEN** a registered agent holding a delivered skill, whose config dir the model catalogue reads for its type
- **WHEN** the agent is disabled through the kind-agnostic enabled flag
- **THEN** the delivered skill's link is gone from the agent's skills directory and no binding remains enabled for it
- **AND** the catalogue for that type no longer reads the agent's config dir
- **AND** a `resource_disabled` audit entry names the agent

#### Scenario: switch an agent off and on from the command line
- **GIVEN** a registered, enabled agent named `codex`
- **WHEN** the user posts to `/api/v1/resources/{uid}/disable`, then to `/api/v1/resources/{uid}/enable`
- **THEN** the agent's kind-agnostic `enabled` flag is false after the first and true after the second
- **AND** a `resource_disabled` and then a `resource_enabled` audit entry name the agent

### Requirement: Discover agents on this machine as candidates without registering them
The system MUST provide a read-only discovery operation that looks, for each supported type, at its standard config directory — named in that type's child spec — and at the directory that type's own environment variable (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) names in the daemon's environment when set, and reports each type with no agent registered and with either detection signal of "Detect an agent by its program and its config directory" as one **candidate**, carrying the fields of "Report every supported type's detection state". Nothing else is scanned. Candidates are derived at scan time and never stored. Discovery MUST NOT register anything automatically — the user reviews candidates and confirms which to add, and an `installed_active` or `installed_never_run` candidate can be added — the second's registration creates its standard config directory with only the entries Coffer needs — while a `config_only` candidate cannot, because a directory whose program is gone belongs to no working agent. The daemon MUST NOT auto-register agents on startup.

Over REST, candidates are the rows of `GET /api/v1/agents/candidates`. Each row MUST carry the candidate's state and version; an addable row is registered through the ordinary registration of "Manage the agent lifecycle" — with a `config_dir` only for a directory other than the standard one — and any other row says why it cannot be added. A candidate MUST NOT be discardable: nothing of Coffer's put the agent there, so no operation adopts or discards one.

#### Scenario: discover installed agents as candidates
- **GIVEN** a Coffer install with a supported agent's program installed, its standard config directory present, and no agent registered
- **WHEN** the user runs discovery
- **THEN** Coffer reports that type as an `installed_active` candidate (type, name, display name, config dir, version, addable) and registers nothing — discovery is read-only

#### Scenario: skip already-registered config directories on subsequent scan
- **GIVEN** a `codex` agent is registered for `~/.codex`, and `CODEX_HOME` names another existing directory
- **WHEN** the user runs discovery again
- **THEN** no `codex` candidate is offered, for either directory, because the type already has its agent

#### Scenario: adopt a discovered agent from the command line
- **GIVEN** Codex is installed, `~/.codex` is present and no `codex` agent is registered
- **WHEN** the user reads `GET /api/v1/agents/candidates`, then registers the type with `POST /api/v1/agents`
- **THEN** the read lists `codex` as an addable candidate and registers nothing
- **AND** the registration creates the `codex` agent at the default config directory, audited as `resource_created`
- **AND** no operation offers to adopt or discard an agent candidate

#### Scenario: add an agent that has never run
- **GIVEN** Codex's program is installed, `~/.codex` does not exist, and no `codex` agent is registered
- **WHEN** the user reads `GET /api/v1/agents/candidates`, then registers the type with `POST /api/v1/agents`
- **THEN** the read lists a `codex` candidate in state `installed_never_run`
- **AND** the registration creates `~/.codex` with only the entries Coffer needs and registers the agent, audited as `resource_created`

### Requirement: List every hook in the agent's native config
The system MUST list, read only, every command hook the agent will run. That covers the hooks in the agent's own hook-carrying files (the type's child spec names them) and those in each enabled plugin's hook file. Each is listed with its event, matcher, command, timeout, source (`user` or `plugin`, with the plugin's id) and the file that declares it. Project-level settings are not read, because Coffer does not know which repositories the agent is used in.

Coffer's own memory hook — its two entries, on `SessionStart` and `UserPromptSubmit` ([memory](../memory/spec.md) "Install delivery hooks explicitly and removably") — MUST be marked, each entry as Coffer's, and reported as one hook with the set of events its entries sit on. Its health MUST be reported by the same marker-and-command comparison the boot repair uses:
- `current` when the entries sit on exactly the events Coffer would install on and each carries exactly the command Coffer would write now;
- `stale` when Coffer's marker carries another command or sits on another set of events;
- `missing` when it is absent.

The report MUST also say whether the agent will run the hook, as its **trust**: `trusted`, `untrusted`, `modified` (approved for an earlier command), `disabled`, `unknown` (the agent's approval record does not parse), or `not_required` for an agent that runs every hook it finds. It MUST also give the last recorded fire from the audit log.

The listing MUST be served by `GET /api/v1/agents/{uid}/hooks`, and MUST write nothing and record no audit event. When the agent will not run a current hook, the trust reports why, and the Hooks tab and the attention list say what the user does about it. A file that does not parse MUST be reported as a parse error beside the hooks the other files yield.

Each listed hook MUST also carry where it sits in its file — `group_index` and `hook_index`, the positions in `hooks.<event>[group_index].hooks[hook_index]` — so a person can find the entry, and the REST listing reports them.

On the agent's Hooks tab the listing is two parts, Coffer's first. **Coffer's memory hook** is one block of properties, never one row per entry: its state (and how long ago it fired), its command, the events it sits on and the file that declares it, with its one fix at the block's title — **Repair** when it is stale or missing, **Check again** while the agent has not approved it — and, when it has never fired, the likely cause and a link to Activity. The reason a state is a problem is written in the block's own line. **The agent's own hooks** — Coffer's excluded — are one table of Event, Command, Matcher and File, with a search over command and file and an **Event** filter that lists each event with its count; the table says how many of how many are shown once either narrows it. A row opens a read-only details dialog with the command in full, the event and when it runs, the matcher, the type, the timeout, the file and the entry's position in it (`hooks.<event>[group].hooks[hook]`), with **Copy command** and **Open in Config files**; nothing in the dialog writes, because a hook is changed in its own file. A file name opens that file in Config files, except a plugin's hooks file, which has no Config files entry.

#### Scenario: list an agent's hooks with Coffer's own marked
- **GIVEN** a registered Claude Code agent whose `settings.json` carries a foreign `PreToolUse` hook and Coffer's memory hook, whose `settings.local.json` carries a `Stop` hook, and which has one enabled and one disabled plugin with a hook file each
- **WHEN** the user lists the agent's hooks
- **THEN** the foreign hooks, the `Stop` hook and the enabled plugin's hook are listed with their sources and files, the disabled plugin's hook is not, and only Coffer's two entries are marked as Coffer's
- **AND** Coffer's hook reads `current` on both events with trust `not_required` and no recorded fire, and nothing is written or audited

#### Scenario: report a stale Coffer hook
- **GIVEN** a registered Codex agent whose `hooks.json` carries Coffer's marked hook on `UserPromptSubmit` alone, with a command other than the one Coffer would write now, and one recorded fire
- **WHEN** the user lists the agent's hooks
- **THEN** Coffer's hook reads `stale` on `UserPromptSubmit`, the installed and expected commands differ, and the last fire is reported

#### Scenario: list the hooks with their position in the file
- **GIVEN** a Claude Code `settings.json` whose `PreToolUse` event holds two groups, the second with two hooks
- **WHEN** the user lists the agent's hooks
- **THEN** the second hook of the second group reports `group_index` 1 and `hook_index` 1, and the first group's hook reports 0 and 0

#### Scenario: coffer's memory hook leads the Hooks tab and the agent's own follow
- **GIVEN** a Claude Code agent whose `settings.json` carries Coffer's two memory-hook entries beside three hooks of its own
- **WHEN** the user opens the agent's Hooks tab
- **THEN** Coffer's hook is one block with its state, command, the two events and its file, and the agent's own hooks are one table of three rows that does not repeat Coffer's
- **AND** choosing a row opens a read-only dialog with the command, event, matcher, type, timeout, file and position, and searching or filtering by event narrows the table and says how many of how many show

## REMOVED Requirements

### Requirement: Offer JSON output on every CLI read
**Reason**: The `--json` flag existed only on the `coffer` read commands, which are gone; the REST reads already return JSON.
**Migration**: Read the same data from the REST routes under `/api/v1/agents`.
