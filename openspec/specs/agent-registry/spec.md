# Agent Registry

## Purpose
The agent registry decides which locally-installed AI coding agents Coffer knows about, so that later features — skills, memory, knowledge, channels, chat — can deliver assets to them. Each agent is a Resource of kind `agent` in the kind-agnostic Resource framework. The supported products are **Claude Code** (`claude_code`) and **OpenAI Codex** (`codex`); each spans its CLI and its app/IDE form, because both forms read one shared config directory, so Coffer manages one config set per agent. The separate **Claude Desktop** chat app (its own `~/Library/Application Support/Claude/` config) and web-only agents such as claude.ai are not agents here. The registry holds only **managed** agents — external coding agents Coffer delivers to; the former built-in "Coffer Assistant" is not a registered agent ([Coffer's Model Is an Internal Engine](../../../docs/decisions/coffer-model-is-an-internal-engine.md)).

This spec holds what the two types share. Everything that differs by type — where the config directory is, which files are allowlisted, the MCP entry shape, the plugin inventory, the model catalogue's sources, the native-memory layout, the transcript location — lives in a child spec: [`agent-registry/claude-code`](claude-code/spec.md) and [`agent-registry/codex`](codex/spec.md), each the reading of one `AGENT_DESCRIPTORS` record, the single per-type table in the code. Adding a product is one enum value, one descriptor record and one child spec.

Beyond registering agents, the user views and edits each agent's known config files (or opens them in an external editor), installs Coffer's own MCP server into an agent with one click, and sees which models that agent can be put on. The registry also reaches into the agent's real on-disk workspace — the MCP servers configured in its own files, its installed plugins, directory-type config entries, its own native memory and its session transcripts — following **ingest → hub → deliver**: anything shareable found in an agent's workspace can be adopted into Coffer's hub (the MCP gateway; the master skill store of skill-manager) and delivered back to any agent, instead of living as per-agent one-off config. All writes go through each agent's documented configuration paths only; the agents' internal state files are read as inputs where needed and never written. Config files are surfaced as raw text with a validate + atomic-write + `.bak` safety net on every save; open-in-external-editor stays alongside as the escape hatch for the long tail, and recurring structured needs graduate into facets.

The user runs Coffer on their own machine; there is no multi-tenant or remote-access requirement. The registry relies on the Resource framework, audit log and immutable-`uid` identity of resource-framework, and renders inside the web-ui application shell. A `coffer-hook` binary with a session-context rules route and a `disable_native_memory` switch once lived here and was removed because it was never installed; session-start delivery is now memory's own, marker-scoped install, which this registry only supports by supplying the agent record, its config directory, its allowlisted settings file and the atomic-write machinery.

## Requirements

### Requirement: Register each agent as an agent resource identified by its uid
The system MUST register each known local agent as a Resource of kind `agent`, identified by the immutable `uid` the resource framework mints for it ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)). Its name is its type's ("Keep one agent per type, named by it"), and every reference another kind holds to an agent — a resource `scope`'s agent list, a channel's `default_agent`, the `--agent-uid` the shim reports — holds the uid, so the reference survives the agent being removed and registered again only if it is re-pointed, never by coincidence of a name.

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
The system MUST validate agent configuration against a kind-specific schema with fields `type` (enum) and `config_dir` (path, optional absolute-path override; when omitted it defaults to the type's standard location, which that type's child spec names), plus the model binding of "Carry the model binding on the agent record". Skills are delivered to `<config_dir>/skills`. The `agent` kind declares no `scope`: a non-null value is rejected at validation (422) — an agent resource is what other kinds' scopes name, never itself a scope target ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)).

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
A removed agent MUST re-appear as a discovery candidate on subsequent scans while its program or its config directory remains — a removal is not permanent (it may be accidental). The system MUST NOT keep a "suppressed types" list.

#### Scenario: re-surface removed agents on subsequent scan
- **GIVEN** an agent has been removed by the user and its program and config directory are still present
- **WHEN** the user runs discovery again
- **THEN** that agent is offered as a candidate again (removal is not permanent; no suppression list)

### Requirement: Manage the agent lifecycle
Users MUST be able to register, list, view, update (its config directory and the model binding of "Carry the model binding on the agent record") and remove agents. An agent also carries the kind-agnostic `enabled` flag every Resource has; switching it is "Switch an agent off with the kind-agnostic enabled flag", not a field of the agent's own update. Registration takes the type and, optionally, a config directory — the type's standard one when omitted — and the name is the type's ("Keep one agent per type, named by it"); there is no name, title or description to supply or edit. Skill bindings between an agent and a skill belong to skill-manager; this registry defines no skill operations beyond exposing an `on_delete` hook for cascade cleanup and an `on_enabled_changed` hook for the reclaim of "Switch an agent off with the kind-agnostic enabled flag".

