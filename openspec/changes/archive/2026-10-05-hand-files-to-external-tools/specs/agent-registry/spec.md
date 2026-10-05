## ADDED Requirements

### Requirement: Back up and compare-and-swap every write Coffer makes to an agent's config
Every write Coffer makes into an agent's own config files — connecting, repairing or disconnecting it, installing or removing Coffer's MCP entry, removing or adopting a direct MCP entry, toggling or uninstalling a plugin, projecting a provider, and the reconciler's repairs — MUST be atomic (temp file + rename) and MUST first copy the prior content to a timestamped backup under `~/.coffer/config-backups/` (Coffer's own folder: machine-local, outside the vault, and never beside the agent's file). A writer that read the file before deciding what to write MUST pass the fingerprint of what it read, and the write MUST be refused with `conflict` (409, `CONFIG_FILE_STALE`) when the file changed since, leaving it untouched, so the agent's own rewrite between Coffer's read and write is never lost. Backups are named by their UTC time and cleaned by the `config_backups` retention policy ([resource-framework](../resource-framework/spec.md) "Retain config backups on an adjustable policy"), which always keeps the newest backup of each file. Each writer records its own audit event; there is no write of a config file on the person's behalf, which edits the file in their own editor (see "Open config files in an external editor or reveal them").

#### Scenario: Coffer's own config write leaves its backup in Coffer's folder
- **GIVEN** `~/.claude/settings.json` holds content, and an older write already left a backup of it
- **WHEN** Coffer writes new content to that file twice
- **THEN** each write copied the prior content to its own timestamped file under `~/.coffer/config-backups/`, in a folder named for that one config file, and the newest backup holds the content the last write replaced
- **AND** no `.bak` file, backup or temporary file is left in the agent's own directory, and nothing under `~/.coffer/vault` was written

#### Scenario: Coffer's own config write is refused when the file changed since it was read
- **GIVEN** a config file Coffer read to plan a write, which the agent then rewrites on disk
- **WHEN** Coffer writes with the fingerprint of what it read
- **THEN** the write is refused `409 CONFIG_FILE_STALE` and the file holds the agent's content

## MODIFIED Requirements

### Requirement: Remove a direct MCP entry from its source file
Users MUST be able to remove a direct MCP entry — from the agent's page or the REST route (`DELETE /api/v1/agents/{uid}/mcp-entries/{entry}`). Removal edits only the entry's source file, reuses the atomic-write + backup machinery of "Back up and compare-and-swap every write Coffer makes to an agent's config", and records an `agent_mcp_entry_removed` audit entry. The `coffer` entry is not removable through this operation — it is managed by "Install Coffer's MCP server into an agent in one action" and "Uninstall Coffer's MCP server from an agent".

