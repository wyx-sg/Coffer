## MODIFIED Requirements

### Requirement: Carry the model binding on the agent record
The agent record MUST carry the model binding the rest of Coffer reads — `model`, `effort`, `tier_models` (Claude Code only: the model for each of `opus`, `sonnet`, `haiku` and `fable`) and `wire_api` — because the model is chosen at the point of USE and an agent is where it is used, not on the connection that serves it. That binding MUST be settable without the web UI: `PATCH /api/v1/agents/{uid}` carries `model` / `effort` / `tier_models` / `wire_api`, and `coffer agent edit` exposes them as `--model`, `--effort`, `--tier <tier>=<model>` (repeatable) and `--wire-api`, with `--clear-effort` and `--clear-tiers` for the explicit nulls that unbind them — options on the verb that edits the agent rather than a command of their own, because they are fields of the agent. A field the request omits is unchanged. Only `effort` and `tier_models` clear on an explicit null; `model` and `wire_api` have no null that unbinds them, so an explicit null for either is treated as omitted. Projecting a binding into the agent's native config is provider-switching's; validating a bound value against what one type accepts is that type's child spec (see [agent-registry/codex](codex/spec.md) "Accept only responses as Codex's wire_api" for `wire_api`).

#### Scenario: bind a model to an agent from the command line
- **GIVEN** a registered agent
- **WHEN** the user runs `coffer agent edit` with `--model`, `--effort high` and `--tier haiku=<model>`, then again with `--clear-tiers`
- **THEN** the agent record reports the bound `model`, `effort` and `tier_models` after the first edit, and carries no `fast_model`
- **AND** after the second edit `tier_models` is null while `model` and `effort` are unchanged


### Requirement: Show one direct MCP entry's full configuration without its secrets
Users MUST be able to open one direct MCP entry and see everything the agent's own config file holds for it, read-only: its transport, its command and arguments (or its URL), its working directory, its per-entry `enabled` flag where the format has one, the names of its environment variables and HTTP headers, every other key the entry carries, which config file it lives in (the resolved absolute path, with open-in-editor and reveal-in-file-manager beside it), and `matches_resource` when an equivalent `mcp_server` resource is already registered. The read is addressed like removal and adoption — the entry's name, plus the source file where the type's entries may come from more than one — and is derived from the file at read time; Coffer stores nothing and starts nothing, so an unmanaged server is never spawned to be looked at.

No secret value crosses the API. Environment and header values are never returned — only their names, with the secret-like ones flagged by the pattern of "Route secret-like environment values to the credential store on adoption". Any other key whose name matches that pattern with a non-empty value, or whose value nests such a key at any depth, has its value withheld by the daemon and is reported as masked.

The detail is available from the REST API (`GET /agents/{uid}/mcp-entries/{entry}`), from `coffer scan --ref <agent>:<entry> [--source] [--json]`, and in the web UI as the page a direct server's name opens on the agent's MCP servers tab (`/agents/<type>/mcp-servers/<entry>?source=`). The page labels the entry as a direct server of that agent, returns to that tab, and offers the row's two writes: adopting it (then opening the new managed server's page) and deleting it behind the same confirm (then returning to the tab).

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

