## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Expose every agent operation through REST, CLI and the Agents page
Every management operation — register/list/view/update/remove, config-file list/read/write (including directory children), Coffer-MCP install/uninstall/status, MCP entry list/remove/adopt, plugin list/detail/toggle/uninstall, native-memory scan and store-file read, transcript listing and single-session read, and the model catalogue — MUST be available through (a) the REST API and (b) the `coffer agent ...` CLI, each subcommand calling the corresponding REST endpoint. The model catalogue's command is `coffer agent models <agent_type> [--json]`: it takes the agent type the catalogue route is keyed by (`claude_code`, `codex`), not an agent's name, prints one line per offered model with its label and its effort levels (the default level marked), and an unknown type exits non-zero with the route's not-found message.

The Agents page in the web UI MUST expose all of these, config-file content writes included. It renders within the web-ui shell at `/agents` as a **dedicated top-level nav entry** — a sibling of the Resources and System groups, not nested under Resources, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file (and a directory-entry child) opens in a viewer that becomes **editable behind an explicit Edit**, saves through the same path as REST and the CLI ("Validate config-file content before saving it", "Write config files atomically with a backup and an audit entry"), and guards an unsaved draft three ways — picking another file asks first, leaving the tab asks first, and leaving the page asks first. Open-in-external-editor / reveal-in-file-manager sit beside the content for the edits that want a real editor.
- The agent detail page has seven tabs — Overview, Skills, MCP servers, Plugins, Memory, Conversations, and Config files. Plugins acts on the agent (enable / disable / uninstall), and a plugin's name opens that plugin's own detail page — the table has no expandable rows. The detail page shows the plugin's version, author, description, homepage, marketplace and its source, the directory it is installed in (with open / reveal), its enabled switch and uninstall (which returns to the Plugins tab), and everything it contributes — skills, commands and subagents with their descriptions, hook events and MCP servers — from "Read one installed plugin's detail read-only". Its back link returns to the agent's Plugins tab. Memory carries one write — installing or removing Coffer's memory-delivery hook, which memory specifies (including its audit events and the per-agent delivery status the tab renders) and this page mounts; the rest of Memory, and all of Conversations, are read-only views of the agent's own stores.
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

#### Scenario: open a plugin's detail page from the Plugins tab
- **GIVEN** an agent with an installed plugin whose package contributes skills and commands
- **WHEN** the user clicks the plugin's name on the agent's Plugins tab
- **THEN** the plugin's detail page opens with its metadata, install directory and the components it contributes, and the Plugins table offers no row expansion
- **AND** the page's back link returns to the agent's Plugins tab, and uninstalling from the page returns there too

