## ADDED Requirements

### Requirement: List every hook in the agent's native config
The system MUST list, read only, every command hook the agent will run. That covers the hooks in the agent's own hook-carrying files (the type's child spec names them) and those in each enabled plugin's hook file. Each is listed with its event, matcher, command, timeout, source (`user` or `plugin`, with the plugin's id) and the file that declares it. Project-level settings are not read, because Coffer does not know which repositories the agent is used in.

The listing MUST be served by `GET /api/v1/agents/{uid}/hooks` as the hooks (`items`) and the files that did not parse (`parse_errors`), and MUST write nothing and record no audit event. A file that does not parse MUST be reported as a parse error beside the hooks the other files yield. Coffer installs no hook into an agent, so no hook is marked as Coffer's and the listing carries no health, trust or last fire.

Each listed hook MUST also carry where it sits in its file — `group_index` and `hook_index`, the positions in `hooks.<event>[group_index].hooks[hook_index]` — so a person can find the entry, and the REST listing reports them.

On the agent's Hooks tab the agent's hooks are one table of Event, Command, Matcher and File, with a search over the command and an **Event** filter that lists each event with its count; the table says how many of how many are shown once either narrows it. A file that does not parse is named above the table. A row opens a read-only details dialog with the command in full, the event and when it runs, the matcher, the type, the timeout, the file and the entry's position in it (`hooks.<event>[group].hooks[hook]`), with **Copy command** and **Open in editor**; nothing in the dialog writes, because a hook is changed in its own file, in the person's own editor. A file name opens that file in the preferred editor (see "Open config files in an external editor or reveal them").

#### Scenario: list an agent's hooks
- **GIVEN** a registered Claude Code agent whose `settings.json` carries a `PreToolUse` hook, whose `settings.local.json` carries a `Stop` hook, and which has one enabled and one disabled plugin with a hook file each
- **WHEN** the user lists the agent's hooks
- **THEN** the `PreToolUse` hook, the `Stop` hook and the enabled plugin's hook are listed with their sources and files, and the disabled plugin's hook is not
- **AND** nothing is written or audited

#### Scenario: list the hooks with their position in the file
- **GIVEN** a Claude Code `settings.json` whose `PreToolUse` event holds two groups, the second with two hooks
- **WHEN** the user lists the agent's hooks
- **THEN** the second hook of the second group reports `group_index` 1 and `hook_index` 1, and the first group's hook reports 0 and 0

#### Scenario: the Hooks tab lists the agent's own hooks
- **GIVEN** a Claude Code agent whose settings files and an enabled plugin carry hooks of its own
- **WHEN** the user opens the agent's Hooks tab
- **THEN** the tab is one table with a row per hook, with no block for a hook of Coffer's
- **AND** choosing a row opens a read-only dialog with the command, event, matcher, type, timeout, file and position, and searching or filtering by event narrows the table and says how many of how many show

### Requirement: Report an agent's Coffer connection part by part
The system MUST report an agent's Coffer connection (`GET /api/v1/agents/{uid}/coffer-connection`) as the list of parts its type has — today the one `mcp` part — each with its key, whether it is installed, and the installed command when it is — and a state: `connected` when every listed part is installed, `disconnected` when none is, and `partial` otherwise, which a type with one part never reports. The report MUST be read from the agent's own configuration files on demand, never stored, and MUST write nothing and record no audit event.

#### Scenario: read an agent's connection without writing anything
- **GIVEN** a registered agent without the gateway entry
- **WHEN** the user reads its Coffer connection, connects it, and reads it again
- **THEN** the first read reports `disconnected` with the `mcp` part not installed, and the second `connected` with the `mcp` part installed and its shim command
- **AND** neither read writes a file or records an audit event

## MODIFIED Requirements

### Requirement: Audit every agent lifecycle event
The system MUST record an audit entry, carrying timestamp, actor and the affected agent reference, for every lifecycle event: agent created, updated, removed (via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events); Coffer MCP installed/uninstalled; MCP entry removed/adopted (`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`); plugin toggled/uninstalled (`agent_plugin_toggled` / `agent_plugin_uninstalled`). Discovery and all workspace listings — MCP entries, plugins, config files, native memory stores, native sessions, the model catalogue, the Coffer connection status — are read-only and emit no audit event. Reading ONE of the listed items — a single store's files — is the same act at a smaller scale and audits nothing either, and renaming or deleting a native session is the agent's own act on its own record ("Rename and delete a native session through the agent") and is not audited here. A connect or disconnect records the events of the parts it installs or removes and none of its own. The `agent_config_file_written` and `agent_config_file_deleted` events are no longer recorded; rows an earlier version recorded keep their wording in Activity.