On the command line the lifecycle is the `coffer agent` group's verbs — `list`, `show <type>`, `add <type> [--config-dir <dir>]`, `edit <type>` (with `--config-dir` and the model options of "Carry the model binding on the agent record"), `rm`, `enable` and `disable`, each taking the type (or a uid). The `agent` kind has no `scope` verb, because it declares no scope. `coffer agent show <type>` MUST print the agent's record together with one derived state, `coffer_connection`: the agent's Coffer connection part by part ("Report an agent's Coffer connection part by part"), in the shape `GET /api/v1/agents/{uid}/coffer-connection` answers — its state and, for each applicable part (the gateway MCP entry, and the memory delivery hook while memory is on), whether it is installed.

#### Scenario: register an agent without an explicit name
- **GIVEN** the daemon is running and no `claude_code` agent is registered
- **WHEN** the user runs `coffer agent add claude-code`, supplying only the type
- **THEN** the agent is registered under the type's name `claude-code` (underscores become hyphens) at the type's standard config directory, audited as `resource_created`

#### Scenario: update an existing agent
- **GIVEN** a registered agent
- **WHEN** the user updates its `config_dir` to a new writable path
- **THEN** the change persists, an audit entry is recorded, and subsequent operations see the new path

#### Scenario: remove an agent
- **GIVEN** a registered agent (any binding cleanup is handled by the skill-manager spec)
- **WHEN** the user removes it
- **THEN** the agent is deleted, an audit entry is recorded, and `coffer agent list` no longer shows it

#### Scenario: use a different config directory from the command line
- **GIVEN** a registered agent `claude-code` at `~/.claude` and another writable directory
- **WHEN** the user runs `coffer agent edit claude-code --config-dir <dir>`
- **THEN** `coffer agent show claude-code` reports `<dir>` as its config directory, with the same uid and name
- **AND** `coffer agent edit` offers no `--name`, `--title` or `--description`

#### Scenario: give an agent a title from the command line
- **GIVEN** a registered agent named `claude-code`
- **WHEN** the user runs `coffer agent edit claude-code --title "Work laptop Claude"`, and submits the same title through the kind-agnostic update route
- **THEN** the command exits non-zero on the unknown option and the route refuses the title as a validation error (422)
- **AND** `coffer agent show claude-code` still shows the agent as `claude-code`, with its uid and no title

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
- **THEN** the agent is persisted with that path (and its `<config_dir>/skills` subdirectory auto-created) and appears in `coffer agent list`

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
The system MUST expose a write (save) for the content of any allowlisted config file through the in-app editor, the REST API and the `coffer agent` CLI — one endpoint serving all three. The content MUST be validated against the file's `format` before any write; malformed `json`/`toml` MUST be rejected (`unprocessable_entity`, 422) and the on-disk file left unchanged. `markdown` files accept any content.

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
Connecting an agent to Coffer ("Connect an agent to Coffer in one action") MUST install Coffer's own MCP server into it as the connection's `mcp` part. The install writes a `coffer` stdio MCP-server entry into the agent's MCP config, using the shape declared by that agent's manifest `McpInjectionSpec` and named by that type's child spec.

- `command` is the absolute path of the `coffer-mcp-shim` binary, resolved on `PATH`, then the running interpreter's scripts directory — so a venv-installed shim is found even when the daemon's `PATH` lacks the venv — then the bundled binary; a `COFFER_MCP_SHIM_PATH` environment override takes precedence over all.
- The install additionally writes `--agent-uid <uid>` in the entry shape's argument slot — the agent's immutable uid, never its mutable name, because the entry is written once into a file Coffer does not otherwise revisit and a name would go stale on the first rename — so the gateway can attribute the session to this agent for per-agent scope enforcement ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)).
- If the shim cannot be resolved, the connect is rejected with an error naming the missing binary and nothing is written.

#### Scenario: refuse the Coffer MCP install when the shim cannot be resolved
- **GIVEN** a registered agent and no resolvable `coffer-mcp-shim` binary
- **WHEN** the user connects the agent to Coffer
- **THEN** the connect is rejected with an error naming the missing binary
- **AND** the agent's MCP config file is not written

#### Scenario: connect an agent to Coffer from the command line
- **GIVEN** a registered agent whose MCP config has no `coffer` entry and a resolvable `coffer-mcp-shim` binary
- **WHEN** the user runs `coffer agent connect <name>`
- **THEN** the agent's MCP config carries a `coffer` entry whose arguments name the agent's uid
- **AND** an `agent_mcp_installed` audit entry is recorded
- **AND** the command prints each part of the connection and whether it is installed

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
- **WHEN** the user runs `coffer agent show <name> --json` for each
- **THEN** the first carries `coffer_connection` whose `mcp` part reports installed and the second `coffer_connection` whose state is `disconnected`
- **AND** `coffer_connection` has the shape `GET /api/v1/agents/{uid}/coffer-connection` answers

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
- **WHEN** the user runs `coffer agent disconnect <name>`
- **THEN** the `coffer` entry is gone from the agent's MCP config
- **AND** `coffer agent show <name>` reports `coffer_connection` as not connected

### Requirement: Back up and audit Coffer MCP install and uninstall
Install and uninstall MUST reuse the atomic-write + `.bak` machinery of "Write config files atomically with a backup and an audit entry" and record an audit entry (`agent_mcp_installed` / `agent_mcp_uninstalled`).

