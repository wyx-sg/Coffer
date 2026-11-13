## RENAMED Requirements

- FROM: `### Requirement: Keep the sidebar to its fourteen entries`
- TO: `### Requirement: Keep the sidebar to its fifteen entries`

## MODIFIED Requirements

### Requirement: Keep the sidebar to its fifteen entries
The sidebar's entries MUST be exactly these, at these routes: one ungrouped entry
and five groups — fifteen today, and no sixteenth without a spec change.
Settings is not an entry: it is a modal opened from the sidebar footer (see
"Open Settings as a modal from the sidebar footer"). Usage is not an entry:
it is a tab of Model providers (see provider-switching "Show metered usage on a
Usage tab of Model providers"). Custom
tools and CLIs are specified by "Manage custom tool groups on their own page" and "Show
every CLI a skill requires on the CLIs page". An
entry whose experimental feature is switched off (spec
[experimental-features](../experimental-features/spec.md) "Close every surface of a switched-off feature")
MUST be left out, and MUST appear on the next render after the feature is
switched on. Knowledge belongs to `knowledge` and Memory to `memory`; every
other entry, Model providers, Sync, Conversations and Channels included, is
owned by no feature and is always there:

```
  Overview         /                  — the landing page
 AGENTS
  Agents           /agents            — the consumers (Bot icon)
  Model providers  /model-providers   — the endpoints agents' models are served from, and what requests through Coffer cost (tabs Providers | Usage)
 RUN
  Conversations    /conversations     — every agent's sessions, wherever they started, each opened in the agent's own terminal
  Channels         /channels          — the IM bots agents answer on
  Scheduled tasks  /scheduled-tasks   — turns Coffer starts on its own in a chat, and Coffer's own background work
 CAPABILITIES
  MCP servers      /mcp-servers       — the aggregated upstream servers
  Custom tools     /custom-tools      — HTTP APIs Coffer serves to agents as tools, in groups
  Skills           /skills            — what Coffer delivers to agents
  CLIs             /clis              — the command-line tools skills require
 CONTEXT
  Knowledge        /knowledge         — the collections under ~/.coffer/vault/knowledge/
  Memory           /memory            — what the agents learned, synced between them and between machines
 SYSTEM
  Secrets          /secrets           — every stored secret and what uses it
  Activity         /activity          — what changed, what was called, what broke
  Sync             /sync              — converging this vault with a git remote
```

#### Scenario: cold-start renders authenticated content
- **GIVEN** the user has never opened Coffer (localStorage is empty, no daemon.json in user HOME yet)
- **AND** every experimental feature is switched on
- **AND** `coffer daemon start` is running (so daemon.json exists in user HOME)
- **WHEN** they navigate to `http://localhost:5173/` in a real browser
- **THEN** the index renders the Overview page at `/`, with the sidebar and main content area, within 2 seconds
- **AND** the main content shows the Overview page (no generic error card)
- **AND** the sidebar lists exactly Coffer's operational surfaces — Overview; Agents, Model providers; Conversations, Channels, Scheduled tasks; MCP servers, Custom tools, Skills, CLIs; Knowledge, Memory; Secrets, Activity, Sync — with Overview under no heading and the rest grouped under "Agents", "Run", "Capabilities", "Context" and "System" headings, with no other entry
- **AND** no navigation entry is Settings; a labelled Settings row sits at the bottom of the sidebar

#### Scenario: a switched-off feature leaves the sidebar
- **GIVEN** a sidebar entry owned by a registered experimental feature that is switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar leaves that entry out and lists every other entry under its heading
- **AND** with every feature switched on, the sidebar lists all fifteen entries
- **AND** with both features switched off, it lists only Overview, Agents, Model providers, Conversations, Channels, Scheduled tasks, MCP servers, Custom tools, Skills, CLIs, Secrets, Activity and Sync

### Requirement: Group the sidebar by what the user comes to do
The sidebar MUST be grouped by what the user comes to Coffer to do, so that each
heading names one intent and a new entry has one obvious home. There are five
groups, under headings in this order:

- **AGENTS** — set up the agents and the models they run on: Agents, then Model
  providers. Agents come first because they are the subject of the product; a
  provider is the endpoint and key each agent's model is served from.
- **RUN** — see and start what agents are working on, and set up the IM bots that put them
  to work: Conversations, then Channels.
- **CAPABILITIES** — give agents things they can do: MCP servers, Custom tools,
  Skills, then CLIs.
- **CONTEXT** — give agents things they know: Knowledge, then Memory.
- **SYSTEM** — look after Coffer and what every other part shares: Secrets,
  Activity, then Sync.

Settings sits in no group: it is machine-level configuration visited rarely, so
it opens as a modal from the sidebar footer rather than taking an entry (see
"Open Settings as a modal from the sidebar footer").

**Overview**, the landing page, MUST sit above the five groups under no heading:
it summarises all of them, so filing it under one would misname it.

A new entry MUST join the group that names what the user comes to it for, and no
group may grow past five entries; growth that is more of an existing thing — one
more agent, channel or custom tool — is a row inside that thing's page, not an
entry. A group whose every entry is left out (see "Keep the sidebar to its
fifteen entries") MUST leave its heading out too, so no heading stands over
nothing. The decision and the options it was weighed against are in
[The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md).

#### Scenario: the sidebar groups entries by what the user comes to do
- **GIVEN** the app shell is rendered with every experimental feature switched on
- **WHEN** the sidebar lists its entries
- **THEN** Overview comes first, under no heading, and the rest sit under five headings in the order Agents, Run, Capabilities, Context, System
- **AND** Agents holds Agents then Model providers, Run holds Conversations, Channels then Scheduled tasks, Capabilities holds MCP servers, Custom tools, Skills and CLIs, Context holds Knowledge then Memory, and System holds Secrets, Activity and Sync

#### Scenario: a group with every entry switched off leaves the sidebar
- **GIVEN** a group whose every entry is owned by a registered experimental feature that is switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar shows no heading for that group, and the other headings and their entries are unchanged

### Requirement: Open Settings as a modal from the sidebar footer
Settings MUST NOT be a navigation entry: it is not one of the sidebar's fifteen
entries and belongs to no group. It MUST open as a large modal over the current
page from three places: a labelled **Settings** row — a gear icon and the word
Settings, not an icon-only button — at the bottom of the sidebar; the ⌘,
shortcut on macOS and Ctrl+, elsewhere, from any page; and the command palette's
Settings tabs. On the collapsed icon rail the row MUST shrink to the gear icon
with a tooltip reading Settings and its shortcut. The row MUST show as active only while the
modal is open, and never mark the page underneath as not current. The row shows
no daemon state — no status dot, no words, no corner dot on the rail — and, like
the shortcut, always opens General; the daemon's state is told by the
reconnecting bar and the offline page. Settings is machine-level
configuration a user visits rarely, so it takes no place in the sidebar
beside the pages used every day, the convention of desktop applications' own
preferences windows.

The modal MUST stay addressable by route: each tab is `/settings/<tab>`
(General, Security, Data, Daemon, Features, About — see "Organise Settings into six
tabs"), and while it is open the address bar and history carry that route,
so a deep link, a reload, a link from another page (such as a link
to `/settings/daemon`) or the palette opens the modal on that tab.
Opening it from a page MUST keep that page rendered underneath, unchanged.
Closing it — the close control, Escape, or a click outside it — MUST return to
the page underneath at that page's own route. A deep link opened with no page
underneath, as on a fresh load of `/settings/daemon`, MUST render the modal over
Overview, and closing it lands on `/`. Browser Back from an open modal MUST
close it and return to the page underneath.

#### Scenario: the Settings row opens Settings over the current page
- **GIVEN** the user on `/mcp-servers`
- **WHEN** they click the labelled Settings row at the bottom of the sidebar
- **THEN** the Settings modal opens on General, the URL reads `/settings/general`, and the MCP servers list stays rendered underneath
- **AND** the Settings row shows as active while the modal is open and not after it closes, and the fifteen navigation entries do not include Settings

#### Scenario: the collapsed rail keeps Settings as a gear with a tooltip
- **GIVEN** the sidebar collapsed to its icon rail
- **WHEN** the user points at the gear icon and clicks it
- **THEN** the gear carries no word and no daemon state, a tooltip reads Settings and its shortcut, and the click opens the Settings modal on General

#### Scenario: the keyboard shortcut opens Settings
- **GIVEN** the app open on any page, with focus outside a text field
- **WHEN** the user presses ⌘, on macOS or Ctrl+, elsewhere
- **THEN** the Settings modal opens on General over that page

#### Scenario: closing Settings returns to the page underneath
- **GIVEN** the Settings modal opened from `/activity` and switched to its Data tab
- **WHEN** the user presses Escape, and again after reopening it and pressing browser Back
- **THEN** each time the modal closes and the app is on `/activity`, with the Activity page as it was

#### Scenario: a deep link opens a Settings tab
- **GIVEN** a fresh load of `/settings/daemon`
- **WHEN** the route resolves
- **THEN** the Settings modal opens on its Daemon tab over the Overview page
- **AND** closing it lands on `/`

#### Scenario: the palette opens a Settings tab over the current page
- **GIVEN** the user on `/agents`
- **WHEN** they open the palette, type "data" and press Enter
- **THEN** the Settings modal opens on its Data tab at `/settings/data`, with the Agents page underneath
