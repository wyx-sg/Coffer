## ADDED Requirements

### Requirement: Show one direct MCP entry's full configuration without its secrets
Users MUST be able to open one direct MCP entry and see everything the agent's own config file holds for it, read-only: its transport, its command and arguments (or its URL), its working directory, its per-entry `enabled` flag where the format has one, the names of its environment variables and HTTP headers, every other key the entry carries, which config file it lives in (the resolved absolute path, with open-in-editor and reveal-in-file-manager beside it), and `matches_resource` when an equivalent `mcp_server` resource is already registered. The read is addressed like removal and adoption — the entry's name, plus the source file where the type's entries may come from more than one — and is derived from the file at read time; Coffer stores nothing and starts nothing, so an unmanaged server is never spawned to be looked at.

No secret value crosses the API. Environment and header values are never returned — only their names, with the secret-like ones flagged by the pattern of "Route secret-like environment values to the credential store on adoption". Any other key whose name matches that pattern with a non-empty value, or whose value nests such a key at any depth, has its value withheld by the daemon and is reported as masked.

The detail is available from the REST API (`GET /agents/{uid}/mcp-entries/{entry}`), from `coffer agent mcp show-entry <agent> <entry> [--source] [--json]`, and in the web UI as the page a direct server's name opens on the agent's MCP servers tab (`/agents/{uid}/mcp-servers/{entry}?source=`). The page labels the entry as a direct server of that agent, returns to the agent's MCP servers tab, and offers the row's two writes: adopting it (then opening the new managed server's page) and deleting it behind the same confirm (then returning to the tab).

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

## MODIFIED Requirements

### Requirement: Expose every agent operation through REST, CLI and the Agents page
Every management operation — register/list/view/update/remove, config-file list/read/write (including directory children), Coffer-MCP install/uninstall/status, MCP entry list/view/remove/adopt, plugin list/toggle/uninstall, native-memory scan and store-file read, transcript listing and single-session read, and the model catalogue — MUST be available through (a) the REST API and (b) the `coffer agent ...` CLI, each subcommand calling the corresponding REST endpoint. The model catalogue's command is `coffer agent models <agent_type> [--json]`: it takes the agent type the catalogue route is keyed by (`claude_code`, `codex`), not an agent's name, prints one line per offered model with its label and its effort levels (the default level marked), and an unknown type exits non-zero with the route's not-found message.

The Agents page in the web UI MUST expose all of these, config-file content writes included. It renders within the web-ui shell at `/agents` as a **dedicated top-level nav entry** — a sibling of the Resources and System groups, not nested under Resources, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file (and a directory-entry child) opens in a viewer that becomes **editable behind an explicit Edit**, saves through the same path as REST and the CLI ("Validate config-file content before saving it", "Write config files atomically with a backup and an audit entry"), and guards an unsaved draft three ways — picking another file asks first, leaving the tab asks first, and leaving the page asks first. Open-in-external-editor / reveal-in-file-manager sit beside the content for the edits that want a real editor.
- The agent detail page has seven tabs — Overview, Skills, MCP servers, Plugins, Memory, Conversations, and Config files. Plugins acts on the agent (enable / disable / uninstall), and each plugin row expands to its manifest detail and bundled components. Memory carries one write — installing or removing Coffer's memory-delivery hook, which memory specifies (including its audit events and the per-agent delivery status the tab renders) and this page mounts; the rest of Memory, and all of Conversations, are read-only views of the agent's own stores.
- A direct server's name on the MCP servers tab opens that entry's own read-only detail page ("Show one direct MCP entry's full configuration without its secrets"), whose header carries the same two writes as the row — adopt and delete — and whose way back returns to the MCP servers tab.
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
