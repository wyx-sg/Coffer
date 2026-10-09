# Agent Registry

## Purpose
The agent registry decides which locally-installed AI coding agents Coffer knows about, so that later features — skills, memory, knowledge, channels, chat — can deliver assets to them. Each agent is a Resource of kind `agent` in the kind-agnostic Resource framework. The supported products are **Claude Code** (`claude_code`) and **OpenAI Codex** (`codex`); each spans its CLI and its app/IDE form, because both forms read one shared config directory, so Coffer manages one config set per agent. The separate **Claude Desktop** chat app (its own `~/Library/Application Support/Claude/` config) and web-only agents such as claude.ai are not agents here. The registry holds only **managed** agents — external coding agents Coffer delivers to; the former built-in "Coffer Assistant" is not a registered agent ([Chat Is a Single-Owner Live Mirror](../../../docs/decisions/chat-single-owner-live-mirror.md)).

This spec holds what the two types share. Everything that differs by type — where the config directory is, which files are allowlisted, the MCP entry shape, the plugin inventory, the model catalogue's sources, the native-memory layout, the transcript location — lives in a child spec: [`agent-registry/claude-code`](claude-code/spec.md) and [`agent-registry/codex`](codex/spec.md), each the reading of one `AGENT_DESCRIPTORS` record, the single per-type table in the code. Adding a product is one enum value, one descriptor record and one child spec.

Beyond registering agents, the user lists and previews each agent's known config files read-only and opens them in their own editor to change them, installs Coffer's own MCP server into an agent with one click, and sees which models that agent can be put on. The registry also reaches into the agent's real on-disk workspace — the MCP servers configured in its own files, its installed plugins, directory-type config entries, its native memory and its session transcripts — following **ingest → hub → deliver**: anything shareable found in an agent's workspace can be adopted into Coffer's hub (the MCP gateway; the master skill store of skill-manager) and delivered back to any agent, instead of living as per-agent one-off config. All writes go through each agent's documented configuration paths only; the agents' internal state files are read as inputs where needed and never written. Config files are shown as raw text, read-only; a person edits them in their own editor, Coffer's own writes into them keep an atomic write and a backup, and recurring structured needs graduate into facets.

The user runs Coffer on their own machine; there is no multi-tenant or remote-access requirement. The registry relies on the Resource framework, audit log and immutable-`uid` identity of resource-framework, and renders inside the web-ui application shell. A `coffer-hook` binary with a session-context rules route and a `disable_native_memory` switch once lived here and was removed because it was never installed; Coffer installs no hook into an agent; the memory sync writes into each agent's own memory files ([memory](../memory/spec.md)), using the agent record and its config directory from this registry.

An agent's connection has one part, the `mcp` gateway entry; it carries no memory part whatever the features say.

## Requirements

### Requirement: Register each agent as an agent resource identified by its uid
The system MUST register each known local agent as a Resource of kind `agent`, identified by the immutable `uid` the resource framework mints for it ([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md)). Its name is its type's ("Keep one agent per type, named by it"), and every reference another kind holds to an agent — a resource `scope`'s agent list, a channel's `default_agent`, the `--agent-uid` the shim reports — holds the uid, so the reference survives the agent being removed and registered again only if it is re-pointed, never by coincidence of a name.

#### Scenario: keep an agent's uid across a rename
- **GIVEN** a registered agent with uid `U` named `codex`
- **WHEN** the user tries to rename it to `after`
- **THEN** the rename is refused with `NAME_IMMUTABLE` and the agent is still read back at `/api/v1/agents/U` with uid `U`, name `codex` and its config dir unchanged
- **AND** `after` addresses nothing as a path segment

#### Scenario: keep an agent's uid while its directory moves
- **GIVEN** a registered agent with uid `U` named `codex`
- **WHEN** the user moves it to another writable config directory
- **THEN** the agent is still read back at `/api/v1/agents/U` and at `/api/v1/agents/codex` with uid `U`, name `codex` and the new config directory

### Requirement: Validate agent configuration against the agent schema
The system MUST validate agent configuration against a kind-specific schema with fields `type` (enum) and `config_dir` (path, optional absolute-path override; when omitted it defaults to the type's standard location, which that type's child spec names), plus the model binding of "Carry the model binding on the agent record" and the connection the agent runs on of "Carry the connection an agent runs on on the agent record". Skills are delivered to `<config_dir>/skills`. The `agent` kind declares no `scope`: a non-null value is rejected at validation (422) — an agent resource is what other kinds' scopes name, never itself a scope target ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)).

#### Scenario: an agent cannot be given a scope
- **GIVEN** a registered agent
- **WHEN** a scope naming another agent is set on it through the kind-agnostic scope route
- **THEN** the request is rejected as `unprocessable_entity` (422) and the agent still has no scope

### Requirement: Support exactly the Claude Code and Codex agent types
The system MUST support the agent types `claude_code` and `codex`; registering any type outside the manifest (e.g. the `claude_desktop` chat app, a Gemini CLI) is rejected with `unprocessable_entity` (422). The rejection carries the generic request-validation message and never echoes the submitted value back. Per-type behaviour is defined by the capability manifest (`AGENT_DESCRIPTORS`) — per-type values in the record, per-type mechanisms in the optional facets it names ([Agent Mechanisms Are Optional Facets on the Descriptor](../../../docs/decisions/agent-mechanisms-are-optional-facets-on-the-descriptor.md)) — so adding a type is one enum value, one descriptor record with the facet implementations it has, and one child spec. Each supported type covers both the CLI and the app/IDE form of that product, which share one config directory.

What a facet looks like for one type is that type's child spec. There is no per-facet capability matrix, no per-facet "not supported" state on the agent surface and no capability booleans on the wire; a facet a type could not support would be a reason not to add that type. The `PluginCapability` flags of "Toggle a plugin through the documented location only" and "Uninstall a plugin by the type's own strategy" are the one exception, and they are per-facet *runtime availability* — whether the agent's own uninstall command is on `PATH` — not a per-type support claim. A further product is added only when it is genuinely in use and its facets can be exercised on a real install; `opencode`, `hermes`, `cursor` and `openclaw` were removed for lacking exactly that.

#### Scenario: reject unsupported agent type
- **GIVEN** the daemon is running
- **WHEN** the user attempts to register an agent of a type outside the supported set (e.g. `claude_desktop`, `gemini_cli`, or a garbage value)
- **THEN** registration is rejected with `unprocessable_entity` (422), and nothing is persisted

### Requirement: Re-offer a removed agent while it is still detected
A removed agent MUST re-appear as a discovery candidate on subsequent scans while its program or its config directory remains — a removal is not permanent (it may be accidental). The system MUST NOT keep a "suppressed types" list. Removal is a REST act (`DELETE /api/v1/agents/{uid}`); the web UI offers none, because its list always holds a row for every supported agent and the way to stop Coffer touching one is to disconnect it.

#### Scenario: re-surface removed agents on subsequent scan
- **GIVEN** an agent has been removed by the user and its program and config directory are still present
- **WHEN** the user runs discovery again
- **THEN** that agent is offered as a candidate again (removal is not permanent; no suppression list)

### Requirement: Manage the agent lifecycle
Users MUST be able to register, list, view, update (its config directory and the model binding of "Carry the model binding on the agent record") and remove agents. An agent cannot be switched off: its kind is non-toggleable, so the generic `POST /api/v1/resources/{uid}/enable|disable` routes refuse it with `RESOURCE_NOT_TOGGLEABLE` and its resource always reads enabled. Registration takes the type and, optionally, a config directory — the type's standard one when omitted — and the name is the type's ("Keep one agent per type, named by it"); there is no name, title or description to supply or edit. Skill bindings between an agent and a skill belong to skill-manager; this registry defines no skill operations beyond exposing an `on_delete` hook for cascade cleanup.

Over REST the lifecycle is `POST /api/v1/agents` (the type and, optionally, `config_dir`), `GET /api/v1/agents` and `GET /api/v1/agents/{uid}`, `PATCH /api/v1/agents/{uid}` (with `config_dir` and the model fields of "Carry the model binding on the agent record") and `DELETE /api/v1/agents/{uid}`, where `{uid}` is the agent's uid or the type it is named by ("Keep one agent per type, named by it"); the Agents page reaches the same operations through each row's Connect and ⋯ menu. The `agent` kind has no scope, because it declares none. The agent's Coffer connection, part by part ("Report an agent's Coffer connection part by part"), is read from `GET /api/v1/agents/{uid}/coffer-connection`: its state and, for its one part (the gateway MCP entry), whether it is installed.

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

#### Scenario: move an agent to a different config directory
- **GIVEN** a registered agent `claude-code` at `~/.claude` and another writable directory
- **WHEN** the user sends `PATCH /api/v1/agents/claude-code` with `config_dir` set to `<dir>`
- **THEN** `GET /api/v1/agents/claude-code` reports `<dir>` as its config directory, with the same uid and name
- **AND** the update route offers no way to change the name, title or description

#### Scenario: refuse a title on the update route
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

### Requirement: Allow one agent per name and per config directory
The system MUST reject registration that would create a duplicate agent name (409 `conflict`, as for any kind) — which, because an agent's name is its type's, is one agent per type ("Keep one agent per type, named by it") — and MUST reject registering more than one agent for the same config directory. The check compares resolved config directories — a registration without a `config_dir` resolves to its type's standard location — and runs on every move of an agent's directory too. A second agent for a directory already registered is rejected with `conflict` (409) and nothing is persisted.

#### Scenario: reject duplicate agent name
- **GIVEN** an agent named `codex` exists
- **WHEN** the user attempts to register another agent of type `codex`, whose name would be the same
- **THEN** registration is rejected with a clear error and nothing is persisted

#### Scenario: reject a second agent for an already-registered config dir
- **GIVEN** a `codex` agent is registered with the config dir `/tmp/shared`
- **WHEN** the user attempts to register a `claude_code` agent, or to move another agent, to a config dir that resolves to `/tmp/shared`
- **THEN** the request is rejected with a clear error and nothing is persisted — only one agent may exist per config directory