#### Scenario: audit lifecycle events
- **GIVEN** the user has registered, edited, or removed agents
- **WHEN** they view the audit log
- **THEN** every lifecycle change (create, update, remove) appears via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events, each carrying timestamp, actor, and the affected agent reference. (Discovery is read-only and registers nothing, so it emits no audit event of its own.)

### Requirement: Show the Coffer connection on the agent pages
An agent has one unconnected state, **Not connected**, and one word per other state: **Connected**, **Needs repair** (the `partial` state), **Config left behind** and, for an added agent whose program and directory are both gone, **Not found**. A newly found agent that was never added and an agent that was disconnected are the same state, so both read Not connected and both offer **Connect**; the list has no "Not added" or "Detected" word and no Add action. Each row of the Agents list MUST show the agent's state and the one action that state calls for: **Connect** for one not connected — which, for a newly found agent, registers it under its default config directory first — **Repair** for one that needs repair, and none for one that is connected, whose ⋯ menu carries **Disconnect**. An agent whose program is not on this machine has no fix Coffer can make: its row offers the daemon's install prompt as the hand-off split button **Ask an agent ▾** before its ⋯ menu (web-ui "Hand a machine-dependent problem to an agent with one split button"), and its own page offers it in the Overview. The same states offer the same actions on the agent's own page, in the Overview's Connection section (**Connect** and **Repair** as solid buttons), never in the page header. The ⋯ menu, on the row and on the page, holds **Use a different config directory…**, **Reveal config directory**, **Copy uid**, and **Disconnect** while a part is installed, in that order, and never repeats a visible action — the install prompt included.

Connect, Repair and Disconnect MUST each open **Review changes** first — every file it will write and the lines it adds or removes, the connection test as the daemon reports it — and write nothing until the user applies it; **Use a different config directory…** on a connected agent moves Coffer's entry to the new directory through the same review, and on an agent not yet added it registers the directory without connecting. The list has two rows, so it carries no row selection and no bulk bar. Which parts a connection installs MUST be explained behind a help affordance beside the action rather than as inline text.

#### Scenario: the Overview offers the action the state calls for
- **GIVEN** an agent's page for an agent that is not connected, one that is connected, and one whose connection is partial
- **WHEN** each Overview's Connection section renders
- **THEN** the unconnected agent offers Connect, the connected one offers no button and has Disconnect in its ⋯ menu, and the partial one reads Needs repair and offers Repair

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

### Requirement: Connect an agent to Coffer in one action
Users MUST be able to connect an agent to Coffer in one action, from the REST API (`POST /api/v1/agents/{uid}/coffer-connection`) and the web UI. Connecting MUST install every **part** Coffer writes into the agent's own configuration for that agent's type. Today every type has one part:

- `mcp` — the gateway MCP entry of "Install Coffer's MCP server into an agent in one action".

Coffer writes no hook into an agent. A connect refused for want of a shim writes nothing. Every part MUST be installed through its own atomic write with a backup and record its own audit event, as it does when installed alone. Connecting MUST be idempotent: connecting a connected agent rewrites each entry in place and never duplicates one.

#### Scenario: connect installs every part that applies
- **GIVEN** a registered Claude Code agent without the gateway entry
- **WHEN** the user connects it to Coffer
- **THEN** the agent's `.claude.json` carries the `coffer` MCP entry, naming the agent by its uid
- **AND** one `agent_mcp_installed` audit entry names the user as actor, and the connection reports `connected` with its `mcp` part installed

### Requirement: Disconnect an agent from Coffer
Users MUST be able to disconnect an agent from Coffer in one action (`DELETE /api/v1/agents/{uid}/coffer-connection`, the web UI). Disconnecting MUST remove every part the agent type has, taking out only Coffer's own marked entries and leaving every other entry, key and hook in those files as it was. A part that is absent MUST be a no-op that writes no file and records no audit event.

#### Scenario: disconnect removes only Coffer's entries
- **GIVEN** a connected Claude Code agent whose `.claude.json` also carries another MCP server and whose `settings.json` carries a hook and settings of its own
- **WHEN** the user disconnects it from Coffer
- **THEN** the `coffer` MCP entry is gone, the other MCP server and the agent's own hook and settings are untouched, and the connection reports `disconnected`
- **AND** disconnecting again writes no file and records no audit entry