The Agents page in the web UI MUST expose all of these, config-file content writes included. It renders within the web-ui shell at `/agents` as the first entry of the sidebar's Agents group ([web-ui](../web-ui/spec.md) "Group the sidebar by what the user comes to do"), never among the Capabilities or Context entries, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file (and a directory-entry child) opens in a viewer that becomes **editable behind an explicit Edit**, saves through the same path as REST and the CLI ("Validate config-file content before saving it", "Write config files atomically with a backup and an audit entry"), and guards an unsaved draft three ways — picking another file asks first, leaving the tab asks first, and leaving the page asks first. Open-in-external-editor / reveal-in-file-manager sit beside the content for the edits that want a real editor.
- The agent detail page has nine tabs, in this order — **Overview**, **Model**, **Skills**, **MCP servers**, **Plugins**, **Hooks**, **Config files**, **Memory** and **Sessions** — each addressable by its own path (`/agents/<type>` for Overview, `/agents/<type>/model`, `/agents/<type>/skills`, `/agents/<type>/mcp-servers`, `/agents/<type>/plugins`, `/agents/<type>/hooks`, `/agents/<type>/config`, `/agents/<type>/memory`, `/agents/<type>/sessions`; the old `/agents/<type>/conversations` redirects there), so a page opened from a tab returns to it:
  - **Overview** carries the agent's details — its type, config directory and Coffer connection, and no Title or Name field, because an agent's name is fixed to its type — and one summary row each for Skills, MCP servers, Plugins and Hooks, counting Coffer's entries and the agent's own, each row opening its tab.
  - **Model** holds the agent's connection and model selection (see [provider-switching](../provider-switching/spec.md) "Offer every connection operation on REST, CLI and web"); it is the only place an agent's provider is switched.
  - **Skills**, **MCP servers**, **Plugins** and **Hooks** each list both Coffer-managed entries and the agent's own, filtered by one owner filter (see "Filter an agent's installed kinds by owner"). The Hooks tab is read only apart from its row actions: it groups the agent's hooks by event with each one's matcher, command and source (from "List every hook in the agent's native config"), marks Coffer's own with its health and last fire, and offers Repair — the Coffer connection's install — when Coffer's hook is stale or missing.
  - **Config files** lists every allowlisted config file of "Define a curated config-file allowlist per type" in one list — the settings files and the human-authored instructions files (`CLAUDE.md`, `AGENTS.md`) alike, because an instructions file is configuration the person wrote, not something installed.
  - The Plugins tab acts on the agent (enable / disable / uninstall), and a plugin's name opens that plugin's own detail page — the table has no expandable rows. The detail page shows the plugin's version, author, description, homepage, marketplace and its source, the directory it is installed in (with open / reveal), its enabled switch and uninstall (which returns to the Plugins tab), and everything it contributes — skills, commands and subagents with their descriptions, hook events and MCP servers — from "Read one installed plugin's detail read-only". Its back link returns to the agent's Plugins tab. Memory and **Sessions** — the agent's own CLI session history, not Coffer's conversations — are read-only views of the agent's own stores — the Memory tab shows only the agent's native memory stores, and what Coffer delivers is on the Memory page ([web-ui](../web-ui/spec.md) "Show memory delivery on the Memory page"); the memory delivery hook is installed and removed with the agent's Coffer connection in the page header ("Show the Coffer connection on the agent pages").
- A direct server's name on the MCP servers tab opens that entry's own read-only detail page ("Show one direct MCP entry's full configuration without its secrets"), whose header carries the same two writes as the row — adopt and delete — and whose way back returns to the MCP servers tab.
- Neither the Memory nor the Sessions table carries per-row actions: a row OPENS its subject, and the open / reveal affordances live on the page it opens, beside the thing they act on. A Sessions row opens that one session rendered as a readable conversation, beside a contents list of the session's prompts that scrolls the conversation to any one of them; a Memory row opens that store's directory as a file tree with a read-only preview, because a store is a directory and one session is a single file.

#### Scenario: desktop app agents page
- **GIVEN** Coffer's web UI is open with a Claude Code agent registered and Codex installed but not added
- **WHEN** the user opens the Agents page
- **THEN** it shows exactly two rows, Claude Code and Codex, the first with its `config_dir` and Coffer connection state and the second as not added with an Add action

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
- **THEN** the plugin's detail page opens with its metadata, install directory and the components it contributes, and the Plugins tab offers no row expansion
- **AND** the page's back link returns to the agent's Plugins tab, and uninstalling from the page returns there too

#### Scenario: the agent detail page carries nine tabs
- **GIVEN** a registered Claude Code agent with a managed skill, a direct MCP entry, an installed plugin and a `CLAUDE.md` instructions file
- **WHEN** the user opens `/agents/claude_code`
- **THEN** the tabs read Overview, Model, Skills, MCP servers, Plugins, Hooks, Config files, Memory and Sessions, in that order, and opening `/agents/claude_code/skills` selects Skills
- **AND** Overview shows no Title or Name field, and its Skills, MCP servers and Plugins summary rows each open their tab; Config files lists the instructions file beside the settings files

### Requirement: Expose agent discovery on every surface
The system MUST expose a read-only discovery operation listing the supported types seen on this machine that have no agent registered, as candidates — at most one per type — available from the REST API (`GET /api/v1/agents/candidates`, rows shaped as "Report every supported type's detection state" describes), the `coffer scan` CLI (as rows of kind `agent`), and the Agents page in the web UI, where a candidate is a row of the list that is not added (see "List the supported agents as fixed rows on the Agents page"). Detection is automatic: the page reads the candidates each time it loads and offers no Detect action. The user adds an addable candidate — `installed_active`, or `installed_never_run`, whose standard directory registration creates — with the row's Add, after a preview of what it will write, with no typing of type identifiers, names or paths; a `config_only` candidate is shown as config left behind with its program not found, with the reinstall command and no Add action. On the command line an addable candidate is registered with the `coffer agent add <type>` command its scan row names.

#### Scenario: list discovery candidates from the command line
- **GIVEN** a supported agent is installed with its standard config directory present and no agent of that type is registered
- **WHEN** the user runs `coffer scan`
- **THEN** the command lists that type as a row of kind `agent` with its config dir, its state and its version
- **AND** no agent is registered as a result

