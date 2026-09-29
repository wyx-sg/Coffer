## MODIFIED Requirements

### Requirement: Show one direct MCP entry's full configuration without its secrets
Users MUST be able to open one direct MCP entry and see everything the agent's own config file holds for it, read-only: its transport, its command and arguments (or its URL), its working directory, its per-entry `enabled` flag where the format has one, the names of its environment variables and HTTP headers, every other key the entry carries, which config file it lives in (the resolved absolute path, with open-in-editor and reveal-in-file-manager beside it), and `matches_resource` when an equivalent `mcp_server` resource is already registered. The read is addressed like removal and adoption — the entry's name, plus the source file where the type's entries may come from more than one — and is derived from the file at read time; Coffer stores nothing and starts nothing, so an unmanaged server is never spawned to be looked at.

No secret value crosses the API. Environment and header values are never returned — only their names, with the secret-like ones flagged by the pattern of "Route secret-like environment values to the credential store on adoption". Any other key whose name matches that pattern with a non-empty value, or whose value nests such a key at any depth, has its value withheld by the daemon and is reported as masked.

The detail is available from the REST API (`GET /agents/{uid}/mcp-entries/{entry}`), from `coffer scan --ref <agent>:<entry> [--source] [--json]`, and in the web UI as the page a direct server's name opens in the MCP servers section of the agent's Installed tab (`/agents/{uid}/mcp-servers/{entry}?source=`). The page labels the entry as a direct server of that agent, returns to that section, and offers the row's two writes: adopting it (then opening the new managed server's page) and deleting it behind the same confirm (then returning to the section).

#### Scenario: read one direct MCP entry with its secrets withheld
- **GIVEN** a registered agent whose config file defines a stdio MCP entry with arguments, a working directory, an environment carrying a secret-like and a plain value, a secret-like extra key and a table that nests one
- **WHEN** the user reads that entry
- **THEN** Coffer returns its transport, command, arguments, working directory, the environment key names with the secret-like one flagged, every other key sorted by name with plain values shown as text, and the absolute path of the file it came from
- **AND** the secret-like extra key and the table nesting one are reported masked with no value, and no environment, header or masked value appears anywhere in the response

#### Scenario: open a direct MCP server's detail page from the agent
- **GIVEN** the MCP servers section of the agent's Installed tab lists a direct server
- **WHEN** the user clicks the server's name
- **THEN** its detail page opens showing it as a direct server of that agent, with its command, arguments, working directory, config file and variable names, and marking secret-looking names and masked fields as hidden without showing any value
- **AND** the back link returns to the MCP servers section of the agent's Installed tab

### Requirement: Expose every agent operation through REST, CLI and the Agents page
Every management operation — register/list/view/update/remove, config-file write and delete (including directory children), Coffer connect/disconnect/connection status, MCP entry list/view/remove/adopt, plugin list/detail/toggle/uninstall, transcript listing and single-session read, and the model catalogue — MUST be available through (a) the REST API and (b) the `coffer` CLI, each command calling the corresponding REST endpoint:

- the lifecycle verbs of "Manage the agent lifecycle" under `coffer agent`;
- `coffer agent config edit` and `coffer agent config rm` for config-file writes and deletes;
- `coffer agent connect` and `coffer agent disconnect` for the agent's Coffer connection ("Connect an agent to Coffer in one action"), whose status `coffer agent show [--json]` carries as `coffer_connection`;
- `coffer scan --agent <name>`, `coffer scan --ref <agent>:<entry>`, `coffer adopt mcp` and `coffer discard mcp` for direct MCP entries;
- `coffer agent plugin list|show|enable|disable|rm` for plugins, where `rm` is the uninstall of "Uninstall a plugin by the type's own strategy";
- `coffer agent transcript <name>` to list an agent's sessions, with the listing's search, project, sort and paging options, and `coffer agent transcript <name> <id>` to read one session in the bounded windows of "Read one transcript session in bounded windows";
- `coffer agent models` for the model catalogue.