### Requirement: List the supported agents as fixed rows on the Agents page
The Agents page MUST list exactly one row per supported agent type — today two, Claude Code and Codex — whether or not each is installed or added, in that order, so the page reads the same on every machine and a first-time user sees at once what Coffer can manage. Each row is found automatically from the detection state of "Detect an agent by its program and its config directory": an `installed_active` type's row reads as its Coffer state ("Show the Coffer connection on the agent pages") with its config directory and version; an `installed_never_run` type reads Not connected too, with its config directory marked as not created, and offers Connect, whose review names the directory it creates and the only entries Coffer needs in it; a `config_only` type reads as config left behind — program not found — and a `missing` type as not installed, each with no Connect and the daemon's prompt that hands reinstalling or installing it to an agent (see "Hand installing an agent's program to an agent") as the split button **Ask an agent ▾** beside its ⋯ menu — Copy prompt behind the chevron, and Copy prompt alone while no other agent can run it. A row whose program is missing shows no version, and its second line says "Not on this Mac" or what is left in the directory. The page MUST NOT show an install command, and carries no Remove action. On first run, with neither agent connected and both connectable, the page MUST offer **Connect both**, which reviews and connects every connectable agent in one confirmation. An agent is named by its type everywhere in the web UI; the page offers no field to name or title one.

Overview's Needs you lists only agents that need the person: an agent that needs repair and one whose config directory is left behind. Not installed, Not connected and a first run raise none.

#### Scenario: the agents page shows both supported agents on first run
- **GIVEN** a fresh Coffer with Claude Code and Codex both installed and neither connected
- **WHEN** the user opens the Agents page
- **THEN** it shows exactly two rows, Claude Code then Codex, each reading Not connected with a Connect action, and a Connect both action, and Overview lists neither as needing the person
- **AND** choosing Connect both reviews the writes for both agents and, on apply, registers and connects both

#### Scenario: an agent that is not installed shows how to install it
- **GIVEN** Codex not installed on the machine
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as not installed and offers the hand-off split button carrying the daemon's prompt that hands installing Codex to an agent, shows no install command, and has no Connect action
- **AND** its ⋯ menu offers neither Copy prompt nor Ask an agent

#### Scenario: an installed agent that has never run can be added
- **GIVEN** Codex's program installed and `~/.codex` not created
- **WHEN** the Agents page renders and the user chooses Connect on the Codex row
- **THEN** the row reads Not connected, with `~/.codex` marked not created
- **AND** the review names `~/.codex` as created and lists only the entries Coffer adds, and nothing is written until the user applies it

#### Scenario: a leftover config directory reads as config left behind
- **GIVEN** `~/.codex` present and the Codex program not on the agent's `PATH`
- **WHEN** the Agents page renders
- **THEN** the Codex row reads as config left behind — program not found — offering the hand-off split button with the daemon's reinstall prompt, no install command, and no Connect action
- **AND** Overview's Needs you lists it

#### Scenario: a row's menu offers a different config directory
- **GIVEN** a Claude Code row on the Agents page
- **WHEN** the user opens the row's menu
- **THEN** it offers Use a different config directory…, and the page carries no Add agent dialog, no Remove action and no name or title field

### Requirement: Show what Coffer manages for an agent in one row
The agent's Skills and MCP servers tabs MUST each hold two parts in the same order: what Coffer manages for the agent first, then what the agent has of its own. There is no owner column, no owner mark on a row, and no filter that switches between the two.

On **Skills** and **MCP servers**, Coffer's part MUST be one **From Coffer** row — how many skills, or servers, Coffer delivers to or serves this agent, their first names, and a link (**Open Skills ›**, **Open MCP servers ›**) to that kind's own page narrowed to this agent (`/skills?agent=<uid>`, `/mcp-servers?agent=<uid>`) — and Coffer's items MUST NOT be listed one by one on the agent's tab. The MCP servers tab carries a second **From Coffer** row for custom-tool groups, which the MCP servers row does not count, linking to `/custom-tools?agent=<uid>` (**Open Custom tools ›**). Those global lists MUST accept the `agent` query parameter and show only what reaches that agent. The agent's own part is a section titled "<Agent>'s own skills" or "<Agent>'s own MCP servers" with a one-line explanation and a search; its items are listed with one state word each — Unmanaged, Invalid SKILL.md, Foreign link, Duplicate, Bypasses Coffer — and at most one button, the fix for that row, with the rest in its ⋯ menu:

- **Skills** — **Adopt** an agent's own skill ([skill-manager](../skill-manager/spec.md) "Adopt an unmanaged skill into the master store"), which opens a form asking for the skill's **name in Coffer** and its **reach** (every agent by default, only chosen agents with at least one ticked, or off), and **Delete duplicate** on a skill folder that has the same name as a skill Coffer delivers to that agent, which deletes the agent's copy behind a confirmation. A row opens the unmanaged skill's own page, with its properties and its files in the shared file tree and viewer.
- **MCP servers** — **Adopt** a direct entry ("Adopt a direct MCP entry into Coffer"), and **Remove duplicate** on a direct entry that `matches_resource` a registered MCP server, which removes it from its source file ("Remove a direct MCP entry from its source file") because Coffer's gateway already serves it; any entry can be taken out of its file from its ⋯ menu. A config file that does not parse is named above the list, and its entries stay read-only.

The **Hooks**, **Memory** and **Plugins** tabs have only the agent's own part: Coffer installs no hook and no plugin, and what memory sync writes into the agent is shown on the Memory page ([memory](../memory/spec.md) "Manage memory sync in the web UI and on the command line"), while the Memory tab lists the agent's native memory stores as they are.

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

#### Scenario: custom-tool groups have their own From Coffer row
- **GIVEN** an agent reached by one registered MCP server and one custom-tool group
- **WHEN** the user opens its MCP servers tab
- **THEN** the MCP servers row reads one server and links to `/mcp-servers?agent=<uid>`, and a second row reads one custom-tool group and links to `/custom-tools?agent=<uid>`

### Requirement: List an agent's native sessions through the agent
The system MUST expose a read-only listing of an agent's native sessions,
`GET /api/v1/agents/{uid}/sessions`, asked of the agent's own session interface
rather than read from its files; how each type is asked is its child spec's
([agent-registry/claude-code](claude-code/spec.md) "List Claude Code sessions through the Agent SDK",
[agent-registry/codex](codex/spec.md) "List Codex sessions through the app-server"). Each row carries
its `session_id`, a `title` (the title the agent itself shows for the session —
its custom title, else its summary, else its first prompt — secret-scrubbed),
`cwd`, `created_at` and `last_activity_at`. When the session is a channel
conversation's, the row also carries `conversation_id`, `running`, `needs_you` and the
conversation's channel binding, read from the conversation index and the turn
platform's in-memory state, so the Sessions tab and the Conversations page open the
same busy dialog for it ([chat](../chat/spec.md) "Ask before opening a session that is running").
The listing MUST support a case-insensitive substring search `q` over title and
working directory (for Codex, the search the app-server itself offers), and `limit`/`cursor` paging, newest activity first with `session_id` as the
tie-break, alongside the matched `total` ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor"),
because an agent accumulates thousands of sessions and the surface cannot load them all.

The listing carries no session text, Coffer stores none, and nothing is written:
it emits no audit event. Coffer does not distil sessions into memory:
[memory](../memory/spec.md) "Reintroduce no retired memory mechanism" forbids transcript distillation.

#### Scenario: browse an agent's native sessions with title and search
- **GIVEN** a registered agent with several native sessions across more than one project
- **WHEN** the agent's sessions are listed with a search query and a `limit`
- **THEN** each row carries a title, `cwd`, `created_at` and `last_activity_at`; only sessions whose title or working directory matches the search are returned, newest activity first, paged by `limit` and the answer's `next_cursor` alongside the matched total
- **AND** the read emits no audit event and writes nothing

#### Scenario: a channel conversation's session carries its conversation
- **GIVEN** a session that a channel conversation points at, with a turn running on it
- **WHEN** the agent's sessions are listed
- **THEN** its row carries the `conversation_id`, `running` true, `needs_you` and the channel binding, while a session no conversation points at carries none of them