### Requirement: Define a curated config-file allowlist per type
Each supported agent type MUST define a curated allowlist of config files in its capability-manifest record, enumerated by that type's child spec, each entry carrying a stable `key`, a display name, a resolved absolute path, and a `format` (`json`, `toml` or `markdown`). Each type's human-authored instructions file carries the key `instructions` — those files are instructions a person wrote, distinct from agent-written memory (memory's domain). The allowlist is what Coffer lists and the only files Coffer's own writers may touch; config files are not persisted in SQLite — the file on disk is the source of truth.

#### Scenario: key each type's instructions file as instructions
- **GIVEN** the capability manifest for every supported agent type
- **WHEN** the type's config-file allowlist is read
- **THEN** every entry carries a key, a display name, an absolute path and a format among `json`, `toml` and `markdown`
- **AND** exactly one entry per type is keyed `instructions` and has format `markdown`

### Requirement: List an agent's config files with their locations
Users MUST be able to list an agent's config files with, for each, its key, display name, path, the containing-folder absolute path (`folder_path`), format, and existence (plus size and modified time when the file exists). The `path`/`folder_path` pair feeds the UI's open-in-external-editor / reveal-in-file-manager affordances (see "Open config files in an external editor or reveal them"). Coffer writes none of these files on the person's behalf; one file's content is read only for its preview ("Preview an agent's config file read-only").

#### Scenario: report each config file's path, folder and existence
- **GIVEN** a registered agent where one allowlisted file exists and another does not
- **WHEN** the user lists the agent's config files
- **THEN** each entry carries its key, display name, absolute `path`, `folder_path` equal to the path's parent, format and `exists` flag
- **AND** the existing file also carries its size and modified time while the missing one carries neither

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

#### Scenario: connect an agent to Coffer over REST
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

#### Scenario: report the Coffer MCP status per agent
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

#### Scenario: disconnect an agent from Coffer over REST
- **GIVEN** an agent that has Coffer's MCP installed
- **WHEN** the user disconnects the agent with `DELETE /api/v1/agents/{uid}/coffer-connection`
- **THEN** the `coffer` entry is gone from the agent's MCP config
- **AND** `GET /api/v1/agents/{uid}/coffer-connection` reports the state as `disconnected`

### Requirement: Back up and audit Coffer MCP install and uninstall
Install and uninstall MUST reuse the atomic-write + backup machinery of "Back up and compare-and-swap every write Coffer makes to an agent's config" and record an audit entry (`agent_mcp_installed` / `agent_mcp_uninstalled`).

#### Scenario: uninstall Coffer's MCP from an agent
- **GIVEN** an agent that has Coffer's MCP installed
- **WHEN** the user uninstalls it
- **THEN** the `coffer` entry is removed from the agent's MCP config, the file is backed up under `~/.coffer/config-backups/`, an `agent_mcp_uninstalled` audit entry is recorded, and status reports `installed=false`

### Requirement: List the MCP entries in the agent's own config files
The system MUST parse and list the MCP server entries configured in the agent's own files, reading the source files that type's child spec names and labelling each entry with the file it came from. Each entry carries name, source, transport (stdio command or HTTP URL), the `enabled` flag where the format defines one, `is_coffer` for Coffer's own gateway entry, and `matches_resource` naming an equivalent registered `mcp_server` resource when one exists. Entries are derived at read time, never stored; Coffer keeps no copy. Coffer's own `coffer` entry is rendered specially and managed by the install/uninstall operations, never as a plain direct entry.

Over REST the entries are `GET /api/v1/agents/{uid}/mcp-entries`; each is addressed by its name — plus its source file where the type's entries may come from more than one — by the routes of the requirements that follow.

Coffer does not offer toggling an entry's `enabled` flag, nor editing an entry in place: for a format with no per-entry flag a toggle could only fail, and for one that has it the toggle would duplicate a switch the agent's own UI already owns while hand-writing another tool's private config format. Removal and adoption are the only entry-level writes, because they are the writes Coffer alone has a reason to make.

#### Scenario: list an agent's real MCP entries
- **GIVEN** a registered agent whose own config files define several MCP server entries including `coffer`
- **WHEN** the user lists the agent's MCP entries
- **THEN** Coffer returns every entry with its name, source file, transport (stdio command or HTTP URL), and the `enabled` flag where that format defines one, marks the `coffer` entry `is_coffer=true`, and stores nothing — the listing is derived from the file at read time

#### Scenario: list an agent's direct MCP entries apart from Coffer's
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
Users MUST be able to remove a direct MCP entry — from the agent's page or the REST route (`DELETE /api/v1/agents/{uid}/mcp-entries/{entry}`). Removal edits only the entry's source file, reuses the atomic-write + backup machinery of "Back up and compare-and-swap every write Coffer makes to an agent's config", and records an `agent_mcp_entry_removed` audit entry. The `coffer` entry is not removable through this operation — it is managed by "Install Coffer's MCP server into an agent in one action" and "Uninstall Coffer's MCP server from an agent".

#### Scenario: remove a direct MCP entry
- **GIVEN** a registered agent with a direct (non-Coffer) MCP entry
- **WHEN** the user removes that entry (carrying the source file where the type's entries may come from more than one)
- **THEN** the entry is deleted from exactly its source file via an atomic write with a backup of the prior content under `~/.coffer/config-backups/`, an `agent_mcp_entry_removed` audit entry is recorded, and the next listing no longer shows it

#### Scenario: remove a direct MCP entry over REST and refuse the coffer entry
- **GIVEN** a registered agent `claude-code` whose own config defines a direct entry `github`
- **WHEN** the user sends `DELETE /api/v1/agents/claude-code/mcp-entries/github`
- **THEN** the entry is gone from its source file, the newest backup under `~/.coffer/config-backups/` holds the prior content, and an `agent_mcp_entry_removed` audit entry is recorded
- **AND** `DELETE /api/v1/agents/claude-code/mcp-entries/coffer` is refused and leaves the file unchanged

### Requirement: Adopt a direct MCP entry into Coffer
Users MUST be able to adopt a direct MCP entry into Coffer, so that it is served to every agent through the gateway instead of benefiting one agent alone — from the agent's page or the REST route (`POST /api/v1/agents/{uid}/mcp-entries/{entry}/adopt`), whose `new_name` registers the server under a different name than the entry's. Adoption (a) registers the entry as an `mcp_server` resource through the standard resource flow (schema validation + audit), (b) verifies the resource reads back, then (c) removes the source entry per "Remove a direct MCP entry from its source file" — strictly in that order. Any failure stops the operation, rolls back a created resource, and leaves the agent's config byte-identical, reporting the failure with a specific error code; audited as `agent_mcp_entry_adopted` on success. A name collision with an existing resource is rejected with `conflict` (409) carrying a suggested alternative; an entry equivalent to an existing resource is reported via `matches_resource` so the user can remove the duplicate instead. The `coffer` entry is never adoptable.

#### Scenario: adopt a direct MCP entry into Coffer
- **GIVEN** a registered agent with a direct stdio MCP entry whose name collides with no existing resource
- **WHEN** the user adopts the entry
- **THEN** Coffer first registers an equivalent `mcp_server` resource (schema-validated, audited), verifies it reads back, then removes the direct entry from the agent's config (atomic + backup), records an `agent_mcp_entry_adopted` audit entry, and the upstream is now served to all agents through the gateway

#### Scenario: reject adoption on resource name conflict
- **GIVEN** an `mcp_server` resource already exists with the same name as a direct entry
- **WHEN** the user adopts that entry without renaming
- **THEN** the request is rejected with `conflict` (409) carrying a suggested alternative name, no resource is created, and the agent's config is untouched

#### Scenario: adoption failure leaves agent config untouched
- **GIVEN** an adoption attempt that fails after resource registration (e.g. the config-file write is rejected as stale)
- **WHEN** the operation aborts
- **THEN** the created resource is rolled back, the agent's config file is byte-identical to before the attempt, and the failure is reported with a specific error code

#### Scenario: adopt a direct MCP entry under a new name
- **GIVEN** an `mcp_server` resource named `github` and an agent `claude-code` whose own config defines a direct entry `github`
- **WHEN** the user adopts the entry with `POST /api/v1/agents/claude-code/mcp-entries/github/adopt` carrying `new_name` `github-work`
- **THEN** an `mcp_server` resource named `github-work` is registered and the direct entry is gone from the agent's config
- **AND** an `agent_mcp_entry_adopted` audit entry is recorded

### Requirement: Route secret-like environment values to the secret store on adoption
Adoption MUST NOT persist secret values into resource config. When an entry's environment or HTTP headers carry values under secret-like keys (defined below), the adopt request MUST supply a secret mapping for each flagged key or be rejected with the unresolved keys listed. Mapped values are stored as Fernet ciphertext in Coffer's secret store through the daemon (per the secrets invariant); the resource config carries references only. A key is secret-like when its value is non-empty and its name matches `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`/`APIKEY`, `CREDENTIAL` or `AUTHORIZATION`, case-insensitively.

#### Scenario: require a secret mapping for secret-like env values
- **GIVEN** a direct MCP entry whose environment contains a value under a secret-like key (e.g. `API_TOKEN`)
- **WHEN** the user adopts the entry without supplying a secret mapping for that key
- **THEN** the request is rejected with a response listing the unresolved keys; when the mapping is supplied, the secret is stored in the secret store via the daemon and the created resource config carries a reference, never the value

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
A config-file allowlist entry MAY be a **directory entry** (`kind=directory`): it resolves to a directory and lists its files (entry-relative path, absolute path, size, modified time) instead of carrying content. A missing directory MUST list as `exists=false` with no files, and the read MUST NOT create it. Which allowlist entries are directory entries is per type, and each child spec names its own. The directory on disk is the source of truth; its files are opened and revealed like any other config file.

#### Scenario: list a directory config entry's files
- **GIVEN** a registered agent whose directory config entry contains Markdown files (possibly nested)
- **WHEN** the user lists that config entry
- **THEN** Coffer returns the entry with `kind=directory` and its files (entry-relative path, size, modified time); a missing directory lists as `exists=false` with no files and is not created by the read

### Requirement: Carry the model binding on the agent record
The agent record MUST carry the model binding the rest of Coffer reads — `model` and `tier_models` (Claude Code only: the model for each of `opus`, `sonnet`, `haiku` and `fable`) — because the model is chosen at the point of USE and an agent is where it is used, not on the connection that serves it. That binding MUST be settable over REST as well as in the web UI: `PATCH /api/v1/agents/{uid}` carries `model` / `tier_models`, with an explicit null to unbind `tier_models`. A field the request omits is unchanged; `tier_models`, when sent, replaces the whole mapping. Only `tier_models` clears on an explicit null; `model` has no null that unbinds it, so an explicit null for it is treated as omitted. A tier other than the four is refused. The binding carries no `fast_model`: Claude Code's background model is its Haiku tier, and no reasoning effort: the agent runs at the effort its own configuration names. Projecting a binding into the agent's native config is provider-switching's. The binding belongs to a connection: an agent that goes to, or is on, its built-in login MUST carry neither `model` nor `tier_models` (provider-switching's apply clears them once the file is written), so what the agent's Overview and list show on the built-in login is the model its own configuration names, never a leftover of an earlier connection.

#### Scenario: bind a model to an agent over REST
- **GIVEN** a registered agent
- **WHEN** the user sends `PATCH /api/v1/agents/{uid}` with a `model` and `tier_models` `{"haiku": "<model>"}`, then again with `tier_models` null
- **THEN** the agent record reports the bound `model` and `tier_models` after the first edit, and carries no `fast_model`
- **AND** after the second edit `tier_models` is null while `model` is unchanged

#### Scenario: the built-in login leaves no binding on the record
- **GIVEN** an agent bound to `kimi-k3` with tiers, running on a connection
- **WHEN** the user applies the built-in login (`POST /api/v1/providers/model-switch/apply` with a null `connection_uid`)
- **THEN** the agent's record reports no `model` and no `tier_models`, and its `connection_uid` is empty

### Requirement: Carry the connection an agent runs on on the agent record
The agent record MUST carry `connection_uid`: the uid of the provider connection the agent runs on, or none when it runs on its own built-in login. The choice is a field of the agent, so an agent runs on at most one connection by construction and nothing on a connection says which agents use it; agents are filed machine-locally, so the choice never travels in a sync round while the connection itself does. `AgentOut` MUST report it. `PATCH /api/v1/agents/{uid}` MUST NOT set it: the connection is switched through the provider routes (`POST /api/v1/providers/{uid}/activate`, `POST /api/v1/providers/use-builtin/{agent_type}`), because a switch writes the agent's native config together with the field ([provider-switching](../provider-switching/spec.md) "Switch one agent at a time"). A `connection_uid` that names a connection that is missing, switched off or no longer reaches the agent means the agent is treated as on its built-in login (provider-switching "Keep an agent on at most one connection").

#### Scenario: an agent reports the connection it runs on
- **GIVEN** a registered agent that was switched onto a connection, and another that was not
- **WHEN** both are read (`GET /api/v1/agents/{uid}`)
- **THEN** the first reports that connection's uid as `connection_uid` and the second reports none

#### Scenario: an agent's update does not switch its connection
- **GIVEN** a registered agent on its built-in login
- **WHEN** a client sends `PATCH /api/v1/agents/{uid}` carrying a `connection_uid`
- **THEN** the field is not applied and the agent's native config and `connection_uid` are unchanged

### Requirement: Read the model catalogue back from the installed agent
The catalogue MUST be one backend service answering per agent, and every entry — id, label, description — MUST be read back from the installed agent rather than written into Coffer, because a list written down here goes stale on the next CLI release; a model released after Coffer shipped appears with no Coffer release. Each type's child spec names its sources, and the order those sources answer in is the order of the picker. Every source MUST degrade to nothing on its own: a missing CLI, a changed bundle layout, an unauthenticated or wedged agent costs the models that source would have added and nothing else.

#### Scenario: lose only a failing source's models
- **GIVEN** an agent type with two catalogue sources, the first of which raises
- **WHEN** the catalogue is read
- **THEN** the answer carries exactly the second source's models and the request does not fail

### Requirement: Keep one source of truth for an agent's models
There MUST be exactly one source of truth. No Coffer surface may keep a model list of its own: the agent's catalogue is the answer of "Serve each agent type's model catalogue from its one agent", and what a picker is OFFERED — which narrows to the curated set of the connection the agent runs on where there is one — is [provider-switching](../provider-switching/spec.md) "Serve one model list to every surface"'s answer, served over the wire from that one backend rather than reassembled by any client. Nothing in Coffer curates an agent's models; two attempts to have someone curate them, first on the agent and then on the channel, were both removed. The accepted cost is that a model the agent's own catalogue does not name cannot be PICKED from a Coffer surface — it stays typeable wherever the CLI accepts a name. The benefit is that a newly released model reaches every surface with no Coffer release at all.

#### Scenario: offer the agent's whole catalogue with nothing curated on the agent
- **GIVEN** a registered agent whose installed agent reports several models and its agent on no connection that curates a set
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

### Requirement: Scan an agent's own native memory stores read-only
The system MUST expose a read-only **native-memory scan** that lists an agent type's own native memory stores — the agent's self-written store, distinct from the human-authored `instructions` config files — in the layout that type's child spec defines. Each row carries a `project` label and `path` that are the REAL project directory, the real `memory_dir`, and an `item_count`. An agent type with no native memory layout, or one whose layout is absent on disk, returns an empty list. The scan is read-only, derives everything from disk at read time (nothing stored), and — consistent with "Audit every agent lifecycle event" — emits NO audit event. It never writes the agent's store. What Coffer does with the agents' own stores beyond showing them is memory's.

Coffer does not import a native memory store into its own knowledge layer: the knowledge layer is a directory of markdown files the user and agents write deliberately ([Knowledge Is Plain Files](../../../docs/decisions/knowledge-is-plain-files.md)), and a bulk copy of another tool's store would be material nobody chose to keep. Reading the store, and opening it where it lives, is the whole of this facet.

#### Scenario: return an empty scan when the agent has no native memory on disk
- **GIVEN** a registered agent whose native memory layout is absent on disk
- **WHEN** the user scans the agent's native memory
- **THEN** the scan returns an empty list
- **AND** no audit event is recorded

### Requirement: Read one native memory store's files read-only
The system MUST expose a read-only **native-memory store read** that returns one store's directory as a file tree (each entry's name, store-relative path, type and size) and one file inside it as text (its contents, its absolute path for the open / reveal affordances, and whether it was truncated or is binary). A store is addressed by the `memory_dir` the native-memory scan handed out, which MUST be exactly a directory that type's layout would have listed — and not merely some path under the agent's config dir, which also holds its transcripts, settings and plugin cache. A directory that is not one of the agent's stores, a file path escaping the store, and a file that does not exist are all `not_found` (404); whether a directory is one of the agent's stores is decided by its shape alone, so the answer cannot be used to probe the filesystem. A store that has that shape but no longer exists on disk reads as an empty tree (200), not a 404. Reads are capped in size and the walk is depth-bounded, with both facts reported rather than silently applied. Read-only: Coffer never writes an agent's own memory, so the surface previews and offers open / reveal instead of an editor, and emits no audit event.

