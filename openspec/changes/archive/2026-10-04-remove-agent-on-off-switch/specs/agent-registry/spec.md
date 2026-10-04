## REMOVED Requirements

### Requirement: Switch an agent off with the kind-agnostic enabled flag
**Reason**: An agent can no longer be switched off. The agent kind declares itself non-toggleable, so the one thing the switch did — stop Coffer reading or writing an agent it still knew about — is Disconnect (and, for a program the person no longer wants Coffer near, removing the agent over REST). Keeping a second off-state beside Not connected left every consumer of an agent (skill delivery, memory aggregation, the model catalogue, chat, provider projection) with a branch for an agent that was registered but to be ignored.
**Migration**: Disconnect the agent from its row's ⋯ menu or its Overview. An agent that was switched off earlier is read as enabled from then on, and its skills, memory and model catalogue are served again on the next pass. The generic enable and disable routes refuse an agent with 409 `RESOURCE_NOT_TOGGLEABLE` (resource-framework "Address every resource by an immutable uid through one kind-agnostic surface").

## MODIFIED Requirements

### Requirement: Manage the agent lifecycle
Users MUST be able to register, list, view, update (its config directory and the model binding of "Carry the model binding on the agent record") and remove agents. An agent cannot be switched off: its kind is non-toggleable, so the generic `POST /api/v1/resources/{uid}/enable|disable` routes refuse it with `RESOURCE_NOT_TOGGLEABLE` and its resource always reads enabled. Registration takes the type and, optionally, a config directory — the type's standard one when omitted — and the name is the type's ("Keep one agent per type, named by it"); there is no name, title or description to supply or edit. Skill bindings between an agent and a skill belong to skill-manager; this registry defines no skill operations beyond exposing an `on_delete` hook for cascade cleanup.

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

### Requirement: Re-offer a removed agent while it is still detected
A removed agent MUST re-appear as a discovery candidate on subsequent scans while its program or its config directory remains — a removal is not permanent (it may be accidental). The system MUST NOT keep a "suppressed types" list. Removal is a REST act (`DELETE /api/v1/agents/{uid}`); the web UI offers none, because its list always holds a row for every supported agent and the way to stop Coffer touching one is to disconnect it.

