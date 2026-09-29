## MODIFIED Requirements

### Requirement: Discover installed agents as candidates without registering them
The system MUST provide a read-only discovery operation that scans each supported type's install marker — named in that type's child spec — and reports installed types that are not already registered as **candidates** (each carrying `type`, `display_name`, `config_dir`, `default_skill_dir`, and `suggested_name`). Candidates are derived at scan time and never stored. Discovery MUST NOT register anything automatically — the user reviews candidates and confirms which to add. The daemon MUST NOT auto-register agents on startup.

On the command line, candidates are rows of kind `agent` in `coffer scan`, the one listing of everything agents hold that Coffer does not manage yet (see [resource-framework](../resource-framework/spec.md), the requirement that defines `coffer scan`, `coffer adopt` and `coffer discard`). Each such row MUST name `coffer agent add <type>` as the way to register it; that command registers the type under its suggested name and default config directory through the ordinary registration of "Manage the agent lifecycle". A candidate MUST NOT be discardable: nothing of Coffer's put the agent there, so neither `coffer adopt` nor `coffer discard` offers an `agent` command.

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
- **WHEN** the user runs `coffer scan`, then `coffer agent add codex`
- **THEN** the scan lists a row of kind `agent` for `codex` that names `coffer agent add codex`, and registers nothing
- **AND** the add registers a `codex` agent under the candidate's suggested name and default config directory, audited as `resource_created`
- **AND** neither `coffer adopt` nor `coffer discard` offers an `agent` command

### Requirement: Manage the agent lifecycle
Users MUST be able to register, list, view, update (config_dir, description, title, name), and remove agents. An agent also carries the kind-agnostic `enabled` flag every Resource has; switching it is "Switch an agent off with the kind-agnostic enabled flag", not a field of the agent's own update. The agent name is optional at registration — when omitted, the system MUST derive a stable per-type default (underscores become hyphens, e.g. `claude_code` → `claude-code`). An agent's name stays renamable, because it appears only on Coffer's own surfaces; like every resource it also carries an optional, editable `title` that surfaces show in place of the name when it is set. Skill bindings between an agent and a skill belong to skill-manager; this registry defines no skill operations beyond exposing an `on_delete` hook for cascade cleanup and an `on_enabled_changed` hook for the reclaim of "Switch an agent off with the kind-agnostic enabled flag".

On the command line the lifecycle is the `coffer agent` group's uniform verbs — `list`, `show`, `add <type>`, `edit <name>` (with `--name`, `--title`, `--description`, `--config-dir` and the model options of "Carry the model binding on the agent record"), `rm`, `enable` and `disable`. The `agent` kind has no `scope` verb, because it declares no scope. `coffer agent show <name>` MUST print the agent's record together with one derived state, `coffer_connection`: the agent's Coffer connection part by part ("Report an agent's Coffer connection part by part"), in the shape `GET /api/v1/agents/{uid}/coffer-connection` answers — its state and, for each applicable part (the gateway MCP entry, and the memory delivery hook while memory is on), whether it is installed.

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

#### Scenario: agent show reports the Coffer MCP status
- **GIVEN** one registered agent with Coffer's MCP installed and one without
- **WHEN** the user runs `coffer agent show <name> --json` for each
- **THEN** the first carries `coffer_connection` whose `mcp` part reports installed and the second `coffer_connection` whose state is `disconnected`
- **AND** `coffer_connection` has the shape `GET /api/v1/agents/{uid}/coffer-connection` answers

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

The Agents page in the web UI MUST expose all of these, config-file content writes included. It renders within the web-ui shell at `/agents` as a **dedicated top-level nav entry** — a sibling of the Resources and System groups, not nested under Resources, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file (and a directory-entry child) opens in a viewer that becomes **editable behind an explicit Edit**, saves through the same path as REST and the CLI ("Validate config-file content before saving it", "Write config files atomically with a backup and an audit entry"), and guards an unsaved draft three ways — picking another file asks first, leaving the tab asks first, and leaving the page asks first. Open-in-external-editor / reveal-in-file-manager sit beside the content for the edits that want a real editor.
- The agent detail page has seven tabs — Overview, Skills, MCP servers, Plugins, Memory, Conversations, and Config files. Plugins acts on the agent (enable / disable / uninstall), and a plugin's name opens that plugin's own detail page — the table has no expandable rows. The detail page shows the plugin's version, author, description, homepage, marketplace and its source, the directory it is installed in (with open / reveal), its enabled switch and uninstall (which returns to the Plugins tab), and everything it contributes — skills, commands and subagents with their descriptions, hook events and MCP servers — from "Read one installed plugin's detail read-only". Its back link returns to the agent's Plugins tab. Memory and Conversations are read-only views of the agent's own stores; the memory delivery hook is installed and removed with the agent's Coffer connection in the page header ("Show the Coffer connection on the agent pages").
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

### Requirement: Expose agent discovery on every surface
The system MUST expose a read-only discovery operation listing installed-but-unregistered agents as candidates, available from the REST API (`GET /api/v1/agents/candidates`), the `coffer scan` CLI (as rows of kind `agent`), and the Agents page in the web UI, where the user adds each candidate with a single confirm and no typing of type identifiers or paths. On the command line a candidate is registered with `coffer agent add <type>`, which its scan row names.

#### Scenario: list discovery candidates from the command line
- **GIVEN** a supported agent's install marker is present and no agent of that type is registered
- **WHEN** the user runs `coffer scan`
- **THEN** the command lists that type as a row of kind `agent` with its default config dir
- **AND** no agent is registered as a result

### Requirement: Report an agent's Coffer connection part by part
The system MUST report an agent's Coffer connection (`GET /api/v1/agents/{uid}/coffer-connection`, `coffer_connection` in `coffer agent show <name> [--json]`) as the list of parts that apply to the agent now — each with its key, whether it is installed, and the installed command when it is — and a state: `connected` when every listed part is installed, `disconnected` when none is, and `partial` otherwise. The report MUST be read from the agent's own configuration files on demand, never stored, and MUST write nothing and record no audit event.

#### Scenario: report a partly installed connection
- **GIVEN** a registered agent carrying the gateway entry but not the memory hook, with `memory` switched on
- **WHEN** the user reads its Coffer connection
- **THEN** the state is `partial`, the `mcp` part is installed with its shim command and the `memory_hook` part is not installed
- **AND** connecting again installs the missing hook and the state becomes `connected`
