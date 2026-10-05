## RENAMED Requirements

- FROM: `### Requirement: Offer a knowledge refusal's hand-off as one Ask an agent control`
- TO: `### Requirement: Offer a knowledge refusal's hand-off as one hand-off control`

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
switched on. Model providers, Usage tab included, belongs to `models`, Knowledge to `knowledge`,
Memory to `memory` and Sync to `sync`; every other entry, Conversations and
Channels included, is owned by no feature and is always there:

```
  Overview         /                  — the landing page
 AGENTS
  Agents           /agents            — the consumers (Bot icon)
  Model providers  /model-providers   — the endpoints agents' models are served from, and what requests through Coffer cost (tabs Providers | Usage)
 RUN
  Conversations    /conversations     — the conversations the IM bots started, each opened in the agent's own terminal
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
- **AND** with the four features switched off, it lists only Overview, Agents, Conversations, Channels, MCP servers, Custom tools, Skills, CLIs, Secrets and Activity

### Requirement: Go back and forward from the title bar
The desktop shell on macOS MUST draw its own 38px title strip across the top of
the window, in the sidebar's colour and with no rule beneath it. Besides the
traffic lights the strip MUST hold only the sidebar toggle and back and forward
arrows through the app's own history, to the right of the toggle; no page puts anything there, and a page's title stays in the page. The controls
start just right of the traffic lights, or at the left edge in full screen,
where the lights are hidden, and the lights and the controls share the strip's
centre line. Under the strip every page's title MUST start at the same place,
16px below the strip and 32px from the sidebar's edge, whether the page scrolls
as a whole or is a workspace whose panes scroll on their own. Where the strip is blank the window MUST remain
draggable. While the sidebar is expanded its right edge MUST run up through the
strip; collapsed, the strip MUST run across. An arrow MUST be greyed out and
inert when the app's history has nowhere to go that way, and ⌘[ and ⌘] (Ctrl
off macOS) MUST do what the arrows do, except while the user types in a text
field. A browser tab has no strip and no arrows; its sidebar toggle sits beside the logo.

#### Scenario: the arrows in the title bar go back and forward through the app's history
- **GIVEN** the desktop shell with no history behind or ahead of the current page
- **THEN** both arrows are greyed out
- **WHEN** the user visits two pages and presses the back arrow
- **THEN** the app shows the first page and the forward arrow is enabled
- **AND** ⌘[ and ⌘] go back and forward the same way, except in a text field

### Requirement: Resize every split view by its divider
Every split view — a list beside its detail, a file tree beside its file, and the sidebar beside the workspace — MUST
be resizable by dragging the divider between its panes. Each pane MUST keep a
minimum width: a list pane at least 240px and a detail pane at least 480px, and
a list pane at most half the window; the expanded sidebar between 200px and
300px (the collapsed icon rail keeps its own fixed width, see "Collapse the
sidebar to a remembered icon rail"). A drag MUST stop at those bounds rather
than pass them. Double-clicking a divider MUST restore that split's default
width. A divider MUST be keyboard-focusable, with an accessible name saying what
it resizes, and while it has focus ← and → MUST move it by a fixed step within
the same bounds.

The chosen width MUST be remembered per page in that viewer's browser storage
and restored on the next visit. It is a convenience: when the storage is empty,
unreadable or blocked, the split opens at its default width and still works,
and a remembered width that no longer fits the window is clamped to the bounds.

#### Scenario: dragging a divider resizes and survives a reload
- **GIVEN** a page's split view, a list beside its detail
- **WHEN** the user drags the divider to widen the list, then reloads the page
- **THEN** the list keeps the width it was dragged to, on that page only, and another page's split opens at its default

#### Scenario: a divider cannot be dragged past a pane's minimum
- **GIVEN** a split view with a list beside its detail
- **WHEN** the user drags the divider towards the list until the list would be narrower than 240px, and then the other way until the detail would be narrower than 480px or the list wider than half the window
- **THEN** the divider stops at 240px, and at whichever of the other two bounds comes first

#### Scenario: double-clicking a divider restores the default
- **GIVEN** a split view whose divider was dragged to a remembered width
- **WHEN** the user double-clicks the divider
- **THEN** the split returns to its default width, and that default is what the next visit opens with

#### Scenario: a divider moves from the keyboard
- **GIVEN** the sidebar expanded at its default width
- **WHEN** the user tabs to the sidebar's divider and presses → three times, then ← once
- **THEN** the sidebar widens by two steps in total, never past 300px, and the divider announces what it resizes

#### Scenario: no stored width falls back to the default
- **GIVEN** browser storage that is blocked for the page
- **WHEN** a split view opens and the user drags its divider
- **THEN** the split opens at its default width, the drag still resizes it, and no error is shown

### Requirement: Group the sidebar by what the user comes to do
The sidebar MUST be grouped by what the user comes to Coffer to do, so that each
heading names one intent and a new entry has one obvious home. There are five
groups, under headings in this order:

- **AGENTS** — set up the agents and the models they run on: Agents, then Model
  providers. Agents come first because they are the subject of the product; a
  provider is the endpoint and key each agent's model is served from.
- **RUN** — see what the IM bots put agents to work on, and set the bots up: Conversations,
  then Channels.
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
fourteen entries") MUST leave its heading out too, so no heading stands over
nothing. The decision and the options it was weighed against are in
[The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md).

#### Scenario: the sidebar groups entries by what the user comes to do
- **GIVEN** the app shell is rendered with every experimental feature switched on
- **WHEN** the sidebar lists its entries
- **THEN** Overview comes first, under no heading, and the rest sit under five headings in the order Agents, Run, Capabilities, Context, System
- **AND** Agents holds Agents then Model providers, Run holds Conversations then Channels, Capabilities holds MCP servers, Custom tools, Skills and CLIs, Context holds Knowledge then Memory, and System holds Secrets, Activity and Sync

#### Scenario: a group with every entry switched off leaves the sidebar
- **GIVEN** a group whose every entry is owned by a registered experimental feature that is switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar shows no heading for that group, and the other headings and their entries are unchanged

### Requirement: Give each listed resource kind one sidebar entry
Every resource kind with a list UI MUST have exactly one sidebar entry — today six
kinds (`mcp_server`, `skill`, `knowledge`, `memory`, `provider`, `channel`), six
entries — filed by what the user comes to do with it rather than under one
Resources heading, because "resource" is the framework's storage word, not a
word a user navigates by:

- **Model providers** is filed under Agents, not Capabilities or Settings: a
  `provider` is `{protocol, base_url, secret_ref}`, the endpoint and key an
  agent's model is served from, and the connection and model are chosen per
  agent in that agent's Change model dialog (spec
  [provider-switching](../provider-switching/spec.md) "Offer every connection operation over REST and in the web UI").
- **Channels** is filed under Run, beside Conversations and not merged into it:
  Conversations is where a person finds every conversation a channel started and opens it in the terminal, a
  channel is an IM bot set up once and revisited rarely, and the conversations a
  channel carries are listed on the Conversations page with its badge (spec
  [chat](../chat/spec.md) "Show channel conversations on the Conversations page");
  the Channels page holds setup, status and settings only.
- **MCP servers** and **Skills** are filed under Capabilities; **Knowledge** and
  **Memory** under Context.
- **Custom tools** are `mcp_server` resources of the HTTP API transport, one per
  group of tools. They share the gateway's machinery with every
  other server but get their own entry under Capabilities, so a user looking for
  "make my own tool" finds it; the MCP servers entry lists the other servers and
  the Custom tools entry these, so each resource still appears under exactly one
  entry.

**CLIs** is not a resource kind: it lists the commands skills require, with their
presence, version and login state (see "Show every CLI a skill requires on the
CLIs page"), and sits under Capabilities beside Skills.

Agents are stored as resources of kind `agent` but are the consumers of the
others, so the Agents entry heads the Agents group and no agent is listed on a
Capabilities or Context page. **Secrets** is not a resource kind — it is the
secret store every kind cites into — and sits under System (see "Manage
stored secrets on the Secrets page").

#### Scenario: each listed resource kind has one sidebar entry
- **GIVEN** the app shell is rendered with every experimental feature switched on
- **WHEN** the entries for resource kinds are read
- **THEN** MCP servers, Custom tools, Skills, Knowledge, Memory, Model providers and Channels each appear exactly once, under Capabilities, Capabilities, Capabilities, Context, Context, Agents and Run respectively
- **AND** the MCP servers and Custom tools entries open `/mcp-servers` and `/custom-tools`, and a custom-tool group is not listed on the MCP servers page
- **AND** no heading reads "Resources"

### Requirement: Jump to any page or object from a command palette
The shell MUST offer a command palette, opened with ⌘K on macOS and Ctrl+K
elsewhere from any page, and from a search control in the sidebar. It MUST do
one thing — take the user somewhere — and MUST NOT carry an action that changes
state: no create, delete, enable, reach or run entry.

It lists two kinds of entry, filtered together by what the user types:

- **Pages** — every sidebar entry and every Settings tab, by the names the
  sidebar and the tabs use (see "Call a surface by one name everywhere"). A
  Settings tab opens in the Settings modal over the current page.
- **Objects** — the agents, the resources of every kind
  with a list surface (custom tools included), the CLIs and the stored secrets
  (by ref, never a value), matched by name — and also by title on the kinds
  that carry one ([resource-framework](../resource-framework/spec.md)
  "Carry an optional editable title on the kinds that have one") — each
  opening its detail page; a secret, which has none, opens the Secrets page.

With an empty query it MUST show **Recent** — the last few entries chosen in
this browser, a convenience that is safe to lose — above every page. Under a
query it MUST show the single best hit as **Best match** (an exact name first,
then a match at the start of a name), then the other matching pages, then the
matching objects in one group per kind, named as the kind's sidebar entry and
in sidebar order, each group holding a few; typing more narrows them. Recent is
not shown under a query: the list holds only what matches it. A skill's row
names the agents it is delivered to (by their display names, from the skill's
own list row), as a secret's row names who uses it.

A page or object of a switched-off experimental feature MUST NOT appear. The
palette MUST read the list routes the pages already read and add no route of its
own. Arrow keys MUST move the selection, Enter MUST open it, and Escape MUST
close the palette and return focus where it was.

Pages MUST be usable at once, whatever the daemon's state. While the objects
are loading, the palette MUST say so; a kind whose list fails MUST show a
readable error in its own group and leave the other groups working; while the
daemon cannot be reached, the palette MUST list Pages only and say that objects
need the daemon. A query that matches nothing MUST say so, and what the palette
searches, rather than show an empty panel.

#### Scenario: the palette jumps to a page
- **GIVEN** the app open on any page
- **WHEN** the user presses ⌘K, types "act" and presses Enter
- **THEN** the app navigates to `/activity` and the palette closes

#### Scenario: the palette jumps to an object
- **GIVEN** a registered provider whose title differs from its name
- **WHEN** the user opens the palette and types part of the provider's name, then part of its title
- **THEN** each query lists the provider as the best match, named by its title and marked as a provider
- **AND** choosing it opens that provider's page and closes the palette

#### Scenario: the palette offers no actions
- **GIVEN** the palette open with an empty query, and then with queries naming objects
- **WHEN** every entry it lists is read
- **THEN** each entry is a page or an object that navigates somewhere
- **AND** choosing any of them sends no request that changes state

#### Scenario: an empty query shows recent choices above every page
- **GIVEN** the user chose an MCP server and then the Secrets page from the palette
- **WHEN** they open the palette again with an empty query
- **THEN** Recent lists Secrets and then the server, and every page is listed below it

#### Scenario: a skill result names the agents that get it
- **GIVEN** a skill delivered to Claude Code and Codex
- **WHEN** the user types part of the skill's name in the palette
- **THEN** its row reads "Skill" and "Claude Code · Codex"

#### Scenario: a query lists only its matches
- **GIVEN** an entry chosen earlier from the palette, so Recent has it
- **WHEN** the user types a query that entry does not match
- **THEN** no Recent group is shown and the entry is not listed

#### Scenario: the palette leaves out switched-off features
- **GIVEN** a registered experimental feature that is switched off, owning a sidebar entry
- **WHEN** the user searches the palette for the entry's name
- **THEN** the entry's page is not listed, and it is listed once the feature is switched on

#### Scenario: the palette lists pages while objects load
- **GIVEN** the palette opened before the object lists have answered
- **WHEN** the user types a page's name
- **THEN** the page is listed and can be opened
- **AND** the palette says the objects are loading

#### Scenario: a failing kind leaves the rest of the palette working
- **GIVEN** the skills list route failing and the MCP servers list answering
- **WHEN** the user opens the palette
- **THEN** the skills group shows a readable error
- **AND** MCP servers and every page are still listed and can be opened

#### Scenario: the palette with the daemon offline
- **GIVEN** the daemon cannot be reached
- **WHEN** the user opens the palette
- **THEN** it lists Pages only and says that objects need the daemon

#### Scenario: the palette says when nothing matches
- **GIVEN** the palette open
- **WHEN** the user types a query no page or object matches
- **THEN** the palette says there are no results

### Requirement: Organise Settings into six tabs
Settings — the modal of "Open Settings as a modal from the sidebar footer" —
MUST carry six tabs, in this order, in every build, grouped by what they manage
rather than by how Coffer is built, and MUST open on General:

- **General** (`/settings/general`) — display preferences (the interface language
  and the theme, the default page size, the preferred external editor, the preferred terminal and the hand-off agent), and a
  **Speech-to-text** section: the connection and model that transcribe voice
  messages (spec [internal-engine](../internal-engine/spec.md) "Show the speech-to-text pair in Settings › General").
  It carries no experimental-features card; the switches are on the Features
  tab. While `models` is off the connection choice for speech-to-text is left out.
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
- **Features** (`/settings/features`) — the four experimental features, each
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

### Requirement: Group the Data tab by what kind of data it is
The Data tab MUST show what Coffer stores in four blocks, one per kind of data
([Storage Is Five Classes by Nature](../../../docs/decisions/storage-is-five-classes-by-nature.md)),
and no other — in particular no "This Mac only" block, since what is true of this
machine only is a setting shown on the tab it belongs to:

- **Vault** — the git repository at `~/.coffer/vault/` holding the user's
  configuration, skills, knowledge and encrypted secrets, a repository whether
  or not it syncs ([vault-storage](../vault-storage/spec.md) "Keep the vault a
  git repository whether or not it syncs"): its size (with its history), how
  many versions it holds, when and by whom it last changed, whether it syncs to
  a remote or is this machine's only copy, and **Open folder**, whose tooltip
  names the folder (no separate location row).
- **Local content** — what is not synced and the user must back up themselves:
  channel attachments and media only, with their size and **Open
  folder**, and one short line saying how they are kept: "Include this folder in
  your own backups." under keep forever, or that attachments are deleted
  automatically after N days. Its **Attachments** row is the retention of those
  files, a Keep forever switch and a number of days (30 by default) that auto-saves like
  every History row, and shortening it asks first, counting the files the shorter
  window deletes.
- **History** — the retention of each record kind — changes, tool calls,
  **Skill working files** (the logs, journals and temporary files skill scripts write under `~/.coffer/skill-data`, 30 days by default, a row whose confirmation counts files) and **Config backups** (the copies Coffer keeps of an agent's config file before it rewrites it, under `~/.coffer/config-backups`, 30 days by default, with the newest copy of each file always kept; a row whose confirmation counts files) — Keep forever or a number of days, cleaned up by the retention
  worker's schedule (at daemon start and every six hours), with a
  **Clear expired now** action behind a confirmation, which reports what it
  removed; the last cleanup reads "Last cleared today at 12:00 — 1,284 rows" ("30 Sep at 12:00" for another day); a saved value survives a reload. Shortening a
  window (or turning Keep forever off) MUST ask first, and the confirmation
  MUST say how many records the shorter window deletes at the next cleanup and
  how many the table holds now and would hold after, counted by the daemon
  without deleting anything. **Clear expired now** also removes attachments past their window and reports them, and skill working files and config backups past theirs, as files. A refused save MUST say so above the blocks with
  **Try again**, name the window still in place, and mark the row "Not saved".
- **Rebuildable cache** — Coffer's memory tree under `~/.coffer/derived/`,
  which Coffer rebuilds on its own: one **Clear** action,
  behind a confirmation saying that memory is rebuilt from the agents' own
  memory on the next update, each entry becoming a note as it stands, and that
  notes whose sources are gone do not come back.

Edits auto-save, like every settings surface: there is no Save button.

#### Scenario: retention period persists across reload
- **GIVEN** the user opens the Data settings tab
- **WHEN** they turn off "Keep forever" for a record kind in History, set a specific number of retention days, and commit the field (blur or Enter), which auto-saves
- **THEN** reloading the page shows the same retention-days value that was saved

#### Scenario: the data tab shows four blocks and no this-mac block
- **GIVEN** a vault with versions, channel media on disk, and memory partitions
- **WHEN** the user opens `/settings/data`
- **THEN** it shows Vault (size, versions, Open folder), Local content (attachments and media, size, Open folder, not synced, and the Attachments retention row), History (retention for changes, tool calls, skill working files and config backups with Clear expired now) and Rebuildable cache (memory tree with Clear), and no This Mac only block

#### Scenario: the attachments retention is set where the attachments are listed
- **GIVEN** attachments kept for 30 days
- **WHEN** the user opens `/settings/data`
- **THEN** Local content has an Attachments row at 30 days and says attachments are deleted automatically after 30 days, and History has no Attachments row
- **AND** after the user turns Keep forever on, the line reads "Include this folder in your own backups." and the choice is saved

#### Scenario: skill working files are kept for a chosen window
- **GIVEN** the `skill_data` policy at 30 days
- **WHEN** the user opens `/settings/data`
- **THEN** History has a Skill working files row at 30 days, after Tool calls
- **AND** shortening it asks first and the confirmation counts files, not records

#### Scenario: shortening a retention window counts what it deletes
- **GIVEN** Tool calls kept for 30 days, some of them older than 7 days
- **WHEN** the user sets the tool calls window to 7 days
- **THEN** a confirmation asks "Keep tool calls for 7 days?", says how many calls older than 7 days the next cleanup deletes, and shows the count now and after
- **AND** nothing is deleted or saved until the user confirms

#### Scenario: clear expired now removes what retention has passed
- **GIVEN** changes kept for 7 days and changes older than that
- **WHEN** the user chooses Clear expired now and confirms
- **THEN** the older changes are removed and the rest remain, as the scheduled cleanup would have done
- **AND** the page reports how many records it removed, by record kind

#### Scenario: clearing the cache is confirmed and rebuilt
- **GIVEN** memory partitions with notes
- **WHEN** the user chooses Clear in Rebuildable cache
- **THEN** a confirmation says the next memory update rebuilds memory from the agents' own memory and that notes whose sources are gone do not come back, and nothing is cleared until the user confirms
- **AND** once confirmed only the memory tree is cleared, with no vault or local content touched

#### Scenario: config backups are kept for a chosen window
- **GIVEN** the `config_backups` policy at 30 days
- **WHEN** the user opens `/settings/data`
- **THEN** History has a Config backups row at 30 days, after Skill working files, whose help text says the newest backup of each file is always kept
- **AND** shortening it asks first and the confirmation counts files, not records

### Requirement: Hand a machine-dependent problem to an agent with one split button
Installing, setting up, logging in and troubleshooting depend on the machine, so a problem whose fix
is outside Coffer and for which the backend wrote a concrete prompt MUST be handed over with one split
button, **Hand off to <Agent> ▾**, never two buttons, where <Agent> is the display name of the hand-off
agent ("Let the user choose the hand-off agent"). Its tooltip reads "Start <Agent> in <terminal> to handle
this". Pressing the main part MUST start that agent in the preferred terminal ("Let the user choose a
terminal") with the prompt sent, through the daemon ([daemon](../daemon/spec.md) "Open an agent session in a terminal"),
with no confirmation; a toast says the terminal opened, and a refusal or a launcher that fails shows its reason
with **Copy prompt** as the way out. The menu holds **Hand off to <other agent>** when the other supported
agent is also managed, then **Copy prompt**, which copies the daemon's prompt as given for an agent
outside Coffer and answers with a "Prompt copied" toast. With one managed agent the menu holds Copy prompt
alone. With no Coffer-managed agent installed only **Copy prompt** is offered as a button, with the
one-sentence help beside it. The split button sits after the state's own buttons (Check again,
Retry, View log), appears once per problem, never on a healthy, success or empty state, and never for
a missing secret or an approval, which only the person can give. Wherever another requirement names
Copy prompt and **Ask an agent** together — the button's former name — they are this button's menu item
and main part. On a Needs you row the same split button sits beside the row's action, and the ⋯ menu holds Ignore.

#### Scenario: the split button hands a prompt over or copies it
- **GIVEN** a problem with a prompt and a managed agent installed
- **WHEN** the person presses Hand off to <Agent>, and separately opens its menu and chooses Copy prompt
- **THEN** the daemon is asked to start the hand-off agent in the preferred terminal with the prompt sent and no confirmation, and the prompt is copied as given with a "Prompt copied" toast
- **AND** with only one managed agent the menu holds Copy prompt alone, and with no managed agent installed only Copy prompt is offered
- **AND** a terminal that fails to open is reported in a toast beside Copy prompt

#### Scenario: the menu offers the other managed agent
- **GIVEN** a problem with a prompt, Claude Code as the hand-off agent and Codex also managed
- **WHEN** the person opens the split button's menu
- **THEN** it holds Hand off to Codex and then Copy prompt, and choosing the first starts Codex in the preferred terminal with the prompt sent

### Requirement: Offer a knowledge refusal's hand-off as one hand-off control
When the daemon refuses a knowledge operation with a hand-off in the error's details
(`details.handoff.prompt`), the Knowledge page MUST offer that prompt through the hand-off split button of "Hand a machine-dependent problem to an agent with one split button"
— its main part starts the hand-off agent in the preferred terminal with the prompt, and its menu holds Copy prompt,
which is the only action when no managed agent is available — passing the prompt on as served and
never assembling it. A History tab or Recent changes that cannot be read because git is not
installed MUST say so in one neutral row — **History needs git** or **Recent changes needs git**,
*Install git on this Mac to see versions. The document itself is fine.* — with **Check again** and
the hand-off, and no Retry or Open Activity. The page MUST NOT
show an install command.

#### Scenario: a history that needs git offers the prompt for installing it
- **GIVEN** a machine with no git, whose history reads are refused with the install hand-off
- **WHEN** a document's History tab opens
- **THEN** it shows the row *History needs git* with Check again and the hand-off split button, whose menu copies the served prompt, and names no install command
- **AND** it offers no Retry and no Open Activity

#### Scenario: recent changes that need git offer the same row
- **GIVEN** a machine with no git, whose history reads are refused with the install hand-off
- **WHEN** Recent changes opens
- **THEN** it shows the row *Recent changes needs git* with Check again and the hand-off split button

### Requirement: Show a knowledge document's history on its History tab
A knowledge document's pane MUST carry two tabs, **Document** (the default) and **History**, neither
with a count. History is the version-history split of "Show every version history as one split": the
document's versions on the left, newest first — who wrote each (the user, an agent, an edit found on disk, or sync; a version an
earlier curation pass wrote keeps its curation label), when, and its added and removed line counts — and the chosen
version on the right, the newest chosen when the tab opens. The right side MUST carry a switch between
**Changes in this version** (against the one before) and **Compare with current**, **Restore this
version** on every version but the current one, which writes a new version rather than rewriting the
past, and the diff. A history that cannot be read
MUST say so in one **Load error** row inside the tab — *Couldn't load the history*, the reason,
**Retry** and **Open Activity** — leaving the Document tab working; without git the row is *History
needs git* (see "Offer a knowledge refusal's hand-off as one hand-off control").

#### Scenario: the history tab lists versions with their writers
- **GIVEN** a document the user created, that an agent then changed
- **WHEN** the user opens its History tab and chooses the older version's row
- **THEN** the tab lists both versions newest first with their writers, its diff shows on the right beside the list, and Restore this version is offered on it and not on the current version
- **AND** restoring it writes it back as a new version

#### Scenario: a history that fails to load leaves the document readable
- **GIVEN** the history read failing
- **WHEN** the user opens the History tab
- **THEN** the tab shows one Load error row with Retry and Open Activity, and the Document tab still renders

### Requirement: List recent knowledge changes across collections
The Knowledge page MUST carry a **Recent changes** view: one timeline across every collection, newest
first, of documents people and agents wrote or deleted. A version an earlier curation pass wrote
keeps its curation label. It MUST be filtered with **Collection** and **Author** filter pills and a
**Clear filters** control, the choice kept in the URL. A delete carries **Restore**. The view has no
waiting items and no pass to inspect or undo; a refusal because git is not installed is handled as in
"Offer a knowledge refusal's hand-off as one hand-off control".

#### Scenario: recent changes shows a cross-collection timeline
- **GIVEN** an agent's write in one collection and a person's edit in another
- **WHEN** the user opens Recent changes
- **THEN** both changes are listed, newest first, each linking the document it wrote, and the view shows no waiting items and no Curate now

#### Scenario: the filter pills narrow the timeline and live in the URL
- **GIVEN** changes in two collections by the user and by an agent
- **WHEN** the user picks one collection in the Collection pill and the agent in the Author pill, then chooses Clear filters
- **THEN** the timeline lists only that collection's changes by that agent and the URL carries both choices, and Clear filters empties both and the URL

### Requirement: Hand an agent's missing program to an agent on the agent pages
Wherever the web UI shows an agent type whose program is not found — its Agents list row, its detail page while it is not added, and the
Overview tab's problem states (config left behind, not found) — it MUST offer the daemon's
`install_handoff` prompt for that type (agent-registry "Hand installing an agent's program to an
agent") through the hand-off split button of "Hand a machine-dependent problem to an agent with one split
button", whose main part, **Hand off to <Agent>**, is offered only for a managed agent other than the missing one: the missing agent
itself cannot run the prompt. On a list row the split button sits before the row's ⋯
menu, which holds neither Copy prompt nor a hand-off, and the detail page's header ⋯ holds
neither. None
of these surfaces MUST show an install command or tell the person to restart Coffer. The
Plugins tab of a Claude Code agent whose program is not found, where Uninstall cannot run, MUST
say so and offer the same prompt. The Connect review MUST offer the hand-off a `SHIM_NOT_FOUND`
refusal carries beside Retry (agent-registry "Install Coffer's MCP server into an agent in one
action").

#### Scenario: an agent whose program is not found offers its install prompt
- **GIVEN** Codex not installed and no managed agent available
- **WHEN** the user presses Copy prompt on the Codex row
- **THEN** the daemon's prompt is copied as given and no install command is shown anywhere
- **AND** the row offers no Hand off to <Agent>, and its ⋯ menu offers no Copy prompt

#### Scenario: ask an agent is offered only while another managed agent is available
- **GIVEN** Claude Code's config left behind with its program gone, and Codex available as a managed agent
- **WHEN** the user presses Hand off to Codex on the Claude Code row's split button
- **THEN** Codex is started in the preferred terminal with the install prompt, and nothing is written to either agent's configuration
- **AND** with only Claude Code itself managed, the row offers Copy prompt alone

#### Scenario: a connect refused for a missing shim offers the daemon's prompt
- **GIVEN** a registered agent and a daemon that refuses its Connect with `SHIM_NOT_FOUND` carrying a hand-off
- **WHEN** the user applies the Connect review
- **THEN** the review shows the change as failed with copy that names no environment variable or command
- **AND** Copy prompt beside Retry copies the refusal's prompt as given

### Requirement: Show every CLI a skill requires on the CLIs page
The CLIs page (`/clis`, under Capabilities) MUST list one row per command that
any skill requires or any enabled stdio MCP server starts with (spec
skill-manager "Check every required command where the agent runs"), with the
version found beside the minimum the skills ask for, the login state where the
command has one, and how many MCP servers and skills need it, problems first —
missing, older than the minimum, or not logged in, grouped under Needs attention above
Ready — as a split view with the selected CLI's detail beside the list
(`/clis/<command>`). The detail's Needed by MUST list the MCP servers started
with the command, each opening that server's page and naming its launcher, and
the skills that declare it, each opening that skill's Requires tab; each row
carries its kind when both need it. The app MUST NOT show an install, update or
login command, a "run it in a terminal" instruction, or run any of them: a CLI
that needs the user says what it costs in a plain sentence — which servers can't
start and which skills fail — and its detail page and the skill's Requires tab
MUST offer the daemon's hand-off prompt (spec skill-manager "Hand a required
command to an agent with a prompt") through the hand-off split button of "Hand a machine-dependent problem to an agent with one split button"
— **Hand off to <Agent>** starts the hand-off agent in the preferred terminal with the prompt sent, and **Copy prompt** copies it;
with no managed agent available only Copy prompt is offered. The page's **Check again** probes every command afresh, and the banner that
states a problem re-checks that one tool. A CLI a person added keeps **Edit** and a
**⋯** menu with **Remove** (a 420-wide confirmation saying the tool stays
installed on this machine); a CLI a skill or MCP server requires has neither, so
its header's right side is empty. **Add CLI** opens a 480-wide form for a command
name or path, which says what Coffer found — where, which version, and whether it
is already added or required — before anything is saved, and keeps a refused
save in the dialog with Retry (see skill-manager "Declare a command-line tool
without a skill"). With nothing required and nothing added the page shows one
empty state with Add CLI and a link to how `requires:` works; `requires:` entries
Coffer skipped are one muted line under the subtitle with a link to Skills. Coffer
reads no command's `--help` and shows no tree of subcommands. A skill's detail page MUST link each requirement it declares to
that CLI's page, and Overview MUST show an attention item while any required CLI
is missing, outdated or not logged in. What a skill declares and how a command
is probed are specified by skill-manager; this page shows what they report.

#### Scenario: the CLIs page lists problems first
- **GIVEN** skills requiring `jq` (not found), `gh` (minimum 2.40, found 2.30.0), `gcloud` (not logged in) and `uv` (found, current)
- **WHEN** the user opens `/clis`
- **THEN** `jq`, `gh` and `gcloud` are listed under Needs attention above `uv` under Ready, `gh` shows 2.30.0 against 2.40, `gcloud` shows not logged in, and each row counts the skills that need it

#### Scenario: a CLI that needs the user offers a prompt for an agent
- **GIVEN** a required CLI that is missing and a Coffer-managed agent
- **WHEN** the user opens its detail page and presses Hand off to <Agent>
- **THEN** the hand-off agent starts in the preferred terminal with the prompt sent
- **AND** the page offers Copy prompt, shows no install command, and with no managed agent available offers only Copy prompt

#### Scenario: check again after logging in
- **GIVEN** a CLI's detail page showing not logged in, with the hand-off to an agent and no login command shown
- **WHEN** the user logs in and chooses Check again
- **THEN** the page probes the command afresh and shows it as logged in

#### Scenario: a CLI an MCP server starts with lists that server
- **GIVEN** `uv` missing, needed by the MCP server `duckdb` (started with `uvx`) and the skill `data-profiling`
- **WHEN** the user opens `/clis/uv`
- **THEN** the list row reads "Not found · duckdb needs it" with "1 server · 1 skill", the header reads "needed by 1 MCP server and 1 skill", and the banner says duckdb can't start and data-profiling fails at the step that calls uv
- **AND** Needed by lists `duckdb` (MCP server, "starts with uvx") opening `/mcp-servers/duckdb` and `data-profiling` (Skill) opening its Requires tab

#### Scenario: a CLI added by hand has Edit and Remove, a required one has neither
- **GIVEN** `demo` added by hand and `uv` required by a skill
- **WHEN** the user opens each one's page
- **THEN** `demo` shows Edit and a ⋯ menu whose Remove asks "Remove demo?" and says the tool stays installed, and `uv` shows neither

#### Scenario: Add CLI shows what Coffer found before anything is saved
- **GIVEN** the Add CLI dialog
- **WHEN** the user types a command name
- **THEN** it says where Coffer found the command and which version, or that it is not on this machine and can still be added, and says when a skill or MCP server already requires it
- **AND** a refused declaration stays in the dialog with its reason

#### Scenario: the empty CLIs page offers Add CLI and the docs
- **GIVEN** no required command and no tool added by hand
- **WHEN** the user opens `/clis`
- **THEN** the page shows "No command-line tools yet" with one Add CLI button, a link to how `requires:` works and no header buttons

#### Scenario: a skill's requirement links to its CLI
- **GIVEN** a skill that requires `gh`
- **WHEN** the user opens the skill's detail page and chooses the `gh` requirement
- **THEN** the app opens `/clis/gh`

#### Scenario: overview flags a required CLI that needs attention
- **GIVEN** a required CLI that is outdated
- **WHEN** the user opens Overview
- **THEN** an attention item names the CLI and the problem, and its name and its Check action open the CLI's page
- **AND** once the daemon's list no longer reports it — every required CLI present, current and logged in — the item is gone

### Requirement: Show what needs the user and each area's health on Overview
Overview MUST answer "is everything OK, and what needs me?" at a glance, from
the capabilities' own reads and never a route of its own. **Needs you** comes
first: one row per item of the attention list ([resource-framework](../resource-framework/spec.md)
"Report what needs a person across every kind"), most severe first and then
oldest, each with its resource and kind, the reason in a sentence, since when
where that is known, and exactly one action that opens the page — or the tab —
where the item is dealt with. The action reads what it does for that kind and
reason, not the bare verb — a channel's check is **Reconnect channel**, sync's
review **Review held changes**, a memory hook's repair **Repair hook** — behind a
small icon for its verb (a key for a secret, an eye for a review, a plug for connecting,
a wrench for repairing, a refresh for checking or testing again), and the reason
may wrap to two lines before it is cut, its whole text on hover. An action that is a non-GET call into Coffer's
own state needing no preview — testing an MCP server again, probing a command
again — MUST run in place instead: the button turns into a disabled
"Retrying…" or "Checking…", the reason gains an accent line ("Starting
postgres… it leaves this list once it answers."), and that lasts until the
attention list has been read again after the call; a row still listed then
returns to its button, and a failed call returns it at once with the error as
a toast. Every other action — connecting an agent or repairing its config
(writes into the agent's own files, previewed on their page), adding a secret,
turning approval on, and every read-only review — keeps opening its page. Every row MUST also
carry the hand-off split button, Hand off to <Agent> ▾ with Copy prompt behind it, and a ⋯ menu
holding Ignore — the daemon's prompt as given (every item carries one, the
kind's own where it has one); the list scrolls inside a frame of about six
rows, under its title, which shows how many items it holds. An attention source that failed MUST be named
above the rows in one muted status line, saying that what it would report is missing. Rows MUST clear
themselves as problems resolve: the page follows the daemon's event stream and
rereads the list when an `attention` change arrives. **Health** follows: one
tile per sidebar area whose feature is switched on — Agents, MCP servers,
Skills, Knowledge, Memory, Model providers, Channels, Sync, Custom tools, CLIs,
Secrets and Usage, in that order (Conversations show in Recent activity) —
each with a status word drawn from that area's attention items (Secrets, which
has no attention source, words its own list: a secret missing on this machine is
a warning, one nothing uses is plain subtle text with no dot; Usage shows its
period, "Last 24 h", and no health), a count from its own list and a one-line
summary, opening the area's page — Usage, which is a tab of Model providers, opening that tab; an area with no backend has no tile. Agents
and Channels count "1 of 2" with the unit "connected" — for Agents only the
items about connecting count, so a hook edited by hand or one the agent has not approved does not make an agent
"not connected" — and Channels names the reconnecting one ("SeaTalk
reconnecting since 13:41"), otherwise the names joined with " · ". Knowledge's
line reads "4 collections · edited today 13:30", Memory's "Last update 14 min
ago", Sync's number is when its last round ended ("4 min ago", "last round")
over "1 behind · 0 ahead", and Usage counts the tokens of the last 24 hours in
one decimal ("2.1M"). A CLI tile words its problem by reason when every item
shares one ("1 not logged in", "1 outdated", "1 missing") and generically
("2 need attention") otherwise. Each tile loads and fails
on its own: a failed tile says what failed, shows the failed request in mono
("GET /api/v1/overview · knowledge · 503 · trace 01JA2M7X4Q"), and offers Retry
and a link to its page while the rest of the page keeps working. **Recent activity** lists the last few changes
with a link to Activity, leaving out changes to a resource whose experimental
feature is switched off. With nothing needing the user the list is a calm "all
good" card rather than an empty space, with one sentence on what is fine — the
agents connected, the servers answering and, while sync is on and has nothing
held, the vault in sync — each clause only for an area with something to report. With no agent registered the page is
the first-run panel alone: the supported agents with their config folders and
whether each was found on this machine, the found ones ticked, and **Review
and connect** opening the connection review for the ticked ones (every file
change shown before Coffer writes it); with none found it says so and its first
step is **Scan again**, each agent not found carrying an **Install** link to its
official install page; both offer adding an agent by hand, and the first step
for what agents share follows.

#### Scenario: overview lists what needs the user, most severe first
- **GIVEN** two failing MCP servers, one failing for five hours and one for two, a skill whose link drifted an hour ago, and an agent the user has not connected
- **WHEN** the user opens Overview
- **THEN** Needs you lists the older failing server first, then the other, then the skill, then the agent, each with its reason, since when where that is known, and one action opening the page or tab where it is dealt with

#### Scenario: health tiles carry the numbers and lines of Overview's board
- **GIVEN** two agents where one is not connected and the other's hook was edited by hand, a reconnecting channel, a knowledge collection edited a minute ago, a memory partition updated 14 minutes ago, a sync round that ended 4 minutes ago with one commit behind, a command that is not logged in, and a secret nothing uses
- **WHEN** the user opens Overview
- **THEN** Agents reads "1 of 2 connected" and "1 to connect", Channels "0 of 1" with "SeaTalk reconnecting since" a time, Knowledge "1 collection · edited" a time, Memory "Last update 14 min ago", Sync "4 min ago", "last round" and "1 behind · 0 ahead", CLIs "1 not logged in", Secrets "1 unused", and Usage "2.1M" with "Last 24 h"

#### Scenario: a row's action that runs in place shows it is in progress
- **GIVEN** a failing MCP server in Needs you whose action is to test it again, and an agent row whose action is to connect it
- **WHEN** the user clicks the server's action
- **THEN** the server's button reads "Retrying…" and is disabled, its reason carries "Starting <name>… it leaves this list once it answers.", and the test is called once
- **AND** once the list is read again with the server still listed, its button returns to normal, while the agent row's action stayed a link to its page throughout

#### Scenario: a needs-you row offers the item's hand-off in its menu
- **GIVEN** an attention item carrying a hand-off prompt, and a managed agent available
- **WHEN** the user opens the split button's menu and chooses Copy prompt, then presses Hand off to <Agent>
- **THEN** the daemon's prompt is copied as given, and Hand off to <Agent> starts the hand-off agent in the preferred terminal with the prompt sent
- **AND** with no managed agent available the row offers a Copy prompt button only, and every row's ⋯ menu ends with Ignore

#### Scenario: overview shows a calm card when nothing needs the user
- **GIVEN** an attention list with no items and no failed source, two connected agents, two enabled MCP servers and sync on with nothing held
- **WHEN** the user opens Overview
- **THEN** Needs you shows "Nothing needs you" with when it was checked and the sentence "Both agents are connected, 2 servers are answering and your vault is in sync. Anything that needs you shows up here.", and the health tiles show their areas as fine

#### Scenario: a needs-you row's action reads what it does for its kind
- **GIVEN** an attention item on a channel whose verb is check, and one on sync whose verb is review
- **WHEN** the user opens Overview
- **THEN** the channel's action reads Reconnect channel and carries an icon, and sync's reads Review held changes

#### Scenario: overview welcomes a first run with the agents to connect
- **GIVEN** a vault with no agent registered
- **WHEN** the user opens Overview
- **THEN** the page offers to connect the supported agents, naming which were found on this machine, followed by the first step for what they share
- **AND** with no supported agent found it says none was found and offers Scan again in place of connecting

#### Scenario: one area failing to load leaves the rest of overview working
- **GIVEN** the skills read fails while every other read answers
- **WHEN** the user opens Overview
- **THEN** the Skills tile says it could not load, with the failed request in mono, Retry and a link to Skills, and every other tile and the Needs you list render

#### Scenario: overview hides an area whose backend or feature is off
- **GIVEN** an area owned by a registered experimental feature that is switched off
- **WHEN** the user opens Overview
- **THEN** there is no tile for that area, while Custom tools, CLIs, Secrets and Usage each have one

#### Scenario: a resolved problem leaves overview on its own
- **GIVEN** Overview open with one item in Needs you
- **WHEN** the problem is resolved and the daemon announces an `attention` change
- **THEN** the page rereads the attention list and the row disappears without a reload

## ADDED Requirements

### Requirement: Let the user choose a terminal
The General tab MUST also expose a **preferred terminal**: the terminal Coffer
opens when the user resumes a conversation or session from a row, or presses a hand-off
button. The default is the operating system's default terminal (Terminal.app on macOS);
the user MAY override it by picking a terminal the daemon detected as installed
(enumerated via `GET /api/v1/fs/terminals`, [daemon](../daemon/spec.md) "List the terminals installed on this host";
a browser cannot list installed applications) or by entering a custom command template that holds
`{cwd}` and `{command}`. Like the preferred editor the value is persisted in `localStorage`
(`coffer.preferredTerminal`; empty means the system terminal), is read when the user clicks, and is never sent to the
daemon, except transiently as the `terminal` of an open ([daemon](../daemon/spec.md) "Open an agent session in a terminal").

#### Scenario: general tab persists the preferred terminal
- **GIVEN** the user opens the General settings tab
- **WHEN** they set a preferred terminal (by picking a detected terminal or entering a custom template)
- **THEN** reloading the page shows the same preferred-terminal value
- **AND** clearing the override restores the operating-system default terminal

#### Scenario: a custom terminal template must hold the command
- **GIVEN** the custom template field
- **WHEN** the user enters a template without `{command}`
- **THEN** the field says the template needs `{command}` and the value is not saved

#### Scenario: the preferred terminal is sent only when a session opens
- **GIVEN** a preferred terminal set and no session opened
- **WHEN** the user opens a session from a row
- **THEN** the open request carries that terminal as its `terminal`, and no other request to the daemon carried it

### Requirement: Let the user choose the hand-off agent
The General tab MUST also expose a **hand-off agent**: Claude Code or Codex, the agent
Coffer starts when the user presses a hand-off button ("Hand a machine-dependent problem
to an agent with one split button"). The choices are the managed agents. The value is persisted in
`localStorage` (`coffer.handoffAgent`: `claude_code` or `codex`) and read when the user clicks. With none
stored, or when the stored agent is not managed, the hand-off agent is the first managed agent
(Claude Code before Codex). With no managed agent the setting offers nothing and says
why.

#### Scenario: general tab persists the hand-off agent
- **GIVEN** Claude Code and Codex both managed
- **WHEN** the user chooses Codex as the hand-off agent and reloads the page
- **THEN** the setting still reads Codex and every hand-off button reads Hand off to Codex

#### Scenario: an unavailable hand-off agent falls back to the first managed one
- **GIVEN** Codex stored as the hand-off agent and only Claude Code managed
- **WHEN** a hand-off button renders
- **THEN** it reads Hand off to Claude Code