#### Scenario: the agents page detects candidates without a detect action
- **GIVEN** Codex installed and run once (state `installed_active`) and no `codex` agent registered
- **WHEN** the user opens the Agents page
- **THEN** the Codex row reads as not added with an Add action, and the page carries no Detect agents button and no Add agent dialog

### Requirement: Offer a folder picker for a custom config directory
When choosing a custom `config_dir`, the web UI MUST offer a folder picker rather than requiring the user to type a path. It is reached from an agent row's menu, **Use a different config directory…**, because the default directory is found automatically and a different one is the exception. It MUST use the daemon's native directory dialog (`POST /api/v1/fs/pick-folder`, owned by the daemon spec), falling back to the daemon-backed folder browser (`GET /api/v1/fs/browse`, owned by the daemon spec) only when the host has no native dialog tool. Both yield an absolute path that is then validated per "Validate the config directory at registration" before registration, or before the agent's directory is moved.

#### Scenario: pick a custom config directory with the native dialog
- **GIVEN** the Agents page and the host offering a native directory dialog
- **WHEN** the user chooses Use a different config directory… from a row's menu and picks a folder
- **THEN** the picked absolute path is validated and used for that agent's config directory
- **AND** the in-app folder browser is not opened

### Requirement: Show the Coffer connection on the agent pages
The agent detail page's header MUST offer **Connect to Coffer** when the agent is not connected or needs repair, and **Disconnect from Coffer** — behind a confirmation — when it is connected. Each row of the Agents list MUST show the agent's Coffer state — **Not added**, **Connected**, **Not connected** or **Needs repair** (the `partial` state) — and the one action that state calls for: **Add** for a row not added, which registers the agent under its default config directory and connects it; **Connect** for one not connected; **Repair** for one that needs repair. Add, Connect and Repair MUST each open a preview of the change first — every file it will write and the entries it adds — and write nothing until the user confirms. The list has two rows, so it carries no row selection and no bulk actions. Which parts a connection installs MUST be explained behind a help affordance beside the action rather than as inline text. The Memory tab MUST NOT carry a separate install or remove action for the memory delivery hook.

#### Scenario: the header offers the action the state calls for
- **GIVEN** an agent's detail page for an agent that is not connected, one that is connected, and one whose connection is partial
- **WHEN** the header renders
- **THEN** the unconnected agent offers Connect to Coffer, the connected one offers Disconnect from Coffer, and the partial one reads Needs repair and offers Connect to Coffer
- **AND** the agent's Memory tab offers no action on the delivery hook

#### Scenario: adding an agent previews the change first
- **GIVEN** the Codex row reading as not added
- **WHEN** the user chooses Add
- **THEN** a preview lists each file the add will write and the entries it adds, and nothing is written yet
- **AND** confirming registers Codex under its default config directory, connects it, and the row reads Connected

#### Scenario: repairing a partial connection previews the missing parts
- **GIVEN** a Claude Code agent whose Coffer connection is partial
- **WHEN** the user chooses Repair on its row
- **THEN** the preview lists only the missing parts, and confirming installs them and the row reads Connected

### Requirement: Detect an agent by its program and its config directory
The system MUST detect an agent from two signals: its program on the agent's real `PATH` — the user's login-shell `PATH` merged with the daemon's inherited one, asked through the platform layer — together with the version that program reports, and its config directory on disk. The version MUST be read with the program's own version flag under a bounded timeout, and detection MUST NOT run anything that needs a login, a network call or the agent's config. The two signals MUST be named as one state: `installed_active` (program and directory), `installed_never_run` (program, no directory yet), `config_only` (directory, program missing) and `missing` (neither). Discovery candidates, the per-type listing of "Report every supported type's detection state" and every registered agent read (`GET /api/v1/agents`, `GET /api/v1/agents/{uid}`, `coffer agent show`) MUST carry the state and the version, read at request time and never stored. An `installed_never_run` agent can be added: its program works and the directory it has not created yet is created by the registration (see "Validate the config directory at registration"). A `config_only` agent is shown as config left behind with its program not found — not as not installed — because a directory of its own is still on disk and the fix is to reinstall the program; `missing` is shown as not installed.

#### Scenario: read the installed program's version
- **GIVEN** the agent's program is on the agent's `PATH` and answers its version flag with `2.1.281 (Claude Code)`
- **WHEN** the agent is detected
- **THEN** the program is found and its version is `2.1.281`
- **AND** a program that does not answer within the bound is still found, with no version

#### Scenario: offer an installed agent that has never run
- **GIVEN** a supported agent's program is on its `PATH` and its standard config directory does not exist
- **WHEN** the user runs discovery
- **THEN** that type is a candidate in state `installed_never_run`, with its version and its standard config directory marked as not created, and is offered for adding

#### Scenario: show a leftover config directory as not installed
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

