## ADDED Requirements

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
The system MUST report an agent's Coffer connection (`GET /api/v1/agents/{uid}/coffer-connection`, `coffer agent connection <name> [--json]`) as the list of parts that apply to the agent now — each with its key, whether it is installed, and the installed command when it is — and a state: `connected` when every listed part is installed, `disconnected` when none is, and `partial` otherwise. The report MUST be read from the agent's own configuration files on demand, never stored, and MUST write nothing and record no audit event.

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

## MODIFIED Requirements

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

### Requirement: Keep the Coffer MCP install idempotent and report its status
Installing the `mcp` part MUST be idempotent — re-installing updates the existing `coffer` entry in place and never creates a duplicate. Whether it is installed MUST be reported as that part of the agent's Coffer connection ("Report an agent's Coffer connection part by part"), derived from the agent's MCP config file, never stored.

#### Scenario: report Coffer-MCP install status
- **GIVEN** a registered agent whose MCP config does not contain a `coffer` server entry
- **WHEN** the user checks the agent's Coffer connection
- **THEN** the `mcp` part reports `installed=false`

#### Scenario: install Coffer's MCP is idempotent
- **GIVEN** an agent that already has Coffer's MCP installed
- **WHEN** the user connects it again
- **THEN** the existing `coffer` entry is updated in place (never duplicated) and the `mcp` part still reports `installed=true`

### Requirement: Uninstall Coffer's MCP server from an agent
Disconnecting an agent from Coffer ("Disconnect an agent from Coffer") MUST uninstall Coffer's MCP, removing the `coffer` entry from the agent's MCP config. Uninstalling when not installed is a no-op success and the `mcp` part then reports not installed.

#### Scenario: uninstall Coffer's MCP when it is not installed
- **GIVEN** a registered agent whose MCP config has no `coffer` entry
- **WHEN** the user disconnects the agent from Coffer
- **THEN** the operation succeeds without changing the agent's MCP config
- **AND** the `mcp` part reports `installed=false`

### Requirement: Expose every agent operation through REST, CLI and the Agents page
Every management operation — register/list/view/update/remove, config-file list/read/write (including directory children), Coffer connect/disconnect/connection status, MCP entry list/remove/adopt, plugin list/toggle/uninstall, native-memory scan and store-file read, transcript listing and single-session read, and the model catalogue — MUST be available through (a) the REST API and (b) the `coffer agent ...` CLI, each subcommand calling the corresponding REST endpoint. The model catalogue's command is `coffer agent models <agent_type> [--json]`: it takes the agent type the catalogue route is keyed by (`claude_code`, `codex`), not an agent's name, prints one line per offered model with its label and its effort levels (the default level marked), and an unknown type exits non-zero with the route's not-found message.

The Agents page in the web UI MUST expose all of these, config-file content writes included. It renders within the web-ui shell at `/agents` as a **dedicated top-level nav entry** — a sibling of the Resources and System groups, not nested under Resources, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file (and a directory-entry child) opens in a viewer that becomes **editable behind an explicit Edit**, saves through the same path as REST and the CLI ("Validate config-file content before saving it", "Write config files atomically with a backup and an audit entry"), and guards an unsaved draft three ways — picking another file asks first, leaving the tab asks first, and leaving the page asks first. Open-in-external-editor / reveal-in-file-manager sit beside the content for the edits that want a real editor.
- The agent detail page has seven tabs — Overview, Skills, MCP servers, Plugins, Memory, Conversations, and Config files. Plugins acts on the agent (enable / disable / uninstall), and each plugin row expands to its manifest detail and bundled components. Memory and Conversations are read-only views of the agent's own stores; the memory delivery hook is installed and removed with the agent's Coffer connection in the page header ("Show the Coffer connection on the agent pages").
- Neither the Memory nor the Conversations table carries per-row actions: a row OPENS its subject, and the open / reveal affordances live on the page it opens, beside the thing they act on. A Conversations row opens that one session rendered as a readable conversation, beside a contents list of the session's prompts that scrolls the conversation to any one of them; a Memory row opens that store's directory as a file tree with a read-only preview, because a store is a directory and one session is a single file.

#### Scenario: desktop app agents page
- **GIVEN** Coffer's web UI is open and one or more agents are registered
- **WHEN** the user opens the Agents page
- **THEN** every registered agent appears with type, name, and `config_dir`

#### Scenario: config-file and MCP operations mirror across surfaces
- **GIVEN** the daemon exposes the config-file and Coffer-connection routes
- **WHEN** the user invokes the equivalent `coffer agent config …` / `coffer agent connect|disconnect|connection` CLI subcommands
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
The system MUST record an audit entry, carrying timestamp, actor and the affected agent reference, for every lifecycle event: agent created, updated, removed (via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events); agent enabled/disabled (via the kind-agnostic `resource_enabled` / `resource_disabled` events); config file written/deleted (`agent_config_file_written` / `agent_config_file_deleted`); Coffer MCP installed/uninstalled; MCP entry removed/adopted (`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`); plugin toggled/uninstalled (`agent_plugin_toggled` / `agent_plugin_uninstalled`). Discovery and all workspace listings — MCP entries, plugins, config files, native memory stores, transcript sessions, the model catalogue, the Coffer connection status — are read-only and emit no audit event, the background pass that warms the transcript summary cache included. Reading ONE of the listed items — a single session's turns, a single store's files — is the same act at a smaller scale and audits nothing either. A connect or disconnect records the events of the parts it installs or removes and none of its own; the memory delivery hook's events are memory's, not this spec's.

#### Scenario: audit lifecycle events
- **GIVEN** the user has registered, edited, or removed agents
- **WHEN** they view the audit log
- **THEN** every lifecycle change (create, update, remove) appears via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events, each carrying timestamp, actor, and the affected agent reference. (Discovery is read-only and registers nothing, so it emits no audit event of its own.)