#### Scenario: browse one native memory store's files
- **GIVEN** a registered agent with a native memory store listed by "Scan an agent's own native memory stores read-only", holding Markdown files in the store directory and a subdirectory
- **WHEN** the user opens that store by the `memory_dir` the listing gave and then reads one file in it
- **THEN** Coffer returns the store directory as a tree (directories before files, paths relative to the store) and the file's contents with the absolute path that backs open / reveal, while a directory that is not one of this agent's stores — its sibling project directory included — and a path escaping the store are both rejected as `not_found` (404); read-only, emitting no audit event and writing nothing

### Requirement: Open config files in an external editor or reveal them
The agent's **Config files** tab MUST be one split view, resizable by its divider (web-ui "Resize every split view by its divider"): a file tree on the left listing every allowlisted config file on disk — and, as a folder of its files, each directory entry — and the selected file read-only on the right, in the shared viewer whose toolbar shows the file's path and size with **Open in editor** and **Reveal in Finder**, using the `path` and `folder_path` from "List an agent's config files with their locations"; a Reveal icon in the tree's header reveals the config directory. Only what exists on disk is listed: a file or directory entry the agent has not created yet is left out of the tree, because opening creates nothing and Coffer creates no config file, and an agent with none on disk shows that no config file was found. The selected file is in the URL (`?file=`) and defaults to the first file listed. Open and reveal perform the real OS action through the daemon's filesystem-action endpoints (`POST /api/v1/fs/open`, `POST /api/v1/fs/reveal`, and the installed-editor enumeration `GET /api/v1/fs/editors` behind the preference — all owned by the daemon spec, which this spec consumes and does not specify), since the loopback daemon is always on the user's own machine ([Daemon Proxies OS File Actions](../../../docs/decisions/daemon-proxies-os-file-actions.md)). Selecting a file shows its read-only preview ("Preview an agent's config file read-only"); the tab offers no edit, new file or delete: a config file is changed in the person's own editor or by their agent. There is no copy-path fallback. The editor used for open-in-external-editor references the user's "preferred external editor" preference defined by web-ui (not re-specified here).

#### Scenario: open a config file and reveal it through the daemon
- **GIVEN** an agent's Config files tab listing an existing config file and one not created yet
- **WHEN** the user chooses Open in editor and then Reveal in Finder on the open file's toolbar
- **THEN** the UI asks the daemon to open that file's absolute path and then to reveal it
- **AND** the file not created yet is not listed in the tree, nothing offers Edit, New file or Delete, and no copy-path affordance is offered

#### Scenario: preview a config file from its row
- **GIVEN** an agent's Config files tab listing an existing `settings.json`
- **WHEN** the user selects the file in the tree
- **THEN** the right pane shows the file's content read-only
- **AND** the pane offers Open in editor and Reveal in Finder and no Edit or Save

### Requirement: Audit every agent lifecycle event
The system MUST record an audit entry, carrying timestamp, actor and the affected agent reference, for every lifecycle event: agent created, updated, removed (via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events); Coffer MCP installed/uninstalled; MCP entry removed/adopted (`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`); plugin toggled/uninstalled (`agent_plugin_toggled` / `agent_plugin_uninstalled`). Discovery and all workspace listings — MCP entries, plugins, config files, native memory stores, native sessions, the model catalogue, the Coffer connection status — are read-only and emit no audit event. Reading ONE of the listed items — a single store's files — is the same act at a smaller scale and audits nothing either, and renaming or deleting a native session is the agent's own act on its own record ("Rename and delete a native session through the agent") and is not audited here. A connect or disconnect records the events of the parts it installs or removes and none of its own. The `agent_config_file_written` and `agent_config_file_deleted` events are no longer recorded; rows an earlier version recorded keep their wording in Activity.

#### Scenario: audit lifecycle events
- **GIVEN** the user has registered, edited, or removed agents
- **WHEN** they view the audit log
- **THEN** every lifecycle change (create, update, remove) appears via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events, each carrying timestamp, actor, and the affected agent reference. (Discovery is read-only and registers nothing, so it emits no audit event of its own.)

