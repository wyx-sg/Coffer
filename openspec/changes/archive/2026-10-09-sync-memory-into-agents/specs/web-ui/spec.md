## ADDED Requirements

### Requirement: Group the Data tab by what kind of data it is
The Data tab MUST show what Coffer stores in three blocks, one per kind of data
([Storage Is Five Classes by Nature](../../../docs/decisions/storage-is-five-classes-by-nature.md)),
and no other — in particular no "This Mac only" block, since what is true of this
machine only is a setting shown on the tab it belongs to:

- **Vault** — the git repository at `~/.coffer/vault/` holding the user's
  configuration, skills, knowledge, the memory hub and encrypted secrets, a repository whether
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
  worker's schedule (at daemon start and every six hours), and, under the tool
  calls row, a **Record tool call content** switch (on by default; [mcp-gateway](../mcp-gateway/spec.md)
  "Switch call content recording per machine") whose help says that arguments and
  results are kept with secrets masked and that turning it off keeps metadata only, with a
  **Clear expired now** action behind a confirmation, which reports what it
  removed; the last cleanup reads "Last cleared today at 12:00 — 1,284 rows" ("30 Sep at 12:00" for another day); a saved value survives a reload. Shortening a
  window (or turning Keep forever off) MUST ask first, and the confirmation
  MUST say how many records the shorter window deletes at the next cleanup and
  how many the table holds now and would hold after, counted by the daemon
  without deleting anything. **Clear expired now** also removes attachments past their window and reports them, and skill working files and config backups past theirs, as files. A refused save MUST say so above the blocks with
  **Try again**, name the window still in place, and mark the row "Not saved".
There is no cache block and no action that clears a cache: what Coffer rebuilds on its own
under `~/.coffer/derived/` is not shown. Edits auto-save, like every settings surface: there is no Save button.

#### Scenario: retention period persists across reload
- **GIVEN** the user opens the Data settings tab
- **WHEN** they turn off "Keep forever" for a record kind in History, set a specific number of retention days, and commit the field (blur or Enter), which auto-saves
- **THEN** reloading the page shows the same retention-days value that was saved

#### Scenario: the data tab shows three blocks and no this-mac block
- **GIVEN** a vault with versions and channel media on disk
- **WHEN** the user opens `/settings/data`
- **THEN** it shows Vault (size, versions, Open folder), Local content (attachments and media, size, Open folder, not synced, and the Attachments retention row) and History (retention for changes, tool calls, skill working files and config backups, the Record tool call content switch, and Clear expired now)
- **AND** it shows no Rebuildable cache block, no Clear cache action and no This Mac only block

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

#### Scenario: config backups are kept for a chosen window
- **GIVEN** the `config_backups` policy at 30 days
- **WHEN** the user opens `/settings/data`
- **THEN** History has a Config backups row at 30 days, after Skill working files, whose help text says the newest backup of each file is always kept
- **AND** shortening it asks first and the confirmation counts files, not records

#### Scenario: tool call content recording is switched on the Data tab
- **GIVEN** recording on, its default
- **WHEN** the user turns Record tool call content off on `/settings/data` and reloads
- **THEN** the switch reads off, and calls made from then on open with "Content was not recorded for this call"

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
- **AND** the sidebar lists exactly Coffer's operational surfaces — Overview; Agents, Model providers; Conversations, Channels; MCP servers, Custom tools, Skills, CLIs; Knowledge, Memory; Secrets, Activity, Sync — with Overview under no heading and the rest grouped under "Agents", "Run", "Capabilities", "Context" and "System" headings, with no other entry
- **AND** no navigation entry is Settings; a labelled Settings row sits at the bottom of the sidebar

#### Scenario: a switched-off feature leaves the sidebar
- **GIVEN** a sidebar entry owned by a registered experimental feature that is switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar leaves that entry out and lists every other entry under its heading
- **AND** with every feature switched on, the sidebar lists all fourteen entries
- **AND** with both features switched off, it lists only Overview, Agents, Model providers, Conversations, Channels, MCP servers, Custom tools, Skills, CLIs, Secrets, Activity and Sync