#### Scenario: re-surface removed agents on subsequent scan
- **GIVEN** an agent has been removed by the user and its program and config directory are still present
- **WHEN** the user runs discovery again
- **THEN** that agent is offered as a candidate again (removal is not permanent; no suppression list)

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
- The agent detail page's **header** carries the agent's mark, its name, one status pill, **New conversation** and a **⋯** menu, and nothing under the name: the version and the config directory are on the Overview. The pill reads Connected, Not connected, Needs repair, Hook not approved or Config left behind. The header never turns into a fix button — Connect, Repair and Check again sit on the Overview's Connection section — and an agent whose program is not on this machine, which has nothing to converse with, shows ⋯ only. **Rotate proxy token** is in ⋯ only while the agent routes through Coffer's proxy ([provider-switching](../provider-switching/spec.md) "Authenticate each agent to the proxy with its own local token").
- The detail page has eight tabs, none carrying a count: six in the strip — **Overview**, **Skills**, **MCP servers**, **Hooks**, **Config files** and **Sessions** — and, behind a **More** menu, **Plugins** and **Memory**, the least used. Each is addressable by its own path (`/agents/<type>` for Overview, then `/agents/<type>/skills`, `/mcp-servers`, `/hooks`, `/config`, `/sessions`, `/plugins` and `/memory`), so a page opened from a tab returns to it. While the open tab is one of the two in More, the More trigger reads that tab's name and carries the underline; a tab in More that needs attention puts a warning dot on More. There is **no Model tab**: an agent's model is a section of the Overview, and `/agents/<type>/model` is not a page.
  - **Overview** stacks, top to bottom, **Connection**, **What this agent can use**, **Model** and **Details**. Connection says what the connection is in one line, lists the `coffer` MCP entry and the memory delivery hook with where each lives and its health, and carries the one fix the state calls for at its title's right — **Connect** or **Repair** as a solid button, **Check again** as an outline one — and none while the agent is healthy. What this agent can use is six tiles, three by two — MCP servers, Skills, Config files, Plugins, Hooks and Memory — each with its count, one fact and, when something of the agent's own waits for a look, a warning "N to review"; a tile opens its tab. Model reads **Provider**, **Model**, **Effort** and **Route** (through Coffer's proxy, with **Test**, or direct) and carries **Change…**, which opens the Change model dialog of [provider-switching](../provider-switching/spec.md) "Review a model change before writing it"; opening the page with `?change-model=1` opens that dialog on arrival. With the `models` feature off the section is read-only and shows no Provider row and no Change. Details reads **Version**, **Config directory**, **UID** and **Registered**, with no Title, Name or Type, because an agent's name is fixed to its type.
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
- **WHEN** the user connects Codex from its row on the Agents page
- **THEN** each action calls the corresponding REST endpoint (`POST /api/v1/agents`, then the connection route) and produces equivalent state changes

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
- **GIVEN** an agent that is not connected, one that is connected and one that needs repair
- **WHEN** each agent's page renders
- **THEN** the header shows the agent's name with one pill reading Not connected, Connected or Needs repair, and New conversation beside the ⋯ menu
- **AND** no header carries a Connect, Repair or Check again button, because those sit on the Overview's Connection section

### Requirement: Audit every agent lifecycle event
The system MUST record an audit entry, carrying timestamp, actor and the affected agent reference, for every lifecycle event: agent created, updated, removed (via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events); config file written/deleted (`agent_config_file_written` / `agent_config_file_deleted`); Coffer MCP installed/uninstalled; MCP entry removed/adopted (`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`); plugin toggled/uninstalled (`agent_plugin_toggled` / `agent_plugin_uninstalled`). Discovery and all workspace listings — MCP entries, plugins, config files, native memory stores, transcript sessions, the model catalogue, the Coffer connection status — are read-only and emit no audit event, the background pass that warms the transcript summary cache included. Reading ONE of the listed items — a single session's turns, a single store's files — is the same act at a smaller scale and audits nothing either. A connect or disconnect records the events of the parts it installs or removes and none of its own; the memory delivery hook's events are memory's, not this spec's.

#### Scenario: audit lifecycle events
- **GIVEN** the user has registered, edited, or removed agents
- **WHEN** they view the audit log
- **THEN** every lifecycle change (create, update, remove) appears via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events, each carrying timestamp, actor, and the affected agent reference. (Discovery is read-only and registers nothing, so it emits no audit event of its own.)

### Requirement: Show the Coffer connection on the agent pages
An agent has one unconnected state, **Not connected**, and one word per other state: **Connected**, **Needs repair** (the `partial` state), **Hook not approved** (on the agent's own page: Codex has not approved, or approved an earlier command of, Coffer's memory hook), **Config left behind** and, for an added agent whose program and directory are both gone, **Not found**. A newly found agent that was never added and an agent that was disconnected are the same state, so both read Not connected and both offer **Connect**; the list has no "Not added" or "Detected" word and no Add action. Each row of the Agents list MUST show the agent's state and the one action that state calls for: **Connect** for one not connected — which, for a newly found agent, registers it under its default config directory first — **Repair** for one that needs repair, and none for one that is connected, whose ⋯ menu carries **Disconnect**. An agent whose program is not on this machine has no button: its ⋯ menu leads with the daemon's install prompt. The same states offer the same actions on the agent's own page, in the Overview's Connection section (**Connect** and **Repair** as solid buttons, **Check again** as an outline one while Codex has not approved Coffer's hook), never in the page header. The ⋯ menu, on the row and on the page, holds **Use a different config directory…**, **Reveal config directory**, **Copy uid**, and **Disconnect** while a part is installed, in that order after the install prompt where there is one, and never repeats the visible button.

Connect, Repair and Disconnect MUST each open **Review changes** first — every file it will write and the lines it adds or removes, the connection test as the daemon reports it — and write nothing until the user applies it; **Use a different config directory…** on a connected agent moves Coffer's entry and hook to the new directory through the same review, and on an agent not yet added it registers the directory without connecting. The list has two rows, so it carries no row selection and no bulk bar. Which parts a connection installs MUST be explained behind a help affordance beside the action rather than as inline text. The Memory tab MUST NOT carry a separate install or remove action for the memory delivery hook beyond the Repair of "Show what Coffer manages for an agent in one row".

#### Scenario: the Overview offers the action the state calls for
- **GIVEN** an agent's page for an agent that is not connected, one that is connected, and one whose connection is partial
- **WHEN** each Overview's Connection section renders
- **THEN** the unconnected agent offers Connect, the connected one offers no button and has Disconnect in its ⋯ menu, and the partial one reads Needs repair and offers Repair
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

### Requirement: Serve each agent type's model catalogue from its one agent
`GET /api/v1/agent-providers/{agent_key}/models` MUST answer, per agent type, which models a picker offers for that agent: the agent's own catalogue, read back from the installed agent and never written down in Coffer, unless the connection the agent runs on curates a set of ids — then those ids, as [provider-switching](../provider-switching/spec.md) "Serve one model list to every surface" defines. Each entry MUST carry `id` (passed to the agent verbatim), `label`, `description`, the reasoning `efforts` its runtime reports and the `default_effort` it would use, keeping a reported default only when it is one of the offered levels. An unknown `agent_key` MUST be a 404. The catalogue reads the native config of the type's one agent ("Keep one agent per type, named by it"), which is also the agent a chat turn on that type runs against ([chat](../chat/spec.md) "Run Claude Code and Codex as subprocess providers on the type's one agent").

#### Scenario: list the models an agent can be put on
- **GIVEN** a registered `codex` agent whose own config names a model
- **WHEN** the user requests `GET /api/v1/agent-providers/codex/models`
- **THEN** the response lists that model with `id`, `label`, `description`, `efforts` and `default_effort`
- **AND** the same request for an unknown agent key answers 404

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

### Requirement: Show what Coffer manages for an agent in one row
The agent's Skills, MCP servers, Hooks and Memory tabs MUST each hold two parts in the same order: what Coffer manages for the agent first, then what the agent has of its own. There is no owner column, no owner mark on a row, and no filter that switches between the two.

On **Skills** and **MCP servers**, Coffer's part MUST be one **From Coffer** row — how many skills, or servers, Coffer delivers to or serves this agent, their first names, and a link (**Open Skills ›**, **Open MCP servers ›**) to that kind's own page narrowed to this agent (`/skills?agent=<uid>`, `/mcp-servers?agent=<uid>`) — and Coffer's items MUST NOT be listed one by one on the agent's tab. Those two global lists MUST accept the `agent` query parameter and show only what reaches that agent. The agent's own part is a section titled "<Agent>'s own skills" or "<Agent>'s own MCP servers" with a one-line explanation and a search; its items are listed with one state word each — Unmanaged, Invalid SKILL.md, Foreign link, Duplicate, Bypasses Coffer — and at most one button, the fix for that row, with the rest in its ⋯ menu:

- **Skills** — **Adopt** an agent's own skill ([skill-manager](../skill-manager/spec.md) "Adopt an unmanaged skill into the master store"), which opens a form asking for the skill's **name in Coffer** and its **reach** (every agent by default, only chosen agents, or off), and **Delete duplicate** on a skill folder that has the same name as a skill Coffer delivers to that agent, which deletes the agent's copy behind a confirmation. A row opens the unmanaged skill's own page, with its properties and its files in the shared file tree and viewer.
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