### Requirement: Expose agent discovery over REST and on the Agents page
The system MUST expose a read-only discovery operation listing the supported types seen on this machine that have no agent registered, as candidates — at most one per type — available from the REST API (`GET /api/v1/agents/candidates`, rows shaped as "Report every supported type's detection state" describes), and the Agents page in the web UI, where a candidate is a row of the list that is not added (see "List the supported agents as fixed rows on the Agents page"). Detection is automatic: the page reads the candidates each time it loads and offers no Detect action. The user connects an addable candidate — `installed_active`, or `installed_never_run`, whose standard directory registration creates — with the row's **Connect**, which registers it and connects it after a preview of what it will write, with no typing of type identifiers, names or paths; a `config_only` candidate is shown as config left behind with its program not found, with the daemon's prompt that hands reinstalling it to an agent and no Add action.

#### Scenario: list discovery candidates over REST
- **GIVEN** a supported agent is installed with its standard config directory present and no agent of that type is registered
- **WHEN** the user reads `GET /api/v1/agents/candidates`
- **THEN** the response lists that type as a candidate with its config dir, its state and its version
- **AND** no agent is registered as a result

#### Scenario: the agents page detects candidates without a detect action
- **GIVEN** Codex installed and run once (state `installed_active`) and no `codex` agent registered
- **WHEN** the user opens the Agents page
- **THEN** the Codex row reads Not connected with a Connect action, and the page carries no Detect agents button and no Add agent dialog

### Requirement: Offer a folder picker for a custom config directory
When choosing a custom `config_dir`, the web UI MUST offer a folder picker rather than requiring the user to type a path. It is reached from an agent row's menu, **Use a different config directory…**, because the default directory is found automatically and a different one is the exception. It MUST use the daemon's native directory dialog (`POST /api/v1/fs/pick-folder`, owned by the daemon spec), falling back to the daemon-backed folder browser (`GET /api/v1/fs/browse`, owned by the daemon spec) only when the host has no native dialog tool. Both yield an absolute path that is then validated per "Validate the config directory at registration" before registration, or before the agent's directory is moved.

#### Scenario: pick a custom config directory with the native dialog
- **GIVEN** the Agents page and the host offering a native directory dialog
- **WHEN** the user chooses Use a different config directory… from a row's menu and picks a folder
- **THEN** the picked absolute path is validated and used for that agent's config directory
- **AND** the in-app folder browser is not opened

### Requirement: Read one installed plugin's detail read-only
The system MUST return one installed plugin's detail, addressed by the `<name>@<marketplace>` id the listing reports: its listing row (enabled state, cache flag, manifest version, description, author and homepage), its marketplace's source, the directory its package was read from, whether in-app uninstall can run now (the listing's `can_uninstall`), and everything the package contributes from its default locations — skills (`skills/<name>/SKILL.md`), commands (`commands/*.md`) and subagents (`agents/*.md`), each with the description from its YAML frontmatter, the hook events `hooks/hooks.json` registers handlers for, and the MCP servers `.mcp.json` bundles. The read is best-effort in the same way as the listing: a missing folder, an unreadable file or malformed frontmatter gives an empty list or a component without a description, and a plugin whose cache directory is missing reports no install directory and no contents. An id the listing does not report is `not_found` (404, `PLUGIN_NOT_FOUND`). The read writes nothing and emits no audit event.

#### Scenario: read one plugin's detail and contents
- **GIVEN** a registered agent with an installed plugin whose package holds a skill, a command and a subagent with frontmatter descriptions, a hooks file and an `.mcp.json`
- **WHEN** the user reads that plugin's detail
- **THEN** Coffer returns the plugin's listing row, its marketplace source, its install directory, and each skill, command and subagent with its description, the hook event names and the MCP server names
- **AND** every file under the agent's config directory is byte-identical before and after the read

#### Scenario: reject a plugin id the agent does not have
- **GIVEN** a registered agent
- **WHEN** the user reads the detail of a plugin id its listing does not report
- **THEN** Coffer answers 404 with `PLUGIN_NOT_FOUND`

### Requirement: Show the Coffer connection on the agent pages
An agent has one unconnected state, **Not connected**, and one word per other state: **Connected**, **Needs repair** (the `partial` state), **Config left behind** and, for an added agent whose program and directory are both gone, **Not found**. A newly found agent that was never added and an agent that was disconnected are the same state, so both read Not connected and both offer **Connect**; the list has no "Not added" or "Detected" word and no Add action. Each row of the Agents list MUST show the agent's state and the one action that state calls for: **Connect** for one not connected — which, for a newly found agent, registers it under its default config directory first — **Repair** for one that needs repair, and none for one that is connected, whose ⋯ menu carries **Disconnect**. An agent whose program is not on this machine has no fix Coffer can make: its row offers the daemon's install prompt as the hand-off split button **Ask an agent ▾** before its ⋯ menu (web-ui "Hand a machine-dependent problem to an agent with one split button"), and its own page offers it in the Overview. The same states offer the same actions on the agent's own page, in the Overview's Connection section (**Connect** and **Repair** as solid buttons), never in the page header. The ⋯ menu, on the row and on the page, holds **Use a different config directory…**, **Reveal config directory**, **Copy uid**, and **Disconnect** while a part is installed, in that order, and never repeats a visible action — the install prompt included.

Connect, Repair and Disconnect MUST each open **Review changes** first — every file it will write and the lines it adds or removes, the connection test as the daemon reports it — and write nothing until the user applies it; **Use a different config directory…** on a connected agent moves Coffer's entry to the new directory through the same review, and on an agent not yet added it registers the directory without connecting. The list has two rows, so it carries no row selection and no bulk bar. Which parts a connection installs MUST be explained behind a help affordance beside the action rather than as inline text.

#### Scenario: the Overview offers the action the state calls for
- **GIVEN** an agent's page for an agent that is not connected, one that is connected, and one whose connection is partial
- **WHEN** each Overview's Connection section renders
- **THEN** the unconnected agent offers Connect, the connected one offers no button and has Disconnect in its ⋯ menu, and the partial one reads Needs repair and offers Repair

#### Scenario: connecting an agent previews the change first
- **GIVEN** the Codex row reading Not connected, never added
- **WHEN** the user chooses Connect
- **THEN** Review changes lists each file the connect will write and the lines it adds, and nothing is written yet
- **AND** applying registers Codex under its default config directory, connects it, and the row reads Connected

#### Scenario: repairing a partial connection previews the missing parts
- **GIVEN** a Claude Code agent whose Coffer connection is partial
- **WHEN** the user chooses Repair on its row
- **THEN** Review changes lists only the missing parts, and applying installs them and the row reads Connected

#### Scenario: moving a connected agent's config directory goes through Review changes
- **GIVEN** a connected Codex agent at `~/.codex`
- **WHEN** the user chooses Use a different config directory… and picks another directory
- **THEN** Review changes shows Coffer's lines leaving the old directory and arriving in the new one, and nothing moves until the user applies it
- **AND** applying leaves the agent connected at the new directory

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

#### Scenario: register a discovered agent over REST
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

### Requirement: Keep one agent per type, named by it
A machine MUST hold at most one agent of each supported type, and that agent's `name` MUST be its type's name — `claude-code` for `claude_code`, `codex` for `codex` — derived from the type at registration, never chosen by a person. The name is fixed: a changed name MUST be refused with `NAME_IMMUTABLE` (409) whose message says the name is the agent's type. An agent MUST carry no `title` and no `description`: a non-empty title is refused as a validation error (422) on every surface, and neither registration nor update takes a description. Its config directory is the one per-agent setting besides the type and the model binding of "Carry the model binding on the agent record". Registering a type that already has an agent MUST be refused with `AGENT_TYPE_REGISTERED` (409) and nothing persisted; using a different directory is an edit of the one agent.

Because a type names exactly one agent, every `/api/v1/agents/{uid}/…` route MUST also accept the type — its name (`claude-code`) or its value (`claude_code`) — in place of the uid, and answer exactly as it does for the uid; a type with no agent registered reads as not found.

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

### Requirement: Report every supported type's detection state
The system MUST serve `GET /api/v1/agents/types`, one row per supported type in manifest order whether or not an agent of it is registered, so a surface can always render one row per type. Each row MUST carry the `type`, its agent's `name`, the `display_name`, the `config_dir` — the registered agent's, or the one registering would use — the type's `standard_config_dir`, the `default_skill_dir`, the detection `state` and `version` of "Detect an agent by its program and its config directory", the registered agent's `uid` (`null` when none), whether it is `addable` now, the product's official `install_url` (kept in the manifest, so a surface can send a person whose machine lacks the program to its install page), and `other_config_dir`: an existing directory the type's own environment variable (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) names in the daemon's environment other than `config_dir`, offered as a different config directory to use, never as a second agent. A type not registered is `addable` exactly when its program is installed. The read is derived at request time, stores nothing and audits nothing.

#### Scenario: list every supported type whether added or not
- **GIVEN** a registered `claude_code` agent, and Codex installed but never run — its program on its `PATH` and `~/.codex` absent
- **WHEN** the user requests `GET /api/v1/agents/types`
- **THEN** the response has exactly two rows: `claude_code` with the agent's uid, its directory and `addable` false, and `codex` with no uid, state `installed_never_run`, `config_dir` `~/.codex` and `addable` true
- **AND** each row carries its product's official install page as `install_url`
- **AND** nothing is registered or created by the read

### Requirement: Serve each agent type's model catalogue from its one agent
`GET /api/v1/agent-providers/{agent_key}/models` MUST answer, per agent type, which models a picker offers for that agent: the agent's own catalogue, read back from the installed agent and never written down in Coffer, unless the connection the agent runs on curates a set of ids — then those ids, as [provider-switching](../provider-switching/spec.md) "Serve one model list to every surface" defines. Each entry MUST carry `id` (passed to the agent verbatim), `label` and `description`. An unknown `agent_key` MUST be a 404. The catalogue reads the native config of the type's one agent ("Keep one agent per type, named by it"), which is also the agent a chat turn on that type runs against ([chat](../chat/spec.md) "Run Claude Code and Codex as subprocess providers on the type's one agent").

#### Scenario: list the models an agent can be put on
- **GIVEN** a registered `codex` agent whose own config names a model
- **WHEN** the user requests `GET /api/v1/agent-providers/codex/models`
- **THEN** the response lists that model with `id`, `label` and `description`
- **AND** the same request for an unknown agent key answers 404

### Requirement: Connect an agent to Coffer in one action
Users MUST be able to connect an agent to Coffer in one action, from the REST API (`POST /api/v1/agents/{uid}/coffer-connection`) and the web UI. Connecting MUST install every **part** Coffer writes into the agent's own configuration for that agent's type. Today every type has one part:

- `mcp` — the gateway MCP entry of "Install Coffer's MCP server into an agent in one action".

Coffer writes no hook into an agent. A connect refused for want of a shim writes nothing. Every part MUST be installed through its own atomic write with a backup and record its own audit event, as it does when installed alone. Connecting MUST be idempotent: connecting a connected agent rewrites each entry in place and never duplicates one.

#### Scenario: connect installs every part that applies
- **GIVEN** a registered Claude Code agent without the gateway entry
- **WHEN** the user connects it to Coffer
- **THEN** the agent's `.claude.json` carries the `coffer` MCP entry, naming the agent by its uid
- **AND** one `agent_mcp_installed` audit entry names the user as actor, and the connection reports `connected` with its `mcp` part installed

### Requirement: Disconnect an agent from Coffer
Users MUST be able to disconnect an agent from Coffer in one action (`DELETE /api/v1/agents/{uid}/coffer-connection`, the web UI). Disconnecting MUST remove every part the agent type has, taking out only Coffer's own marked entries and leaving every other entry, key and hook in those files as it was. A part that is absent MUST be a no-op that writes no file and records no audit event.

#### Scenario: disconnect removes only Coffer's entries
- **GIVEN** a connected Claude Code agent whose `.claude.json` also carries another MCP server and whose `settings.json` carries a hook and settings of its own
- **WHEN** the user disconnects it from Coffer
- **THEN** the `coffer` MCP entry is gone, the other MCP server and the agent's own hook and settings are untouched, and the connection reports `disconnected`
- **AND** disconnecting again writes no file and records no audit entry

### Requirement: Plan an import of agents' direct MCP entries
The daemon MUST plan an import of direct MCP entries chosen from the agents' own config files without writing anything — no file, no resource, no secret, no audit event — so the person sees what Import will do before it does it. The plan MUST list one server per distinct server: an entry whose transport matches a server Coffer already has is a duplicate (only the entry is removed, and its agent joins that server's reach when the server is scoped); entries sharing one transport across agents merge into one new server reaching the agents that had it; every other entry becomes a new server reaching its agent, under its name normalised to the rule a new server name follows, with a name that cannot be registered flagged. The plan MUST include, per agent config file that changes, the file's path and unified-diff hunks computed against its current text and the text removing the entries would write, with every shown line's secret values redacted — context lines included — and never the whole file. It MUST express the planned writes in the reconciler's change vocabulary and include any difference the reconciler has pending on Coffer's own entry for the agents involved.