#### Scenario: uninstall Coffer's MCP from an agent
- **GIVEN** an agent that has Coffer's MCP installed
- **WHEN** the user uninstalls it
- **THEN** the `coffer` entry is removed from the agent's MCP config, the file is backed up to `.bak`, an `agent_mcp_uninstalled` audit entry is recorded, and status reports `installed=false`

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

### Requirement: Show one direct MCP entry's full configuration without its secrets
Users MUST be able to open one direct MCP entry and see everything the agent's own config file holds for it, read-only: its transport, its command and arguments (or its URL), its working directory, its per-entry `enabled` flag where the format has one, the names of its environment variables and HTTP headers, every other key the entry carries, which config file it lives in (the resolved absolute path, with open-in-editor and reveal-in-file-manager beside it), and `matches_resource` when an equivalent `mcp_server` resource is already registered. The read is addressed like removal and adoption — the entry's name, plus the source file where the type's entries may come from more than one — and is derived from the file at read time; Coffer stores nothing and starts nothing, so an unmanaged server is never spawned to be looked at.

No secret value crosses the API. Environment and header values are never returned — only their names, with the secret-like ones flagged by the pattern of "Route secret-like environment values to the credential store on adoption". Any other key whose name matches that pattern with a non-empty value, or whose value nests such a key at any depth, has its value withheld by the daemon and is reported as masked.

The detail is available from the REST API (`GET /agents/{uid}/mcp-entries/{entry}`), from `coffer scan --ref <agent>:<entry> [--source] [--json]`, and in the web UI as the page a direct server's name opens on the agent's MCP servers tab (`/agents/{uid}/mcp-servers/{entry}?source=`). The page labels the entry as a direct server of that agent, returns to the agent's MCP servers tab, and offers the row's two writes: adopting it (then opening the new managed server's page) and deleting it behind the same confirm (then returning to the tab).

#### Scenario: read one direct MCP entry with its secrets withheld
- **GIVEN** a registered agent whose config file defines a stdio MCP entry with arguments, a working directory, an environment carrying a secret-like and a plain value, a secret-like extra key and a table that nests one
- **WHEN** the user reads that entry
- **THEN** Coffer returns its transport, command, arguments, working directory, the environment key names with the secret-like one flagged, every other key sorted by name with plain values shown as text, and the absolute path of the file it came from
- **AND** the secret-like extra key and the table nesting one are reported masked with no value, and no environment, header or masked value appears anywhere in the response

#### Scenario: open a direct MCP server's detail page from the agent
- **GIVEN** the agent's MCP servers tab lists a direct server
- **WHEN** the user clicks the server's name
- **THEN** its detail page opens showing it as a direct server of that agent, with its command, arguments, working directory, config file and variable names, and marking secret-looking names and masked fields as hidden without showing any value
- **AND** the back link returns to the agent's MCP servers tab

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

### Requirement: Route secret-like environment values to the credential store on adoption
Adoption MUST NOT persist secret values into resource config. When an entry's environment or HTTP headers carry values under secret-like keys (defined below), the adopt request MUST supply a credential mapping for each flagged key or be rejected with the unresolved keys listed. Mapped values are stored as Fernet ciphertext in Coffer's credential store through the daemon (per the credentials invariant); the resource config carries references only. A key is secret-like when its value is non-empty and its name matches `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`/`APIKEY`, `CREDENTIAL` or `AUTHORIZATION`, case-insensitively.

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

### Requirement: Carry the model binding on the agent record
The agent record MUST carry the model binding the rest of Coffer reads — `model`, `fast_model` and `wire_api` — because the model is chosen at the point of USE and an agent is where it is used, not on the connection that serves it. That binding MUST be settable without the web UI: `PATCH /api/v1/agents/{uid}` carries `model` / `fast_model` / `wire_api`, and `coffer agent edit` exposes them as `--model` / `--fast-model` / `--wire-api`, with `--clear-fast-model` for the explicit null that unbinds the fast slot — options on the verb that edits the agent rather than a command of their own, because they are fields of the agent. A field the request omits is unchanged. Only `fast_model` clears on an explicit null; `model` and `wire_api` have no null that unbinds them, so an explicit null for either is treated as omitted. Projecting a binding into the agent's native config is provider-switching's; validating a bound value against what one type accepts is that type's child spec (see [agent-registry/codex](codex/spec.md) "Accept only responses as Codex's wire_api" for `wire_api`).

#### Scenario: bind a model to an agent from the command line
- **GIVEN** a registered agent
- **WHEN** the user runs `coffer agent edit` with `--model` and `--fast-model`, then again with `--clear-fast-model`
- **THEN** the agent record reports the bound `model` and `fast_model` after the first edit
- **AND** after the second edit `fast_model` is null while `model` is unchanged

### Requirement: Read the model catalogue back from the installed agent
The catalogue MUST be one backend service answering per agent, and every entry — id, label, description — MUST be read back from the installed agent rather than written into Coffer, because a list written down here goes stale on the next CLI release; a model released after Coffer shipped appears with no Coffer release. Each type's child spec names its sources, and the order those sources answer in is the order of the picker. Every source MUST degrade to nothing on its own: a missing CLI, a changed bundle layout, an unauthenticated or wedged agent costs the models that source would have added and nothing else.

#### Scenario: lose only a failing source's models
- **GIVEN** an agent type with two catalogue sources, the first of which raises
- **WHEN** the catalogue is read
- **THEN** the answer carries exactly the second source's models and the request does not fail

### Requirement: Keep one source of truth for an agent's models
There MUST be exactly one source of truth. No Coffer surface may keep a model list of its own: the agent's catalogue is the answer of "Serve each agent type's model catalogue from its one agent", and what a picker is OFFERED — which narrows to an active connection's curated set where there is one — is [provider-switching](../provider-switching/spec.md) "Serve one model list to every surface"'s answer, served over the wire from that one backend rather than reassembled by any client. Nothing in Coffer curates an agent's models; two attempts to have someone curate them, first on the agent and then on the channel, were both removed. The accepted cost is that a model the agent's own catalogue does not name cannot be PICKED from a Coffer surface — it stays typeable wherever the CLI accepts a name. The benefit is that a newly released model reaches every surface with no Coffer release at all.

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
The system MUST expose a read-only **native-memory store read** that returns one store's directory as a file tree (each entry's name, store-relative path, type and size) and one file inside it as text (its contents, its absolute path for the open / reveal affordances, and whether it was truncated or is binary). A store is addressed by the `memory_dir` the native-memory scan handed out, which MUST be exactly a directory that type's layout would have listed — and not merely some path under the agent's config dir, which also holds its transcripts, settings and plugin cache. A directory that is not one of the agent's stores, a file path escaping the store, and a file that does not exist are all `not_found` (404); whether a directory is one of the agent's stores is decided by its shape alone, so the answer cannot be used to probe the filesystem. A store that has that shape but no longer exists on disk reads as an empty tree (200), not a 404. Reads are capped in size and the walk is depth-bounded, with both facts reported rather than silently applied. Read-only: Coffer never writes an agent's own memory, so the surface previews and offers open / reveal instead of an editor, and emits no audit event.