#### Scenario: remove a direct MCP entry
- **GIVEN** a registered agent with a direct (non-Coffer) MCP entry
- **WHEN** the user removes that entry (carrying the source file where the type's entries may come from more than one)
- **THEN** the entry is deleted from exactly its source file via an atomic write with a backup of the prior content under `~/.coffer/config-backups/`, an `agent_mcp_entry_removed` audit entry is recorded, and the next listing no longer shows it

#### Scenario: remove a direct MCP entry over REST and refuse the coffer entry
- **GIVEN** a registered agent `claude-code` whose own config defines a direct entry `github`
- **WHEN** the user sends `DELETE /api/v1/agents/claude-code/mcp-entries/github`
- **THEN** the entry is gone from its source file, the newest backup under `~/.coffer/config-backups/` holds the prior content, and an `agent_mcp_entry_removed` audit entry is recorded
- **AND** `DELETE /api/v1/agents/claude-code/mcp-entries/coffer` is refused and leaves the file unchanged

### Requirement: Back up and audit Coffer MCP install and uninstall
Install and uninstall MUST reuse the atomic-write + backup machinery of "Back up and compare-and-swap every write Coffer makes to an agent's config" and record an audit entry (`agent_mcp_installed` / `agent_mcp_uninstalled`).

#### Scenario: uninstall Coffer's MCP from an agent
- **GIVEN** an agent that has Coffer's MCP installed
- **WHEN** the user uninstalls it
- **THEN** the `coffer` entry is removed from the agent's MCP config, the file is backed up under `~/.coffer/config-backups/`, an `agent_mcp_uninstalled` audit entry is recorded, and status reports `installed=false`

### Requirement: Define a curated config-file allowlist per type
Each supported agent type MUST define a curated allowlist of config files in its capability-manifest record, enumerated by that type's child spec, each entry carrying a stable `key`, a display name, a resolved absolute path, and a `format` (`json`, `toml` or `markdown`). Each type's human-authored instructions file carries the key `instructions` — those files are instructions a person wrote, distinct from agent-written memory (memory's domain). The allowlist is what Coffer lists and the only files Coffer's own writers may touch; config files are not persisted in SQLite — the file on disk is the source of truth.

#### Scenario: key each type's instructions file as instructions
- **GIVEN** the capability manifest for every supported agent type
- **WHEN** the type's config-file allowlist is read
- **THEN** every entry carries a key, a display name, an absolute path and a format among `json`, `toml` and `markdown`
- **AND** exactly one entry per type is keyed `instructions` and has format `markdown`

### Requirement: List an agent's config files with their locations
Users MUST be able to list an agent's config files with, for each, its key, display name, path, the containing-folder absolute path (`folder_path`), format, and existence (plus size and modified time when the file exists). The `path`/`folder_path` pair feeds the UI's open-in-external-editor / reveal-in-file-manager affordances (see "Open config files in an external editor or reveal them"). The listing is the only config-file route: Coffer serves no config file's content and writes none on the person's behalf.

#### Scenario: report each config file's path, folder and existence
- **GIVEN** a registered agent where one allowlisted file exists and another does not
- **WHEN** the user lists the agent's config files
- **THEN** each entry carries its key, display name, absolute `path`, `folder_path` equal to the path's parent, format and `exists` flag
- **AND** the existing file also carries its size and modified time while the missing one carries neither

### Requirement: List directory config entries
A config-file allowlist entry MAY be a **directory entry** (`kind=directory`): it resolves to a directory and lists its files (entry-relative path, absolute path, size, modified time) instead of carrying content. A missing directory MUST list as `exists=false` with no files, and the read MUST NOT create it. Which allowlist entries are directory entries is per type, and each child spec names its own. The directory on disk is the source of truth; its files are opened and revealed like any other config file.

#### Scenario: list a directory config entry's files
- **GIVEN** a registered agent whose directory config entry contains Markdown files (possibly nested)
- **WHEN** the user lists that config entry
- **THEN** Coffer returns the entry with `kind=directory` and its files (entry-relative path, size, modified time); a missing directory lists as `exists=false` with no files and is not created by the read

### Requirement: Open config files in an external editor or reveal them
The agent's **Config files** tab MUST list every allowlisted config file — and, under a directory entry, each of its files — as a read-only row naming the file, its folder, its size and when it changed, with **Open in editor** and **Reveal in Finder** on each, using the `path` and `folder_path` from "List an agent's config files with their locations". A file that does not exist yet reads *Not created* and offers only Reveal in Finder on its folder, because opening creates nothing. Open and reveal perform the real OS action through the daemon's filesystem-action endpoints (`POST /api/v1/fs/open`, `POST /api/v1/fs/reveal`, and the installed-editor enumeration `GET /api/v1/fs/editors` behind the preference — all owned by the daemon spec, which this spec consumes and does not specify), since the loopback daemon is always on the user's own machine ([Daemon Proxies OS File Actions](../../../docs/decisions/daemon-proxies-os-file-actions.md)). The tab shows no file's content and offers no edit, new file or delete: a config file is changed in the person's own editor or by their agent. There is no copy-path fallback. The editor used for open-in-external-editor references the user's "preferred external editor" preference defined by web-ui (not re-specified here).

#### Scenario: open a config file and reveal it through the daemon
- **GIVEN** an agent's Config files tab listing an existing config file and one not created yet
- **WHEN** the user chooses Open in editor and then Reveal in Finder on the existing file's row
- **THEN** the UI asks the daemon to open that file's absolute path and then to reveal it
- **AND** the row of the file not created yet offers Reveal in Finder only, no row shows the file's content or offers Edit, New file or Delete, and no copy-path affordance is offered

### Requirement: Audit every agent lifecycle event
The system MUST record an audit entry, carrying timestamp, actor and the affected agent reference, for every lifecycle event: agent created, updated, removed (via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events); Coffer MCP installed/uninstalled; MCP entry removed/adopted (`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`); plugin toggled/uninstalled (`agent_plugin_toggled` / `agent_plugin_uninstalled`). Discovery and all workspace listings — MCP entries, plugins, config files, native memory stores, native sessions, the model catalogue, the Coffer connection status — are read-only and emit no audit event. Reading ONE of the listed items — a single store's files — is the same act at a smaller scale and audits nothing either, and renaming or deleting a native session is the agent's own act on its own record ("Rename and delete a native session through the agent") and is not audited here. A connect or disconnect records the events of the parts it installs or removes and none of its own; the memory delivery hook's events are memory's, not this spec's. The `agent_config_file_written` and `agent_config_file_deleted` events are no longer recorded; rows an earlier version recorded keep their wording in Activity.

#### Scenario: audit lifecycle events
- **GIVEN** the user has registered, edited, or removed agents
- **WHEN** they view the audit log
- **THEN** every lifecycle change (create, update, remove) appears via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events, each carrying timestamp, actor, and the affected agent reference. (Discovery is read-only and registers nothing, so it emits no audit event of its own.)

### Requirement: List every hook in the agent's native config
The system MUST list, read only, every command hook the agent will run. That covers the hooks in the agent's own hook-carrying files (the type's child spec names them) and those in each enabled plugin's hook file. Each is listed with its event, matcher, command, timeout, source (`user` or `plugin`, with the plugin's id) and the file that declares it. Project-level settings are not read, because Coffer does not know which repositories the agent is used in.

