# Agent Registry

## Purpose
The agent registry decides which locally-installed AI coding agents Coffer knows about, so that later features — skills, memory, knowledge, channels, chat — can deliver assets to them. Each agent is a Resource of kind `agent` in the kind-agnostic Resource framework. The supported products are **Claude Code** (`claude_code`) and **OpenAI Codex** (`codex`); each spans its CLI and its app/IDE form, because both forms read one shared config directory, so Coffer manages one config set per agent. The separate **Claude Desktop** chat app (its own `~/Library/Application Support/Claude/` config) and web-only agents such as claude.ai are not agents here. The registry holds only **managed** agents — external coding agents Coffer delivers to; the former built-in "Coffer Assistant" is not a registered agent ([Coffer's Model Is an Internal Engine](../../../docs/decisions/coffer-model-is-an-internal-engine.md)).

This spec holds what the two types share. Everything that differs by type — where the config directory is, which files are allowlisted, the MCP entry shape, the plugin inventory, the model catalogue's sources, the native-memory layout, the transcript location — lives in a child spec: [`agent-registry/claude-code`](claude-code/spec.md) and [`agent-registry/codex`](codex/spec.md), each the reading of one `AGENT_DESCRIPTORS` record, the single per-type table in the code. Adding a product is one enum value, one descriptor record and one child spec.

Beyond registering agents, the user views and edits each agent's known config files (or opens them in an external editor), installs Coffer's own MCP server into an agent with one click, and sees which models that agent can be put on. The registry also reaches into the agent's real on-disk workspace — the MCP servers configured in its own files, its installed plugins, directory-type config entries, its own native memory and its session transcripts — following **ingest → hub → deliver**: anything shareable found in an agent's workspace can be adopted into Coffer's hub (the MCP gateway; the master skill store of skill-manager) and delivered back to any agent, instead of living as per-agent one-off config. All writes go through each agent's documented configuration paths only; the agents' internal state files are read as inputs where needed and never written. Config files are surfaced as raw text with a validate + atomic-write + `.bak` safety net on every save; open-in-external-editor stays alongside as the escape hatch for the long tail, and recurring structured needs graduate into facets.

The user runs Coffer on their own machine; there is no multi-tenant or remote-access requirement. The registry relies on the Resource framework, audit log and immutable-`uid` identity of resource-framework, and renders inside the web-ui application shell. A `coffer-hook` binary with a session-context rules route and a `disable_native_memory` switch once lived here and was removed because it was never installed; session-start delivery is now memory's own, marker-scoped install, which this registry only supports by supplying the agent record, its config directory, its allowlisted settings file and the atomic-write machinery.

An agent's connection status carries no `memory_hook` part while the `memory` feature is switched off, and the provider projection into the agent's config is withdrawn while `models` is off (spec [experimental-features](../experimental-features/spec.md) "Close the memory feature's surfaces", "Close the models feature's surfaces").

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
Each supported agent type MUST define a curated allowlist of config files in its capability-manifest record, enumerated by that type's child spec, each entry carrying a stable `key`, a display name, a resolved absolute path, and a `format` (`json`, `toml` or `markdown`). Each type's human-authored instructions file carries the key `instructions` — those files are instructions a person wrote, distinct from agent-written memory (memory's domain). Config files are not persisted in SQLite — the file on disk is the source of truth.

#### Scenario: key each type's instructions file as instructions
- **GIVEN** the capability manifest for every supported agent type
- **WHEN** the type's config-file allowlist is read
- **THEN** every entry carries a key, a display name, an absolute path and a format among `json`, `toml` and `markdown`
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

### Requirement: Address config files only by allowlisted key
Config-file read and write MUST be addressable only by allowlisted `key` (never by caller-supplied path); an unknown key returns `not_found` (404) and performs no filesystem access.

#### Scenario: reject config-file key outside the allowlist
- **GIVEN** a registered agent
- **WHEN** the user references a config-file key not in that agent type's curated allowlist
- **THEN** Coffer responds `not_found` (404) and performs no filesystem read

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
Install and uninstall MUST reuse the atomic-write + `.bak` machinery of "Write config files atomically with a backup and an audit entry" and record an audit entry (`agent_mcp_installed` / `agent_mcp_uninstalled`).

#### Scenario: uninstall Coffer's MCP from an agent
- **GIVEN** an agent that has Coffer's MCP installed
- **WHEN** the user uninstalls it
- **THEN** the `coffer` entry is removed from the agent's MCP config, the file is backed up to `.bak`, an `agent_mcp_uninstalled` audit entry is recorded, and status reports `installed=false`

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
Users MUST be able to remove a direct MCP entry — from the agent's page or the REST route (`DELETE /api/v1/agents/{uid}/mcp-entries/{entry}`). Removal edits only the entry's source file, reuses the atomic-write + `.bak` machinery of "Write config files atomically with a backup and an audit entry", and records an `agent_mcp_entry_removed` audit entry. The `coffer` entry is not removable through this operation — it is managed by "Install Coffer's MCP server into an agent in one action" and "Uninstall Coffer's MCP server from an agent".

#### Scenario: remove a direct MCP entry
- **GIVEN** a registered agent with a direct (non-Coffer) MCP entry
- **WHEN** the user removes that entry (carrying the source file where the type's entries may come from more than one)
- **THEN** the entry is deleted from exactly its source file via an atomic write with a `.bak` of the prior content, an `agent_mcp_entry_removed` audit entry is recorded, and the next listing no longer shows it

#### Scenario: remove a direct MCP entry over REST and refuse the coffer entry
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
A config-file allowlist entry MAY be a **directory entry** (`kind=directory`): it resolves to a directory and lists its files (entry-relative path, size, modified time) instead of carrying content. A missing directory MUST list as `exists=false` with no files, and the read MUST NOT create it. Which allowlist entries are directory entries is per type, and each child spec names its own. The directory on disk is the source of truth.

#### Scenario: list a directory config entry's files
- **GIVEN** a registered agent whose directory config entry contains Markdown files (possibly nested)
- **WHEN** the user lists that config entry
- **THEN** Coffer returns the entry with `kind=directory` and its files (entry-relative path, size, modified time); a missing directory lists as `exists=false` with no files and is not created by the read

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

#### Scenario: write a config file over REST
- **GIVEN** a registered agent with an existing `json` config file under the allowlisted key `<key>`, and well-formed JSON content to write
- **WHEN** the user writes that content with `PUT /api/v1/agents/{uid}/config-files/<key>`
- **THEN** the config file holds the written content, a `.bak` holds the prior content, and an `agent_config_file_written` audit entry is recorded
- **AND** the same request with malformed JSON is refused with `unprocessable_entity` (422) and leaves the config file unchanged

### Requirement: Carry the model binding on the agent record
The agent record MUST carry the model binding the rest of Coffer reads — `model`, `effort`, `tier_models` (Claude Code only: the model for each of `opus`, `sonnet`, `haiku` and `fable`) — because the model is chosen at the point of USE and an agent is where it is used, not on the connection that serves it. That binding MUST be settable over REST as well as in the web UI: `PATCH /api/v1/agents/{uid}` carries `model` / `effort` / `tier_models`, with an explicit null to unbind `effort` or `tier_models`. A field the request omits is unchanged; `tier_models`, when sent, replaces the whole mapping. Only `effort` and `tier_models` clear on an explicit null; `model` has no null that unbinds it, so an explicit null for it is treated as omitted. A tier other than the four is refused. The binding carries no `fast_model`: Claude Code's background model is its Haiku tier. Projecting a binding into the agent's native config is provider-switching's.

#### Scenario: bind a model to an agent over REST
- **GIVEN** a registered agent
- **WHEN** the user sends `PATCH /api/v1/agents/{uid}` with a `model`, `effort` `high` and `tier_models` `{"haiku": "<model>"}`, then again with `tier_models` null
- **THEN** the agent record reports the bound `model`, `effort` and `tier_models` after the first edit, and carries no `fast_model`
- **AND** after the second edit `tier_models` is null while `model` and `effort` are unchanged

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
The system MUST expose a read-only listing of an agent's local transcript sessions, found at the location that type's child spec names. Each session summary carries its `session_id`, a derived `title` (the session's first *real* user turn, secret-scrubbed — a turn whose text is nothing but an injected markup block was written by the harness, not by a person, and is not a candidate), `project_path`, `message_count`, `started_at`, `last_activity_at`, and the transcript file's absolute `source_path` — the last feeding the open / reveal affordances of "Open config files in an external editor or reveal them". The listing MUST support a case-insensitive substring search over title and project path, an exact `project` filter, sorting by `started_at`, `last_activity_at` (default) or `message_count` in either direction with `session_id` as the tie-break, and `limit`/`cursor` paging alongside the matched `total` ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor"), because an agent accumulates thousands of sessions — and keeps writing new ones while a reader pages — and the surface cannot load them all. Parsing is per-file and cached by the file's modification time **and size**; a file that fails to parse is skipped rather than failing the listing. Message text is not carried on the wire by THIS listing and is not retained by it — a body travels only through "Read one transcript session in bounded windows", for the one session a reader opened.

Coffer never writes the transcript files, never stores their content and never sends them anywhere. It does not distil transcripts into memory: the agent's own memory is memory's domain, and [memory](../memory/spec.md) "Reintroduce no retired mechanism" forbids reintroducing a path that writes back into it.

#### Scenario: browse an agent's transcript history with title, search, and sort
- **GIVEN** a registered agent with several local transcript sessions across more than one project
- **WHEN** the agent's transcripts are listed with a search query, a project filter, and a sort key (`started_at`, `last_activity_at` or `message_count`)
- **THEN** each returned session summary carries a derived title, message count, `started_at`, `last_activity_at`, and the session file's absolute source path; only sessions whose title or project path matches the search and whose project matches the filter are returned, ordered by the requested sort key and direction, and paged by `limit` and the answer's `next_cursor` alongside the matched total — read-only, emitting no audit event and writing nothing

#### Scenario: a new transcript session does not shift the next page
- **GIVEN** an agent's transcript sessions read with `limit=2`, sorted by `last_activity_at`
- **WHEN** a new session is written and the next page is read with the first answer's `next_cursor`
- **THEN** the second page holds the sessions that followed the first page's last one, none of the first page's sessions and not the new one

### Requirement: Keep the transcript summary sidecar disposable
The listing MAY keep a **disposable derived sidecar** of those summaries so a cold parse is not repeated on every daemon restart — an agent's transcripts run to thousands of files and gigabytes, and re-deriving them is seconds of blocking I/O. The sidecar holds no message text, lives **in the derived class, outside the vault and every database** — under `~/.coffer/derived/cache/agent/` — at one path the user may delete at any moment, and no export or backup carries it. It MUST never change an answer, only the time to reach one: a summary is served from it only while its file's modification time and size still match, and with the sidecar missing, empty, corrupt or mid-write the listing MUST still be correct — merely slower. The system MAY warm it in the background, off the request path, so the first visit after an install is not the one that pays. Everything the listing returns is still derived from the agent's own files on disk: nothing about a session is a stored truth. Like the other workspace listings, neither the listing nor the warm pass emits an audit event.

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
The system MUST expose a read-only **native-memory store read** that returns one store's directory as a file tree (each entry's name, store-relative path, type and size) and one file inside it as text (its contents, its absolute path for the open / reveal affordances, and whether it was truncated or is binary). A store is addressed by the `memory_dir` the native-memory scan handed out, which MUST be exactly a directory that type's layout would have listed — and not merely some path under the agent's config dir, which also holds its transcripts, settings and plugin cache. A directory that is not one of the agent's stores, a file path escaping the store, and a file that does not exist are all `not_found` (404); whether a directory is one of the agent's stores is decided by its shape alone, so the answer cannot be used to probe the filesystem. A store that has that shape but no longer exists on disk reads as an empty tree (200), not a 404. Reads are capped in size and the walk is depth-bounded, with both facts reported rather than silently applied. Read-only: Coffer never writes an agent's own memory, so the surface previews and offers open / reveal instead of an editor, and emits no audit event.

#### Scenario: browse one native memory store's files
- **GIVEN** a registered agent with a native memory store listed by "Scan an agent's own native memory stores read-only", holding Markdown files in the store directory and a subdirectory
- **WHEN** the user opens that store by the `memory_dir` the listing gave and then reads one file in it
- **THEN** Coffer returns the store directory as a tree (directories before files, paths relative to the store) and the file's contents with the absolute path that backs open / reveal, while a directory that is not one of this agent's stores — its sibling project directory included — and a path escaping the store are both rejected as `not_found` (404); read-only, emitting no audit event and writing nothing

### Requirement: Expose every agent operation through REST and the Agents page
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

#### Scenario: the Agents page calls the connection routes
- **GIVEN** the daemon exposes the Coffer-connection routes and Claude Code is connected
- **WHEN** the user disconnects the agent from its row's ⋯ menu, then connects it again from the row's Connect, on the Agents page
- **THEN** each action calls the corresponding REST endpoint (`DELETE` then `POST /api/v1/agents/{uid}/coffer-connection`) and produces the same state as calling that endpoint directly
- **AND** the row shows the state `GET /api/v1/agents/{uid}/coffer-connection` reports

#### Scenario: the Agents page calls the lifecycle routes
- **GIVEN** the daemon is running and exposes the REST agent routes, and Codex is found but not registered
- **WHEN** the user connects Codex from its row, then switches it off and on again from the row, on the Agents page
- **THEN** each action calls the corresponding REST endpoint (`POST /api/v1/agents`, the connection route, then the kind-agnostic disable and enable routes) and produces equivalent state changes

#### Scenario: report the absolute locations of an agent's files
- **GIVEN** a registered agent with config files, a native memory store and transcript sessions on disk
- **WHEN** the user reads the agent's config-file listing, native-memory scan and transcript listing over REST
- **THEN** each reports the absolute locations of the files for that agent
- **AND** nothing is written and no audit event is recorded

#### Scenario: read one transcript session over REST
- **GIVEN** a registered agent with a transcript session listed by `GET /api/v1/agents/{uid}/transcripts`
- **WHEN** the user reads `GET /api/v1/agents/{uid}/transcripts/session` with that session's `source_path`
- **THEN** the response carries a window of that session's turns with the pasted secrets redacted and the whole session's turn count
- **AND** a path the agent has no session for is `not_found` (404)

#### Scenario: list an agent's models with their efforts
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

### Requirement: Lead a transcript turn with the person's own words
**Readable means the person's words lead.** A "user turn" in a transcript is not only what the user typed: every harness prepends its own blocks to the same turn — reminders, task notifications, environment dumps. The conversation MUST read the turn as the person's, not the harness's: it MUST lead with their words, with the prepended blocks folded away rather than dropped — the blocks are part of the record and a view that discarded them would be claiming the turn said less than it did. A turn made only of harness blocks MUST still render, as what it is. Blocks are identified by SHAPE, not by a list of block names: naming them one at a time never finishes, and prose that merely contains a `<` is not markup.

#### Scenario: lead a turn with the person's words, not the harness's blocks
- **GIVEN** an opened conversation whose user turns include one led by a harness reminder block before the person's question, and one made only of harness blocks
- **WHEN** the conversation renders
- **THEN** the first turn leads with the person's question and the reminder block is folded behind it, not dropped
- **AND** the turn made only of harness blocks renders as harness text, with no empty bubble of the person's

### Requirement: Open config files in an external editor or reveal them
For each config file (and each directory-entry child) the UI MUST offer **open-in-external-editor** and **reveal-in-file-manager** actions on the file, using the `path` from "List an agent's config files with their locations" and "Read allowlisted config files without creating them". Open and reveal perform the real OS action through the daemon's filesystem-action endpoints (`POST /api/v1/fs/open`, `POST /api/v1/fs/reveal`, and the installed-editor enumeration `GET /api/v1/fs/editors` behind the preference — all owned by the daemon spec, which this spec consumes and does not specify), since the loopback daemon is always on the user's own machine ([Daemon Proxies OS File Actions](../../../docs/decisions/daemon-proxies-os-file-actions.md)). There is no copy-path fallback. The editor used for open-in-external-editor references the user's "preferred external editor" preference defined by web-ui (not re-specified here).

#### Scenario: open a config file and reveal it through the daemon
- **GIVEN** an agent's Config files tab with an existing config file selected
- **WHEN** the user chooses open-in-external-editor and then reveal-in-file-manager on it
- **THEN** the UI asks the daemon to open that file's absolute path and then to reveal it
- **AND** no copy-path affordance is offered

### Requirement: Audit every agent lifecycle event
The system MUST record an audit entry, carrying timestamp, actor and the affected agent reference, for every lifecycle event: agent created, updated, removed (via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events); agent enabled/disabled (via the kind-agnostic `resource_enabled` / `resource_disabled` events); config file written/deleted (`agent_config_file_written` / `agent_config_file_deleted`); Coffer MCP installed/uninstalled; MCP entry removed/adopted (`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`); plugin toggled/uninstalled (`agent_plugin_toggled` / `agent_plugin_uninstalled`). Discovery and all workspace listings — MCP entries, plugins, config files, native memory stores, transcript sessions, the model catalogue, the Coffer connection status — are read-only and emit no audit event, the background pass that warms the transcript summary cache included. Reading ONE of the listed items — a single session's turns, a single store's files — is the same act at a smaller scale and audits nothing either. A connect or disconnect records the events of the parts it installs or removes and none of its own; the memory delivery hook's events are memory's, not this spec's.

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

### Requirement: Switch an agent off with the kind-agnostic enabled flag
An agent MUST carry the kind-agnostic `enabled` flag, toggled through the generic `POST /api/v1/resources/{uid}/enable|disable` routes, and audited as `resource_enabled` / `resource_disabled`. A disabled agent is one Coffer does not write into and does not read from: its delivered skills are reclaimed and nothing new is delivered to it ([skill-manager](../skill-manager/spec.md)), its native memory is not aggregated ([memory](../memory/spec.md)), and its native config does not feed the model catalogue of "Serve each agent type's model catalogue from its one agent" — the catalogue is read as if no agent of that type were registered. Enabling it again puts back whatever the skills' own state grants, so the switch is never a one-way door. The one exception is adoption ([skill-manager](../skill-manager/spec.md) "Adopt an unmanaged skill"): adopting a folder from a disabled agent's skills directory links it in place and records an enabled binding for that agent, the agent's next reconcile reclaims that link and disables the binding, and enabling the agent delivers the skill back whenever the skill's own `enabled` flag and scope grant it. The agent's own routes neither carry nor change the flag: `AgentOut` does not report it and `PATCH /api/v1/agents/{uid}` does not set it.

#### Scenario: disabling an agent reclaims its skills and drops it from the catalogue
- **GIVEN** a registered agent holding a delivered skill, whose config dir the model catalogue reads for its type
- **WHEN** the agent is disabled through the kind-agnostic enabled flag
- **THEN** the delivered skill's link is gone from the agent's skills directory and no binding remains enabled for it
- **AND** the catalogue for that type no longer reads the agent's config dir
- **AND** a `resource_disabled` audit entry names the agent

#### Scenario: switch an agent off and on over REST
- **GIVEN** a registered, enabled agent named `codex`
- **WHEN** the user posts to `/api/v1/resources/{uid}/disable`, then to `/api/v1/resources/{uid}/enable`
- **THEN** the agent's kind-agnostic `enabled` flag is false after the first and true after the second
- **AND** a `resource_disabled` and then a `resource_enabled` audit entry name the agent

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
An agent has one off state, **Not connected**, and one word per other state: **Connected**, **Needs repair** (the `partial` state), **Hook not approved** (on the agent's own page: Codex has not approved, or approved an earlier command of, Coffer's memory hook), **Off** (switched off), **Config left behind** and, for an added agent whose program and directory are both gone, **Not found**. A newly found agent that was never added and an agent that was disconnected are the same state, so both read Not connected and both offer **Connect**; the list has no "Not added" or "Detected" word and no Add action. Each row of the Agents list MUST show the agent's state and the one action that state calls for: **Connect** for one not connected — which, for a newly found agent, registers it under its default config directory first — **Repair** for one that needs repair, **Turn on** for one that is off, and none for one that is connected, whose ⋯ menu carries **Disconnect**. An agent whose program is not on this machine has no button: its ⋯ menu leads with the daemon's install prompt. The same states offer the same actions on the agent's own page, in the Overview's Connection section (**Connect**, **Repair** and **Turn on** as solid buttons, **Check again** as an outline one while Codex has not approved Coffer's hook), never in the page header. The ⋯ menu, on the row and on the page, holds **Use a different config directory…**, **Reveal config directory**, **Copy uid**, **Disconnect** while a part is installed, and **Turn off** while the agent is on, in that order after the install prompt where there is one, and never repeats the visible button.

Connect, Repair and Disconnect MUST each open **Review changes** first — every file it will write and the lines it adds or removes, the connection test as the daemon reports it — and write nothing until the user applies it; **Use a different config directory…** on a connected agent moves Coffer's entry and hook to the new directory through the same review, and on an agent not yet added it registers the directory without connecting. The list has two rows, so it carries no row selection and no bulk bar. Which parts a connection installs MUST be explained behind a help affordance beside the action rather than as inline text. The Memory tab MUST NOT carry a separate install or remove action for the memory delivery hook beyond the Repair of "Show what Coffer manages for an agent in one row".

#### Scenario: the Overview offers the action the state calls for
- **GIVEN** an agent's page for an agent that is not connected, one that is connected, one whose connection is partial and one that is off
- **WHEN** each Overview's Connection section renders
- **THEN** the unconnected agent offers Connect, the connected one offers no button and has Disconnect in its ⋯ menu, the partial one reads Needs repair and offers Repair, and the one that is off offers Turn on
- **AND** the agent's Memory tab offers no action on the delivery hook while it is healthy

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

### Requirement: List every hook in the agent's native config
The system MUST list, read only, every command hook the agent will run. That covers the hooks in the agent's own hook-carrying files (the type's child spec names them) and those in each enabled plugin's hook file. Each is listed with its event, matcher, command, timeout, source (`user` or `plugin`, with the plugin's id) and the file that declares it. Project-level settings are not read, because Coffer does not know which repositories the agent is used in.

Coffer's own memory hook — its two entries, on `SessionStart` and `UserPromptSubmit` ([memory](../memory/spec.md) "Install delivery hooks explicitly and removably") — MUST be marked, each entry as Coffer's, and reported as one hook with the set of events its entries sit on. Its health MUST be reported by the same marker-and-command comparison the boot repair uses:
- `current` when the entries sit on exactly the events Coffer would install on and each carries exactly the command Coffer would write now;
- `stale` when Coffer's marker carries another command or sits on another set of events;
- `missing` when it is absent.

The report MUST also say whether the agent will run the hook, as its **trust**: `trusted`, `untrusted`, `modified` (approved for an earlier command), `disabled`, `unknown` (the agent's approval record does not parse), or `not_required` for an agent that runs every hook it finds. It MUST also give the last recorded fire from the audit log.

The listing MUST be served by `GET /api/v1/agents/{uid}/hooks`, and MUST write nothing and record no audit event. When the agent will not run a current hook, the trust reports why, and the Hooks tab and the attention list say what the user does about it. A file that does not parse MUST be reported as a parse error beside the hooks the other files yield.

Each listed hook MUST also carry where it sits in its file — `group_index` and `hook_index`, the positions in `hooks.<event>[group_index].hooks[hook_index]` — so a person can find the entry, and the REST listing reports them.

On the agent's Hooks tab the listing is two parts, Coffer's first. **Coffer's memory hook** is one block of properties, never one row per entry: its state (and how long ago it fired), its command, the events it sits on and the file that declares it, with its one fix at the block's title — **Repair** when it is stale or missing, **Check again** while the agent has not approved it — and, when it has never fired, the likely cause and a link to Activity. The reason a state is a problem is written in the block's own line. **The agent's own hooks** — Coffer's excluded — are one table of Event, Command, Matcher and File, with a search over the command and an **Event** filter that lists each event with its count; the table says how many of how many are shown once either narrows it. A row opens a read-only details dialog with the command in full, the event and when it runs, the matcher, the type, the timeout, the file and the entry's position in it (`hooks.<event>[group].hooks[hook]`), with **Copy command** and **Open in Config files**; nothing in the dialog writes, because a hook is changed in its own file. A file name opens that file in Config files, except a plugin's hooks file, which has no Config files entry.

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
`GET /api/v1/agent-providers/{agent_key}/models` MUST answer, per agent type, which models a picker offers for that agent: the agent's own catalogue, read back from the installed agent and never written down in Coffer, unless the connection the agent runs on curates a set of ids — then those ids, as [provider-switching](../provider-switching/spec.md) "Serve one model list to every surface" defines. Each entry MUST carry `id` (passed to the agent verbatim), `label`, `description`, the reasoning `efforts` its runtime reports and the `default_effort` it would use, keeping a reported default only when it is one of the offered levels. An unknown `agent_key` MUST be a 404. The catalogue reads the native config of the type's one agent ("Keep one agent per type, named by it") while it is enabled, which is also the agent a chat turn on that type runs against ([chat](../chat/spec.md) "Ship Claude Code and Codex subprocess providers on the type's one agent").

#### Scenario: list the models an agent can be put on
- **GIVEN** a registered `codex` agent whose own config names a model
- **WHEN** the user requests `GET /api/v1/agent-providers/codex/models`
- **THEN** the response lists that model with `id`, `label`, `description`, `efforts` and `default_effort`
- **AND** the same request for an unknown agent key answers 404

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
- **GIVEN** an enabled registered agent whose program is not found
- **WHEN** the Overview attention list is read
- **THEN** its `agent_program_missing` item carries the reinstall prompt for that agent's type and config directory
- **AND** the item's reason names no command

#### Scenario: carry the install prompt on the type listing
- **GIVEN** Claude Code's program is not found and Codex's is
- **WHEN** the user reads `GET /api/v1/agents/types`
- **THEN** the Claude Code row carries the install prompt as `install_handoff`
- **AND** the Codex row carries `install_handoff` null

### Requirement: List the supported agents as fixed rows on the Agents page
The Agents page MUST list exactly one row per supported agent type — today two, Claude Code and Codex — whether or not each is installed or added, in that order, so the page reads the same on every machine and a first-time user sees at once what Coffer can manage. Each row is found automatically from the detection state of "Detect an agent by its program and its config directory": an `installed_active` type's row reads as its Coffer state ("Show the Coffer connection on the agent pages") with its config directory and version; an `installed_never_run` type reads Not connected too, with its config directory marked as not created, and offers Connect, whose review names the directory it creates and the only entries Coffer needs in it; a `config_only` type reads as config left behind — program not found — and a `missing` type as not installed, each with no button and the daemon's prompt that hands reinstalling or installing it to an agent (see "Hand installing an agent's program to an agent") at the head of its ⋯ menu — Copy prompt, then Ask an agent while another agent can run it. A row whose program is missing shows no version, and its second line says "Not on this Mac" or what is left in the directory. The page MUST NOT show an install command, and carries no Remove action. On first run, with neither agent connected and both connectable, the page MUST offer **Connect both**, which reviews and connects every connectable agent in one confirmation. An agent is named by its type everywhere in the web UI; the page offers no field to name or title one.

Overview's Needs you lists only agents that need the person: an agent that needs repair, one whose config directory is left behind, and one whose Coffer memory hook needs the person ("Report an agent whose Coffer hook needs the person"). Not installed, Not connected and a first run raise none.

#### Scenario: the agents page shows both supported agents on first run
- **GIVEN** a fresh Coffer with Claude Code and Codex both installed and neither connected
- **WHEN** the user opens the Agents page
- **THEN** it shows exactly two rows, Claude Code then Codex, each reading Not connected with a Connect action, and a Connect both action, and Overview lists neither as needing the person
- **AND** choosing Connect both reviews the writes for both agents and, on apply, registers and connects both

#### Scenario: an agent that is not installed shows how to install it
- **GIVEN** Codex not installed on the machine
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as not installed with no button, and its ⋯ menu leads with Copy prompt carrying the daemon's prompt that hands installing Codex to an agent, shows no install command, and has no Connect action

#### Scenario: an installed agent that has never run can be added
- **GIVEN** Codex's program installed and `~/.codex` not created
- **WHEN** the Agents page renders and the user chooses Connect on the Codex row
- **THEN** the row reads Not connected, with `~/.codex` marked not created
- **AND** the review names `~/.codex` as created and lists only the entries Coffer adds, and nothing is written until the user applies it

#### Scenario: a leftover config directory reads as config left behind
- **GIVEN** `~/.codex` present and the Codex program not on the agent's `PATH`
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as config left behind — program not found — with no button, its ⋯ menu offering Copy prompt with the daemon's reinstall prompt, no install command, and no Connect action
- **AND** Overview's Needs you lists it

#### Scenario: a row's menu offers a different config directory
- **GIVEN** a Claude Code row on the Agents page
- **WHEN** the user opens the row's menu
- **THEN** it offers Use a different config directory…, and the page carries no Add agent dialog, no Remove action and no name or title field

### Requirement: Show what Coffer manages for an agent in one row
The agent's Skills, MCP servers, Hooks and Memory tabs MUST each hold two parts in the same order: what Coffer manages for the agent first, then what the agent has of its own. There is no owner column, no owner mark on a row, and no filter that switches between the two.

On **Skills** and **MCP servers**, Coffer's part MUST be one **From Coffer** row — how many skills, or servers, Coffer delivers to or serves this agent, their first names, and a link (**Open Skills ›**, **Open MCP servers ›**) to that kind's own page narrowed to this agent (`/skills?agent=<uid>`, `/mcp-servers?agent=<uid>`) — and Coffer's items MUST NOT be listed one by one on the agent's tab. Those two global lists MUST accept the `agent` query parameter and show only what reaches that agent. The agent's own part is a section titled "<Agent>'s own skills" or "<Agent>'s own MCP servers" with a one-line explanation and a search; its items are listed with one state word each — Unmanaged, Invalid SKILL.md, Foreign link, Duplicate, Bypasses Coffer — and at most one button, the fix for that row, with the rest in its ⋯ menu:

- **Skills** — **Adopt** an agent's own skill ([skill-manager](../skill-manager/spec.md) "Adopt an unmanaged skill"), which opens a form asking for the skill's **name in Coffer** and its **reach** (every agent by default, only chosen agents, or off), and **Delete duplicate** on a skill folder that has the same name as a skill Coffer delivers to that agent, which deletes the agent's copy behind a confirmation. A row opens the unmanaged skill's own page, with its properties and its files in the shared file tree and viewer.
- **MCP servers** — **Adopt** a direct entry ("Adopt a direct MCP entry into Coffer"), and **Remove duplicate** on a direct entry that `matches_resource` a registered MCP server, which removes it from its source file ("Remove a direct MCP entry from its source file") because Coffer's gateway already serves it; any entry can be taken out of its file from its ⋯ menu. A config file that does not parse is named above the list, and its entries stay read-only.

On **Hooks**, Coffer's part is Coffer's memory hook and the agent's own is its other hooks ("List every hook in the agent's native config"). On **Memory**, Coffer's part is Coffer's memory for this agent, shown only while the `memory` feature is on, and the agent's own are its native memory stores. The **Plugins** tab has only the agent's own part, since Coffer installs no plugin.

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

### Requirement: Report an agent whose Coffer hook needs the person
The attention list ([resource-framework](../resource-framework/spec.md) "Report what needs a person across every kind") MUST carry an `agent_hook_attention` item, at warning severity with the action of checking the agent, for a connected agent whose connection is otherwise complete when Coffer's memory hook is current but is not doing its job: the agent has not approved it, or approved an earlier command (trust `untrusted` or `modified`), or it has never fired while the agent runs hooks it finds or has approved. An agent that has switched hooks off (trust `disabled`), whose hook is trusted and has fired, or that carries no memory hook produces no such item. The item is read from Coffer's own hook alone, without reading every hook file or plugin of the agent, and is what lists a hook problem on Overview. It never replaces the more basic items: a partial connection or a missing program is reported first, one item per agent.

#### Scenario: a hook the agent has not approved is a warning
- **GIVEN** a connected Codex agent whose Coffer memory hook is current but unapproved
- **WHEN** the attention list is read
- **THEN** it carries one `agent_hook_attention` item for the agent at warning severity, saying it has not approved the hook

#### Scenario: a hook that never fired is a warning
- **GIVEN** a connected agent that runs every hook it finds and whose Coffer hook has never fired
- **WHEN** the attention list is read
- **THEN** it carries an `agent_hook_attention` item saying the hook has never fired

#### Scenario: a healthy hook reports nothing
- **GIVEN** a connected agent whose Coffer hook is trusted and has fired, one whose hooks are switched off, and one with no memory hook
- **WHEN** the attention list is read
- **THEN** none of them carries an `agent_hook_attention` item

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
