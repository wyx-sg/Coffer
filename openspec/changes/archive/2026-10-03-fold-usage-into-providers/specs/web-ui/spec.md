## RENAMED Requirements

- FROM: `### Requirement: Keep the sidebar to its fifteen entries`
- TO: `### Requirement: Keep the sidebar to its fourteen entries`

## MODIFIED Requirements

### Requirement: Keep the sidebar to its fourteen entries
The sidebar's entries MUST be exactly these, at these routes: one ungrouped entry
and five groups — fourteen today, and no fifteenth without a spec change.
Settings is not an entry: it is a modal opened from the sidebar footer (see
"Open Settings as a modal from the sidebar footer"). Usage is not an entry:
it is a tab of Model providers (see provider-switching "Show metered usage on a
Usage tab of Model providers"). Custom
tools and CLIs are specified by "Manage custom tools on their own page" and "Show
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
  Conversations    /conversations     — every conversation Coffer runs, from channels and from Coffer itself
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

### Requirement: Group the sidebar by what the user comes to do
The sidebar MUST be grouped by what the user comes to Coffer to do, so that each
heading names one intent and a new entry has one obvious home. There are five
groups, under headings in this order:

- **AGENTS** — set up the agents and the models they run on: Agents, then Model
  providers. Agents come first because they are the subject of the product; a
  provider is the endpoint and key each agent's model is served from.
- **RUN** — put an agent to work, directly or through an IM bot: Conversations,
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

### Requirement: Open Settings as a modal from the sidebar footer
Settings MUST NOT be a navigation entry: it is not one of the sidebar's fourteen
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
- **AND** the Settings row shows as active while the modal is open and not after it closes, and the fourteen navigation entries do not include Settings

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

### Requirement: Jump to any page or object from a command palette
The shell MUST offer a command palette, opened with ⌘K on macOS and Ctrl+K
elsewhere from any page, and from a search control in the sidebar. It MUST do
one thing — take the user somewhere — and MUST NOT carry an action that changes
state: no create, delete, enable, reach or run entry.

It lists two kinds of entry, filtered together by what the user types:

- **Pages** — every sidebar entry and every Settings tab, by the names the
  sidebar and the tabs use (see "Call a surface by one name everywhere"). A
  Settings tab opens in the Settings modal over the current page.
- **Objects** — the agents, the conversations, the resources of every kind
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
- **GIVEN** a registered MCP server whose title differs from its name
- **WHEN** the user opens the palette and types part of the server's name, then part of its title
- **THEN** each query lists the server as the best match, named by its title and marked as an MCP server
- **AND** choosing it opens `/mcp-servers/<name>` and closes the palette

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
carry a ⋯ menu — Copy prompt, Ask an agent while a managed agent is available,
then Ignore — with the daemon's prompt as given (every item carries one, the
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
items about connecting count, so a hook edited by hand does not make an agent
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
- **WHEN** the user opens the row's ⋯ menu and chooses Copy prompt, then Ask an agent
- **THEN** the daemon's prompt is copied as given, and Ask an agent opens New conversation and then the draft with the prompt in its composer, unsent
- **AND** with no managed agent available the menu offers Copy prompt only, and every row's menu ends with Ignore

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