Coffer's own memory hook — its two entries, on `SessionStart` and `UserPromptSubmit` ([memory](../memory/spec.md) "Install delivery hooks explicitly and removably") — MUST be marked, each entry as Coffer's, and reported as one hook with the set of events its entries sit on. Its health MUST be reported by the same marker-and-command comparison the boot repair uses:
- `current` when the entries sit on exactly the events Coffer would install on and each carries exactly the command Coffer would write now;
- `stale` when Coffer's marker carries another command or sits on another set of events;
- `missing` when it is absent.

The report MUST also say whether the agent will run the hook, as its **trust**: `trusted`, `untrusted`, `modified` (approved for an earlier command), `disabled`, `unknown` (the agent's approval record does not parse), or `not_required` for an agent that runs every hook it finds. It MUST also give the last recorded fire from the audit log.

The listing MUST be served by `GET /api/v1/agents/{uid}/hooks`, and MUST write nothing and record no audit event. When the agent will not run a current hook, the trust reports why, and the Hooks tab and the attention list say what the user does about it. A file that does not parse MUST be reported as a parse error beside the hooks the other files yield.

Each listed hook MUST also carry where it sits in its file — `group_index` and `hook_index`, the positions in `hooks.<event>[group_index].hooks[hook_index]` — so a person can find the entry, and the REST listing reports them.

On the agent's Hooks tab the listing is two parts, Coffer's first. **Coffer's memory hook** is one block of properties, never one row per entry: its state (and how long ago it fired), its command, the events it sits on and the file that declares it, with its one fix at the block's title — **Repair** when it is stale or missing, **Check again** while the agent has not approved it — and, when it has never fired, the likely cause and a link to Activity. The reason a state is a problem is written in the block's own line. **The agent's own hooks** — Coffer's excluded — are one table of Event, Command, Matcher and File, with a search over the command and an **Event** filter that lists each event with its count; the table says how many of how many are shown once either narrows it. A row opens a read-only details dialog with the command in full, the event and when it runs, the matcher, the type, the timeout, the file and the entry's position in it (`hooks.<event>[group].hooks[hook]`), with **Copy command** and **Open in editor**; nothing in the dialog writes, because a hook is changed in its own file, in the person's own editor. A file name opens that file in the preferred editor (see "Open config files in an external editor or reveal them").

#### Scenario: list an agent's hooks with Coffer's own marked
- **GIVEN** a registered Claude Code agent whose `settings.json` carries a foreign `PreToolUse` hook and Coffer's memory hook, whose `settings.local.json` carries a `Stop` hook, and which has one enabled and one disabled plugin with a hook file each
- **WHEN** the user lists the agent's hooks
- **THEN** the foreign hooks, the `Stop` hook and the enabled plugin's hook are listed with their sources and files, the disabled plugin's hook is not, and only Coffer's two entries are marked as Coffer's
- **AND** Coffer's hook reads `current` on both events with trust `not_required` and no recorded fire, and nothing is written or audited

#### Scenario: report a stale Coffer hook
- **GIVEN** a registered Codex agent whose `hooks.json` carries Coffer's marked hook on `UserPromptSubmit` alone, with a command other than the one Coffer would write now, and one recorded fire
- **WHEN** the user lists the agent's hooks
- **THEN** Coffer's hook reads `stale` on `UserPromptSubmit`, the installed and expected commands differ, and the last fire is reported

#### Scenario: list the hooks with their position in the file
- **GIVEN** a Claude Code `settings.json` whose `PreToolUse` event holds two groups, the second with two hooks
- **WHEN** the user lists the agent's hooks
- **THEN** the second hook of the second group reports `group_index` 1 and `hook_index` 1, and the first group's hook reports 0 and 0

#### Scenario: coffer's memory hook leads the Hooks tab and the agent's own follow
- **GIVEN** a Claude Code agent whose `settings.json` carries Coffer's two memory-hook entries beside three hooks of its own
- **WHEN** the user opens the agent's Hooks tab
- **THEN** Coffer's hook is one block with its state, command, the two events and its file, and the agent's own hooks are one table of three rows that does not repeat Coffer's
- **AND** choosing a row opens a read-only dialog with the command, event, matcher, type, timeout, file and position, and searching or filtering by event narrows the table and says how many of how many show


### Requirement: Offer every agent operation over REST and on the Agents page
Every management operation — register/list/view/update/remove, the config-file listing, Coffer connect/disconnect/connection status, MCP entry list/view/remove/adopt, plugin list/detail/toggle/uninstall, the hooks listing, native session listing, rename and delete, and the model catalogue — MUST be available through (a) the REST API and (b) the Agents page in the web UI. The command line carries none of them: it has no `agent` command group.

- the lifecycle of "Manage the agent lifecycle" under `/api/v1/agents`;
- the config-file listing at `GET /api/v1/agents/{uid}/config-files`;
- the agent's Coffer connection under `/api/v1/agents/{uid}/coffer-connection` ("Connect an agent to Coffer in one action");
- direct MCP entries under `/api/v1/agents/{uid}/mcp-entries`;
- plugins under `/api/v1/agents/{uid}/plugins`, where `DELETE` is the uninstall of "Uninstall a plugin by the type's own strategy";
- the hooks of "List every hook in the agent's native config" at `GET /api/v1/agents/{uid}/hooks`;
- native sessions at `GET /api/v1/agents/{uid}/sessions` ("List an agent's native sessions through the agent"), renamed with `PATCH` and deleted with `DELETE` at `/api/v1/agents/{uid}/sessions/{session_id}` ("Rename and delete a native session through the agent");
- the model catalogue at `GET /api/v1/agent-providers/{agent_key}/models`.

The listing of an agent's config files and the reads of its native memory stores' files are served over REST for the web UI, and the Overview's Details names the config directory for anyone who wants the files themselves. The model catalogue's route takes the agent type it is keyed by (`claude_code`, `codex`), not an agent's name, and an unknown type is its not-found.

The Agents page in the web UI MUST expose all of these. It renders within the web-ui shell at `/agents` as the first entry of the sidebar's Agents group ([web-ui](../web-ui/spec.md) "Group the sidebar by what the user comes to do"), never among the Capabilities or Context entries, because agents are consumers of vault assets, not assets themselves; agent resources do not appear in the kind-agnostic resources browser.

- A config file is never shown or edited in the page: its row opens it in the person's editor or reveals it ("Open config files in an external editor or reveal them"). Every place the page shows a file the agent holds read-only — a native memory store, an unmanaged skill's folder — uses the same file tree and the same viewer toolbar, so a file reads the same wherever it is opened.
- The agent detail page's **header** carries the agent's mark, its name, one status pill and a **⋯** menu, and nothing under the name: the version and the config directory are on the Overview. The pill reads Connected, Not connected, Needs repair, Hook not approved or Config left behind. The header never turns into a fix button — Connect, Repair and Check again sit on the Overview's Connection section. **Rotate proxy token** is in ⋯ only while the agent routes through Coffer's proxy ([provider-switching](../provider-switching/spec.md) "Authenticate each agent to the proxy with its own local token").
- The detail page has eight tabs, none carrying a count: six in the strip — **Overview**, **Skills**, **MCP servers**, **Hooks**, **Config files** and **Sessions** — and, behind a **More** menu, **Plugins** and **Memory**, the least used. Each is addressable by its own path (`/agents/<type>` for Overview, then `/agents/<type>/skills`, `/mcp-servers`, `/hooks`, `/config`, `/sessions`, `/plugins` and `/memory`), so a page opened from a tab returns to it. While the open tab is one of the two in More, the More trigger reads that tab's name and carries the underline; a tab in More that needs attention puts a warning dot on More. There is **no Model tab**: an agent's model is a section of the Overview, and `/agents/<type>/model` is not a page.
  - **Overview** stacks, top to bottom, **Connection**, **What this agent can use**, **Model** and **Details**. Connection says what the connection is in one line, lists the `coffer` MCP entry and the memory delivery hook with where each lives and its health, and carries the one fix the state calls for at its title's right — **Connect** or **Repair** as a solid button, **Check again** as an outline one — and none while the agent is healthy. What this agent can use is six tiles, three by two — MCP servers, Skills, Config files, Plugins, Hooks and Memory — each with its count, one fact and, when something of the agent's own waits for a look, a warning "N to review"; a tile opens its tab. Model reads **Provider**, **Model** and **Route** (through Coffer's proxy, with **Test**, or direct) and carries **Change…**, which opens the Change model dialog of [provider-switching](../provider-switching/spec.md) "Review a model change before writing it"; opening the page with `?change-model=1` opens that dialog on arrival. With the `models` feature off the section is read-only and shows no Provider row and no Change. Details reads **Version**, **Config directory**, **UID** and **Registered**, with no Title, Name or Type, because an agent's name is fixed to its type.
  - **Skills** and **MCP servers** open with Coffer's part and then the agent's own, per "Show what Coffer manages for an agent in one row". **Plugins** lists the agent's installed plugins — all its own, since Coffer installs none — with a search, an enabled switch and a ⋯ menu whose only item is Uninstall…, and a plugin's name opens an information dialog.
  - **Hooks** opens with **Coffer's memory hook**, then **the agent's own hooks**, per "List every hook in the agent's native config". The tab is read only apart from Repair and Check again on Coffer's hook.
  - **Config files** lists every allowlisted config file of "Define a curated config-file allowlist per type" as read-only rows — the settings files and the human-authored instructions files (`CLAUDE.md`, `AGENTS.md`) alike, because an instructions file is configuration the person wrote, not something installed — each opened in the editor or revealed ("Open config files in an external editor or reveal them").
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


## REMOVED Requirements

### Requirement: Read allowlisted config files without creating them
**Reason**: Coffer is not a second editor (principles, What Coffer is not › Not a second agent). The content read existed for the in-app viewer and editor, which are removed; the Config files tab lists the files and opens them in the person's editor.
**Migration**: Open the file from its row (Open in editor) or read it at the path the listing gives. `GET /api/v1/agents/{uid}/config-files/{key}` is removed.

### Requirement: Validate config-file content before saving it
**Reason**: There is no save of a config file on the person's behalf any more; the person's editor and the agent itself validate what they write, and Coffer's own writers produce well-formed content by construction and report a file that does not parse ("Degrade a facet to a parse-error state when its config file is unparseable").
**Migration**: Edit the file in the editor. `PUT /api/v1/agents/{uid}/config-files/{key}` is removed.

### Requirement: Write config files atomically with a backup and an audit entry
**Reason**: The person's write of a config file through Coffer is removed. The atomic write and the backup stay for Coffer's own writes, stated in "Back up and compare-and-swap every write Coffer makes to an agent's config".
**Migration**: `agent_config_file_written` is no longer recorded. A person's own edit is backed up by their editor or their git, not by Coffer.

### Requirement: Address config files only by allowlisted key
**Reason**: No route takes a config-file key any more: the listing takes the agent only, and the content read and write routes are removed. The allowlist still bounds what is listed and what Coffer's writers touch ("Define a curated config-file allowlist per type").
**Migration**: None.

### Requirement: Read, write and delete files inside a directory entry
**Reason**: Creating, editing and deleting a subagent file is the person's editor's or the agent's job, not Coffer's. The directory's files stay listed with Open in editor and Reveal in Finder ("List directory config entries").
**Migration**: `GET`, `PUT` and `DELETE /api/v1/agents/{uid}/config-files/{key}/files/{relpath}` are removed, and `agent_config_file_deleted` is no longer recorded. Create a subagent file in the `agents/` folder with the editor (Reveal in Finder opens the folder).

### Requirement: Reject stale config-file writes by fingerprint
**Reason**: The stale check guarded the in-app editor's save, which is removed. Coffer's own writers keep the same compare-and-swap, stated in "Back up and compare-and-swap every write Coffer makes to an agent's config".
**Migration**: None. `CONFIG_FILE_STALE` stays for Coffer's own writes.