#### Scenario: an import plan merges one server two agents share and writes nothing
- **GIVEN** two agents whose config files each hold a direct entry with the same command, one of them with a token in its environment
- **WHEN** the person plans importing both entries
- **THEN** the plan lists one new server reaching both agents, and a diff of each agent's file removing its entry in which the token's value does not appear
- **AND** both files are byte-identical afterwards, and no resource, secret or audit event was created

#### Scenario: an import plan removes only the duplicate of a server Coffer has
- **GIVEN** a registered server scoped to one agent and another agent whose config holds a direct entry with the same command
- **WHEN** the person plans importing that entry
- **THEN** the plan lists the server as already in Coffer, with that agent to be added to its reach, and adds no server

### Requirement: Apply an import of agents' direct MCP entries
Applying an import MUST perform the plan recomputed from the files as they are at that moment, never an entry a file no longer holds: each new server is adopted from its first entry per "Adopt a direct MCP entry into Coffer" (secret values moved into the secret store under `mcp/<agent>/<entry>/<KEY>` first) and its reach set to the agents that had it; every merged or duplicate entry is removed from its file per "Remove a direct MCP entry from its source file" after its agent joins the server's reach when the server is scoped. Each write is audited as its own route audits it. One entry failing MUST NOT stop the rest, and the answer MUST give every chosen entry its outcome — added, merged, duplicate removed, failed with a readable message, or skipped because it could not be imported — so a partial import can be reported.

#### Scenario: applying an import adds, merges and removes duplicates as planned
- **GIVEN** two agents holding the same direct entry, and one of them also holding the duplicate of a registered server
- **WHEN** the person applies importing all three entries
- **THEN** one new server reaching both agents is registered, the duplicate's agent can reach the registered server, and all three entries are gone from the agents' files
- **AND** each entry reports its outcome

#### Scenario: a partial import reports the entry that could not be imported
- **GIVEN** two chosen entries, one of which was removed from its file after the plan was shown
- **WHEN** the person applies the import
- **THEN** the other entry is imported, the removed one is reported as skipped with the reason, and nothing is written for it

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
- **GIVEN** a registered agent whose program is not found
- **WHEN** the Overview attention list is read
- **THEN** its `agent_program_missing` item carries the reinstall prompt for that agent's type and config directory
- **AND** the item's reason names no command

#### Scenario: carry the install prompt on the type listing
- **GIVEN** Claude Code's program is not found and Codex's is
- **WHEN** the user reads `GET /api/v1/agents/types`
- **THEN** the Claude Code row carries the install prompt as `install_handoff`
- **AND** the Codex row carries `install_handoff` null

### Requirement: List the supported agents as fixed rows on the Agents page
The Agents page MUST list exactly one row per supported agent type — today two, Claude Code and Codex — whether or not each is installed or added, in that order, so the page reads the same on every machine and a first-time user sees at once what Coffer can manage. Each row is found automatically from the detection state of "Detect an agent by its program and its config directory": an `installed_active` type's row reads as its Coffer state ("Show the Coffer connection on the agent pages") with its config directory and version; an `installed_never_run` type reads Not connected too, with its config directory marked as not created, and offers Connect, whose review names the directory it creates and the only entries Coffer needs in it; a `config_only` type reads as config left behind — program not found — and a `missing` type as not installed, each with no Connect and the daemon's prompt that hands reinstalling or installing it to an agent (see "Hand installing an agent's program to an agent") as the split button **Ask an agent ▾** beside its ⋯ menu — Copy prompt behind the chevron, and Copy prompt alone while no other agent can run it. A row whose program is missing shows no version, and its second line says "Not on this Mac" or what is left in the directory. The page MUST NOT show an install command, and carries no Remove action. On first run, with neither agent connected and both connectable, the page MUST offer **Connect both**, which reviews and connects every connectable agent in one confirmation. An agent is named by its type everywhere in the web UI; the page offers no field to name or title one.

Overview's Needs you lists only agents that need the person: an agent that needs repair and one whose config directory is left behind. Not installed, Not connected and a first run raise none.

#### Scenario: the agents page shows both supported agents on first run
- **GIVEN** a fresh Coffer with Claude Code and Codex both installed and neither connected
- **WHEN** the user opens the Agents page
- **THEN** it shows exactly two rows, Claude Code then Codex, each reading Not connected with a Connect action, and a Connect both action, and Overview lists neither as needing the person
- **AND** choosing Connect both reviews the writes for both agents and, on apply, registers and connects both

#### Scenario: an agent that is not installed shows how to install it
- **GIVEN** Codex not installed on the machine
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as not installed and offers the hand-off split button carrying the daemon's prompt that hands installing Codex to an agent, shows no install command, and has no Connect action
- **AND** its ⋯ menu offers neither Copy prompt nor Ask an agent

#### Scenario: an installed agent that has never run can be added
- **GIVEN** Codex's program installed and `~/.codex` not created
- **WHEN** the Agents page renders and the user chooses Connect on the Codex row
- **THEN** the row reads Not connected, with `~/.codex` marked not created
- **AND** the review names `~/.codex` as created and lists only the entries Coffer adds, and nothing is written until the user applies it

#### Scenario: a leftover config directory reads as config left behind
- **GIVEN** `~/.codex` present and the Codex program not on the agent's `PATH`
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as config left behind — program not found — offering the hand-off split button with the daemon's reinstall prompt, no install command, and no Connect action
- **AND** Overview's Needs you lists it

#### Scenario: a row's menu offers a different config directory
- **GIVEN** a Claude Code row on the Agents page
- **WHEN** the user opens the row's menu
- **THEN** it offers Use a different config directory…, and the page carries no Add agent dialog, no Remove action and no name or title field

### Requirement: Show what Coffer manages for an agent in one row
The agent's Skills and MCP servers tabs MUST each hold two parts in the same order: what Coffer manages for the agent first, then what the agent has of its own. There is no owner column, no owner mark on a row, and no filter that switches between the two.

On **Skills** and **MCP servers**, Coffer's part MUST be one **From Coffer** row — how many skills, or servers, Coffer delivers to or serves this agent, their first names, and a link (**Open Skills ›**, **Open MCP servers ›**) to that kind's own page narrowed to this agent (`/skills?agent=<uid>`, `/mcp-servers?agent=<uid>`) — and Coffer's items MUST NOT be listed one by one on the agent's tab. The MCP servers tab carries a second **From Coffer** row for custom-tool groups, which the MCP servers row does not count, linking to `/custom-tools?agent=<uid>` (**Open Custom tools ›**). Those global lists MUST accept the `agent` query parameter and show only what reaches that agent. The agent's own part is a section titled "<Agent>'s own skills" or "<Agent>'s own MCP servers" with a one-line explanation and a search; its items are listed with one state word each — Unmanaged, Invalid SKILL.md, Foreign link, Duplicate, Bypasses Coffer — and at most one button, the fix for that row, with the rest in its ⋯ menu:

- **Skills** — **Adopt** an agent's own skill ([skill-manager](../skill-manager/spec.md) "Adopt an unmanaged skill into the master store"), which opens a form asking for the skill's **name in Coffer** and its **reach** (every agent by default, only chosen agents with at least one ticked, or off), and **Delete duplicate** on a skill folder that has the same name as a skill Coffer delivers to that agent, which deletes the agent's copy behind a confirmation. A row opens the unmanaged skill's own page, with its properties and its files in the shared file tree and viewer.
- **MCP servers** — **Adopt** a direct entry ("Adopt a direct MCP entry into Coffer"), and **Remove duplicate** on a direct entry that `matches_resource` a registered MCP server, which removes it from its source file ("Remove a direct MCP entry from its source file") because Coffer's gateway already serves it; any entry can be taken out of its file from its ⋯ menu. A config file that does not parse is named above the list, and its entries stay read-only.

