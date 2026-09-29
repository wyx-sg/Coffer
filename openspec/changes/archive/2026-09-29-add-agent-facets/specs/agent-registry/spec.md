## ADDED Requirements

### Requirement: Detect an agent by its program and its config directory
The system MUST detect an agent from two signals: its program on the agent's real `PATH` — the user's login-shell `PATH` merged with the daemon's inherited one, asked through the platform layer — together with the version that program reports, and its config directory on disk. The version MUST be read with the program's own version flag under a bounded timeout, and detection MUST NOT run anything that needs a login, a network call or the agent's config. The two signals MUST be named as one state: `installed_active` (program and directory), `installed_never_run` (program, no directory yet), `config_only` (directory, program missing) and `missing` (neither). Discovery candidates and every registered agent read (`GET /api/v1/agents`, `GET /api/v1/agents/{uid}`, `coffer agent show`) MUST carry the state and the version, read at request time and never stored. A `config_only` agent is shown as not installed.

#### Scenario: read the installed program's version
- **GIVEN** the agent's program is on the agent's `PATH` and answers its version flag with `2.1.281 (Claude Code)`
- **WHEN** the agent is detected
- **THEN** the program is found and its version is `2.1.281`
- **AND** a program that does not answer within the bound is still found, with no version

#### Scenario: offer an installed agent that has never run
- **GIVEN** a supported agent's program is on its `PATH` and its standard config directory does not exist
- **WHEN** the user runs discovery
- **THEN** that type is a candidate in state `installed_never_run` and is not offered for adding

#### Scenario: show a leftover config directory as not installed
- **GIVEN** a supported agent's standard config directory exists and its program is not on its `PATH`
- **WHEN** the user runs discovery
- **THEN** that type is a candidate in state `config_only`, with no version, and is not offered for adding

#### Scenario: offer the directory named by the agent's environment variable
- **GIVEN** the daemon's environment sets `CLAUDE_CONFIG_DIR` to an existing directory other than `~/.claude`, and Claude Code's program is installed
- **WHEN** the user runs discovery
- **THEN** that directory is a candidate beside the standard one, with a suggested name of its own
- **AND** a variable naming the standard directory adds no second candidate

#### Scenario: report a registered agent's detection state
- **GIVEN** a registered agent whose program is installed and whose config directory exists
- **WHEN** the agent is read
- **THEN** it carries state `installed_active` and the program's version
- **AND** an agent whose program and directory are both gone reads `missing`

### Requirement: List every hook in the agent's native config
The system MUST list, read only, every command hook the agent will run: those in the agent's own hook-carrying files (the type's child spec names them) and those in each enabled plugin's hook file, each with its event, matcher, command, timeout, source (`user` or `plugin`, with the plugin's id) and the file that declares it. Project-level settings are not read, because Coffer does not know which repositories the agent is used in. Coffer's own delivery hook MUST be marked, and its health reported by the same marker-and-command comparison the boot repair uses: `current` when the installed command is exactly the one Coffer would write now, `stale` when Coffer's marker carries another command, `missing` when it is absent — together with the last recorded fire from the audit log. The listing MUST be served by `GET /api/v1/agents/{uid}/hooks` and `coffer agent hooks <name> [--json]`, MUST write nothing and record no audit event, and a file that does not parse MUST be reported as a parse error beside the hooks the other files yield.

#### Scenario: list an agent's hooks with Coffer's own marked
- **GIVEN** a registered Claude Code agent whose `settings.json` carries a foreign `PreToolUse` hook and Coffer's delivery hook, whose `settings.local.json` carries a `Stop` hook, and which has one enabled and one disabled plugin with a hook file each
- **WHEN** the user lists the agent's hooks
- **THEN** the foreign hooks, the `Stop` hook and the enabled plugin's hook are listed with their sources and files, the disabled plugin's hook is not, and only Coffer's hook is marked as Coffer's
- **AND** Coffer's hook reads `current` with no recorded fire, and nothing is written or audited

#### Scenario: report a stale Coffer hook
- **GIVEN** a registered Codex agent whose `hooks.json` carries Coffer's marked hook with a command an older build wrote, and one recorded fire
- **WHEN** the user lists the agent's hooks
- **THEN** Coffer's hook reads `stale` on `UserPromptSubmit`, the installed and expected commands differ, and the last fire is reported

### Requirement: Discover agents on this machine as candidates without registering them
The system MUST provide a read-only discovery operation that looks, for each supported type, at its standard config directory — named in that type's child spec — and at the directory that type's own environment variable (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) names in the daemon's environment when set, and reports every such directory with either detection signal of "Detect an agent by its program and its config directory" that no registered agent holds as a **candidate** (each carrying `type`, `display_name`, `config_dir`, `default_skill_dir`, `suggested_name`, `state` and `version`). Nothing else is scanned. Candidates are derived at scan time and never stored. Discovery MUST NOT register anything automatically — the user reviews candidates and confirms which to add, and only an `installed_active` candidate can be added, because registration never creates the config directory and a directory whose program is gone belongs to no working agent. The daemon MUST NOT auto-register agents on startup.

