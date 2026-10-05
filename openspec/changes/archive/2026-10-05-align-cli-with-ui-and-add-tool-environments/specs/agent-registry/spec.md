## MODIFIED Requirements

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
- The agent detail page's **header** carries the agent's mark, its name, one status pill and a **⋯** menu, and nothing under the name: the version and the config directory are on the Overview. The pill reads Connected, Not connected, Needs repair, Hook not approved or Config left behind. The header never turns into a fix button — Connect, Repair and Check again sit on the Overview's Connection section. **Rotate proxy token** is in ⋯ only while the agent routes through Coffer's proxy ([provider-switching](../provider-switching/spec.md) "Authenticate each agent to the proxy with its own local token").
- The detail page has eight tabs, none carrying a count: six in the strip — **Overview**, **Skills**, **MCP servers**, **Hooks**, **Config files** and **Sessions** — and, behind a **More** menu, **Plugins** and **Memory**, the least used. Each is addressable by its own path (`/agents/<type>` for Overview, then `/agents/<type>/skills`, `/mcp-servers`, `/hooks`, `/config`, `/sessions`, `/plugins` and `/memory`), so a page opened from a tab returns to it. While the open tab is one of the two in More, the More trigger reads that tab's name and carries the underline; a tab in More that needs attention puts a warning dot on More. There is **no Model tab**: an agent's model is a section of the Overview, and `/agents/<type>/model` is not a page.
  - **Overview** stacks, top to bottom, **Connection**, **What this agent can use**, **Model** and **Details**. Connection says what the connection is in one line, lists the `coffer` MCP entry and the memory delivery hook with where each lives and its health, and carries the one fix the state calls for at its title's right — **Connect** or **Repair** as a solid button, **Check again** as an outline one — and none while the agent is healthy. What this agent can use is six tiles, three by two — MCP servers, Skills, Config files, Plugins, Hooks and Memory — each with its count, one fact and, when something of the agent's own waits for a look, a warning "N to review"; a tile opens its tab. Model reads **Provider**, **Model** and **Route** (through Coffer's proxy, with **Test**, or direct) and carries **Change…**, which opens the Change model dialog of [provider-switching](../provider-switching/spec.md) "Review a model change before writing it"; opening the page with `?change-model=1` opens that dialog on arrival. With the `models` feature off the section is read-only and shows no Provider row and no Change. Details reads **Version**, **Config directory**, **UID** and **Registered**, with no Title, Name or Type, because an agent's name is fixed to its type.
  - **Skills** and **MCP servers** open with Coffer's part and then the agent's own, per "Show what Coffer manages for an agent in one row". **Plugins** lists the agent's installed plugins — all its own, since Coffer installs none — with a search, an enabled switch and a ⋯ menu whose only item is Uninstall…, and a plugin's name opens an information dialog.
  - **Hooks** opens with **Coffer's memory hook**, then **the agent's own hooks**, per "List every hook in the agent's native config". The tab is read only apart from Repair and Check again on Coffer's hook.
  - **Config files** lists every allowlisted config file of "Define a curated config-file allowlist per type" as a file tree beside a read-only preview — the settings files and the human-authored instructions files (`CLAUDE.md`, `AGENTS.md`) alike, because an instructions file is configuration the person wrote, not something installed — each previewed on the right, opened in the editor or revealed ("Open config files in an external editor or reveal them").
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