#### Scenario: browse one native memory store's files
- **GIVEN** a registered agent with a native memory store listed by "Scan an agent's own native memory stores read-only", holding Markdown files in the store directory and a subdirectory
- **WHEN** the user opens that store by the `memory_dir` the listing gave and then reads one file in it
- **THEN** Coffer returns the store directory as a tree (directories before files, paths relative to the store) and the file's contents with the absolute path that backs open / reveal, while a directory that is not one of this agent's stores — its sibling project directory included — and a path escaping the store are both rejected as `not_found` (404); read-only, emitting no audit event and writing nothing

### Requirement: Expose every agent operation through REST, CLI and the Agents page
Every management operation — register/list/view/update/remove, config-file write and delete (including directory children), Coffer connect/disconnect/connection status, MCP entry list/view/remove/adopt, plugin list/detail/toggle/uninstall, the hooks listing, transcript listing and single-session read, and the model catalogue — MUST be available through (a) the REST API and (b) the `coffer` CLI, each command calling the corresponding REST endpoint:

- the lifecycle verbs of "Manage the agent lifecycle" under `coffer agent`;
- `coffer agent config edit` and `coffer agent config rm` for config-file writes and deletes;
- `coffer agent connect` and `coffer agent disconnect` for the agent's Coffer connection ("Connect an agent to Coffer in one action"), whose status `coffer agent show [--json]` carries as `coffer_connection`;
- `coffer scan --agent <name>`, `coffer scan --ref <agent>:<entry>`, `coffer adopt mcp` and `coffer discard mcp` for direct MCP entries;
- `coffer agent plugin list|show|enable|disable|rm` for plugins, where `rm` is the uninstall of "Uninstall a plugin by the type's own strategy";
- `coffer agent hooks <name> [--json]` for the hooks of "List every hook in the agent's native config";
- `coffer agent transcript <name>` to list an agent's sessions, with the listing's search, project, sort and paging options, and `coffer agent transcript <name> <id>` to read one session in the bounded windows of "Read one transcript session in bounded windows";
- `coffer agent models` for the model catalogue.

The reads of plain files on disk — an agent's config files and their content, the files of its native memory stores, and the transcript files themselves — are served over REST for the web UI, and on the command line by `coffer path agent <name> config|memory|transcripts`, which prints their absolute locations for the user or an agent to read directly (see [resource-framework](../resource-framework/spec.md), the requirement that defines `coffer path`). The model catalogue's command is `coffer agent models <agent_type> [--json]`: it takes the agent type the catalogue route is keyed by (`claude_code`, `codex`), not an agent's name, prints one line per offered model with its label and its effort levels (the default level marked), and an unknown type exits non-zero with the route's not-found message.