### Requirement: Offer every agent operation over REST and on the Agents page
Every management operation — register/list/view/update/remove, the config-file listing and preview, Coffer connect/disconnect/connection status, MCP entry list/view/remove/adopt, plugin list/detail/toggle/uninstall, the hooks listing, native session listing, rename and delete, and the model catalogue — MUST be available through (a) the REST API, (b) the Agents page in the web UI and (c) the `coffer agent` commands, which call the same routes ([resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"). An agent's config files and native-memory files are its own plain files: their listings are commands, their content is read with the reader's own tools.

- the lifecycle of "Manage the agent lifecycle" under `/api/v1/agents`;
- the config-file listing at `GET /api/v1/agents/{uid}/config-files` and one file's preview at `GET /api/v1/agents/{uid}/config-files/{key}/content`;
- the agent's Coffer connection under `/api/v1/agents/{uid}/coffer-connection` ("Connect an agent to Coffer in one action");
- direct MCP entries under `/api/v1/agents/{uid}/mcp-entries`;
- plugins under `/api/v1/agents/{uid}/plugins`, where `DELETE` is the uninstall of "Uninstall a plugin by the type's own strategy";
- the hooks of "List every hook in the agent's native config" at `GET /api/v1/agents/{uid}/hooks`;
- native sessions at `GET /api/v1/agents/{uid}/sessions` ("List an agent's native sessions through the agent"), renamed with `PATCH` and deleted with `DELETE` at `/api/v1/agents/{uid}/sessions/{session_id}` ("Rename and delete a native session through the agent");
- the model catalogue at `GET /api/v1/agent-providers/{agent_key}/models`.

The listing of an agent's config files, one config file's preview and the reads of its native memory stores' files are served over REST for the web UI, and the Overview's Details names the config directory for anyone who wants the files themselves. The model catalogue's route takes the agent type it is keyed by (`claude_code`, `codex`), not an agent's name, and an unknown type is its not-found.

The Agents page in the web UI MUST expose all of these. It renders within the web-ui shell at `/agents` as the first entry of the sidebar's Agents group ([web-ui](../web-ui/spec.md) "Group the sidebar by what the user comes to do"), never among the Capabilities or Context entries, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file is shown read-only and never edited in the page: selecting it in the tree previews it beside the tree, and the preview's toolbar opens it in the person's editor or reveals it ("Open config files in an external editor or reveal them"). Every place the page shows a file the agent holds read-only — a native memory store, an unmanaged skill's folder — uses the same file tree and the same viewer toolbar, so a file reads the same wherever it is opened.
- The agent detail page's **header** carries the agent's mark, its name, one status pill and a **⋯** menu, and nothing under the name: the version and the config directory are on the Overview. The pill reads Connected, Not connected, Needs repair or Config left behind. The header never turns into a fix button — Connect and Repair sit on the Overview's Connection section. **Rotate proxy token** is in ⋯ only while the agent routes through Coffer's proxy ([provider-switching](../provider-switching/spec.md) "Authenticate each agent to the proxy with its own local token").
- The detail page has eight tabs, none carrying a count: six in the strip — **Overview**, **Skills**, **MCP servers**, **Hooks**, **Config files** and **Sessions** — and, behind a **More** menu, **Plugins** and **Memory**, the least used. Each is addressable by its own path (`/agents/<type>` for Overview, then `/agents/<type>/skills`, `/mcp-servers`, `/hooks`, `/config`, `/sessions`, `/plugins` and `/memory`), so a page opened from a tab returns to it. While the open tab is one of the two in More, the More trigger reads that tab's name and carries the underline; a tab in More that needs attention puts a warning dot on More. There is **no Model tab**: an agent's model is a section of the Overview, and `/agents/<type>/model` is not a page.
  - **Overview** stacks, top to bottom, **Connection**, **What this agent can use**, **Model** and **Details**. Connection says what the connection is in one line, lists the `coffer` MCP entry with where it lives and its health, and carries the one fix the state calls for at its title's right — **Connect** or **Repair** as a solid button — and none while the agent is healthy. What this agent can use is six tiles, three by two — MCP servers, Skills, Config files, Plugins, Hooks and Memory — each with its count, one fact and, when something of the agent's own waits for a look, a warning "N to review"; a tile opens its tab. Model reads **Provider**, **Model** and **Route** (through Coffer's proxy, with **Test**, or direct) and carries **Change…**, which opens the Change model dialog of [provider-switching](../provider-switching/spec.md) "Review a model change before writing it"; opening the page with `?change-model=1` opens that dialog on arrival. Details reads **Version**, **Config directory**, **UID** and **Registered**, with no Title, Name or Type, because an agent's name is fixed to its type.
  - **Skills** and **MCP servers** open with Coffer's part and then the agent's own, per "Show what Coffer manages for an agent in one row". **Plugins** lists the agent's installed plugins — all its own, since Coffer installs none — with a search, an enabled switch and a ⋯ menu whose only item is Uninstall…, and a plugin's name opens an information dialog.
  - **Hooks** lists the agent's own hooks, per "List every hook in the agent's native config". The tab is read only.
  - **Config files** lists every allowlisted config file of "Define a curated config-file allowlist per type" as a file tree beside a read-only preview — the settings files and the human-authored instructions files (`CLAUDE.md`, `AGENTS.md`) alike, because an instructions file is configuration the person wrote, not something installed — each previewed on the right, opened in the editor or revealed ("Open config files in an external editor or reveal them").
  - **Memory** lists **the agent's own memory stores**, read-only; what memory sync writes into the agent is shown on the Memory page ([memory](../memory/spec.md) "Manage memory sync in the web UI and on the command line"). **Sessions** — the agent's own session history, asked of the agent itself — is one list whose rows open in the terminal ("Open an agent's sessions from its Sessions tab").
- A direct server's name on the MCP servers tab opens that entry's read-only JSON in a dialog ("Show one direct MCP entry's full configuration without its secrets"), whose footer carries the row's two writes — remove it from its file (Remove, or Remove duplicate when Coffer already serves it) and adopt it into Coffer — around Close.
- The Memory list carries no per-row actions: a row OPENS its subject, and the open / reveal affordances live on the page it opens, beside the thing they act on. A Memory row opens that store's directory as a file tree with a read-only preview, because a store is a directory.

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
- **GIVEN** a registered agent with config files and a native memory store on disk
- **WHEN** the user reads the agent's config-file listing and native-memory scan over REST
- **THEN** each reports the absolute locations of the files for that agent
- **AND** nothing is written and no audit event is recorded

#### Scenario: list an agent's models
- **GIVEN** the catalogue route offers two `codex` models
- **WHEN** the user reads `GET /api/v1/agent-providers/codex/models`
- **THEN** each model carries its id and its label
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

#### Scenario: the header carries one status pill and a menu
- **GIVEN** an agent that is not connected, one that is connected and one that needs repair
- **WHEN** each agent's page renders
- **THEN** the header shows the agent's name with one pill reading Not connected, Connected or Needs repair, and the ⋯ menu
- **AND** no header carries a Connect or Repair button, because those sit on the Overview's Connection section

#### Scenario: the Sessions tab calls the session routes
- **GIVEN** a registered agent with a native session
- **WHEN** the user renames it from its row's ⋯ menu and then deletes it
- **THEN** each action calls the corresponding REST endpoint (`PATCH` then `DELETE /api/v1/agents/{uid}/sessions/{session_id}`) and produces the same state as calling that endpoint directly

## REMOVED Requirements

### Requirement: Report an agent whose Coffer hook never fires
**Reason**: Coffer installs no hook into an agent, so there is no hook of Coffer's to report as never firing; the `agent_hook_attention` item is gone.
**Migration**: None. An agent that needs repair or whose config directory is left behind is still listed by "List the supported agents as fixed rows on the Agents page".

### Requirement: List every hook in the agent's native config (before memory sync)
**Reason**: A MODIFIED block cannot drop a scenario, and this requirement loses "list an agent's hooks with Coffer's own marked", "report a stale Coffer hook", "coffer's memory hook leads the Hooks tab and the agent's own follow", which described the retired memory layer; it is renamed out of the way, removed, and added again under its own title (see ADDED below).
**Migration**: The dropped scenarios' markers are deleted or pointed at the scenarios of the requirement added again.

### Requirement: Report an agent's Coffer connection part by part (before memory sync)
**Reason**: A MODIFIED block cannot drop a scenario, and this requirement loses "report a partly installed connection", which described the retired memory layer; it is renamed out of the way, removed, and added again under its own title (see ADDED below).
**Migration**: The dropped scenarios' markers are deleted or pointed at the scenarios of the requirement added again.

## RENAMED Requirements

- FROM: `### Requirement: List every hook in the agent's native config`
- TO: `### Requirement: List every hook in the agent's native config (before memory sync)`

- FROM: `### Requirement: Report an agent's Coffer connection part by part`
- TO: `### Requirement: Report an agent's Coffer connection part by part (before memory sync)`