The **Hooks**, **Memory** and **Plugins** tabs have only the agent's own part: Coffer installs no hook and no plugin, and what memory sync writes into the agent is shown on the Memory page ([memory](../memory/spec.md) "Manage memory sync in the web UI and on the command line"), while the Memory tab lists the agent's native memory stores as they are.

#### Scenario: Coffer's part is one row and the agent's own items follow
- **GIVEN** an agent with one Coffer-managed skill and two of its own skill folders
- **WHEN** the user opens its Skills tab
- **THEN** one From Coffer row reads one skill from Coffer and links to `/skills?agent=<uid>`, and the agent's own section lists the two folders; the Coffer-managed skill is not listed
- **AND** the tab has no owner filter or owner mark

#### Scenario: adopting a skill asks for its name and reach
- **GIVEN** an unmanaged skill folder in the agent's skills directory
- **WHEN** the user chooses Adopt on its row
- **THEN** a form asks for the name in Coffer, prefilled with the skill's own, and the reach, defaulting to every agent
- **AND** confirming adopts it under that name with that reach, and an error stays inside the form

#### Scenario: a duplicate direct MCP entry can be removed
- **GIVEN** an agent whose config file carries a direct MCP entry that matches a registered MCP server
- **WHEN** the user chooses Remove duplicate on that row and confirms
- **THEN** the entry is removed from its source file, and the MCP servers tab counts the server once, as Coffer's

#### Scenario: the global lists narrow to one agent
- **GIVEN** a skill that reaches only Claude Code and another that reaches every agent
- **WHEN** the user opens `/skills?agent=<Codex uid>`
- **THEN** only the skill that reaches every agent is listed

#### Scenario: custom-tool groups have their own From Coffer row
- **GIVEN** an agent reached by one registered MCP server and one custom-tool group
- **WHEN** the user opens its MCP servers tab
- **THEN** the MCP servers row reads one server and links to `/mcp-servers?agent=<uid>`, and a second row reads one custom-tool group and links to `/custom-tools?agent=<uid>`

### Requirement: Act on several of an agent's own items at once
On the agent's Skills, MCP servers and Plugins tabs, the agent's own part MUST let the person tick several items and act on them together; Coffer's part (the From Coffer row) MUST NOT. Each row carries a checkbox and a select-all box heads the list; select-all reaches only the rows the search shows, and a row that cannot be acted on in bulk (an MCP entry of a config file that does not parse) takes no checkbox. While any row is ticked, a selection bar reading "N of M selected" replaces the search row, with the actions — safe ones first, destructive last — and Clear; Escape clears the selection unless a dialog is open.

A bulk action MUST send the same request the single-item action sends, once per item and one after another, MUST NOT stop at the first failure, and MUST refresh the tab's lists once at the end. When every item went through, the person is told once and the selection clears. When some failed, the failures are listed by name with the reason, and Retry sends only them. An action that cannot apply to some of the ticked items MUST say how many it skips.

- **Skills** — **Adopt** acts on unmanaged folders only and opens one confirmation with a reach shared by every adopted skill (every agent by default); each skill keeps its folder name, and a name Coffer already has fails that skill alone. **Delete…** acts on every ticked folder behind one confirmation naming them.
- **MCP servers** — **Adopt** acts on entries that bypass Coffer only, under each entry's own name and with the default secret references; its confirmation says how many secret values move into the secret store. **Remove…** acts on every ticked entry behind one confirmation naming each entry and its file.
- **Plugins** — **Enable** and **Disable** need no confirmation and act on the plugins not yet in that state, saying how many were already; **Uninstall…** asks first and is disabled, with the reason, while the agent's program is not found.

#### Scenario: adopt or delete several of the agent's own skills at once
- **GIVEN** an agent with three unmanaged skill folders and one duplicate of a skill Coffer delivers
- **WHEN** the user ticks all four rows, chooses Adopt and confirms the shared reach
- **THEN** the three unmanaged folders are adopted one after another with that reach, the confirmation says the duplicate is skipped, and one toast reports three adopted
- **AND** a folder whose name Coffer already has is listed as failed with the others adopted, and Retry sends only it
- **AND** choosing Delete… over ticked rows deletes each ticked folder after one confirmation

#### Scenario: adopt or remove several of the agent's own MCP entries at once
- **GIVEN** an agent with two direct MCP entries that bypass Coffer, one of them with a secret-looking env value, and an entry of a config file that does not parse
- **WHEN** the user opens the tab
- **THEN** the unreadable entry has no checkbox
- **AND** ticking both readable entries and choosing Adopt shows a confirmation saying one secret value moves into the secret store, and confirming adopts each under its own name with its default secret reference
- **AND** Remove… removes each ticked entry from its source file after one confirmation naming the entries and their files

#### Scenario: enable, disable or uninstall several plugins at once
- **GIVEN** an agent with three plugins, two on and one off
- **WHEN** the user ticks all three and chooses Disable
- **THEN** the two plugins that are on are switched off without a confirmation and the toast says one was already off
- **AND** Uninstall… asks once for the ticked plugins and is disabled, with the reason, while the agent's program is not found

### Requirement: List an agent's native sessions through the agent
The system MUST expose a read-only listing of an agent's native sessions,
`GET /api/v1/agents/{uid}/sessions`, asked of the agent's own session interface
rather than read from its files; how each type is asked is its child spec's
([agent-registry/claude-code](claude-code/spec.md) "List Claude Code sessions through the Agent SDK",
[agent-registry/codex](codex/spec.md) "List Codex sessions through the app-server"). Each row carries
its `session_id`, a `title` (the title the agent itself shows for the session —
its custom title, else its summary, else its first prompt — secret-scrubbed),
`cwd`, `created_at` and `last_activity_at`. When the session is a channel
conversation's, the row also carries `conversation_id`, `running`, `needs_you` and the
conversation's channel binding, read from the conversation index and the turn
platform's in-memory state, so the Sessions tab and the Conversations page open the
same busy dialog for it ([chat](../chat/spec.md) "Ask before opening a session that is running").
The listing MUST support a case-insensitive substring search `q` over title and
working directory (for Codex, the search the app-server itself offers), and `limit`/`cursor` paging, newest activity first with `session_id` as the
tie-break, alongside the matched `total` ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor"),
because an agent accumulates thousands of sessions and the surface cannot load them all.

The listing carries no session text, Coffer stores none, and nothing is written:
it emits no audit event. Coffer does not distil sessions into memory:
[memory](../memory/spec.md) "Reintroduce no retired memory mechanism" forbids transcript distillation.

#### Scenario: browse an agent's native sessions with title and search
- **GIVEN** a registered agent with several native sessions across more than one project
- **WHEN** the agent's sessions are listed with a search query and a `limit`
- **THEN** each row carries a title, `cwd`, `created_at` and `last_activity_at`; only sessions whose title or working directory matches the search are returned, newest activity first, paged by `limit` and the answer's `next_cursor` alongside the matched total
- **AND** the read emits no audit event and writes nothing

#### Scenario: a channel conversation's session carries its conversation
- **GIVEN** a session that a channel conversation points at, with a turn running on it
- **WHEN** the agent's sessions are listed
- **THEN** its row carries the `conversation_id`, `running` true, `needs_you` and the channel binding, while a session no conversation points at carries none of them