The Agents page in the web UI MUST expose all of these, config-file content writes included. It renders within the web-ui shell at `/agents` as a **dedicated top-level nav entry** — a sibling of the Resources and System groups, not nested under Resources, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file (and a directory-entry child) opens in a viewer that becomes **editable behind an explicit Edit**, saves through the same path as REST and the CLI ("Validate config-file content before saving it", "Write config files atomically with a backup and an audit entry"), and guards an unsaved draft three ways — picking another file asks first, leaving the tab asks first, and leaving the page asks first. Open-in-external-editor / reveal-in-file-manager sit beside the content for the edits that want a real editor.
- The agent detail page has eight tabs — Overview, Skills, MCP servers, Plugins, Hooks, Memory, Conversations, and Config files. Hooks is read only: it groups the agent's hooks by event with each one's matcher, command and source, marks Coffer's own with its health and last fire, and offers Repair — the Coffer connection's install — when Coffer's hook is stale or missing. Plugins acts on the agent (enable / disable / uninstall), and a plugin's name opens that plugin's own detail page — the table has no expandable rows. The detail page shows the plugin's version, author, description, homepage, marketplace and its source, the directory it is installed in (with open / reveal), its enabled switch and uninstall (which returns to the Plugins tab), and everything it contributes — skills, commands and subagents with their descriptions, hook events and MCP servers — from "Read one installed plugin's detail read-only". Its back link returns to the agent's Plugins tab. Memory and Conversations are read-only views of the agent's own stores; the memory delivery hook is installed and removed with the agent's Coffer connection in the page header ("Show the Coffer connection on the agent pages").
- A direct server's name on the MCP servers tab opens that entry's own read-only detail page ("Show one direct MCP entry's full configuration without its secrets"), whose header carries the same two writes as the row — adopt and delete — and whose way back returns to the MCP servers tab.
- Neither the Memory nor the Conversations table carries per-row actions: a row OPENS its subject, and the open / reveal affordances live on the page it opens, beside the thing they act on. A Conversations row opens that one session rendered as a readable conversation, beside a contents list of the session's prompts that scrolls the conversation to any one of them; a Memory row opens that store's directory as a file tree with a read-only preview, because a store is a directory and one session is a single file.

#### Scenario: desktop app agents page
- **GIVEN** Coffer's web UI is open and one or more agents are registered
- **WHEN** the user opens the Agents page
- **THEN** every registered agent appears with type, name, and `config_dir`

#### Scenario: config-file and MCP operations mirror across surfaces
- **GIVEN** the daemon exposes the config-file and Coffer-connection routes
- **WHEN** the user invokes `coffer agent config edit`, `coffer agent config rm`, `coffer agent connect` and `coffer agent disconnect`
- **THEN** each command calls the corresponding REST endpoint and produces equivalent state
- **AND** `coffer agent show --json` reports, as `coffer_connection`, the connection the REST status route reports

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

#### Scenario: open a plugin's detail page from the Plugins tab
- **GIVEN** an agent with an installed plugin whose package contributes skills and commands
- **WHEN** the user clicks the plugin's name on the agent's Plugins tab
- **THEN** the plugin's detail page opens with its metadata, install directory and the components it contributes, and the Plugins table offers no row expansion
- **AND** the page's back link returns to the agent's Plugins tab, and uninstalling from the page returns there too

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
- **WHEN** the user runs `coffer agent list --json` and `coffer agent show <type> --json`
- **THEN** each prints only JSON, carrying the agent's name, display name, type and config directory, and `show` also its uid and its `coffer_connection` status

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

### Requirement: Expose agent discovery on every surface
The system MUST expose a read-only discovery operation listing the supported types seen on this machine that have no agent registered, as candidates — at most one per type — available from the REST API (`GET /api/v1/agents/candidates`, rows shaped as "Report every supported type's detection state" describes), the `coffer scan` CLI (as rows of kind `agent`), and the Agents page in the web UI, where the user adds an addable candidate — `installed_active`, or `installed_never_run`, whose standard directory registration creates — with a single confirm and no typing of type identifiers, names or paths; a `config_only` one is shown as not installed, with no add action. On the command line an addable candidate is registered with the `coffer agent add <type>` command its scan row names.

#### Scenario: list discovery candidates from the command line
- **GIVEN** a supported agent is installed with its standard config directory present and no agent of that type is registered
- **WHEN** the user runs `coffer scan`
- **THEN** the command lists that type as a row of kind `agent` with its config dir, its state and its version
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

### Requirement: Switch an agent off with the kind-agnostic enabled flag
An agent MUST carry the kind-agnostic `enabled` flag, toggled through the generic `POST /api/v1/resources/{uid}/enable|disable` routes and `coffer agent enable|disable <name>`, and audited as `resource_enabled` / `resource_disabled`. A disabled agent is one Coffer does not write into and does not read from: its delivered skills are reclaimed and nothing new is delivered to it ([skill-manager](../skill-manager/spec.md)), its native memory is not aggregated ([memory](../memory/spec.md)), and its native config does not feed the model catalogue of "Serve each agent type's model catalogue from its one agent" — the catalogue is read as if no agent of that type were registered. Enabling it again puts back whatever the skills' own state grants, so the switch is never a one-way door. The one exception is adoption ([skill-manager](../skill-manager/spec.md) "Adopt an unmanaged skill"): adopting a folder from a disabled agent's skills directory links it in place and records an enabled binding for that agent, the agent's next reconcile reclaims that link and disables the binding, and enabling the agent delivers the skill back whenever the skill's own `enabled` flag and scope grant it. The agent's own routes neither carry nor change the flag: `AgentOut` does not report it and `PATCH /api/v1/agents/{uid}` does not set it.

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