On the command line, candidates are rows of kind `agent` in `coffer scan`, the one listing of everything agents hold that Coffer does not manage yet (see [resource-framework](../resource-framework/spec.md), the requirement that defines `coffer scan`, `coffer adopt` and `coffer discard`). Each row MUST carry the candidate's state and version; an addable row MUST name the `coffer agent add <type>` command that registers it — with `--name` and `--config-dir` for a directory other than the standard one — through the ordinary registration of "Manage the agent lifecycle", and any other row says why it cannot be added yet. A candidate MUST NOT be discardable: nothing of Coffer's put the agent there, so neither `coffer adopt` nor `coffer discard` offers an `agent` command.

#### Scenario: discover installed agents as candidates
- **GIVEN** a Coffer install with a supported agent's program installed, its standard config directory present, and no agent registered
- **WHEN** the user runs discovery
- **THEN** Coffer reports that type as an `installed_active` candidate (type, display name, config dir, suggested name, version) and registers nothing — discovery is read-only

#### Scenario: skip already-registered config directories on subsequent scan
- **GIVEN** `codex` agents are already registered for `~/.codex` and for the directory `CODEX_HOME` names
- **WHEN** the user runs discovery again
- **THEN** no `codex` candidate is offered

#### Scenario: adopt a discovered agent from the command line
- **GIVEN** Codex is installed, `~/.codex` is present and no `codex` agent is registered
- **WHEN** the user runs `coffer scan`, then `coffer agent add codex`
- **THEN** the scan lists a row of kind `agent` for `codex` that names `coffer agent add codex`, and registers nothing
- **AND** the add registers a `codex` agent under the candidate's suggested name and default config directory, audited as `resource_created`
- **AND** neither `coffer adopt` nor `coffer discard` offers an `agent` command

## MODIFIED Requirements

### Requirement: Re-offer a removed agent while it is still detected
A removed agent MUST re-appear as a discovery candidate on subsequent scans while its program or its config directory remains — a removal is not permanent (it may be accidental). The system MUST NOT keep a "suppressed types" list.

#### Scenario: re-surface removed agents on subsequent scan
- **GIVEN** an agent has been removed by the user and its program and config directory are still present
- **WHEN** the user runs discovery again
- **THEN** that agent is offered as a candidate again (removal is not permanent; no suppression list)

### Requirement: Expose agent discovery on every surface
The system MUST expose a read-only discovery operation listing the agents seen on this machine that are not registered, as candidates, available from the REST API (`GET /api/v1/agents/candidates`), the `coffer scan` CLI (as rows of kind `agent`), and the Agents page in the web UI, where the user adds an `installed_active` candidate with a single confirm and no typing of type identifiers or paths; an `installed_never_run` candidate is shown as installed but never run, and a `config_only` one as not installed, neither with an add action. On the command line an addable candidate is registered with the `coffer agent add` command its scan row names.

#### Scenario: list discovery candidates from the command line
- **GIVEN** a supported agent is installed with its standard config directory present and no agent of that type is registered
- **WHEN** the user runs `coffer scan`
- **THEN** the command lists that type as a row of kind `agent` with its config dir, its state and its version
- **AND** no agent is registered as a result

### Requirement: Support exactly the Claude Code and Codex agent types
The system MUST support the agent types `claude_code` and `codex`; registering any type outside the manifest (e.g. the `claude_desktop` chat app, a Gemini CLI) is rejected with `unprocessable_entity` (422). The rejection carries the generic request-validation message and never echoes the submitted value back. Per-type behaviour is defined by the capability manifest (`AGENT_DESCRIPTORS`) — per-type values in the record, per-type mechanisms in the optional facets it names ([Agent Mechanisms Are Optional Facets on the Descriptor](../../../docs/decisions/agent-mechanisms-are-optional-facets-on-the-descriptor.md)) — so adding a type is one enum value, one descriptor record with the facet implementations it has, and one child spec. Each supported type covers both the CLI and the app/IDE form of that product, which share one config directory.

What a facet looks like for one type is that type's child spec. There is no per-facet capability matrix, no per-facet "not supported" state on the agent surface and no capability booleans on the wire; a facet a type could not support would be a reason not to add that type. The `PluginCapability` flags of "Toggle a plugin through the documented location only" and "Uninstall a plugin by the type's own strategy" are the one exception, and they are per-facet *runtime availability* — whether the agent's own uninstall command is on `PATH` — not a per-type support claim. A further product is added only when it is genuinely in use and its facets can be exercised on a real install; `opencode`, `hermes`, `cursor` and `openclaw` were removed for lacking exactly that.

#### Scenario: reject unsupported agent type
- **GIVEN** the daemon is running
- **WHEN** the user attempts to register an agent of a type outside the supported set (e.g. `claude_desktop`, `gemini_cli`, or a garbage value)
- **THEN** registration is rejected with `unprocessable_entity` (422), and nothing is persisted

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

## REMOVED Requirements

### Requirement: Discover installed agents as candidates without registering them
**Reason**: Discovery no longer scans one install marker per type. It reads two signals — the program and the config directory — for each directory it looks at, and offers one candidate per unregistered directory rather than per unregistered type.
**Migration**: Replaced by "Discover agents on this machine as candidates without registering them". Nothing stored changes; candidates were never stored.

## RENAMED Requirements

- FROM: `### Requirement: Re-offer a removed agent while its install marker remains`
- TO: `### Requirement: Re-offer a removed agent while it is still detected`
