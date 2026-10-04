## REMOVED Requirements

### Requirement: Keep the transcript summary sidecar disposable
**Reason**: Coffer no longer parses transcripts, so it derives no summaries and keeps no sidecar. Listings come from the agent's own session interface on every read.
**Migration**: None. Delete `~/.coffer/derived/cache/agent/` if it exists; nothing reads it, and "Report what Coffer stores and clear the rebuildable cache" in [daemon](../daemon/spec.md) no longer counts it.

### Requirement: Read one transcript session in bounded windows
**Reason**: Coffer is not a second reader of the agent's conversations. A session is read in the agent's own interface, which a row of the Sessions tab opens in the terminal.
**Migration**: Open the session from its row ("Open an agent's sessions from its Sessions tab"). `GET /api/v1/agents/{uid}/transcripts/session` is removed.

### Requirement: Lead a transcript turn with the person's own words
**Reason**: There is no transcript reader to render turns: Coffer shows no session body.
**Migration**: None. The agent's own interface shows its sessions.

### Requirement: List an agent's transcript sessions read-only
**Reason**: The listing is no longer a parse of the agent's transcript files with Coffer's own title rule, message count, source path and sort keys; it is the agent's own session list (title, directory, times) with search and paging. Three of its scenarios describe the removed parse.
**Migration**: See "List an agent's native sessions through the agent" ("browse an agent's native sessions with title and search" replaces "browse an agent's transcript history with title, search, and sort"; "a new Claude Code session does not shift the next page" in the claude-code child replaces "a new transcript session does not shift the next page"; "keep attachment markers out of a session's title" is dropped). `GET /api/v1/agents/{uid}/transcripts` is removed.

### Requirement: Expose every agent operation over REST and on the Agents page
**Reason**: It lists transcript routes, a session reader and a New conversation header button that no longer exist, and two of its scenarios ("read one transcript session over REST", "the header carries one status pill and a fixed action pair") describe them. The rest of the requirement is unchanged.
**Migration**: See "Offer every agent operation over REST and on the Agents page" ("the header carries one status pill and a menu" replaces "the header carries one status pill and a fixed action pair"; "read one transcript session over REST" is dropped).

## MODIFIED Requirements

### Requirement: Audit every agent lifecycle event
The system MUST record an audit entry, carrying timestamp, actor and the affected agent reference, for every lifecycle event: agent created, updated, removed (via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events); config file written/deleted (`agent_config_file_written` / `agent_config_file_deleted`); Coffer MCP installed/uninstalled; MCP entry removed/adopted (`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`); plugin toggled/uninstalled (`agent_plugin_toggled` / `agent_plugin_uninstalled`). Discovery and all workspace listings — MCP entries, plugins, config files, native memory stores, native sessions, the model catalogue, the Coffer connection status — are read-only and emit no audit event. Reading ONE of the listed items — a single store's files — is the same act at a smaller scale and audits nothing either, and renaming or deleting a native session is the agent's own act on its own record ("Rename and delete a native session through the agent") and is not audited here. A connect or disconnect records the events of the parts it installs or removes and none of its own; the memory delivery hook's events are memory's, not this spec's.

#### Scenario: audit lifecycle events
- **GIVEN** the user has registered, edited, or removed agents
- **WHEN** they view the audit log
- **THEN** every lifecycle change (create, update, remove) appears via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events, each carrying timestamp, actor, and the affected agent reference. (Discovery is read-only and registers nothing, so it emits no audit event of its own.)

## ADDED Requirements

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
it emits no audit event. Coffer does not distil sessions into memory: the agent's own
memory is memory's domain, and [memory](../memory/spec.md) "Reintroduce no retired mechanism" forbids reintroducing a
path that writes back into it.

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
Every management operation — register/list/view/update/remove, config-file write and delete (including directory children), Coffer connect/disconnect/connection status, MCP entry list/view/remove/adopt, plugin list/detail/toggle/uninstall, the hooks listing, native session listing, rename and delete, and the model catalogue — MUST be available through (a) the REST API and (b) the Agents page in the web UI. The command line carries none of them: it has no `agent` command group.

- the lifecycle of "Manage the agent lifecycle" under `/api/v1/agents`;
- config-file reads, writes and deletes of directory children under `/api/v1/agents/{uid}/config-files`;
- the agent's Coffer connection under `/api/v1/agents/{uid}/coffer-connection` ("Connect an agent to Coffer in one action");
- direct MCP entries under `/api/v1/agents/{uid}/mcp-entries`;
- plugins under `/api/v1/agents/{uid}/plugins`, where `DELETE` is the uninstall of "Uninstall a plugin by the type's own strategy";
- the hooks of "List every hook in the agent's native config" at `GET /api/v1/agents/{uid}/hooks`;
- native sessions at `GET /api/v1/agents/{uid}/sessions` ("List an agent's native sessions through the agent"), renamed with `PATCH` and deleted with `DELETE` at `/api/v1/agents/{uid}/sessions/{session_id}` ("Rename and delete a native session through the agent");
- the model catalogue at `GET /api/v1/agent-providers/{agent_key}/models`.

