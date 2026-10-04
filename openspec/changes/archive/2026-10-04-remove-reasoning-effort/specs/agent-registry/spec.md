## ADDED Requirements

### Requirement: Expose every agent operation over REST and on the Agents page
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
  - **Overview** stacks, top to bottom, **Connection**, **What this agent can use**, **Model** and **Details**. Connection says what the connection is in one line, lists the `coffer` MCP entry and the memory delivery hook with where each lives and its health, and carries the one fix the state calls for at its title's right — **Connect** or **Repair** as a solid button, **Check again** as an outline one — and none while the agent is healthy. What this agent can use is six tiles, three by two — MCP servers, Skills, Config files, Plugins, Hooks and Memory — each with its count, one fact and, when something of the agent's own waits for a look, a warning "N to review"; a tile opens its tab. Model reads **Provider**, **Model** and **Route** (through Coffer's proxy, with **Test**, or direct) and carries **Change…**, which opens the Change model dialog of [provider-switching](../provider-switching/spec.md) "Review a model change before writing it"; opening the page with `?change-model=1` opens that dialog on arrival. With the `models` feature off the section is read-only and shows no Provider row and no Change. Details reads **Version**, **Config directory**, **UID** and **Registered**, with no Title, Name or Type, because an agent's name is fixed to its type.
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

#### Scenario: the header carries one status pill and a fixed action pair
- **GIVEN** an agent that is not connected, one that is connected and one that needs repair
- **WHEN** each agent's page renders
- **THEN** the header shows the agent's name with one pill reading Not connected, Connected or Needs repair, and New conversation beside the ⋯ menu
- **AND** no header carries a Connect, Repair or Check again button, because those sit on the Overview's Connection section

## MODIFIED Requirements

### Requirement: Carry the model binding on the agent record
The agent record MUST carry the model binding the rest of Coffer reads — `model` and `tier_models` (Claude Code only: the model for each of `opus`, `sonnet`, `haiku` and `fable`) — because the model is chosen at the point of USE and an agent is where it is used, not on the connection that serves it. That binding MUST be settable over REST as well as in the web UI: `PATCH /api/v1/agents/{uid}` carries `model` / `tier_models`, with an explicit null to unbind `tier_models`. A field the request omits is unchanged; `tier_models`, when sent, replaces the whole mapping. Only `tier_models` clears on an explicit null; `model` has no null that unbinds it, so an explicit null for it is treated as omitted. A tier other than the four is refused. The binding carries no `fast_model`: Claude Code's background model is its Haiku tier, and no reasoning effort: the agent runs at the effort its own configuration names. Projecting a binding into the agent's native config is provider-switching's.

#### Scenario: bind a model to an agent over REST
- **GIVEN** a registered agent
- **WHEN** the user sends `PATCH /api/v1/agents/{uid}` with a `model` and `tier_models` `{"haiku": "<model>"}`, then again with `tier_models` null
- **THEN** the agent record reports the bound `model` and `tier_models` after the first edit, and carries no `fast_model`
- **AND** after the second edit `tier_models` is null while `model` is unchanged

### Requirement: Serve each agent type's model catalogue from its one agent
`GET /api/v1/agent-providers/{agent_key}/models` MUST answer, per agent type, which models a picker offers for that agent: the agent's own catalogue, read back from the installed agent and never written down in Coffer, unless the connection the agent runs on curates a set of ids — then those ids, as [provider-switching](../provider-switching/spec.md) "Serve one model list to every surface" defines. Each entry MUST carry `id` (passed to the agent verbatim), `label` and `description`. An unknown `agent_key` MUST be a 404. The catalogue reads the native config of the type's one agent ("Keep one agent per type, named by it"), which is also the agent a chat turn on that type runs against ([chat](../chat/spec.md) "Run Claude Code and Codex as subprocess providers on the type's one agent").

#### Scenario: list the models an agent can be put on
- **GIVEN** a registered `codex` agent whose own config names a model
- **WHEN** the user requests `GET /api/v1/agent-providers/codex/models`
- **THEN** the response lists that model with `id`, `label` and `description`
- **AND** the same request for an unknown agent key answers 404

## REMOVED Requirements

### Requirement: Expose every agent operation through REST and the Agents page
**Reason**: Renamed: one of its scenarios no longer mentions efforts, and a scenario cannot be renamed in place.
**Migration**: Read "Expose every agent operation over REST and on the Agents page".

### Requirement: Carry reasoning-effort levels beside the model id
**Reason**: Reasoning effort is removed from Coffer; the agent decides it.
**Migration**: None: the catalogue entry carries id, label and description only.

### Requirement: Read reasoning-effort levels from the agent runtime
**Reason**: Reasoning effort is removed from Coffer; no source of levels is read.
**Migration**: None.

### Requirement: Report no default effort the runtime does not publish
**Reason**: Reasoning effort is removed from Coffer; no default is reported.
**Migration**: None.