### Requirement: Connect an agent to Coffer in one action
Users MUST be able to connect an agent to Coffer in one action, from the REST API (`POST /api/v1/agents/{uid}/coffer-connection`), the CLI (`coffer agent connect <name>`) and the web UI. Connecting MUST install every **part** Coffer writes into the agent's own configuration that applies to that agent now:

- `mcp` — the gateway MCP entry of "Install Coffer's MCP server into an agent in one action", for every agent type;
- `memory_hook` — the memory delivery hook of [memory](../memory/spec.md) "Install delivery hooks explicitly and removably", for an agent type with a hook adapter, and only while the `memory` experimental feature is on.

The gateway entry MUST be installed first, so that a connect refused for want of a shim writes nothing. Every part MUST be installed through its own atomic write with a `.bak` and record its own audit event, as it does when installed alone. Connecting MUST be idempotent: connecting a connected agent rewrites each entry in place and never duplicates one.

#### Scenario: connect installs every part that applies
- **GIVEN** a registered Claude Code agent with neither the gateway entry nor the memory hook, and `memory` switched on
- **WHEN** the user connects it to Coffer
- **THEN** the agent's `.claude.json` carries the `coffer` MCP entry and its `settings.json` carries Coffer's marked hook entry
- **AND** one `agent_mcp_installed` and one `memory_delivery_installed` audit entry name the user as actor, and the connection reports `connected` with both parts installed

#### Scenario: connect leaves out a part whose feature is off
- **GIVEN** a registered agent and `memory` switched off
- **WHEN** the user connects it to Coffer
- **THEN** only the gateway entry is installed, no hook is written into the agent's settings, and the connection reports `connected` with the `mcp` part alone

### Requirement: Report an agent's Coffer connection part by part
The system MUST report an agent's Coffer connection (`GET /api/v1/agents/{uid}/coffer-connection`, `coffer_connection` in `coffer agent show <name> [--json]`) as the list of parts that apply to the agent now — each with its key, whether it is installed, and the installed command when it is — and a state: `connected` when every listed part is installed, `disconnected` when none is, and `partial` otherwise. The report MUST be read from the agent's own configuration files on demand, never stored, and MUST write nothing and record no audit event.

#### Scenario: report a partly installed connection
- **GIVEN** a registered agent carrying the gateway entry but not the memory hook, with `memory` switched on
- **WHEN** the user reads its Coffer connection
- **THEN** the state is `partial`, the `mcp` part is installed with its shim command and the `memory_hook` part is not installed
- **AND** connecting again installs the missing hook and the state becomes `connected`

### Requirement: Disconnect an agent from Coffer
Users MUST be able to disconnect an agent from Coffer in one action (`DELETE /api/v1/agents/{uid}/coffer-connection`, `coffer agent disconnect <name>`, the web UI). Disconnecting MUST remove every part the agent type has — whether or not it applies now, since a part whose feature was switched off may still have been left behind — taking out only Coffer's own marked entries and leaving every other entry, key and hook in those files as it was. A part that is absent MUST be a no-op that writes no file and records no audit event.

#### Scenario: disconnect removes only Coffer's entries
- **GIVEN** a connected Claude Code agent whose `.claude.json` also carries another MCP server and whose `settings.json` also carries a foreign hook on the same event
- **WHEN** the user disconnects it from Coffer
- **THEN** the `coffer` MCP entry and Coffer's hook entry are gone, the other MCP server and the foreign hook are untouched, and the connection reports `disconnected`
- **AND** disconnecting again writes no file and records no audit entry

### Requirement: Show the Coffer connection on the agent pages
The agent detail page's header MUST offer **Connect to Coffer** when the agent is not connected or needs repair, and **Disconnect from Coffer** — behind a confirmation — when it is connected. The Agents list MUST carry a Coffer column showing each agent's state as **Connected**, **Not connected** or **Needs repair** (the `partial` state), and bulk **Connect to Coffer** / **Disconnect from Coffer** actions over the selected agents. Which parts a connection installs MUST be explained behind a help affordance beside the action rather than as inline text. The Memory tab MUST NOT carry a separate install or remove action for the memory delivery hook.

#### Scenario: the header offers the action the state calls for
- **GIVEN** an agent's detail page for an agent that is not connected, one that is connected, and one whose connection is partial
- **WHEN** the header renders
- **THEN** the unconnected agent offers Connect to Coffer, the connected one offers Disconnect from Coffer, and the partial one reads Needs repair and offers Connect to Coffer
- **AND** the agent's Memory tab offers no action on the delivery hook