The reads of plain files on disk — an agent's config files and their content, the files of its native memory stores, and the transcript files themselves — are served over REST for the web UI, and on the command line by `coffer path agent <name> config|memory|transcripts`, which prints their absolute locations for the user or an agent to read directly (see [resource-framework](../resource-framework/spec.md), the requirement that defines `coffer path`). The model catalogue's command is `coffer agent models <agent_type> [--json]`: it takes the agent type the catalogue route is keyed by (`claude_code`, `codex`), not an agent's name, prints one line per offered model with its label and its effort levels (the default level marked), and an unknown type exits non-zero with the route's not-found message.

The Agents page in the web UI MUST expose all of these, config-file content writes included. It renders within the web-ui shell at `/agents` as the first entry of the sidebar's Agents group ([web-ui](../web-ui/spec.md) "Group the sidebar by what the user comes to do"), never among the Capabilities or Context entries, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file (and a directory-entry child) opens in a viewer that becomes **editable behind an explicit Edit**, saves through the same path as REST and the CLI ("Validate config-file content before saving it", "Write config files atomically with a backup and an audit entry"), and guards an unsaved draft three ways — picking another file asks first, leaving the tab asks first, and leaving the page asks first. Open-in-external-editor / reveal-in-file-manager sit beside the content for the edits that want a real editor.
- The agent detail page has six tabs, in this order — **Overview**, **Installed**, **Config files**, **Conversations**, **Memory** and **Model**:
  - **Installed** groups everything installed into the agent in sections — **Skills**, **MCP servers**, **Plugins** and **Hooks** — each row marked as managed by Coffer or the agent's own, each section addressable so a page opened from it returns to it. The Hooks section lists the hooks the agent's own configuration declares, Coffer's own marked, and appears with the change that reads an agent's hooks; until then Installed carries three sections.
  - **Config files** lists every allowlisted config file of "Define a curated config-file allowlist per type" in one list — the settings files and the human-authored instructions files (`CLAUDE.md`, `AGENTS.md`) alike, because an instructions file is configuration the person wrote, not something installed.
  - **Model** holds the agent's connection and model selection (see [provider-switching](../provider-switching/spec.md) "Offer every connection operation on REST, CLI and web").
  - The Plugins section acts on the agent (enable / disable / uninstall), and a plugin's name opens that plugin's own detail page — the table has no expandable rows. The detail page shows the plugin's version, author, description, homepage, marketplace and its source, the directory it is installed in (with open / reveal), its enabled switch and uninstall (which returns to the Plugins section of the Installed tab), and everything it contributes — skills, commands and subagents with their descriptions, hook events and MCP servers — from "Read one installed plugin's detail read-only". Its back link returns to the Plugins section of the agent's Installed tab. Memory and Conversations are read-only views of the agent's own stores; the memory delivery hook is installed and removed with the agent's Coffer connection in the page header ("Show the Coffer connection on the agent pages").
- A direct server's name in the MCP servers section opens that entry's own read-only detail page ("Show one direct MCP entry's full configuration without its secrets"), whose header carries the same two writes as the row — adopt and delete — and whose way back returns to the MCP servers section.
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
- **WHEN** the user clicks the plugin's name in the Plugins section of the agent's Installed tab
- **THEN** the plugin's detail page opens with its metadata, install directory and the components it contributes, and the Plugins section offers no row expansion
- **AND** the page's back link returns to the Plugins section of the agent's Installed tab, and uninstalling from the page returns there too

#### Scenario: the agent detail page carries six tabs
- **GIVEN** a registered agent with a managed skill, a direct MCP entry, an installed plugin and a `CLAUDE.md` instructions file
- **WHEN** the user opens its detail page
- **THEN** the tabs read Overview, Installed, Config files, Conversations, Memory and Model, in that order
- **AND** Installed shows the skill, the MCP entry and the plugin in their own sections, each marked as Coffer's or the agent's own, and Config files lists the instructions file beside the settings files