The reads of plain files on disk — an agent's config files and their content and the files of its native memory stores — are served over REST for the web UI, and the Overview's Details names the config directory for anyone who wants the files themselves. The model catalogue's route takes the agent type it is keyed by (`claude_code`, `codex`), not an agent's name, and an unknown type is its not-found.

The Agents page in the web UI MUST expose all of these, config-file content writes included. It renders within the web-ui shell at `/agents` as the first entry of the sidebar's Agents group ([web-ui](../web-ui/spec.md) "Group the sidebar by what the user comes to do"), never among the Capabilities or Context entries, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file (and a directory-entry child) opens in a viewer that becomes **editable behind an explicit Edit**, saves through the same path as REST ("Validate config-file content before saving it", "Write config files atomically with a backup and an audit entry"), and guards an unsaved draft three ways — picking another file asks first, leaving the tab asks first, and leaving the page asks first. Open-in-external-editor / reveal-in-file-manager sit beside the content for the edits that want a real editor. Every place the page shows a file the agent holds — Config files, a native memory store, an unmanaged skill's folder — uses the same file tree and the same viewer toolbar, so a file reads the same wherever it is opened.
- The agent detail page's **header** carries the agent's mark, its name, one status pill and a **⋯** menu, and nothing under the name: the version and the config directory are on the Overview. The pill reads Connected, Not connected, Needs repair, Hook not approved or Config left behind. The header never turns into a fix button — Connect, Repair and Check again sit on the Overview's Connection section. **Rotate proxy token** is in ⋯ only while the agent routes through Coffer's proxy ([provider-switching](../provider-switching/spec.md) "Authenticate each agent to the proxy with its own local token").
- The detail page has eight tabs, none carrying a count: six in the strip — **Overview**, **Skills**, **MCP servers**, **Hooks**, **Config files** and **Sessions** — and, behind a **More** menu, **Plugins** and **Memory**, the least used. Each is addressable by its own path (`/agents/<type>` for Overview, then `/agents/<type>/skills`, `/mcp-servers`, `/hooks`, `/config`, `/sessions`, `/plugins` and `/memory`), so a page opened from a tab returns to it. While the open tab is one of the two in More, the More trigger reads that tab's name and carries the underline; a tab in More that needs attention puts a warning dot on More. There is **no Model tab**: an agent's model is a section of the Overview, and `/agents/<type>/model` is not a page.
  - **Overview** stacks, top to bottom, **Connection**, **What this agent can use**, **Model** and **Details**. Connection says what the connection is in one line, lists the `coffer` MCP entry and the memory delivery hook with where each lives and its health, and carries the one fix the state calls for at its title's right — **Connect** or **Repair** as a solid button, **Check again** as an outline one — and none while the agent is healthy. What this agent can use is six tiles, three by two — MCP servers, Skills, Config files, Plugins, Hooks and Memory — each with its count, one fact and, when something of the agent's own waits for a look, a warning "N to review"; a tile opens its tab. Model reads **Provider**, **Model** and **Route** (through Coffer's proxy, with **Test**, or direct) and carries **Change…**, which opens the Change model dialog of [provider-switching](../provider-switching/spec.md) "Review a model change before writing it"; opening the page with `?change-model=1` opens that dialog on arrival. With the `models` feature off the section is read-only and shows no Provider row and no Change. Details reads **Version**, **Config directory**, **UID** and **Registered**, with no Title, Name or Type, because an agent's name is fixed to its type.
  - **Skills** and **MCP servers** open with Coffer's part and then the agent's own, per "Show what Coffer manages for an agent in one row". **Plugins** lists the agent's installed plugins — all its own, since Coffer installs none — with a search, an enabled switch and a ⋯ menu whose only item is Uninstall…, and a plugin's name opens an information dialog.
  - **Hooks** opens with **Coffer's memory hook**, then **the agent's own hooks**, per "List every hook in the agent's native config". The tab is read only apart from Repair and Check again on Coffer's hook.
  - **Config files** lists every allowlisted config file of "Define a curated config-file allowlist per type" in one file tree — the settings files and the human-authored instructions files (`CLAUDE.md`, `AGENTS.md`) alike, because an instructions file is configuration the person wrote, not something installed.
  - **Memory** leads with **Coffer's memory** — Coffer's memory hook for this agent, when it last fired and what it delivers, with a link to the Memory page and a Repair when the hook is out of date or missing — only while the `memory` feature is on, and then lists **the agent's own memory stores**, read-only ([web-ui](../web-ui/spec.md) "Show memory delivery on the Memory page"). **Sessions** — the agent's own session history, asked of the agent itself — is one list whose rows open in the terminal ("Open an agent's sessions from its Sessions tab").
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
- **AND** no header carries a Connect, Repair or Check again button, because those sit on the Overview's Connection section

#### Scenario: the Sessions tab calls the session routes
- **GIVEN** a registered agent with a native session
- **WHEN** the user renames it from its row's ⋯ menu and then deletes it
- **THEN** each action calls the corresponding REST endpoint (`PATCH` then `DELETE /api/v1/agents/{uid}/sessions/{session_id}`) and produces the same state as calling that endpoint directly

### Requirement: Rename and delete a native session through the agent
The system MUST rename and delete an agent's native sessions only through the
agent's own interface, never by editing its files: `PATCH /api/v1/agents/{uid}/sessions/{session_id}`
takes a `title`, and `DELETE /api/v1/agents/{uid}/sessions/{session_id}` removes the session. Delete is
permanent: the agent keeps no copy and Coffer keeps none. When a conversation of the turn platform points at
the session, rename also sets the conversation's title, and delete also cancels any turn in flight on it and removes
its index row — the same act as [chat](../chat/spec.md) "Rename and delete a conversation through its agent", reached
from the other list. A session id the agent does not list is `not_found` (404). An agent
that refuses the operation has its reason returned and Coffer changes nothing of its own. The
type-specific calls are in the child specs ([agent-registry/claude-code](claude-code/spec.md) "List Claude Code sessions through the Agent SDK",
[agent-registry/codex](codex/spec.md) "List Codex sessions through the app-server"). The agent owns the session, so
neither operation is audited here.

#### Scenario: rename a native session
- **GIVEN** a registered agent with a native session
- **WHEN** its title is changed with `PATCH`
- **THEN** the agent lists the session under the new title
- **AND** a conversation pointing at it shows the new title

#### Scenario: delete a native session permanently
- **GIVEN** a native session that a channel conversation points at, with a turn running on it
- **WHEN** it is deleted with `DELETE`
- **THEN** the agent no longer lists the session, the turn is cancelled and the conversation's index row is gone

#### Scenario: an unknown session is not found
- **GIVEN** a registered agent
- **WHEN** a session id the agent does not list is renamed or deleted
- **THEN** the answer is `not_found` (404) and nothing changes

#### Scenario: a refused operation changes nothing in Coffer
- **GIVEN** an agent that refuses to delete a session
- **WHEN** the user deletes it
- **THEN** the agent's reason is returned and the conversation's index row is still there

### Requirement: Open an agent's sessions from its Sessions tab
The agent detail page's **Sessions** tab MUST list the agent's native sessions
("List an agent's native sessions through the agent") as rows of the same kind the
Conversations page uses ([chat](../chat/spec.md) "Show channel conversations on the Conversations page"), without the
channel column unless the session is a channel conversation's: title, working directory and last
activity, with the channel, the Running / Needs you mark and an inline **Stop** when it is. A search
box over title and working directory filters the list in the server, and the list pages by
cursor as it is scrolled. Pressing a row, or the main part of its split button **Open in
terminal ▾ Copy command**, MUST open the session in the preferred terminal exactly as
[chat](../chat/spec.md) "Open a conversation in the terminal" says, asking first when the session is
busy ("Ask before opening a session that is running"). A hovering **⋯** menu holds **Rename** (in
place) and **Delete…**, which asks first and says the session is deleted from the agent and cannot be recovered. A
failure to load the list shows in the list's area with a Retry. The tab shows no session text.

#### Scenario: a session row opens in the terminal
- **GIVEN** an agent's Sessions tab listing a session `abc-123` in `/work/api`
- **WHEN** the user presses the row
- **THEN** the daemon is asked to open the agent's resume command for that session in `/work/api` in the preferred terminal

#### Scenario: a session that is a channel conversation shows its channel
- **GIVEN** a listed session that a SeaTalk conversation points at, with a turn running
- **WHEN** the tab renders
- **THEN** its row shows the SeaTalk badge, Running and an inline Stop, and a session no conversation points at shows none

#### Scenario: the sessions list searches title and directory
- **GIVEN** an agent with sessions titled "Alpha rollout" and "Gamma", the second in `/work/alpha-api`
- **WHEN** the user types "alpha" in the search box
- **THEN** both rows are listed

#### Scenario: deleting a session asks first
- **GIVEN** a listed session
- **WHEN** the user chooses Delete… from its ⋯ menu
- **THEN** a confirmation says it is deleted from the agent and cannot be recovered, and nothing is deleted until the user confirms