### Requirement: Detect an agent by its program and its config directory
The system MUST detect an agent from two signals: its program on the agent's real `PATH` — the user's login-shell `PATH` merged with the daemon's inherited one, asked through the platform layer — together with the version that program reports, and its config directory on disk. The version MUST be read with the program's own version flag under a bounded timeout, and detection MUST NOT run anything that needs a login, a network call or the agent's config. The two signals MUST be named as one state: `installed_active` (program and directory), `installed_never_run` (program, no directory yet), `config_only` (directory, program missing) and `missing` (neither). Discovery candidates, the per-type listing of "Report every supported type's detection state" and every registered agent read (`GET /api/v1/agents`, `GET /api/v1/agents/{uid}`, `coffer agent show`) MUST carry the state and the version, read at request time and never stored. A `config_only` agent is shown as not installed.

#### Scenario: read the installed program's version
- **GIVEN** the agent's program is on the agent's `PATH` and answers its version flag with `2.1.281 (Claude Code)`
- **WHEN** the agent is detected
- **THEN** the program is found and its version is `2.1.281`
- **AND** a program that does not answer within the bound is still found, with no version

#### Scenario: offer an installed agent that has never run
- **GIVEN** a supported agent's program is on its `PATH` and its standard config directory does not exist
- **WHEN** the user runs discovery
- **THEN** that type is a candidate in state `installed_never_run`, with its standard config directory, and is offered for adding

#### Scenario: show a leftover config directory as not installed
- **GIVEN** a supported agent's standard config directory exists and its program is not on its `PATH`
- **WHEN** the user runs discovery
- **THEN** that type is a candidate in state `config_only`, with no version, and is not offered for adding

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

Coffer's own memory hook — its entries on `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse` ([memory](../memory/spec.md) "Install delivery hooks explicitly and removably") — MUST be marked, each entry as Coffer's, and reported as one hook with the set of events its entries sit on. Its health MUST be reported by the same marker-and-command comparison the boot repair uses:
- `current` when the entries sit on exactly the events Coffer would install on and each carries exactly the command Coffer would write now;
- `stale` when Coffer's marker carries another command or sits on another set of events;
- `missing` when it is absent.