### Requirement: Offer every agent operation over REST and on the Agents page
Every management operation — register/list/view/update/remove, the config-file listing and preview, Coffer connect/disconnect/connection status, MCP entry list/view/remove/adopt, plugin list/detail/toggle/uninstall, the hooks listing, native session listing, rename and delete, and the model catalogue — MUST be available through (a) the REST API, (b) the Agents page in the web UI and (c) the `coffer agent` commands, which call the same routes ([resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"). An agent's config files and native-memory files are its own plain files: their listings are commands, their content is read with the reader's own tools.

- the lifecycle of "Manage the agent lifecycle" under `/api/v1/agents`;
- the config-file listing at `GET /api/v1/agents/{uid}/config-files` and one file's preview at `GET /api/v1/agents/{uid}/config-files/{key}/content`;
- the agent's Coffer connection under `/api/v1/agents/{uid}/coffer-connection` ("Connect an agent to Coffer in one action");
- direct MCP entries under `/api/v1/agents/{uid}/mcp-entries`;
- plugins under `/api/v1/agents/{uid}/plugins`, where `DELETE` is the uninstall of "Uninstall a plugin by the type's own strategy";
- the hooks of "List every hook in the agent's native config" at `GET /api/v1/agents/{uid}/hooks`;
- native sessions at `GET /api/v1/agents/{uid}/sessions` ("List an agent's native sessions through the agent"), renamed with `PATCH` and deleted with `DELETE` at `/api/v1/agents/{uid}/sessions/{session_id}` ("Rename and delete a native session through the agent");
- the model catalogue at `GET /api/v1/agent-providers/{agent_key}/models`.

The listing of an agent's config files, one config file's preview and the reads of its native memory stores' files are served over REST for the web UI, and the Overview's Details names the config directory for anyone who wants the files themselves. The model catalogue's route takes the agent type it is keyed by (`claude_code`, `codex`), not an agent's name, and an unknown type is its not-found.

The Agents page in the web UI MUST expose all of these. It renders within the web-ui shell at `/agents` as the first entry of the sidebar's Agents group ([web-ui](../web-ui/spec.md) "Group the sidebar by what the user comes to do"), never among the Capabilities or Context entries, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file is shown read-only and never edited in the page: selecting it in the tree previews it beside the tree, and the preview's toolbar opens it in the person's editor or reveals it ("Open config files in an external editor or reveal them"). Every place the page shows a file the agent holds read-only — a native memory store, an unmanaged skill's folder — uses the same file tree and the same viewer toolbar, so a file reads the same wherever it is opened.
- The agent detail page's **header** carries the agent's mark, its name, one status pill and a **⋯** menu, and nothing under the name: the version and the config directory are on the Overview. The pill reads Connected, Not connected, Needs repair or Config left behind. The header never turns into a fix button — Connect and Repair sit on the Overview's Connection section. **Rotate proxy token** is in ⋯ only while the agent routes through Coffer's proxy ([provider-switching](../provider-switching/spec.md) "Authenticate each agent to the proxy with its own local token").
- The detail page has eight tabs, none carrying a count: six in the strip — **Overview**, **Skills**, **MCP servers**, **Hooks**, **Config files** and **Sessions** — and, behind a **More** menu, **Plugins** and **Memory**, the least used. Each is addressable by its own path (`/agents/<type>` for Overview, then `/agents/<type>/skills`, `/mcp-servers`, `/hooks`, `/config`, `/sessions`, `/plugins` and `/memory`), so a page opened from a tab returns to it. While the open tab is one of the two in More, the More trigger reads that tab's name and carries the underline; a tab in More that needs attention puts a warning dot on More. There is **no Model tab**: an agent's model is a section of the Overview, and `/agents/<type>/model` is not a page.
  - **Overview** stacks, top to bottom, **Connection**, **What this agent can use**, **Model** and **Details**. Connection says what the connection is in one line, lists the `coffer` MCP entry with where it lives and its health, and carries the one fix the state calls for at its title's right — **Connect** or **Repair** as a solid button — and none while the agent is healthy. What this agent can use is six tiles, three by two — MCP servers, Skills, Config files, Plugins, Hooks and Memory — each with its count, one fact and, when something of the agent's own waits for a look, a warning "N to review"; a tile opens its tab. Model reads **Provider**, **Model** and **Route** (through Coffer's proxy, with **Test**, or direct) and carries **Change…**, which opens the Change model dialog of [provider-switching](../provider-switching/spec.md) "Review a model change before writing it"; opening the page with `?change-model=1` opens that dialog on arrival. Details reads **Version**, **Config directory**, **UID** and **Registered**, with no Title, Name or Type, because an agent's name is fixed to its type.
  - **Skills** and **MCP servers** open with Coffer's part and then the agent's own, per "Show what Coffer manages for an agent in one row". **Plugins** lists the agent's installed plugins — all its own, since Coffer installs none — with a search, an enabled switch and a ⋯ menu whose only item is Uninstall…, and a plugin's name opens an information dialog.
  - **Hooks** lists the agent's own hooks, per "List every hook in the agent's native config". The tab is read only.
  - **Config files** lists every allowlisted config file of "Define a curated config-file allowlist per type" as a file tree beside a read-only preview — the settings files and the human-authored instructions files (`CLAUDE.md`, `AGENTS.md`) alike, because an instructions file is configuration the person wrote, not something installed — each previewed on the right, opened in the editor or revealed ("Open config files in an external editor or reveal them").
  - **Memory** lists **the agent's own memory stores**, read-only; what memory sync writes into the agent is shown on the Memory page ([memory](../memory/spec.md) "Manage memory sync in the web UI and on the command line"). **Sessions** — the agent's own session history, asked of the agent itself — is one list whose rows open in the terminal ("Open an agent's sessions from its Sessions tab").
- A direct server's name on the MCP servers tab opens that entry's read-only JSON in a dialog ("Show one direct MCP entry's full configuration without its secrets"), whose footer carries the row's two writes — remove it from its file (Remove, or Remove duplicate when Coffer already serves it) and adopt it into Coffer — around Close.
- The Memory list carries no per-row actions: a row OPENS its subject, and the open / reveal affordances live on the page it opens, beside the thing they act on. A Memory row opens that store's directory as a file tree with a read-only preview, because a store is a directory.

#### Scenario: desktop app agents page
- **GIVEN** Coffer's web UI is open with a Claude Code agent registered and connected and Codex installed but not yet connected
- **WHEN** the user opens the Agents page
- **THEN** it shows exactly two rows, Claude Code and Codex, the first with its `config_dir` and Connected and no button of its own, and the second reading Not connected with a Connect action

#### Scenario: the Agents page calls the connection routes
- **GIVEN** the daemon exposes the Coffer-connection routes and Claude Code is connected
- **WHEN** the user disconnects the agent from its row's ⋯ menu, then connects it again from the row's Connect, on the Agents page
- **THEN** each action calls the corresponding REST endpoint (`DELETE` then `POST /api/v1/agents/{uid}/coffer-connection`) and produces the same state as calling that endpoint directly
- **AND** the row shows the state `GET /api/v1/agents/{uid}/coffer-connection` reports

#### Scenario: the Agents page calls the lifecycle routes
- **GIVEN** the daemon is running and exposes the REST agent routes, and Codex is found but not registered
- **WHEN** the user connects Codex from its row on the Agents page
- **THEN** each action calls the corresponding REST endpoint (`POST /api/v1/agents`, then the connection route) and produces equivalent state changes

#### Scenario: report the absolute locations of an agent's files
- **GIVEN** a registered agent with config files and a native memory store on disk
- **WHEN** the user reads the agent's config-file listing and native-memory scan over REST
- **THEN** each reports the absolute locations of the files for that agent
- **AND** nothing is written and no audit event is recorded

#### Scenario: list an agent's models
- **GIVEN** the catalogue route offers two `codex` models
- **WHEN** the user reads `GET /api/v1/agent-providers/codex/models`
- **THEN** each model carries its id and its label
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

#### Scenario: the header carries one status pill and a menu
- **GIVEN** an agent that is not connected, one that is connected and one that needs repair
- **WHEN** each agent's page renders
- **THEN** the header shows the agent's name with one pill reading Not connected, Connected or Needs repair, and the ⋯ menu
- **AND** no header carries a Connect or Repair button, because those sit on the Overview's Connection section

#### Scenario: the Sessions tab calls the session routes
- **GIVEN** a registered agent with a native session
- **WHEN** the user renames it from its row's ⋯ menu and then deletes it
- **THEN** each action calls the corresponding REST endpoint (`PATCH` then `DELETE /api/v1/agents/{uid}/sessions/{session_id}`) and produces the same state as calling that endpoint directly

### Requirement: Rename and delete a native session through the agent
The system MUST rename and delete an agent's native sessions only through the
agent's own interface, never by editing its files: `PATCH /api/v1/agents/{uid}/sessions/{session_id}`
takes a `title`, and `DELETE /api/v1/agents/{uid}/sessions/{session_id}` removes the session. Delete is
permanent: the agent keeps no copy and Coffer keeps none. When a conversation of the turn platform points at
the session, rename also sets the conversation's title, and delete also cancels any turn in flight on it and removes
its index row — the same act as [chat](../chat/spec.md) "Rename and delete a conversation through its agent", reached
from the other list. A session id the agent does not list is `not_found` (404). An agent
that refuses the operation has its reason returned and Coffer changes nothing of its own. The
type-specific calls are in the child specs ([agent-registry/claude-code](claude-code/spec.md) "List Claude Code sessions through the Agent SDK",
[agent-registry/codex](codex/spec.md) "List Codex sessions through the app-server"). The agent owns the session, so
neither operation is audited here.

#### Scenario: rename a native session
- **GIVEN** a registered agent with a native session
- **WHEN** its title is changed with `PATCH`
- **THEN** the agent lists the session under the new title
- **AND** a conversation pointing at it shows the new title

#### Scenario: delete a native session permanently
- **GIVEN** a native session that a channel conversation points at, with a turn running on it
- **WHEN** it is deleted with `DELETE`
- **THEN** the agent no longer lists the session, the turn is cancelled and the conversation's index row is gone

#### Scenario: an unknown session is not found
- **GIVEN** a registered agent
- **WHEN** a session id the agent does not list is renamed or deleted
- **THEN** the answer is `not_found` (404) and nothing changes

#### Scenario: a refused operation changes nothing in Coffer
- **GIVEN** an agent that refuses to delete a session
- **WHEN** the user deletes it
- **THEN** the agent's reason is returned and the conversation's index row is still there

### Requirement: Open an agent's sessions from its Sessions tab
The agent detail page's **Sessions** tab MUST list the agent's native sessions
("List an agent's native sessions through the agent") as rows of the same kind the
Conversations page uses ([chat](../chat/spec.md) "Show every agent's sessions on the Conversations page"), without the
channel column unless the session is a channel conversation's: title, working directory and last
activity, with the channel, the Running / Needs you mark and an inline **Stop** when it is. A search
box over title and working directory filters the list in the server, and the list pages by
cursor as it is scrolled. The main part of a row's split button **Open in
<terminal> ▾** MUST open the session in the preferred terminal exactly as
[chat](../chat/spec.md) "Open a conversation in the terminal" says, asking first when the session is
busy ("Ask before opening a session that is running"). An always-shown **⋯** menu holds **Rename** (in
place) and **Delete…**, which asks first and says the session is deleted from the agent and cannot be recovered. A
failure to load the list shows in the list's area with a Retry. The tab shows no session text.
Beside the search box the tab carries **New conversation**, which opens the dialog of
[chat](../chat/spec.md) "Start a new conversation in the terminal" with this agent chosen.
The tab is the Conversations page's list narrowed to this agent: the same header row, rows,
actions and paging, without the Agent column.

#### Scenario: a session row opens in the terminal
- **GIVEN** an agent's Sessions tab listing a session `abc-123` in `/work/api`
- **WHEN** the user presses the row, and then the main part of its split button
- **THEN** pressing the row asks the daemon for nothing, and the button asks it to open the agent's resume command for that session in `/work/api` in the preferred terminal

#### Scenario: a session that is a channel conversation shows its channel
- **GIVEN** a listed session that a SeaTalk conversation points at, with a turn running
- **WHEN** the tab renders
- **THEN** its row shows the SeaTalk badge, Running and an inline Stop, and a session no conversation points at shows none

#### Scenario: the sessions list searches title and directory
- **GIVEN** an agent with sessions titled "Alpha rollout" and "Gamma", the second in `/work/alpha-api`
- **WHEN** the user types "alpha" in the search box
- **THEN** both rows are listed

#### Scenario: deleting a session asks first
- **GIVEN** a listed session
- **WHEN** the user chooses Delete… from its ⋯ menu
- **THEN** a confirmation says it is deleted from the agent and cannot be recovered, and nothing is deleted until the user confirms

#### Scenario: New conversation on the Sessions tab starts this agent
- **GIVEN** Codex's Sessions tab
- **WHEN** the user presses New conversation and confirms the dialog without changing it
- **THEN** the dialog had Codex chosen, and the daemon is asked to start a blank Codex session in the chosen directory

### Requirement: Back up and compare-and-swap every write Coffer makes to an agent's config
Every write Coffer makes into an agent's own config files — connecting, repairing or disconnecting it, installing or removing Coffer's MCP entry, removing or adopting a direct MCP entry, toggling or uninstalling a plugin, projecting a provider, and the reconciler's repairs — MUST be atomic (temp file + rename) and MUST first copy the prior content to a timestamped backup under `~/.coffer/config-backups/` (Coffer's own folder: machine-local, outside the vault, and never beside the agent's file). A writer that read the file before deciding what to write MUST pass the fingerprint of what it read, and the write MUST be refused with `conflict` (409, `CONFIG_FILE_STALE`) when the file changed since, leaving it untouched, so the agent's own rewrite between Coffer's read and write is never lost. Backups are named by their UTC time and cleaned by the `config_backups` retention policy ([resource-framework](../resource-framework/spec.md) "Retain config backups on an adjustable policy"), which always keeps the newest backup of each file. Each writer records its own audit event; there is no write of a config file on the person's behalf, which edits the file in their own editor (see "Open config files in an external editor or reveal them").

#### Scenario: Coffer's own config write leaves its backup in Coffer's folder
- **GIVEN** `~/.claude/settings.json` holds content, and an older write already left a backup of it
- **WHEN** Coffer writes new content to that file twice
- **THEN** each write copied the prior content to its own timestamped file under `~/.coffer/config-backups/`, in a folder named for that one config file, and the newest backup holds the content the last write replaced
- **AND** no `.bak` file, backup or temporary file is left in the agent's own directory, and nothing under `~/.coffer/vault` was written

#### Scenario: Coffer's own config write is refused when the file changed since it was read
- **GIVEN** a config file Coffer read to plan a write, which the agent then rewrites on disk
- **WHEN** Coffer writes with the fingerprint of what it read
- **THEN** the write is refused `409 CONFIG_FILE_STALE` and the file holds the agent's content

### Requirement: Preview an agent's config file read-only
Users MUST be able to read one allowlisted config file of an agent for a read-only preview at `GET /api/v1/agents/{uid}/config-files/{key}/content`, and one file under a directory entry with `?child=<relpath>`, where the relpath MUST be one the listing of "List an agent's config files with their locations" returns for that entry. A key off the allowlist, a directory key without a listed child, and a file key given a child MUST be answered `404` (`CONFIG_FILE_NOT_ALLOWED`) before any read, so the preview can never name a path the listing would not show; a listed file not created yet is `404` (`NOT_FOUND`).

The answer carries the file's absolute path, format, size and its text as written, read up to 1 MiB (`truncated` past it; `binary` with no text for a file that is not UTF-8 or holds a NUL byte). The text is the file's own, values included: the file is the person's, on their own machine, and the loopback daemon shows it to them as their editor would. A preview writes nothing, records no audit event and carries no fingerprint: a config file is edited in the person's own editor.

#### Scenario: preview a config file as written
- **GIVEN** a registered Claude Code agent whose `settings.json` holds a theme and an `env` map with `ANTHROPIC_AUTH_TOKEN`
- **WHEN** the user reads the preview of the `settings` key
- **THEN** the answer carries the file's absolute path, its size and its text exactly as on disk
- **AND** the file on disk is byte-identical and no audit event is recorded

#### Scenario: preview a file under a directory entry only when the listing names it
- **GIVEN** a Claude Code agent whose `agents/` directory holds `reviewer.md`
- **WHEN** the user reads the `subagents` preview with the child `reviewer.md`, then with the child `../settings.json`, then with no child
- **THEN** the first answers the file's text
- **AND** the second and third are answered `404` and nothing outside the listed files is read

#### Scenario: answer a config file not created yet as not found
- **GIVEN** a Claude Code agent with no `CLAUDE.md`
- **WHEN** the user reads the preview of the `instructions` key
- **THEN** the answer is `404` and no file is created

### Requirement: List every agent's sessions in one list
The system MUST expose `GET /api/v1/agent-sessions`, one listing of the native sessions of
every managed agent, each asked of the agent exactly as "List an agent's native sessions
through the agent" says and merged newest activity first, with agent key and `session_id`
as the tie-breaks. Each row carries what that listing's row carries plus the agent's key.
It MUST page by one opaque cursor over all the agents ([resource-framework](../resource-framework/spec.md)
"Page growing lists by an opaque cursor") and carry no `total`, because an agent may not
count its sessions. It MUST narrow, in the server, by `agent` (a comma-separated set of agent
keys: only those agents are asked), by `source` (a comma-separated set of `local` — a session
no channel conversation points at — and channel uids — a session that channel's conversation
points at) and by `q`, passed to each agent's own search; a cursor MUST be bound to the
filters it was issued for. When `source` names channels only, the rows are those channels'
conversations from the conversation index, so a conversation on which no turn has run is
listed, without a session. An agent whose listing fails MUST be left out of the page and
named under `unavailable` with its reason, while the other agents are listed. The read
carries no session text and is not audited.
The daemon MUST keep each agent's last answer for a given position and search in memory —
never on disk, never synced — and answer from it: within 5 seconds of the read without
asking the agent, and up to 5 minutes later at once while one refresh of that answer runs in
the background; an older answer is read again before replying. Concurrent reads of the same
answer share one request to the agent, and renaming or deleting a session through the agent
drops that agent's kept answers. An agent is asked in pages of a fixed size whatever the
page's `limit`, so the following pages of one listing reuse the answers the first read kept.
Asking an agent is the expensive part of the read (Codex answers `thread/list` in about a
second whatever the size of the page), so the page is shown at once and a session started
elsewhere appears within one refresh.

#### Scenario: sessions from two agents are listed in one order
- **GIVEN** Claude Code with sessions last active at 10:00 and 08:00, and Codex with one last active at 09:00
- **WHEN** `GET /api/v1/agent-sessions` is read with `limit=2` and then with the answer's `next_cursor`
- **THEN** the first page holds the 10:00 Claude Code and 09:00 Codex sessions, each with its agent key, and the second the 08:00 one with a `null` `next_cursor`
- **AND** neither answer carries a `total`

#### Scenario: the listing narrows by source and agent
- **GIVEN** a Claude Code session started in a terminal and one a SeaTalk conversation points at, and a Codex session
- **WHEN** the listing is read with `source=local`, then with `source=<SeaTalk uid>`, then with `agent=codex`
- **THEN** the first lists the terminal session and the Codex one, the second only the SeaTalk one with its channel binding, and the third only Codex's
- **AND** a cursor issued for one set of filters is `CURSOR_INVALID` for another

#### Scenario: a channel conversation with no session yet is listed under its channel
- **GIVEN** a SeaTalk conversation on which no turn has run
- **WHEN** the listing is read with `source=<SeaTalk uid>`
- **THEN** it is listed with its title and channel binding and a null `session_id`

#### Scenario: one agent failing leaves the others listed
- **GIVEN** Claude Code with sessions and a Codex whose listing fails
- **WHEN** the listing is read
- **THEN** Claude Code's sessions are listed and `unavailable` names Codex with the reason

#### Scenario: a repeated read is answered without asking the agent again
- **GIVEN** the listing was read a moment ago
- **WHEN** it is read again, and then its next page is read
- **THEN** both are answered from the kept answers and the agents are not asked again
- **AND** after a session is renamed through its agent, the next read asks that agent again

### Requirement: List every hook in the agent's native config
The system MUST list, read only, every command hook the agent will run. That covers the hooks in the agent's own hook-carrying files (the type's child spec names them) and those in each enabled plugin's hook file. Each is listed with its event, matcher, command, timeout, source (`user` or `plugin`, with the plugin's id) and the file that declares it. Project-level settings are not read, because Coffer does not know which repositories the agent is used in.

The listing MUST be served by `GET /api/v1/agents/{uid}/hooks` as the hooks (`items`) and the files that did not parse (`parse_errors`), and MUST write nothing and record no audit event. A file that does not parse MUST be reported as a parse error beside the hooks the other files yield. Coffer installs no hook into an agent, so no hook is marked as Coffer's and the listing carries no health, trust or last fire.

Each listed hook MUST also carry where it sits in its file — `group_index` and `hook_index`, the positions in `hooks.<event>[group_index].hooks[hook_index]` — so a person can find the entry, and the REST listing reports them.

On the agent's Hooks tab the agent's hooks are one table of Event, Command, Matcher and File, with a search over the command and an **Event** filter that lists each event with its count; the table says how many of how many are shown once either narrows it. A file that does not parse is named above the table. A row opens a read-only details dialog with the command in full, the event and when it runs, the matcher, the type, the timeout, the file and the entry's position in it (`hooks.<event>[group].hooks[hook]`), with **Copy command** and **Open in editor**; nothing in the dialog writes, because a hook is changed in its own file, in the person's own editor. A file name opens that file in the preferred editor (see "Open config files in an external editor or reveal them").

#### Scenario: list an agent's hooks
- **GIVEN** a registered Claude Code agent whose `settings.json` carries a `PreToolUse` hook, whose `settings.local.json` carries a `Stop` hook, and which has one enabled and one disabled plugin with a hook file each
- **WHEN** the user lists the agent's hooks
- **THEN** the `PreToolUse` hook, the `Stop` hook and the enabled plugin's hook are listed with their sources and files, and the disabled plugin's hook is not
- **AND** nothing is written or audited

#### Scenario: list the hooks with their position in the file
- **GIVEN** a Claude Code `settings.json` whose `PreToolUse` event holds two groups, the second with two hooks
- **WHEN** the user lists the agent's hooks
- **THEN** the second hook of the second group reports `group_index` 1 and `hook_index` 1, and the first group's hook reports 0 and 0

#### Scenario: the Hooks tab lists the agent's own hooks
- **GIVEN** a Claude Code agent whose settings files and an enabled plugin carry hooks of its own
- **WHEN** the user opens the agent's Hooks tab
- **THEN** the tab is one table with a row per hook, with no block for a hook of Coffer's
- **AND** choosing a row opens a read-only dialog with the command, event, matcher, type, timeout, file and position, and searching or filtering by event narrows the table and says how many of how many show

### Requirement: Report an agent's Coffer connection part by part
The system MUST report an agent's Coffer connection (`GET /api/v1/agents/{uid}/coffer-connection`) as the list of parts its type has — today the one `mcp` part — each with its key, whether it is installed, and the installed command when it is — and a state: `connected` when every listed part is installed, `disconnected` when none is, and `partial` otherwise, which a type with one part never reports. The report MUST be read from the agent's own configuration files on demand, never stored, and MUST write nothing and record no audit event.

#### Scenario: read an agent's connection without writing anything
- **GIVEN** a registered agent without the gateway entry
- **WHEN** the user reads its Coffer connection, connects it, and reads it again
- **THEN** the first read reports `disconnected` with the `mcp` part not installed, and the second `connected` with the `mcp` part installed and its shim command
- **AND** neither read writes a file or records an audit event