#### Scenario: add an agent that has never run
- **GIVEN** Codex's program is installed, `~/.codex` does not exist, and no `codex` agent is registered
- **WHEN** the user runs `coffer scan`, then `coffer agent add codex`
- **THEN** the scan lists a `codex` row in state `installed_never_run` that names `coffer agent add codex`
- **AND** the add creates `~/.codex` with only the entries Coffer needs and registers the agent, audited as `resource_created`

## ADDED Requirements

### Requirement: List the supported agents as fixed rows on the Agents page
The Agents page MUST list exactly one row per supported agent type — today two, Claude Code and Codex — whether or not each is installed or added, in that order, so the page reads the same on every machine and a first-time user sees at once what Coffer can manage. Each row is found automatically from the detection state of "Detect an agent by its program and its config directory": an `installed_active` type's row reads as added (with its config directory and version) or not added; an `installed_never_run` type reads as installed but never run, with its config directory marked as not created, and offers Add, whose preview names the directory it creates and the only entries Coffer needs in it; a `config_only` type reads as config left behind — program not found — and shows the command that reinstalls it, to copy, and no Add; a `missing` type reads as not installed and shows the command that installs it, to copy, and no Add. A row's menu carries **Use a different config directory…** (see "Offer a folder picker for a custom config directory"). On first run, with neither agent added, the page MUST offer **Add both**, which previews and adds every installed, not-added agent in one confirmation. An agent is named by its type everywhere in the web UI; the page offers no field to name or title one.

#### Scenario: the agents page shows both supported agents on first run
- **GIVEN** a fresh Coffer with Claude Code and Codex both installed and neither added
- **WHEN** the user opens the Agents page
- **THEN** it shows exactly two rows, Claude Code then Codex, each not added with an Add action, and an Add both action
- **AND** choosing Add both previews the writes for both agents and, on confirmation, adds and connects both

#### Scenario: an agent that is not installed shows how to install it
- **GIVEN** Codex not installed on the machine
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as not installed and shows the command that installs Codex, to copy, and no Add action

#### Scenario: an installed agent that has never run can be added
- **GIVEN** Codex's program installed and `~/.codex` not created
- **WHEN** the Agents page renders and the user chooses Add on the Codex row
- **THEN** the row reads as installed, never run, with `~/.codex` marked not created
- **AND** the preview names `~/.codex` as created and lists only the entries Coffer adds, and nothing is written until the user confirms

#### Scenario: a leftover config directory reads as config left behind
- **GIVEN** `~/.codex` present and the Codex program not on the agent's `PATH`
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as config left behind — program not found — with the command that reinstalls Codex, to copy, and no Add action

#### Scenario: a row's menu offers a different config directory
- **GIVEN** a Claude Code row on the Agents page
- **WHEN** the user opens the row's menu
- **THEN** it offers Use a different config directory…, and the page carries no Add agent dialog and no name or title field

### Requirement: Filter an agent's installed kinds by owner
The agent's Skills, MCP servers, Plugins and Hooks tabs MUST each list, in one table, both the entries Coffer manages and the agent's own, each row marked with its owner, and MUST carry one owner filter — All, Coffer, or the agent's own — that narrows the table and is kept in the tab's URL. Each tab carries the actions its kind needs and no other:

- **Skills** — **Adopt** an agent's own skill ([skill-manager](../skill-manager/spec.md) "Adopt an unmanaged skill"), and **Remove duplicate** on an agent's own skill folder that has the same name as a skill Coffer delivers to that agent, which deletes the agent's copy behind a confirmation.
- **MCP servers** — **Adopt** a direct entry ("Adopt a direct MCP entry into Coffer"), and **Remove duplicate** on a direct entry that `matches_resource` a registered MCP server, which removes it from its source file ("Remove a direct MCP entry from its source file") because Coffer's gateway already serves it.
- **Plugins** — enable, disable and **Uninstall** ("Uninstall a plugin by the type's own strategy").
- **Hooks** — **Open file**, which opens the configuration file that declares the hook in the external editor ("Open config files in an external editor or reveal them"), and **Repair** on Coffer's own hook when it is stale or missing.

#### Scenario: the owner filter narrows an installed-kind tab
- **GIVEN** an agent with one Coffer-managed skill and two of its own skill folders
- **WHEN** the user opens its Skills tab and sets the owner filter to the agent's own
- **THEN** the table lists the two agent-owned skills only, each marked as the agent's own, and the URL carries the filter
- **AND** setting the filter to All lists all three

#### Scenario: a duplicate direct MCP entry can be removed
- **GIVEN** an agent whose config file carries a direct MCP entry that matches a registered MCP server
- **WHEN** the user chooses Remove duplicate on that row and confirms
- **THEN** the entry is removed from its source file, and the MCP servers tab lists the server once, as Coffer's