The report MUST also say whether the agent will run the hook, as its **trust**: `trusted`, `untrusted`, `modified` (approved for an earlier command), `disabled`, `unknown` (the agent's approval record does not parse), or `not_required` for an agent that runs every hook it finds. It MUST also give the last recorded fire from the audit log.

The listing MUST be served by `GET /api/v1/agents/{uid}/hooks` and `coffer agent hooks <name> [--json]`, and MUST write nothing and record no audit event. When the agent will not run a current hook, the CLI MUST say what the user does about it. A file that does not parse MUST be reported as a parse error beside the hooks the other files yield.

#### Scenario: list an agent's hooks with Coffer's own marked
- **GIVEN** a registered Claude Code agent whose `settings.json` carries a foreign `PreToolUse` hook and Coffer's memory hook, whose `settings.local.json` carries a `Stop` hook, and which has one enabled and one disabled plugin with a hook file each
- **WHEN** the user lists the agent's hooks
- **THEN** the foreign hooks, the `Stop` hook and the enabled plugin's hook are listed with their sources and files, the disabled plugin's hook is not, and only Coffer's four entries are marked as Coffer's
- **AND** Coffer's hook reads `current` on all four events with trust `not_required` and no recorded fire, and nothing is written or audited

#### Scenario: report a stale Coffer hook
- **GIVEN** a registered Codex agent whose `hooks.json` carries Coffer's marked hook on `UserPromptSubmit` alone, as an older build wrote it, and one recorded fire
- **WHEN** the user lists the agent's hooks
- **THEN** Coffer's hook reads `stale` on `UserPromptSubmit`, the installed and expected commands differ, and the last fire is reported

### Requirement: Discover agents on this machine as candidates without registering them
The system MUST provide a read-only discovery operation that looks, for each supported type, at its standard config directory — named in that type's child spec — and at the directory that type's own environment variable (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) names in the daemon's environment when set, and reports each type with no agent registered and with either detection signal of "Detect an agent by its program and its config directory" as one **candidate**, carrying the fields of "Report every supported type's detection state". Nothing else is scanned. Candidates are derived at scan time and never stored. Discovery MUST NOT register anything automatically — the user reviews candidates and confirms which to add, and an `installed_active` or `installed_never_run` candidate can be added — the second's registration creates its standard config directory with only the entries Coffer needs — while a `config_only` candidate cannot, because a directory whose program is gone belongs to no working agent. The daemon MUST NOT auto-register agents on startup.

On the command line, candidates are rows of kind `agent` in `coffer scan`, the one listing of everything agents hold that Coffer does not manage yet (see [resource-framework](../resource-framework/spec.md), the requirement that defines `coffer scan`, `coffer adopt` and `coffer discard`). Each row MUST carry the candidate's state and version; an addable row MUST name the `coffer agent add <type>` command that registers it — with `--config-dir` only for a directory other than the standard one — through the ordinary registration of "Manage the agent lifecycle", and any other row says why it cannot be added. A candidate MUST NOT be discardable: nothing of Coffer's put the agent there, so neither `coffer adopt` nor `coffer discard` offers an `agent` command.

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
- **WHEN** the user runs `coffer scan`, then `coffer agent add codex`
- **THEN** the scan lists a row of kind `agent` for `codex` that names `coffer agent add codex`, and registers nothing
- **AND** the add registers the `codex` agent at the default config directory, audited as `resource_created`
- **AND** neither `coffer adopt` nor `coffer discard` offers an `agent` command

### Requirement: Keep one agent per type, named by it
A machine MUST hold at most one agent of each supported type, and that agent's `name` MUST be its type's name — `claude-code` for `claude_code`, `codex` for `codex` — derived from the type at registration, never chosen by a person. The name is fixed: a changed name MUST be refused with `NAME_IMMUTABLE` (409) whose message says the name is the agent's type. An agent MUST carry no `title` and no `description`: a non-empty title is refused as a validation error (422) on every surface, and neither registration nor update takes a description. Its config directory is the one per-agent setting besides the type and the model binding of "Carry the model binding on the agent record". Registering a type that already has an agent MUST be refused with `AGENT_TYPE_REGISTERED` (409) and nothing persisted; using a different directory is an edit of the one agent.

Because a type names exactly one agent, every `/api/v1/agents/{uid}/…` route MUST also accept the type — its name (`claude-code`) or its value (`claude_code`) — in place of the uid, and answer exactly as it does for the uid; a type with no agent registered reads as not found. Every `coffer agent` command, `coffer path agent`, `coffer scan --agent` and a reach's `--agents` MUST take the type the same way, or a uid.

A database holding several agents of one type from before this rule MUST be collapsed on upgrade to one: the one whose own Coffer MCP entry names its uid, else an enabled one, else the most recently used, else the one on the type's standard directory, else the oldest. Every reach list and channel `default_agent` that named a dropped agent MUST be re-pointed at the kept one — a reach list never widened to every agent by it — the kept agent renamed to its type with its title and description cleared, and each dropped agent reported in the daemon log with its type, name, uid, config directory and the uid kept in its place. Nothing is written into a dropped agent's config directory.

#### Scenario: register a second agent of a registered type
- **GIVEN** a `codex` agent is registered at `~/.codex`
- **WHEN** the user registers another `codex` agent, on `~/.codex` or on any other writable directory
- **THEN** the registration is refused with `AGENT_TYPE_REGISTERED` (409) and nothing is persisted or created on disk
- **AND** the registered agent is still named `codex` and keeps its uid

#### Scenario: address an agent by its type
- **GIVEN** a registered `claude_code` agent with uid `U`
- **WHEN** the user requests `/api/v1/agents/claude-code`, `/api/v1/agents/claude_code/config-files` and `/api/v1/agents/U`, and runs `coffer agent show claude-code`
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

### Requirement: Report every supported type's detection state
The system MUST serve `GET /api/v1/agents/types`, one row per supported type in manifest order whether or not an agent of it is registered, so a surface can always render one row per type. Each row MUST carry the `type`, its agent's `name`, the `display_name`, the `config_dir` — the registered agent's, or the one registering would use — the type's `standard_config_dir`, the `default_skill_dir`, the detection `state` and `version` of "Detect an agent by its program and its config directory", the registered agent's `uid` (`null` when none), whether it is `addable` now, and `other_config_dir`: an existing directory the type's own environment variable (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) names in the daemon's environment other than `config_dir`, offered as a different config directory to use, never as a second agent. A type not registered is `addable` exactly when its program is installed. The read is derived at request time, stores nothing and audits nothing.

#### Scenario: list every supported type whether added or not
- **GIVEN** a registered `claude_code` agent, and Codex installed but never run — its program on its `PATH` and `~/.codex` absent
- **WHEN** the user requests `GET /api/v1/agents/types`
- **THEN** the response has exactly two rows: `claude_code` with the agent's uid, its directory and `addable` false, and `codex` with no uid, state `installed_never_run`, `config_dir` `~/.codex` and `addable` true
- **AND** nothing is registered or created by the read

### Requirement: Serve each agent type's model catalogue from its one agent
`GET /api/v1/agent-providers/{agent_key}/models` MUST answer, per agent type, which models a picker offers for that agent: the agent's own catalogue, read back from the installed agent and never written down in Coffer, unless an active connection for that agent curates a set of ids — then those ids, as [provider-switching](../provider-switching/spec.md) "Serve one model list to every surface" defines. Each entry MUST carry `id` (passed to the agent verbatim), `label`, `description`, the reasoning `efforts` its runtime reports and the `default_effort` it would use, keeping a reported default only when it is one of the offered levels. An unknown `agent_key` MUST be a 404. The catalogue reads the native config of the type's one agent ("Keep one agent per type, named by it") while it is enabled, which is also the agent a chat turn on that type runs against ([chat](../chat/spec.md) "Ship Claude Code and Codex subprocess providers on the type's one agent").

#### Scenario: list the models an agent can be put on
- **GIVEN** a registered `codex` agent whose own config names a model
- **WHEN** the user requests `GET /api/v1/agent-providers/codex/models`
- **THEN** the response lists that model with `id`, `label`, `description`, `efforts` and `default_effort`
- **AND** the same request for an unknown agent key answers 404