### Requirement: Use one shared table for every list surface
Every list surface that is a table — agents, the rounds
on Sync's Status tab — MUST use one shared table. It is searchable, filterable
and paginated where its list needs that, and it behaves the same everywhere:

- the filter row is the search first (`/` focuses it), then the pills, then
  **Clear filters** while anything is set, and shows no result counts;
- only number and time columns sort, in three states (one direction, the other,
  then the page's own order);
- a list that is bounded in memory shows whole, and past 100 rows grows 100 at a time as its
  end scrolls into view, with no button to press and no page-size setting; a list that can
  outgrow that pages by cursor and loads on scroll;
- a time reads relative while recent ("3 h ago") and as a date ("Aug 12") after;
- rows are selected with the header checkbox, a bar over the table reads "N of M
  selected" with the actions that apply, it holds no select-all of its own, and
  **Esc** clears the selection;
- a row's detail that opens beside the list opens in the one right-hand drawer,
  640 wide over a dimmed page, closed by **Esc**, a click outside or its ✕, with
  focus returning to the row.

The rules above have their exceptions: Sync's rounds table, whose quiet rounds
fold into one row, has no search or filter. A row click MUST open that item's
detail page, or for a sync round, its drawer. The Model providers, Channels, MCP
servers, Custom tools, Skills and CLIs pages are lists beside a reading pane
instead: a filterable list of rows, each a link that opens its item in the pane
at the item's own address, so a row click opens the item there; the same holds
for the rows of an agent's Skills, MCP servers and Plugins tabs, where the row
opens the dialog or page its name opens. A click anywhere on such a row MUST do
what a click on its name does, except when it lands on a control inside the row
(a button, link, switch, checkbox, menu item or input), carries a modifier key,
or ends a text selection; the name stays a real link or button, so keyboard
focus, Cmd/Ctrl-click and middle-click keep working. Knowledge is
its collection tree beside the pane in the same way. Activity's tabs share one
record list of their own, each row opening its record (see "Filter each
Activity tab and expand any row"). Sync's Remote tab is not a list surface: it
is the remote's settings, and the machine registry on its Machines tab is a
small plain table.

#### Scenario: a selection bar counts the rows and Esc clears it
- **GIVEN** a list with several rows
- **WHEN** the user ticks two rows, and then presses Esc
- **THEN** a bar reads "2 of N selected" with the actions that apply and holds no select-all, and Esc leaves no row selected and no bar

#### Scenario: a click anywhere on a list row opens its detail
- **GIVEN** the Skills library, the MCP servers list or an agent's Plugins tab showing at least one row
- **WHEN** the user clicks the row's empty space or a plain text cell, and then, on another row, clicks its switch or ⋯ menu
- **THEN** the first click opens that item's detail page or dialog, and the second only toggles or opens the menu without opening a detail

#### Scenario: a row click opens the item's detail page
- **GIVEN** a list surface showing at least one row
- **WHEN** the user clicks the row, or presses Enter on it
- **THEN** the app navigates to that item's detail page

### Requirement: Lay out every detail page's tabs alike
Every detail page MUST lay its tabs out the same way as every other. What a tab
shows belongs to the capability that owns that kind — the agent detail page's
tabs are [agent-registry](../agent-registry/spec.md)'s; this capability owns
only that they are tabs on a detail page laid out like every other.

Every detail page MUST put its tab in the path: `/<kind>/<id>/<tab>`, with the
default tab at the bare `/<kind>/<id>`, never in a `?tab=` query. A list page
with no detail to nest under (Sync, Activity) carries its tab in the query
instead, as `?tab=`, with the default tab at the bare address. The `<id>` is
the resource's name where the kind's name is fixed and unique within the kind —
skills (`/skills/<name>`), MCP servers (`/mcp-servers/<name>`) and custom tool
groups (`/custom-tools/<group>`), which are `mcp_server` resources — the agent's
type for agents (`/agents/<type>`), and the command for CLIs (`/clis/<command>`).
A kind whose name can be renamed — model providers, channels, knowledge
collections — MUST keep its immutable `uid` as the `<id>`
(`/model-providers/<uid>`), because a renamed name would break every
address to it. A page opened from a tab (a plugin, a direct MCP entry, an
unmanaged skill) nests under that tab's path.

#### Scenario: detail pages share one tab layout
- **GIVEN** two detail pages of different kinds
- **WHEN** each is opened with a tab named in its URL
- **THEN** each renders its tabs in the shared tab strip with that tab selected
- **AND** switching tab rewrites the URL the same way on both

#### Scenario: a detail tab lives in the path
- **GIVEN** a skill named `release-notes` and an MCP server named `github`
- **WHEN** the user opens the skill's Delivery tab and the server's Tools tab
- **THEN** the addresses read `/skills/release-notes/delivery` and `/mcp-servers/github/tools`
- **AND** `/skills/release-notes` and `/mcp-servers/github` open each page on its default tab

#### Scenario: a renamable kind keeps its uid in the address
- **GIVEN** a model provider renamed from `work` to `work-proxy`
- **WHEN** the user follows an address to it saved before the rename
- **THEN** the address still opens that provider, because it carries the uid and not the name

### Requirement: Show reach as one button that names it
Every list surface of a scoped kind that is a table MUST carry a **reach**
column — named for what it holds, not for the on/off flag it replaced: one
button that names the answer it already holds and nothing else — **All agents**,
**Off**, or the badges of the chosen agents alone. The button never reads "N of M agents": a count lives
only in the panel's footer. A list beside a reading pane shows no reach button in
its rows: the MCP servers and Skills lists show each row's reach as a mark
instead — Off, All agents, or the badges of the agents it reaches — and the Model
providers and Channels lists show none. A row of an object that is off leaves its
Reach cell empty. Every detail page of a scoped kind MUST carry the same button
in its header — a channel's sits in its Overview tab's agents section instead,
beside the agent the channel answers with. A kind that declares no scope — an
agent, a knowledge collection — MUST carry neither the
column, the button, nor a bulk reach action; see "Offer reach as one choice in a
panel". No list offers a filter by reach.

#### Scenario: the reach button states the reach it holds
- **GIVEN** resources that reach every agent, two chosen agents, and one that is off
- **WHEN** each one's reach button renders
- **THEN** they read "All agents", the two agents' badges alone and "Off"
- **AND** each is one button rather than a row of segments

#### Scenario: a kind that cannot be disabled shows no status control
- **GIVEN** the Agents page and one agent's page, and the Knowledge page and one collection's page
- **WHEN** each renders
- **THEN** the Agents list has no Status or Reach column, the collection tree carries no reach mark, and neither the agent's header nor the collection's carries a reach button or an on/off switch

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
- **Data** (`/settings/data`) — what Coffer stores, by kind: Vault, Local content and
  History (see "Group the Data tab by what kind of data it is").
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

### Requirement: Give each listed resource kind one sidebar entry
Every resource kind with a list UI MUST have exactly one sidebar entry — today five
kinds (`mcp_server`, `skill`, `knowledge`, `provider`, `channel`), five
entries — filed by what the user comes to do with it rather than under one
Resources heading, because "resource" is the framework's storage word, not a
word a user navigates by:

- **Model providers** is filed under Agents, not Capabilities or Settings: a
  `provider` is `{protocol, base_url, secret_ref}`, the endpoint and key an
  agent's model is served from, and the connection and model are chosen per
  agent in that agent's Change model dialog (spec
  [provider-switching](../provider-switching/spec.md) "Offer every connection operation over REST and in the web UI").
- **Channels** is filed under Run, beside Conversations and not merged into it:
  Conversations is where a person finds every session of every agent — a channel's among
  them — and opens or starts one in the terminal, while a channel is an IM bot set up once
  and revisited rarely. The conversations a channel carries are listed on the Conversations
  page with its badge (spec [chat](../chat/spec.md) "Show every agent's sessions on the
  Conversations page"), reached from the channel's Overview by one link; the Channels page
  holds setup, status and settings only.
- **MCP servers** and **Skills** are filed under Capabilities; **Knowledge** under
  Context.
- **Memory** is not a resource kind: its entry is the memory sync's page
  ([memory](../memory/spec.md) "Manage memory sync in the web UI and on the command line"), filed under Context beside Knowledge.
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
- **WHEN** the entries for resource kinds, and Memory's, are read
- **THEN** MCP servers, Custom tools, Skills, Knowledge, Memory, Model providers and Channels each appear exactly once, under Capabilities, Capabilities, Capabilities, Context, Context, Agents and Run respectively
- **AND** the MCP servers and Custom tools entries open `/mcp-servers` and `/custom-tools`, and a custom-tool group is not listed on the MCP servers page
- **AND** no heading reads "Resources"

### Requirement: Show what needs the user and each area's health on Overview
Overview MUST answer "is everything OK, and what needs me?" at a glance, from
the capabilities' own reads and never a route of its own. **Needs you** comes
first: one row per item of the attention list ([resource-framework](../resource-framework/spec.md)
"Report what needs a person across every kind"), most severe first and then
oldest, each with its resource and kind, the reason in a sentence, since when
where that is known, and exactly one action that opens the page — or the tab —
where the item is dealt with. The action reads what it does for that kind and
reason, not the bare verb — a channel's check is **Reconnect channel**, sync's
review **Review held changes** — behind a
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
items about connecting count — and Channels names the reconnecting one ("SeaTalk
reconnecting since 13:41"), otherwise the names joined with " · ". Knowledge's
line reads "4 collections · edited today 13:30", Memory's count of memories in the hub over "Last synced 14 min
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
- **GIVEN** two agents where one is not connected, a reconnecting channel, a knowledge collection edited a minute ago, nine memories in the hub last synced 14 minutes ago, a sync round that ended 4 minutes ago with one commit behind, a command that is not logged in, and a secret nothing uses
- **WHEN** the user opens Overview
- **THEN** Agents reads "1 of 2 connected" and "1 to connect", Channels "0 of 1" with "SeaTalk reconnecting since" a time, Knowledge "1 collection · edited" a time, Memory "9 memories" and "Last synced 14 min ago", Sync "4 min ago", "last round" and "1 behind · 0 ahead", CLIs "1 not logged in", Secrets "1 unused", and Usage "2.1M" with "Last 24 h"

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

## REMOVED Requirements

### Requirement: Send a memory-hook problem on Overview to the agent's Hooks tab
**Reason**: Coffer installs no memory hook into an agent, so there is no hook of Coffer's to change by hand or to repair.
**Migration**: None. Overview's Needs you lists the agent problems that remain, per [agent-registry](../agent-registry/spec.md) "List the supported agents as fixed rows on the Agents page".

### Requirement: Show memory delivery on the Memory page
**Reason**: Coffer delivers no memory into a session: there are no partitions, no Delivered tab and no delivery hook state to show. The Memory page is the memory sync's page.
**Migration**: See [memory](../memory/spec.md) "Manage memory sync in the web UI and on the command line"; the agent's Memory tab lists its own memory stores ([agent-registry](../agent-registry/spec.md) "Offer every agent operation over REST and on the Agents page").

### Requirement: Group the Data tab by what kind of data it is (before memory sync)
**Reason**: A MODIFIED block cannot drop a scenario, and this requirement loses "the data tab shows four blocks and no this-mac block", "clearing the cache is confirmed and rebuilt", which described the retired memory layer; it is renamed out of the way, removed, and added again under its own title (see ADDED below).
**Migration**: The dropped scenarios' markers are deleted or pointed at the scenarios of the requirement added again.

## RENAMED Requirements

- FROM: `### Requirement: Group the Data tab by what kind of data it is`
- TO: `### Requirement: Group the Data tab by what kind of data it is (before memory sync)`
