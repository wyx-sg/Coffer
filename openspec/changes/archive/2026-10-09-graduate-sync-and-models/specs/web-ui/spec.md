## MODIFIED Requirements

### Requirement: Keep the sidebar to its fourteen entries
The sidebar's entries MUST be exactly these, at these routes: one ungrouped entry
and five groups — fourteen today, and no fifteenth without a spec change.
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
 CAPABILITIES
  MCP servers      /mcp-servers       — the aggregated upstream servers
  Custom tools     /custom-tools      — HTTP APIs Coffer serves to agents as tools, in groups
  Skills           /skills            — what Coffer delivers to agents
  CLIs             /clis              — the command-line tools skills require
 CONTEXT
  Knowledge        /knowledge         — the collections under ~/.coffer/vault/knowledge/
  Memory           /memory            — the partitions aggregated from the agents' own stores
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
- **AND** the sidebar lists exactly Coffer's operational surfaces — Overview; Agents, Model providers; Conversations, Channels; MCP servers, Custom tools, Skills, CLIs; Knowledge, Memory; Secrets, Activity, Sync — with Overview under no heading and the rest grouped under "Agents", "Run", "Capabilities", "Context" and "System" headings, with no other entry
- **AND** no navigation entry is Settings; a labelled Settings row sits at the bottom of the sidebar

#### Scenario: a switched-off feature leaves the sidebar
- **GIVEN** a sidebar entry owned by a registered experimental feature that is switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar leaves that entry out and lists every other entry under its heading
- **AND** with every feature switched on, the sidebar lists all fourteen entries
- **AND** with both features switched off, it lists only Overview, Agents, Model providers, Conversations, Channels, MCP servers, Custom tools, Skills, CLIs, Secrets, Activity and Sync

### Requirement: Organise Settings into six tabs
Settings — the modal of "Open Settings as a modal from the sidebar footer" —
MUST carry six tabs, in this order, in every build, grouped by what they manage
rather than by how Coffer is built, and MUST open on General:

- **General** (`/settings/general`) — display preferences (the interface language
  and the theme, the preferred external editor, the preferred terminal and the hand-off agent), **Check skills for updates** (spec [skill-manager](../skill-manager/spec.md) "Hand a Git-imported skill's update to an agent"), and a
  **Speech-to-text** section: the connection and model that transcribe voice
  messages (spec [internal-engine](../internal-engine/spec.md) "Show the speech-to-text pair in Settings › General").
  It carries no experimental-features card; the switches are on the Features
  tab.
- **Security** (`/settings/security`) — what is about this machine only: where
  the master encryption key lives — in a signed release its Keychain access
  group; in a development build the file `~/.coffer/master.key` or the login
  keychain, with the switch that moves it — with its backup, import and
  fingerprint; the daemon's access token (see "Show, copy and rotate the access
  token on Settings › Security"); and whether a secret waits for approval
  before it goes somewhere new. It lists and edits no stored secret; those are
  on the Secrets page (see "Manage stored secrets on the Secrets page").
- **Data** (`/settings/data`) — what Coffer stores, by kind: Vault, Local content, History
  and Rebuildable cache (see "Group the Data tab by what kind of data it is").
- **Daemon** (`/settings/daemon`) — the daemon's state and the controls a user
  needs for it (see "Show and manage the daemon on Settings → Daemon").
- **Features** (`/settings/features`) — the two experimental features, each
  marked Experimental, with its switch (spec
  [experimental-features](../experimental-features/spec.md) "Show the Features tab in every build").
- **About** (`/settings/about`) — version, license, source, whether a newer
  version is available (see "Check for and install updates on Settings › About"),
  and a small **Copy diagnostics** action beside the version.

Clicking a tab
swaps the modal's right pane without a full page reload and without closing the
modal.

Every pane follows the page grammar: it opens with the tab's title (an `h1`) and
one muted intro line, then its sections 32px apart. A section is not boxed — its
title carries its meta and action on one line, its description is one muted line
under the title, and its rows are separated by hairlines; a tab with a single
section (Features) prints no section title. Settings save on change: no pane has
a Save button, and a text field applies on Enter or when it loses focus.

#### Scenario: settings layout uses the redesigned tabbed sidebar
- **GIVEN** the user navigates to `/settings`
- **WHEN** the route resolves
- **THEN** the Settings modal opens on the General tab
- **AND** the modal's tab list shows General, Security, Data, Daemon, Features and About — exactly those six, in that order — with the current route highlighted
- **AND** clicking a tab swaps the right pane content without a full page reload and the modal stays open

#### Scenario: every settings tab opens with its title and an intro line
- **GIVEN** the Settings modal
- **WHEN** each of the six tabs is opened
- **THEN** its pane starts with an `h1` named for the tab, followed by one intro line
- **AND** the pane has no Save button

#### Scenario: the security tab keeps only machine-level settings
- **GIVEN** stored secrets cited by a registered MCP server and a model provider
- **WHEN** the user opens `/settings/security`
- **THEN** the tab shows where the master key lives and, in a development build, its move control, and the access token's Show, Copy and Rotate controls
- **AND** it lists no stored secret and offers no control that adds, reveals or deletes one
