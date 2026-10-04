# Web UI

## Purpose
The web UI is the product shell a developer operates Coffer through: the
information architecture, the visual language, the list and detail conventions
every surface shares, the first-run, empty, loading and error states, and
internationalisation. It turned the gateway's functional skeleton into a real
product — a first-time visitor lands on content with one obvious next step, and
routine MCP work (registering a server, watching its health, browsing and
toggling its capabilities) looks and feels finished rather than scaffolded. A
first-time user can register an MCP server and reach a working gateway in-app;
pointing an MCP client at the shim is documented in the project README.

The sidebar is grouped **by what the person comes to do**: Overview on top,
then five groups — **Agents** (the agents and the model providers they run on),
**Run** (conversations and channels), **Capabilities** (MCP servers, custom
tools, skills, CLIs), **Context** (knowledge and memory) and **System**
(secrets, activity, sync) — with Settings a modal opened from the sidebar
footer. See
[The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md)
for the decision behind it, and the earlier
[The Sidebar Is Grouped by What the Person Comes to Do: Agents, Run, Capabilities, Context, System](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md)
for the axis it replaced (sidebar policy kept from it: no "soon" placeholders).
**Observability** (system health / metrics) is a reserved future surface and
appears in the sidebar only once it ships; Activity is not it, because a record
of what happened is not a measurement of how the system is doing.

This capability adds no REST route and no backend of its own. Every screen
renders over routes and entities other capabilities own, and those are named
where they are used. The Activity page in particular reads three records with
three owners: `GET /api/v1/audit` is the resource framework's record, written
for every kind; `GET /api/v1/mcp/invocations` (cross-server, each row naming its
server) is [mcp-gateway](../mcp-gateway/spec.md)'s; and `GET /api/v1/daemon/logs`
is [daemon](../daemon/spec.md)'s. What the page needs of them and does not
itself provide: that the invocation and daemon-log routes exist as read-only,
cross-cutting lanes, and that the daemon-log route is authenticated (the daemon
router leaves `/status` open, and log contents are not status). Normalising the
daemon log onto one field set is the daemon's work, not this page's: Coffer's
own records are one JSON object per line ([daemon](../daemon/spec.md) "Write one bounded daemon log in one format"), while the other
processes sharing `daemon.log` — uvicorn, rich output from an upstream MCP
server, a tail written before the daemon's
own format was fixed — are normalised onto the same fields on the daemon's side
of the wire, escape sequences stripped, a traceback riding with the record that
raised it, and a line no format fits kept whole rather than dropped. The page
renders what it is given and must not invent: a row shows a dash where its line
stated no time, no level or no logger, and each record is one row.
An agent reads each record on its own with `coffer log audit`, `coffer log mcp` and
`coffer log daemon`, and correlates them itself. The page's Everything tab
interleaves the three by time for a person, but each row keeps its own record's
columns and each record keeps its own tab, so a call's duration and a record's
level still have somewhere to live.

## Requirements

### Requirement: Give every scoped resource kind its own list surface
Every scoped resource kind MUST have its own list surface, so the navigation and
each list page carry no kind-specific branch.

#### Scenario: every resource entry opens a list page of its own
- **GIVEN** the sidebar's entries for resource kinds (see "Give each listed resource kind one sidebar entry")
- **WHEN** each entry's route is resolved against the app's route table
- **THEN** each resolves to its own list route rather than to "page not found"
- **AND** no two entries resolve to the same route

### Requirement: List only shipped surfaces in the sidebar
The sidebar MUST list only surfaces that have shipped. It MUST NOT carry "not
yet implemented" placeholders — a sidebar full of "soon" entries reads as an
unfinished scaffold, not a product; an entry leaves the sidebar when its
feature does, and returns with it. **Machines** left the sidebar as a top-level
fleet view and came back under Sync's Machines tab, where a machine is one
participant in convergence rather than a surface of its own.

#### Scenario: the sidebar carries no placeholder entries
- **GIVEN** the app shell is rendered
- **WHEN** every sidebar entry is inspected
- **THEN** each is a link to a route the app serves
- **AND** none is marked as coming soon or not yet implemented

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

### Requirement: Call a surface by one name everywhere
A surface MUST carry one name in every place it is named — sidebar, page header,
welcome panel, command palette and dialogs — because a surface the user reaches
two ways must not have two names. The names are these, in English and 中文, and
nothing else:

| English | 中文 |
| --- | --- |
| Overview | 总览 |
| Agents (group and entry) | 智能体 |
| Model providers | 模型提供商 |
| Run (group) | 运行 |
| Conversations | 对话 |
| Channels | 消息渠道 |
| Capabilities (group) | 能力 |
| MCP servers | MCP 服务器 |
| Custom tools | 自定义工具 |
| Skills | 技能 |
| CLIs | 命令行工具 |
| Context (group) | 上下文 |
| Knowledge | 知识 |
| Memory | 记忆 |
| System (group) | 系统 |
| Secrets | 密钥 |
| Activity | 活动 |
| Usage (a tab of Model providers) | 用量 |
| Sync | 同步 |
| Settings | 设置 |

In Chinese an agent MUST be called **智能体** everywhere the UI names one —
headings, page titles, buttons, dialogs and prose — never "Agent" or 代理.

#### Scenario: a surface carries one name in the sidebar and on its page
- **GIVEN** the UI in English and then in 中文
- **WHEN** each sidebar entry's label is compared with the title its page shows
- **THEN** the two are the same words for every surface in both languages
- **AND** in 中文 the group headings read 智能体, 运行, 能力, 上下文 and 系统, and no zh string names an agent as "Agent"

### Requirement: Collapse the sidebar to a remembered icon rail
The sidebar MUST collapse to an icon-only rail and back, and that choice MUST
persist across sessions (`localStorage`). The sidebar toggle's shortcut is ⌘\
(Ctrl+\ off macOS), shown in its tooltip.

#### Scenario: the collapsed sidebar stays collapsed after a reload
- **GIVEN** the user collapses the sidebar to its icon rail
- **WHEN** the shell is rendered again, as after a reload
- **THEN** it opens as the icon rail
- **AND** expanding it again is likewise remembered

### Requirement: Go back and forward from the title bar
The desktop shell on macOS MUST draw its own 44px title strip across the top of
the window, in the sidebar's colour and with no rule beneath it. Besides the
traffic lights the strip MUST hold only the sidebar toggle and back and forward
arrows through the app's own history, to the right of the toggle — with one
exception: an open conversation's title row (its title, its channel source and
its ⋯ menu) sits in the strip, 32px right of the sidebar's edge, because that page
has no header of its own; no other page puts anything there, and a page's title
stays in the page. The controls
start 16px right of the traffic lights, or at the left edge in full screen,
where the lights are hidden. Where the strip is blank the window MUST remain
draggable. While the sidebar is expanded its right edge MUST run up through the
strip; collapsed, the strip MUST run across. An arrow MUST be greyed out and
inert when the app's history has nowhere to go that way, and ⌘[ and ⌘] (Ctrl
off macOS) MUST do what the arrows do, except while the user types in a text
field. A browser tab has no strip and no arrows; its sidebar toggle sits beside
the logo, and an open conversation's title row is a 44px bar at the top of the content.

#### Scenario: the arrows in the title bar go back and forward through the app's history
- **GIVEN** the desktop shell with no history behind or ahead of the current page
- **THEN** both arrows are greyed out
- **WHEN** the user visits two pages and presses the back arrow
- **THEN** the app shows the first page and the forward arrow is enabled
- **AND** ⌘[ and ⌘] go back and forward the same way, except in a text field

### Requirement: Use one shared table for every list surface
Every list surface that is a table — agents, memory partitions, the rounds
on Sync's Status tab — MUST use one shared table. It is searchable, filterable
and paginated where its list needs that, and it behaves the same everywhere:

- the filter row is the search first (`/` focuses it), then the pills, then
  **Clear filters** while anything is set, and shows no result counts;
- only number and time columns sort, in three states (one direction, the other,
  then the page's own order);
- a long list shows a few rows and "Showing 5 of N · Show all";
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
at the item's own address, so a row click opens the item there; Knowledge is
its collection tree beside the pane in the same way. Activity's tabs share one
record list of their own, each row opening its record (see "Filter each
Activity tab and expand any row"). Sync's Remote tab is not a list surface: it
is the remote's settings, and the machine registry on its Machines tab is a
small plain table.

#### Scenario: a selection bar counts the rows and Esc clears it
- **GIVEN** a list with several rows
- **WHEN** the user ticks two rows, and then presses Esc
- **THEN** a bar reads "2 of N selected" with the actions that apply and holds no select-all, and Esc leaves no row selected and no bar

#### Scenario: a row click opens the item's detail page
- **GIVEN** a list surface showing at least one row
- **WHEN** the user clicks the row, or presses Enter on it
- **THEN** the app navigates to that item's detail page

### Requirement: Label every row action
A row action MUST be an icon plus its label, never a bare icon — a bare icon
reads as a different affordance from the labelled action beside it. Cards are
reserved for welcome and empty states.

#### Scenario: a row action shows its label beside its icon
- **GIVEN** a list row carrying a delete action
- **WHEN** the row renders
- **THEN** the action shows both its icon and its visible text label

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
collections, memory partitions — MUST keep its immutable `uid` as the `<id>`
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
**Off**, the badges of the chosen agents alone, or **No agent selected** for a
scope narrowed to nobody. The button never reads "N of M agents": a count lives
only in the panel's footer. A list beside a reading pane shows no reach button in
its rows: the MCP servers and Skills lists show each row's reach as a mark
instead — Off, All agents, or the badges of the agents it reaches — and the Model
providers and Channels lists show none. A row of an object that is off leaves its
Reach cell empty. Every detail page of a scoped kind MUST carry the same button
in its header — a channel's sits in its Overview tab's agents section instead,
beside the agent the channel answers with. A kind that declares no scope — an
agent, a knowledge collection, a memory partition — MUST carry neither the
column, the button, nor a bulk reach action; see "Offer reach as one choice in a
panel". No list offers a filter by reach.

#### Scenario: the reach button states the reach it holds
- **GIVEN** resources that reach every agent, two chosen agents, nobody selected, and one that is off
- **WHEN** each one's reach button renders
- **THEN** they read "All agents", the two agents' badges alone, "No agent selected" and "Off"
- **AND** each is one button rather than a row of segments

#### Scenario: a kind that cannot be disabled shows no status control
- **GIVEN** the knowledge and memory list pages and one collection's and one partition's page
- **WHEN** each renders
- **THEN** no list has a Status or Reach column and no header carries a reach or status button

### Requirement: Offer reach as one choice in a panel
The button MUST open a popover where "who does this reach?" is a single choice
between **Off**, **All agents** (which includes agents added later) and **Chosen
agents**, the last over the scope's list of agents with a **Filter agents** box
that narrows it. The list stays visible but dimmed and frozen under Off and All
agents, with its ticks kept, so switching back restores them. Off is a choice and
never an inference: choosing Chosen agents with nothing ticked reaches nobody and
reads "No agent selected", not Off. The footer carries the one summary of the
reach — the only place a count appears.

#### Scenario: the reach panel offers the reach states as one choice
- **GIVEN** a resource of a scoped kind
- **WHEN** its reach panel is opened
- **THEN** it offers Off, All agents and Chosen agents as radio choices with its current state chosen
- **AND** choosing Chosen agents shows the list of agents to pick from

### Requirement: Save the reach on every change
The panel MUST write every change at once — each switch of mode and each tick,
with no Done button — and say how the write is going in its footer ("Applying…",
then "✓ Saved"), so a panel that is opened and dismissed writes nothing. The
panel keeps its own choice while it is open, so the refetch that follows a write
cannot move the row it is anchored to; the lists refresh once when it closes. A
write that fails MUST stay in the panel, on the row of the agent just ticked,
with **Retry** and **Untick**, and MUST NOT be a toast. For a skill the write
reports delivery per agent: an agent the reach was saved for but the skill could
not be delivered to is a failed row with the daemon's reason.

#### Scenario: a dismissed reach panel writes nothing
- **GIVEN** a reach panel opened on a resource
- **WHEN** the user dismisses it without choosing
- **THEN** nothing is written

#### Scenario: each reach change is saved at once
- **GIVEN** a reach panel open on a resource reaching nobody
- **WHEN** the user ticks Claude Code, then Codex, then unticks Claude Code
- **THEN** each tick writes the whole list at that moment, naming the agent just ticked, and the footer says the write is applying and then saved
- **AND** there is no Done button

#### Scenario: a failed reach write stays on the agent's row
- **GIVEN** a reach panel on which the write for Codex fails
- **WHEN** the failure comes back
- **THEN** Codex's row reads Failed with the reason, Retry resends exactly that write, and Untick drops the tick, with no toast

### Requirement: Mount one reach control in three places
The reach control MUST be one component mounted in every place a reach is
changed — a table's row, the detail header and the multi-select bar — so they
can never drift into different answers to one question. On a list beside a
reading pane the row shows the reach as a mark and the header and the
selection bar carry the control.

#### Scenario: row, header and selection bar mount the same reach control
- **GIVEN** an MCP server that reaches every agent
- **WHEN** its list row, its detail header and the list's selection bar render
- **THEN** the row reads its reach and the header and the selection bar each carry the same reach button, which opens the same reach panel

### Requirement: Apply reach to a whole selection
A multi-select MUST apply the same choice to the whole selection from the
selection bar's **Reach** button. A bulk write is a new intent, so its popover
(340 wide) opens with no mode picked rather than on any one row's value; it shows
for each agent how many of the selected items it reaches (a dash where only some
do) and, once the person changes one, the old → new counts, and nothing is
written until **Apply**. A row that fails MUST be reported inside the popover —
"Applied to 2 of 3", the failing names, a **Retry** that resends only those —
never as a toast, and the selection is cleared only when every row succeeded.
Delete stays its own button beside it.

#### Scenario: a bulk reach write starts blank and reports failures in one summary
- **GIVEN** several selected rows, one of which will fail to update
- **WHEN** the user opens the selection bar's reach control, chooses Off and presses Apply
- **THEN** the popover opened with no mode picked, every other row is written, and the one failure is reported in the popover as "Applied to 2 of 3" naming the item, with no toast
- **AND** Retry resends only the failed item, and success closes the popover and clears the selection

### Requirement: Reach an item inside a group through the group's reach
An item that lives inside a parent — a custom tool in its group — MUST carry an
**inherited** reach control in its own table cell, with the same button and popover
and no Off: **Same as the group** (the default, which follows the group's agents
and says which), **All agents**, or **Chosen agents**. Each change saves at once.
A tool never reaches an agent its group does not reach, and an item that is off
leaves its Reach cell empty.

#### Scenario: an item's reach offers the group's reach first
- **GIVEN** a tool in the `deploy-api` group, which reaches Claude Code and Codex
- **WHEN** the tool's reach is opened
- **THEN** the trigger reads "Same as the group" and the popover offers Same as the group, All agents and Chosen agents, with no Off, saying "deploy-api gives it to Claude Code and Codex"
- **AND** each choice is written as soon as it is made, and the list is frozen unless Chosen agents is picked

### Requirement: Make empty, loading and error states first-class
No surface may render a blank page, or a generic error, where a next action
exists. Empty, loading and error states MUST be first-class on every surface,
not an afterthought on some of them. A split-view list page (MCP servers,
Skills, CLIs, Channels, Custom tools, Model providers, Knowledge) keeps its
header and filter in every state and states each inside the pane it belongs to:
while the list loads, seven two-line skeleton rows stand in the list pane and
the right pane is empty; when the list read fails, a compact danger block in the
list pane titled "Couldn’t load <kind>" says nothing was changed and offers
Retry, Open daemon log (Activity › Daemon log) and the failed request as
`GET <path> · <status> · trace <id>`; when a filter hides every row, the list
pane names the filter ("No server matches “terraform”") with what the filter
searches and a Clear filter button, and the right pane reads Nothing selected
with the page's Add action as an outline button. A detail whose object no
longer exists is a page-size state — "This server no longer exists", the
address that was asked for, Last seen and Audit rows read from the audit log,
Back to the list and View in Activity.

#### Scenario: a list surface shows first-class loading and error states
- **GIVEN** a list surface whose query is still pending, and then one whose query fails
- **WHEN** each renders
- **THEN** the pending one keeps its page header over skeleton rows rather than a blank page
- **AND** the failed one shows an error block in the list pane with a readable message rather than an empty page

#### Scenario: a failed list shows its error block in the list pane
- **GIVEN** the MCP servers list read fails with a 500 and a trace id
- **WHEN** the page renders
- **THEN** the header and the filter stay, and the list pane shows "Couldn’t load MCP servers" with Retry, Open daemon log and the line `GET /api/v1/resources?kind=mcp_server · 500 · trace <id>`
- **AND** Open daemon log leads to Activity's Daemon log tab

#### Scenario: a filter that matches nothing names the filter and offers Clear filter
- **GIVEN** the MCP servers list with servers
- **WHEN** the user types a filter no server matches
- **THEN** the list pane reads "No server matches “terraform”" with what the filter searches and a Clear filter button
- **AND** Clear filter empties the field and brings the rows back

#### Scenario: a detail whose object is gone says so and leads back
- **GIVEN** the address names an MCP server that is not registered
- **WHEN** the detail pane renders
- **THEN** it reads "This server no longer exists" with the address, and offers Back to MCP servers and View in Activity

### Requirement: Show loading only when it lasts
A loading placeholder (a skeleton row, the page fallback) MUST stay invisible for
its first 300 ms and then appear, so an answer that arrives quickly never
flashes one.

#### Scenario: a loading placeholder waits 300 ms before it shows
- **GIVEN** a skeleton block and the page fallback
- **WHEN** either renders
- **THEN** each carries the 300 ms delayed-appearance animation, so it is invisible until the wait is over

### Requirement: Keep an error toast until it is dismissed
A toast that reports an error MUST stay on screen until the user dismisses it and
MUST draw no countdown line; a success or info toast leaves on its own after 5
seconds (8 with Undo) and draws that line.

#### Scenario: an error toast stays until dismissed
- **GIVEN** a failed action that raised an error toast
- **WHEN** a minute passes
- **THEN** the toast is still on screen with no timer line
- **AND** dismissing it removes it

### Requirement: Never show a generic error text
A view MUST NOT show the literal text "unexpected error" or `INTERNAL_ERROR`.

#### Scenario: a server error never reads as an unexpected error
- **GIVEN** a list surface whose query fails with an `INTERNAL_ERROR` envelope
- **WHEN** the page renders the failure
- **THEN** it shows a readable message
- **AND** neither the literal text "unexpected error" nor `INTERNAL_ERROR` appears anywhere on the page

### Requirement: Welcome an empty list with one next action
A list with nothing in it MUST render a welcome card — a short pitch and one
primary action — and MUST NOT render an empty table or a placeholder ghost row.

#### Scenario: empty resources list renders a welcome view
- **GIVEN** the daemon is running and zero resources are registered
- **WHEN** the user opens `/mcp-servers`
- **THEN** the page renders a welcome card with a short pitch and a primary "Add server" button
- **AND** the welcome card does NOT show an empty table or a placeholder ghost row

### Requirement: Explain an unreachable daemon without losing the shell
When the daemon cannot be reached at all, the app MUST render a "Daemon not
running" view naming the one recovery its host can actually offer, and the
sidebar MUST stay visible so the user can orient themselves.

#### Scenario: token-missing renders an actionable empty state
- **GIVEN** `~/.coffer/daemon.json` does not exist (daemon is not running)
- **WHEN** the user navigates to `http://localhost:5173/`
- **THEN** the page shows a "Daemon not running" view naming the one recovery a browser can offer — the `coffer daemon start` command to run (the Restart control belongs to the desktop shell, which can actually spawn a daemon)
- **AND** the sidebar is still visible so the user can orient themselves
- **AND** no view shows the literal text "unexpected error" or `INTERNAL_ERROR`

### Requirement: Show a self-clearing offline banner
When the daemon's status probe stops answering while the app is open, the shell
MUST first try to reconnect without taking the page away: it retries after 1, 2,
4 and 8 seconds, and for the first 10 seconds of failures the page stays where
it was, dimmed and not interactive, under a reconnecting bar at the top of the
workspace that names the attempt, when the next one runs and that nothing is
lost, with a Retry now control. After that the page MUST make way for an
offline state in the workspace — the sidebar stays — naming the recovery the
host can offer: in the desktop shell a Start daemon control, because only it can
spawn a daemon; in both hosts Retry, the `coffer daemon start` command to copy
("Or start it from a terminal"), and a footer line with when the next check
runs and when the daemon last answered. The daemon log is read without the
daemon, which the Activity page's Daemon log tab needs: in the desktop shell an
Open daemon log control has the shell open `~/.coffer/logs/daemon.log` in the
system's default viewer; in a browser the screen shows the `coffer log daemon`
command to copy ("Read the daemon log from a terminal"). The reconnecting bar
marks its state with a still partial ring, not a spinner.
Both MUST clear themselves once the daemon is reachable again, with no manual
page reload: every query is read again and a toast says the app reconnected.
The reconnecting bar and the offline state express the daemon's state; the
sidebar's Settings row carries none of it.

#### Scenario: daemon-offline banner appears when daemon is unreachable
- **GIVEN** the daemon is not running (no reachable `127.0.0.1:<port>` from `~/.coffer/daemon.json`, or the file is absent)
- **WHEN** the user has the app open and any authenticated request to the daemon fails to connect
- **THEN** the reconnecting bar shows first, and after 10 seconds of failures the offline state renders in the workspace offering the recovery the host can actually give — the `coffer daemon start` command to copy in both hosts, and in the desktop shell also a Start daemon control, because only it can spawn a daemon
- **AND** the offline state disappears automatically once the daemon becomes reachable again, without a manual page reload

#### Scenario: the offline screen opens the daemon log without the daemon
- **GIVEN** the offline state is showing in the desktop shell
- **WHEN** the user clicks Open daemon log in its footer line
- **THEN** the shell opens the daemon log file in the system's default viewer, without asking the daemon

#### Scenario: the offline screen offers the daemon log command in a browser
- **GIVEN** the offline state is showing in a browser
- **WHEN** the user reads the screen
- **THEN** it shows the `coffer log daemon` command with a Copy button instead of a link to Activity

#### Scenario: a daemon that comes back within seconds leaves the page in place
- **GIVEN** a page open with a running daemon
- **WHEN** the daemon stops answering and answers again within 10 seconds
- **THEN** the page stays mounted under the reconnecting bar, dimmed and not interactive, while the retries run
- **AND** once it answers the bar goes, every query is read again and a toast says the app reconnected

### Requirement: Express every surface in one visual language
Every surface MUST be expressed in one visual language — a distinct typographic
hierarchy and consistent spacing, drawn from the shared design tokens rather
than restated per screen.

#### Scenario: page headers share one typographic scale
- **GIVEN** two different list pages
- **WHEN** each renders its page header
- **THEN** both titles are the page's single top-level heading with the same typographic classes
- **AND** both subtitles share one style distinct from the title

### Requirement: Open an MCP server on its Overview
An MCP server's detail page MUST open on a primary "what is this server doing?"
Overview, before the per-capability tabs, and its tabs — Overview, Tools,
Resources, Prompts, Invocations — MUST carry no counts. Under the banner the
Overview stacks **Last 24 hours** (the server's calls and errors, with a table of
the agents that made them and a line for a session that named no agent; for a
server that is off, only its last call and who made it), **Requires** — what the
server's command and settings need from this machine (see mcp-gateway "Show what
an MCP server requires"): the launcher as a row reading "Found · <version>" or
"Not found" with a View in CLIs link to `/clis/<launcher>`, and each secret as
Set, Missing or Waiting for approval with a View in Secrets link to `/secrets` —
and **Most-called tools**: the busiest four, read-only with no switches, each
marked when it sits behind search, with the rest one link away ("Show all N in
Tools").

#### Scenario: a server's detail page opens on its Overview
- **GIVEN** a registered MCP server
- **WHEN** its detail page is opened with no tab named in the URL
- **THEN** the Overview tab is the selected tab and its content is shown
- **AND** the Tools, Resources and Prompts tabs follow it

#### Scenario: the Overview stacks the last 24 hours by agent, what it requires and the busiest tools
- **GIVEN** a server with 312 calls in 24 hours, a launcher that is found, one secret that is missing and five tools
- **WHEN** its Overview opens
- **THEN** it shows the totals and the table of the agents that called it, then Requires with the launcher found and linked to its CLI page and the secret Missing and linked to Secrets, then the four busiest tools without switches and a link to all five
- **AND** no Agents section and no reach note sit on it

### Requirement: Keep an MCP server's header fixed and answer each state in a banner
An MCP server's header MUST carry the same actions whatever the server's state —
**Reach**, **Test** and **Edit** and a **⋯** menu — and Test MUST never become
"Test again". What is wrong MUST be said in a banner under the tabs that holds the
fix: a failing server says its last error, since when and its last success, and
offers **View errors** for an HTTP server — which Coffer does not start, so it has
no log — opening the Invocations tab on its errors, or **View log** for a stdio
server, opening the Server log; a rejected key says so and offers **Replace key**;
a server that is off says no agent can use it and offers **Turn on**; a secret
missing on this machine is named with **Add secret**. The ⋯ menu of a stdio server
holds Server log, Copy config as JSON, Turn off and Delete…; an HTTP server's has
no Server log, and a server that is already off has no Turn off. The Server log is
a drawer with no tabs, each line saying who wrote it (Coffer or the server's own
stderr). Turning a server off answers with a toast offering Undo, saying its
settings and the agents chosen are kept.

#### Scenario: a failing HTTP server says why and offers View errors, not a log
- **GIVEN** an HTTP server that is failing with a last error, a time it started failing and a last success
- **WHEN** its page opens
- **THEN** the banner shows the error, since when and the last successful call, the header still offers Test, and the banner offers View errors and no View log
- **AND** View errors opens the Invocations tab filtered to errors

#### Scenario: a failing stdio server opens its Server log
- **GIVEN** a stdio server that is failing
- **WHEN** the user chooses View log in its banner
- **THEN** the Server log drawer opens

#### Scenario: an Off server explains itself and offers Turn on
- **GIVEN** an MCP server that is off
- **WHEN** its page opens
- **THEN** a banner says no agent can use it, and Turn on enables it

#### Scenario: an HTTP server's menu has no Server log
- **GIVEN** an HTTP server and a stdio server
- **WHEN** each one's ⋯ menu opens
- **THEN** the HTTP server's offers Copy config as JSON, Turn off and Delete… and the stdio server's also offers Server log first

### Requirement: Open one call in a drawer
A row of a server's Invocations tab MUST open the call in a 640-wide drawer
below the title bar with its attributes — the outcome and error, the server and
its transport, the tool, the agent that called, the session and the time — and a
note that the arguments and the result are never stored. For a call the server
never answered the drawer offers the daemon's hand-off. It MUST NOT offer a
server log for an HTTP server.

#### Scenario: a call opens in a drawer with its attributes
- **GIVEN** an HTTP server with one errored call
- **WHEN** the user opens that call from the Invocations tab
- **THEN** the drawer shows the error, "sentry · Streamable HTTP" and who called, says the arguments and the result are never stored, and offers no server log

### Requirement: Select several MCP servers from the list
A MCP server's row MUST show its checkbox on hover or focus, and on every row
once any is ticked. Ticking a row puts the selection bar at the top of the list:
"N of M selected", **Reach** (the bulk control of "Apply reach to a whole
selection"), **Delete** and a clear (×); a select-all row appears and ticks every
listed server. The built-in server has no checkbox and is not counted, and Esc
clears the selection. The list's search is its only filter.

#### Scenario: ticking a server puts the selection bar at the top
- **GIVEN** the MCP servers list
- **WHEN** the user ticks one row
- **THEN** the bar at the top reads "1 of N selected" with Reach, Delete and a clear control
- **AND** the list offers no reach filter

### Requirement: Keep a failed save and a partial batch in the MCP dialogs
The Add server and Edit dialogs MUST test the form as typed before it is saved
(Test), showing the answer in the form: a failure says why and that nothing was
saved, and offers the daemon's hand-off when the failure depends on this machine
(a command not found, a process that exits, no connection, a timeout) — never when
the person must act, such as a secret that is not stored. A failed save MUST stay
in the dialog with every edit intact and the primary button reading **Retry**. A
batch that only partly went in MUST stay on the review, say which servers were
added and which were refused with the reason, and let Add retry only the refused
ones. A server whose secret cites one already sent elsewhere is added with its
binding waiting for approval; that MUST be said before the dialog lets go,
naming the secret. A success is a toast that says what was kept or added.

#### Scenario: a failed save stays in the Edit dialog and Save becomes Retry
- **GIVEN** the Edit dialog with changes and a daemon that refuses the save
- **WHEN** the user saves
- **THEN** the dialog stays open, the changes are intact and the primary button reads Retry

#### Scenario: a batch that only partly went in stays on the review
- **GIVEN** a review of three servers of which the daemon refuses one
- **WHEN** the user presses Add
- **THEN** the review stays open saying two were added and naming the refused one with its reason, and Add retries only the refused server

#### Scenario: a server citing an existing secret says it waits for approval before the dialog lets go
- **GIVEN** a form whose server cites a secret already sent to another server
- **WHEN** the server is added
- **THEN** the dialog says the secret waits for approval before it closes

### Requirement: Keep the capability tabs uniform
The Tools, Resources and Prompts tabs MUST be uniform — each carrying its count of how many are on, a filter box, All on · All off and a per-row enable toggle, with each row's use in the last 24 hours — and MUST keep that chrome even when the upstream exposes none of that kind, saying so inside the tab rather than as a bare card. A tool row opens to its full description, its input parameters and the name agents see it by. The server list likewise carries a search box — its only filter — and a client-side pager so a large vault stays navigable; the skills list works the same way, and no list offers a filter by reach.

#### Scenario: capability toggle uses the redesigned tab layout
- **GIVEN** a registered MCP server with at least one tool and one resource
- **WHEN** the user opens the server's detail page and clicks the Tools tab
- **THEN** each tool renders as a row with its name, description, and an enabled/disabled switch
- **AND** toggling a tool's switch persists the change (capability preference) and re-fetches the tool list
- **AND** the same flow works for the Resources tab and the Prompts tab

#### Scenario: resource capability toggle works via the Resources tab
- **GIVEN** a registered MCP server that exposes at least one resource URI
- **WHEN** the user navigates to the Resources tab and disables a resource via its toggle
- **THEN** the resource switch reflects the disabled state

#### Scenario: prompt capability toggle works via the Prompts tab
- **GIVEN** a registered MCP server that exposes at least one prompt
- **WHEN** the user navigates to the Prompts tab and disables a prompt via its toggle
- **THEN** the prompt switch reflects the disabled state

#### Scenario: capability search box narrows the tool list
- **GIVEN** a registered MCP server with multiple tools
- **WHEN** the user types a partial name in the capability search box on the Tools tab
- **THEN** only matching tools remain visible and non-matching tools are hidden

### Requirement: Add MCP servers from one paste box
The MCP servers page MUST carry one **Add server** action, and no separate
paste-JSON action. It opens a modal whose first step is one paste box that
recognises what was pasted, so the user can paste whatever an MCP server's
README gives them:

- an `mcpServers` JSON block, or a single server object, holding one server or
  many;
- Codex TOML `[mcp_servers.<name>]` tables, one or many;
- a command line, including `claude mcp add …` and `codex mcp add …`, which
  becomes a stdio server — its name, environment (`-e` / `--env`) and command
  taken from the command, a plain command's name suggested from its package;
- a URL, which becomes a Streamable HTTP server, its name suggested from the
  host.

One recognised server MUST open the manual form prefilled with it; several MUST
open the review step. The same dialog carries **Import from agents** as a link,
which lists the direct MCP entries in the agents' own config files to adopt
([agent-registry](../agent-registry/spec.md) "Adopt a direct MCP entry into Coffer"); it is not a
second button on the page. The dialog adds MCP servers only: it offers no
custom tool (an HTTP API imported from an OpenAPI document or defined by hand),
which is added on the Custom tools page (see "Manage custom tools on their own
page").

The review step covers every server's environment values and, for an HTTP
server, the values of its `headers` too, read with the same secret detection as
the environment rather than ignored (a header and an environment entry of the
same name are one header, the `headers` value winning). The user confirms which
values are secrets; secrets MUST be lifted into the encrypted secret store
with only their refs kept in the resource config, and each server MUST be
registered before its secrets are written, so a failed registration leaves no
orphan secret entry. The user also chooses the servers' reach there.

The review step MUST show each server's name as the name it will keep: it
cannot be changed after registration
([mcp-gateway](../mcp-gateway/spec.md) "Manage MCP servers as resources"). Each
name is taken from its key, table or command, normalised to the pattern
mcp-gateway allows — lower case, other characters turned into hyphens — and can
be corrected in the review before it is added. A name longer than 24
characters MUST be flagged, before submit, with a message naming the limit, and
the dialog MUST NOT send that server's registration until the name is shortened.

#### Scenario: MCP server registration round-trip via JSON import
- **GIVEN** the user opens the Add server dialog from the MCP servers page
- **WHEN** they paste the standard `mcpServers` JSON holding one server and add it from the prefilled form
- **THEN** the app posts the server to `/api/v1/resources`, then writes any secret env values to `/api/v1/secrets` (register-first ordering avoids orphan secret entries when registration fails)
- **AND** on success the dialog closes and the app navigates to the server's detail page `/mcp-servers/<name>` showing the Overview tab
- **AND** the new server appears on the MCP servers list with health "unknown" then "healthy" within 10 seconds

#### Scenario: add-server form navigates to detail then back to list shows card
- **GIVEN** the user completes the Add server dialog for a new MCP server
- **WHEN** they are taken to the server's detail page and then navigate back to `/mcp-servers`
- **THEN** the server appears in the MCP servers list

#### Scenario: a pasted HTTP server's headers are reviewed for secrets
- **GIVEN** the user pastes an `mcpServers` block holding an HTTP server with a `headers` object that carries an `Authorization` value
- **WHEN** the review step is shown and confirmed
- **THEN** the header is offered as a secret, its value is written to the secret store, and the registered server keeps only its ref (`secret_refs`), never the value in `headers`

#### Scenario: the import review shows each server's fixed name
- **GIVEN** the user pastes an `mcpServers` block holding one server keyed `My Server` and one keyed with a 30-character name
- **WHEN** the review step is shown
- **THEN** each server's name is shown with a note that it cannot be changed after registration, the first normalised to `my-server`, and the 30-character name is flagged with the 24-character limit
- **AND** no request is sent to `/api/v1/resources` for the flagged server until its name is shortened in the review

#### Scenario: pasting JSON with three servers opens the review
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes an `mcpServers` block holding three servers
- **THEN** the dialog recognises three servers and opens the review step listing all three with their detected secrets and a reach choice
- **AND** confirming registers the three servers, each before its secrets are written

#### Scenario: pasting a command line prefills a stdio server
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes `claude mcp add github -e GITHUB_TOKEN=ghp_x -- npx -y @modelcontextprotocol/server-github`
- **THEN** the manual form opens prefilled as a stdio server named `github` with command `npx`, arguments `-y @modelcontextprotocol/server-github` and `GITHUB_TOKEN` offered as a secret

#### Scenario: pasting a URL prefills a Streamable HTTP server
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes `https://mcp.example.com/mcp`
- **THEN** the manual form opens prefilled as a Streamable HTTP server with that URL and a name suggested from the host

#### Scenario: pasting Codex TOML reads its server tables
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes a `[mcp_servers.docs]` table with a command, arguments and an `env` table
- **THEN** the manual form opens prefilled as a stdio server named `docs` with that command, arguments and environment, the secret-looking values offered as secrets

#### Scenario: the add dialog links to importing from agents
- **GIVEN** the MCP servers page
- **WHEN** it renders and the user opens Add server
- **THEN** the page carries one Add server action and no separate paste-JSON action, and the dialog carries an Import from agents link
- **AND** the dialog offers no custom tool, neither an OpenAPI import nor a hand-made HTTP request

### Requirement: Explain unreadable pasted input in the dialog
Input the paste box cannot read as any of the recognised forms — malformed
JSON or TOML, a JSON or TOML document that does not match a server's shape, or
text that is neither a command line nor a URL — MUST keep the dialog open with a
readable message saying what was expected and, where it applies, the parse
location or the failing field, and MUST offer a manual choice of the server's
type (stdio or Streamable HTTP) that opens the empty form. It MUST NOT send a
request.

#### Scenario: JSON import shows readable error for malformed JSON
- **GIVEN** the user opens the Add server dialog
- **WHEN** they paste a payload that is not valid JSON (or a valid JSON document that does not match the `mcpServers` shape)
- **THEN** the dialog stays open and renders a readable error explaining what is wrong (parse error location for malformed JSON, or the failing field for shape-mismatch)
- **AND** no request is sent to `/api/v1/resources` or `/api/v1/secrets`
- **AND** the dialog never shows the literal text "unexpected error" or `INTERNAL_ERROR`

#### Scenario: unreadable input offers a manual type choice
- **GIVEN** the Add server dialog open on its paste box
- **WHEN** the user pastes text that is no recognised form, such as a sentence from a README
- **THEN** the dialog says it could not read a server from it and what it accepts, and offers stdio and Streamable HTTP as a manual choice
- **AND** choosing one opens the empty form for that type, and no request is sent

### Requirement: Scope Activity's calls table to one server on its page
A server's **Invocations** tab MUST read the same invocation log Activity's MCP
calls tab reads, scoped to that one server, rather than a second record that
would have to be kept in step with the first. It renders the one calls list the
server's "Calls and server log" drawer renders: the calls the gateway proxied
for this server in the last 24 hours, newest first, All or Errors, one agent or
all, each row its time, tool, calling agent, result and duration, and the
chosen call (the newest by default) opened below with its result, how long it
took and its session — the account of what an agent did when the agent is the
thing that is broken. Activity's MCP calls tab reads every server's calls and
names each row's server.

#### Scenario: a server's invocations tab is the Activity calls table scoped to it
- **GIVEN** a registered MCP server
- **WHEN** its Invocations tab and Activity's MCP calls tab each render
- **THEN** the server's tab asks only for that server's calls, lists them without a server column and opens the newest below the list
- **AND** Activity's tab asks the cross-server route for every server's calls and names each row's server

### Requirement: Gather the three records on one Activity page
The three records Coffer keeps — the audit log (what changed in the vault, and
who changed it), the MCP invocation log (every call the gateway proxied, and
which agent's session made it) and the daemon log (what Coffer itself did,
including what broke) — MUST reach a person through one page at `/activity`,
under System. The header carries the title, a **Live** mark (a dot and the word,
**Reconnecting…** while the daemon's change feed is closed), the line "Every
change, tool call and daemon record, newest first." and a ghost **Export** menu.
Four tabs follow, without counts: **Everything**, the default, merging the
changes, the calls and the daemon's warnings and errors into one newest-first
stream, then one tab per record — **Changes**, **MCP calls**, **Daemon log** —
each a newest-first table in a bordered box with the columns that record
actually has: Everything — time, an icon, the event, who (an agent or the actor)
and how long a call took; Changes — time, an icon, the change, who; MCP calls —
time, agent, `server.` (muted) and tool, how long it took (right-aligned,
sortable over the loaded rows) and the status as a dot and its word; Daemon log —
time with milliseconds, level, logger and message. The day a run of rows falls
on is a sunken heading row inside the box ("Today · Sep 29"); no summary line
sits above the table. A tab whose log failed to load shows a warning icon. On the
Daemon log a line above the box names the file the tail is read from, "newest
first", "following" while the change feed is open, and **Open in Finder**, which
reveals the file through the daemon. Each tab pages older records on request:
the box's last row says "Showing 30 of 1,204 · next 50 from before 13:58" with
**Load 50 more**, and only once everything kept is shown does it say so, with how
long MCP calls are kept and a link to Settings › Data.

#### Scenario: activity gives each record its own tab
- **GIVEN** Coffer has recorded an audit entry, an MCP invocation and a daemon log record
- **WHEN** the user opens `/activity` and moves through its tabs
- **THEN** Everything shows all three newest first, and each other tab renders that record's own newest-first table with the columns that record has, and no tab carries a count
- **AND** a change reads as a plain-language line, not a raw event code
- **AND** Changes has its own Kind filter listing the eleven kinds of change

#### Scenario: the daemon tab reads every writer in the log
- **GIVEN** `daemon.log` holds lines from several writers at once — Coffer's own JSON, an upstream's `LEVEL - logger - message` lines, uvicorn and rich — with a colour-escaped line among them and a traceback written under the record that raised it
- **WHEN** the user opens the Daemon tab
- **THEN** each row carries the time, level and logger its own line stated, and nothing carries a time or a level it never stated
- **AND** no message renders a terminal escape sequence as text
- **AND** the traceback rides with the record that raised it rather than becoming rows of its own
- **AND** the severity-floor filter judges each line by its own level rather than treating every non-JSON line as an error

#### Scenario: the box ends with what is shown and what is kept
- **GIVEN** the Changes tab with more records than the first page holds
- **WHEN** the user reads to the end of the first page, and later of everything kept
- **THEN** the box's last row first says how many are shown of how many, what the next page holds and from before when, with Load 50 more
- **AND** only after the last page does it say "That's everything kept" with how long MCP calls are kept and a link to Settings › Data

### Requirement: Filter each Activity tab and expand any row
Every Activity tab MUST filter in one row — the search first (240 wide), then
the time range and the pills, with **Clear filters** at the far right while
anything is set — and show no counts in it. Everything: search, time range,
**By** and **Kind**; Changes: search, time range, **By** and **Kind**; MCP calls:
a segmented **All / OK / Failed** first (Failed is an error, a timeout or a
denial), then search, time range and **By**; Daemon log: a segmented **All /
Info / Warnings / Errors** first, then search, time range and **Logger**. There
is no filter for a server: the search matches a server's name. **By** chooses
several values, listing the agents and, under "Not an agent", you (the web UI,
the desktop app), the command line, Coffer itself and sync, last; on MCP calls
it lists agents only. **Kind** on Everything is three flat values — MCP calls,
Changes, Daemon records — and on Changes the eleven kinds of change (a resource
kind, or secrets, sync, settings and CLIs for a change that names no resource),
flat. A pill lists no counts and searches only above eight values. The time
range is the shared picker: Last hour, Last 24 h, Last 7 days, Last 30 days and
a custom range (calendar days, optional HH:MM, an end of "now", at most 90 days
back); a tab opens on the last hour, the Daemon log on the last 24 hours, until
the user picks one. A record passes when it matches any chosen value.

Selecting a row on Everything, Changes or MCP calls MUST open it in the shared
right-hand drawer (640 wide, the page dimmed behind it; Esc, a click outside or
its ✕ closes it, ↑ ↓ step to the previous or next record, focus returns to the
row), answer first — a failed call's error and how its server has been doing
(since when it has been failing, and its errors in the last 24 hours), a
change's who and what, then its configuration before and after as a diff, a
daemon record's message and traceback — then the records written within five
minutes of it, ending in its raw underlying record, pretty-printed in a
monospace, scrollable block that stays folded until asked for. The footer holds
the next step: **Open** the resource beside **Copy details**. A call's drawer
shows its metadata only, since Coffer stores no call's arguments or results. A
change whose event the page has no sentence for reads through the same facts and
diff. On the Daemon log a row opens in place under its own line instead, with its
traceback, **Copy record** and, when the record names a server and tool, **Show
the MCP call**, which opens the MCP calls tab looking for that call.

#### Scenario: activity row expands to its raw record
- **GIVEN** an Activity tab has at least one row
- **WHEN** the user clicks (or presses Enter/Space on) that row on Everything, Changes or MCP calls
- **THEN** the shared drawer opens over the page and offers its raw underlying record — the full JSON, pretty-printed in a monospace, scrollable block — once Raw log is unfolded

#### Scenario: a daemon log row opens in place
- **GIVEN** the Daemon log tab with an error record carrying a traceback and naming `server=github tool=search_issues`
- **WHEN** the user selects that row, then chooses Show the MCP call
- **THEN** the row opens under its own line with the traceback and Copy record, and no drawer opens
- **AND** Show the MCP call opens the MCP calls tab searching `github.search_issues`

#### Scenario: who and kind choose several values
- **GIVEN** Everything holding a call by an agent, a change made in the web UI, a change made from the command line and a daemon warning
- **WHEN** the user chooses the agent and "You" under By, then MCP calls and Changes under Kind
- **THEN** the list keeps the agent's call and the web UI's change and drops the others, and the Kind pill reads "Kind: MCP calls, Changes"

### Requirement: Query only the visible Activity tab and isolate failures
Only the visible tab pages through records — Everything through all three
logs, each other tab through its own — and no tab reads a count: tabs carry
none. A record whose route fails MUST render its error inside its own tab,
leaving the other two working — one failing lane must not take the other two
down with it; on Everything the failing record is named in one warning banner
above the box with its error and which records below are complete ("Changes and
daemon records below are complete."), the stream shows the other two records,
the failed record's tab shows a warning icon, and the banner offers **Retry**
for the failed log only. The banner cannot be closed. There MUST be no manual
refresh control and no Pause / Resume control: switching tab or changing a
filter refetches, and new records arrive on their own (see "Stream new Activity
records while the list is at the top").

#### Scenario: a failing record shows its error inside its own tab
- **GIVEN** one of the three routes is unavailable (an older daemon that does not serve it)
- **WHEN** the user opens `/activity`
- **THEN** the failing record's tab renders a readable error and carries a warning icon
- **AND** the other two tabs still render their rows

#### Scenario: a failed log is one banner that retries only that log
- **GIVEN** Everything with the MCP call log unavailable
- **WHEN** the banner's Retry is chosen
- **THEN** only the call log is read again, and the banner has no close control

### Requirement: Keep the command-line record readers
Each of the three records the Activity page shows MUST also be readable from the
command line, over the same route the page reads: `coffer log audit` reads the
audit log (`GET /api/v1/audit`), `coffer log mcp` reads the invocation log, and
`coffer log daemon` reads the daemon log (`GET /api/v1/daemon/logs`). Without
`--server`, `coffer log mcp` reads the same cross-server log the MCP calls tab
renders (`GET /api/v1/mcp/invocations`), Coffer's own built-in calls (`coffer`)
and deleted servers' rows (`deleted:<name>`) included; with `--server <name>`, it
reads that server's log. Each reader takes `--since`, `--limit` and `--json`,
plus the filter its record affords: `--status` for invocations, and `--errors`
for the daemon log.

#### Scenario: the command-line readers still read the records
- **GIVEN** a running daemon that has recorded an audit entry, MCP invocations on
  two servers, on Coffer's own built-in tools and on a deleted server, and a daemon
  log record
- **WHEN** a script runs `coffer log audit`, `coffer log mcp --server <server>`,
  `coffer log mcp` with no server and `coffer log daemon`
- **THEN** each exits successfully and prints that record's entries, the per-server
  reader only that server's calls and the reader with no server every row, each
  naming its server
- **AND** with `--json` each prints one parseable document and no human-readable framing

### Requirement: Render event types as plain-language lines
Event types MUST render as plain-language activity lines ("Enabled demo-fs") in
both locales, guarded the way error codes are: a new event type with no string
fails CI rather than showing a reader a raw `resource_enabled`.

#### Scenario: every audit event type reads as a sentence in both locales
- **GIVEN** every audit event type the daemon can record
- **WHEN** each is looked up in the English and the 中文 strings
- **THEN** each has a plain-language line in both locales
- **AND** a change of that type renders as its line rather than as the raw event code

### Requirement: Organise Settings into six tabs
Settings — the modal of "Open Settings as a modal from the sidebar footer" —
MUST carry six tabs, in this order, in every build, grouped by what they manage
rather than by how Coffer is built, and MUST open on General:

- **General** (`/settings/general`) — display preferences (the interface language
  and the theme, the default page size and the preferred external editor), the
  **Coffer's model** section: the
  model Coffer's own engine runs on and the speech-to-text model (see "Choose
  Coffer's model in Settings › General"). It carries no experimental-features
  card; the switches are on the Features tab. While `models` is off the
  connection choice for Coffer's model is left out.
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
- **About** (`/settings/about`) — version, license, source, whether a newer
  version is available (see "Check for and install updates on Settings › About"),
  and a small **Copy diagnostics** action beside the version.
- **Features** (`/settings/features`) — the four experimental features, each
  marked Experimental, with its switch (spec
  [experimental-features](../experimental-features/spec.md) "Show the Features tab in every build").

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

### Requirement: Let the user set the default page size
The General tab MUST expose the default page-size preference — the rows-per-page
every list table seeds from — persisted in `localStorage`.

#### Scenario: the default page size seeds every list table
- **GIVEN** the General tab's default page-size control
- **WHEN** the user picks a different page size
- **THEN** the choice is stored in `localStorage`
- **AND** a list table then shows that many rows per page

### Requirement: Let the user choose an external editor
The General tab MUST also expose a **preferred external editor**: the
application Coffer uses when the user opens a managed file, or its containing
folder, from a read-only file viewer. The default is the operating system's
default application; the user MAY override it by picking an editor the daemon
detected as installed (enumerated via `GET /api/v1/fs/editors`,
[daemon](../daemon/spec.md) "Open and reveal existing absolute paths"; a browser cannot list installed applications) or by entering
a custom application or launch command. Like the other display preferences the
value is persisted in `localStorage` and never sent to the daemon, except
transiently as the target when opening a file.

#### Scenario: general tab persists the preferred editor
- **GIVEN** the user opens the General settings tab
- **WHEN** they set a preferred external editor (by picking a detected editor or entering a custom launch command)
- **THEN** reloading the page shows the same preferred-editor value
- **AND** clearing the override restores the operating-system default

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
  a remote or is this machine's only copy, its location, and **Open folder**.
- **Local content** — what is not synced and the user must back up themselves:
  chat and channel attachments and media only, with their size and **Open
  folder**, and a line saying so.
- **History** — the retention of each record kind — changes, MCP calls and
  conversations — Keep forever or a number of days, cleaned up by the retention
  worker's schedule (at daemon start and every six hours), with a
  **Clear expired now** action behind a confirmation, which reports what it
  removed; the last cleanup reads "Last cleared today at 12:00 — 1,284 rows" ("30 Sep at 12:00" for another day); a saved value survives a reload. Shortening a
  window (or turning Keep forever off) MUST ask first, and the confirmation
  MUST say how many records the shorter window deletes at the next cleanup and
  how many the table holds now and would hold after, counted by the daemon
  without deleting anything. A refused save MUST say so above the blocks with
  **Try again**, name the window still in place, and mark the row "Not saved".
- **Rebuildable cache** — Coffer's memory tree and the transcript summary cache,
  both under `~/.coffer/derived/`, which Coffer rebuilds on its own: one **Clear** action,
  behind a confirmation saying that memory is rebuilt from the agents' own
  memory on the next update, that an equivalent rebuild needs Coffer's model
  (without it each entry becomes a note of its own), and that notes whose
  sources are gone do not come back.

Edits auto-save, like every settings surface: there is no Save button.

#### Scenario: retention period persists across reload
- **GIVEN** the user opens the Data settings tab
- **WHEN** they turn off "Keep forever" for a record kind in History, set a specific number of retention days, and commit the field (blur or Enter), which auto-saves
- **THEN** reloading the page shows the same retention-days value that was saved

#### Scenario: the data tab shows four blocks and no this-mac block
- **GIVEN** a vault with versions, chat media on disk, and memory partitions
- **WHEN** the user opens `/settings/data`
- **THEN** it shows Vault (size, versions, Open folder), Local content (attachments and media, size, Open folder, not synced), History (retention for changes, MCP calls and conversations with Clear expired now) and Rebuildable cache (memory tree and transcript summary cache with Clear), and no This Mac only block

#### Scenario: shortening a retention window counts what it deletes
- **GIVEN** MCP calls kept for 30 days, some of them older than 7 days
- **WHEN** the user sets the MCP calls window to 7 days
- **THEN** a confirmation asks "Keep MCP calls for 7 days?", says how many calls older than 7 days the next cleanup deletes, and shows the count now and after
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
- **AND** once confirmed only the memory tree and the transcript summary cache are cleared, with no vault or local content touched

### Requirement: Switch language from the sidebar
The English / 简体中文 switch MUST be reachable from every screen in Settings ›
General, each locale named in its own language.
Every sidebar label, page title and form label MUST switch on the very next
render, with no full page reload, and the choice MUST persist in `localStorage`
under `coffer.language`.

#### Scenario: language switcher round-trips correctly
- **GIVEN** the UI is in English
- **WHEN** the user opens Settings › General and selects 简体中文
- **THEN** all sidebar labels, page titles, and form labels switch to Chinese without a full page reload, on the very next render
- **AND** the preference persists across reloads (localStorage `coffer.language`)

### Requirement: Read each Activity tab from its record owner's route
The Activity page MUST add no route of its own: each tab reads the read-only
route belonging to whichever capability owns that record (see Purpose) — the
Changes tab `GET /api/v1/audit`, the MCP calls tab `GET /api/v1/mcp/invocations`
and the Daemon tab `GET /api/v1/daemon/logs`, Everything all three — and its
filters list agents and servers from those kinds' own list routes. An agent or
a script that asks "what happened" reads the same three records from the
command line (see "Keep the command-line record readers").

#### Scenario: each activity tab reads its owner's route
- **GIVEN** a running daemon that has recorded an audit entry, an MCP invocation and a daemon log record
- **WHEN** the user opens each of the Activity tabs in turn
- **THEN** each tab shows only its own record's rows, read from that record's owner's route
- **AND** no tab requests a route of the Activity page's own

### Requirement: Draw every colour from the theme tokens
Every colour the web UI renders MUST come from a theme token: a role such as
surface, raised surface, border, text, muted text, accent, success, warning or
danger, defined once for the light theme and once for the dark theme in the one
stylesheet that holds the tokens. A component MUST ask for a role, never for a
colour value, so that switching theme re-colours every surface. Colour is
reserved for state and action: the accent marks the primary action, focus and
selection only, and the four status colours are never borrowed for anything
else. A colour literal — a hex value, an `rgb()` or `hsl()` value, or a Tailwind
palette class — anywhere in the frontend source outside the token stylesheet
MUST fail the lint gate.

#### Scenario: a colour literal outside the tokens fails the lint gate
- **GIVEN** a frontend source file other than the token stylesheet that sets a hex colour, an `rgb()` / `hsl()` value or a Tailwind palette class such as `bg-red-500`
- **WHEN** `make lint` runs
- **THEN** the colour gate fails, naming the file, the line and the literal
- **AND** a class that names a role (`bg-surface-raised`, `text-danger`) and an `rgb(var(--role))` read pass

#### Scenario: every colour role is defined for both themes
- **GIVEN** the token stylesheet
- **WHEN** its light and dark definitions are compared
- **THEN** every colour role the light theme defines is defined again for the dark theme

### Requirement: Follow the system theme with a per-viewer override
The UI MUST render in light or dark. By default it MUST follow the operating
system's appearance and follow it live, without a reload, when the system
switches. The viewer MUST be able to override it with a System / Light / Dark
choice on the General tab of Settings; the choice is a display preference of
this browser, persisted in `localStorage` under `coffer.theme`, and never sent to
the daemon. The resolved theme MUST be exposed as `data-theme="light"` or
`data-theme="dark"` on the document's root element.

#### Scenario: the theme follows the system appearance live
- **GIVEN** no stored theme choice and a system in light mode
- **WHEN** the page loads and the system then switches to dark and back
- **THEN** the root element reads `data-theme="light"`, then `dark`, then `light`, with no reload

#### Scenario: a manual theme choice overrides the system and persists
- **GIVEN** a system in light mode
- **WHEN** the viewer chooses Dark
- **THEN** the root element reads `data-theme="dark"`, `coffer.theme` holds `dark`, and a system switch no longer changes the theme
- **AND** after a reload the page opens dark, and choosing System again clears the key and follows the system

#### Scenario: the General tab offers the theme choice
- **GIVEN** the Settings General tab
- **WHEN** it renders
- **THEN** it offers the theme as one choice of System, Light and Dark with the current preference chosen
- **AND** picking one applies it at once, with no Save button

### Requirement: Ship the interface fonts with the app
The interface face (Figtree) and the identifier face (JetBrains Mono) MUST be
bundled into the web build and loaded from the app's own origin, never from a
font service, so the desktop shell's content security policy (`font-src 'self'
data:`) never blocks them and the UI looks the same offline. The interface MUST
run on a 13px base size, with anything a user could paste into a terminal —
paths, ports, tool names, environment keys, commit ids — set in the identifier
face.

#### Scenario: the interface fonts load from the app's own origin
- **GIVEN** the token stylesheet's font declarations
- **WHEN** the web build is produced
- **THEN** every font source is a file bundled with the build, and none is an absolute URL to another host
- **AND** the default face is Figtree at 13px, with JetBrains Mono as the monospace face

### Requirement: Show an agent by its official mark
Wherever the UI names an agent in a compact form, it MUST show the agent's
official mark on a neutral tile — Claude Code as the Claude Spark, Codex as the
OpenAI Blossom beside the word "Codex" — and never letters. An agent type Coffer
does not support MUST get a neutral agent glyph on the same tile. Every agent
sits on the same neutral tile, so colour outside the mark stays reserved for
state: a healthy agent's badge is plain, and only a problem adds a status mark.
A badge shown without its name MUST carry the name, and its state when it has
one, in its accessible label and its tooltip.

#### Scenario: a supported agent is shown by its official mark
- **GIVEN** a Claude Code agent and a Codex agent
- **WHEN** each renders as an agent badge
- **THEN** Claude Code shows the Claude Spark mark and Codex the OpenAI Blossom mark, on the same neutral tile, and neither shows letters
- **AND** a badge without a visible name is labelled with the agent's name and state, such as "Codex, not connected to Coffer"

#### Scenario: an agent Coffer does not support gets the neutral glyph
- **GIVEN** an agent type other than Claude Code or Codex
- **WHEN** it renders as an agent badge
- **THEN** the badge shows the neutral agent glyph on the neutral tile, labelled with the agent's name

### Requirement: Pair every status colour with its word
A status MUST never be conveyed by colour alone: the dot MUST always sit beside
the word it means (Running, Degraded, Failing, Disabled), so the state survives
colour-blindness and a greyscale screenshot. A healthy status reads quietly —
its word in muted text — while a problem colours its word with its status colour.

#### Scenario: a status is a dot beside its word
- **GIVEN** statuses of each tone: running, degraded, failing and disabled
- **WHEN** each renders
- **THEN** each shows a dot and its word together, the dot carrying the status colour
- **AND** the running word is set in muted text while the degraded and failing words take their status colour

### Requirement: Preview a write before it lands
Before Coffer writes into files it does not own on the user's behalf — repairing
drift, connecting an agent, resolving a sync conflict — the UI MUST be able to
show the change first, in one shared preview: the changes grouped by agent and
by file, each file with its operation (add, modify, remove) and its added and
removed line counts, a plain-words summary of what will happen per agent, and
the diff of every changed file. The preview MUST show each of its states —
computing, nothing to change, ready, applying, applied, and failed partway. When
some changes fail, the preview MUST stay open, say which changes were applied,
name the reason each failed one failed, and offer to retry only the failed ones.

#### Scenario: the change preview groups a write by agent and file
- **GIVEN** a planned write of four changes across two agents' files
- **WHEN** the change preview renders it
- **THEN** it summarises the four changes by operation, lists each file under its agent with its operation and line counts, and shows each changed file's diff
- **AND** its primary action reads "Apply 4 changes"

#### Scenario: a write that failed partway retries only what failed
- **GIVEN** a change preview whose apply left one of four changes failed
- **WHEN** it renders the result
- **THEN** it stays open, says the other three were applied, and shows the failed change's reason under its path
- **AND** its retry action names and retries only the one failed change

### Requirement: Show a chosen reach by its agents' badges
A reach control whose resource reaches only chosen agents MUST show each chosen
agent's badge as the whole of its label — no word and no count — in the order of
the Agents page, so the reader sees who has it without opening the panel. The
panel MUST show each agent of the pick-list by its badge and name.

#### Scenario: a reach narrowed to chosen agents shows their badges
- **GIVEN** a resource whose reach names one Claude Code agent
- **WHEN** its reach button renders
- **THEN** it shows the Claude Code badge alone, with no text
- **AND** its panel lists each agent by its badge and name

### Requirement: Mark the app with the Coffer logo
The app MUST carry the Coffer mark — an open rounded square drawn with the
navigation icons' pen around a single accent dot — as the sidebar's brand and
as the browser tab's icon, drawn in theme colours so it reads on light and dark.

#### Scenario: the sidebar carries the Coffer mark
- **GIVEN** the app shell
- **WHEN** the sidebar renders, expanded or collapsed
- **THEN** its brand shows the Coffer mark, labelled "Coffer"
- **AND** the document declares the Coffer mark as its icon

### Requirement: Check for and install updates on Settings › About
In the desktop shell, the About tab MUST show the version running, when updates
were last checked, a **Check for updates** control, and the result of the
latest check — up to date, or a newer version available with its version number,
its release notes and a **Download and restart** control — and a **Check
automatically** switch that turns the shell's launch and six-hourly checks on or
off, kept in the page's storage and reported to the shell at startup. The check
and the install are the shell's (spec [desktop-app](../desktop-app/spec.md)
"Check for updates against a signed release manifest"), reached through the
same module as the shell's other host affordances; the tab only renders what the
shell reports and asks it to act. While a check or a download is running its
control MUST show that it is busy — a download its progress — and not accept a
second press; a check or a download that fails MUST show a readable error on
the tab, keep the last successful check's time, and leave the running version
untouched. A desktop build made without an updater key MUST say it does not
check for updates. In a browser, About MUST show the version and say that
updates are installed by the desktop app, with no update control, because a page
the daemon serves cannot replace the application; it MUST instead offer the
daemon's upgrade hand-off (spec [daemon](../daemon/spec.md) "Hand an upgrade of
Coffer to an agent") — Copy prompt, and Ask an agent when a managed agent is
available — and name no install command itself. The desktop shell never asks
for that hand-off.

#### Scenario: about shows the version and when updates were last checked
- **GIVEN** the desktop shell running version 1.0.0, last checked at launch, with no newer release
- **WHEN** the user opens `/settings/about`
- **THEN** the tab shows 1.0.0, the time of that check, that Coffer is up to date, and a Check for updates control

#### Scenario: checking by hand finds a newer version
- **GIVEN** the About tab open in the desktop shell and a newer signed release on the manifest
- **WHEN** the user chooses Check for updates
- **THEN** the control shows it is checking, then the tab shows the newer version number, its notes and a Download and restart control
- **AND** the last-checked time moves to now

#### Scenario: download and restart installs the newer version
- **GIVEN** the About tab showing a newer version available
- **WHEN** the user chooses Download and restart
- **THEN** the tab shows the download's progress and the shell installs the update and relaunches
- **AND** after the relaunch About shows the new version as the one running

#### Scenario: a failed check keeps the last good result
- **GIVEN** the About tab in the desktop shell with the release manifest unreachable
- **WHEN** the user chooses Check for updates
- **THEN** the tab shows a readable error and keeps the time of the last successful check
- **AND** the running version is unchanged

#### Scenario: about in a browser offers no update control
- **GIVEN** the web UI opened in a browser
- **WHEN** the user opens `/settings/about`
- **THEN** the tab shows the version and says updates are installed by the desktop app
- **AND** it shows no Check for updates or Download and restart control, and offers Copy prompt with the daemon's upgrade hand-off

### Requirement: Test a server in the Add dialog before adding it
The Add server dialog's one-server form MUST offer Test, which tests the
config as typed without saving it ([mcp-gateway](../mcp-gateway/spec.md) "Test
an unsaved server config before adding it"), and MUST show the result in the
form before Add server: the time it took, how many tools, resources and prompts
the server listed, the first tool names, a warning for a tool whose name agents
would see as longer than model APIs accept, and the stderr lines behind Show;
or, when it failed, why — the exit code of a process that stopped — and the
last lines it printed on stderr. A new secret pasted or typed into a row is sent for
the test only and nothing is written to the keychain. An edit to the form
after a test retires its result. A stored secret picked for a row is not
released to the test, which says the server is tested once it is added.

#### Scenario: the add form tests the unsaved server before Add server
- **GIVEN** the Add server form prefilled from a pasted command with a secret environment value
- **WHEN** the user presses Test
- **THEN** the app posts the form's config to `/api/v1/resources/mcp_server/test-config` with the typed value in `secret_values`, and shows "Test passed in 1.4 s" with the tools it listed
- **AND** no resource is registered and no secret is written

### Requirement: Review an import from the agents before it is applied
Import from your agents MUST open the shared change preview of the daemon's
import plan ([agent-registry](../agent-registry/spec.md) "Plan an import of
agents' direct MCP entries") before anything is written: the servers found,
each ticked, with the agents that hold it and a note when two agents' entries
merge into one server or an entry duplicates a server Coffer already has;
what will happen to Coffer and to each agent; and each agent config file the
import edits, with its diff. A name the daemon cannot register is listed
unticked. Unticking a server re-plans without it. Import MUST apply the ticked
entries through the apply route, and the outcome MUST say which entries were
not imported and why.

#### Scenario: the import review shows each file's diff before it imports
- **GIVEN** an agent whose config file holds one direct MCP entry
- **WHEN** the user opens Import from your agents and presses Import 1 server
- **THEN** the dialog first shows the plan with that agent's file and its diff, and only then posts the ticked entries to `/api/v1/agents/mcp-import/apply`
- **AND** the entry is not adopted one by one through the agent's adopt route

### Requirement: Show the built-in coffer server read-only
The MCP servers list MUST end with a Built-in group holding Coffer's own
`coffer` server, and its detail MUST be read-only: no Test, Edit, Delete, Turn
off or ⋯ menu, its reach a fixed "All connected agents", a note that it cannot
be edited or removed because it is how agents reach the other servers, its
calls in the last 24 hours, and its tools, always on, with the names agents see
them by. It is described by the daemon ([mcp-gateway](../mcp-gateway/spec.md)
"Describe the built-in coffer server") and is not a registered resource.

#### Scenario: the built-in coffer server is listed last and opens read-only
- **GIVEN** the MCP servers page with one registered server
- **WHEN** it renders and the user opens the Built-in `coffer` row
- **THEN** the row sits under Built-in after the registered servers and its detail shows its tools with no Test, Edit or ⋯ menu

### Requirement: Show the Skills page as the final canvas draws it
The Skills page MUST follow canvas 4.3: a compact header (title, help) over the
library beside a reading pane. The library MUST group skills under **Needs
attention**, **In use**, **Off** and **Built-in**, without counts in the group
titles; a row MUST show, in place of its description, the one thing that needs the
reader, and an Off row carries no reach word. The library offers a search, which
applies to the built-in skills too, and no filter by reach or by kind. Rows ticked
for bulk actions MUST show the selection as a bar above the list ("N of M
selected", Reach, Delete, ×) and in the reading pane, which names the selected
skills, says the built-in skill can't be selected and offers only what the bar does
not — **Check copies of N skills**.

The open skill's header MUST name it with a state pill, its source, its master
path and when it changed, and carry **Reach** and a **⋯** menu (Open in editor,
Reveal in Finder, Copy master path, Delete…) whatever the state; each problem is
answered in a banner under the tabs, never in the header. Its tabs — Files,
Delivery, Requires, History — carry no counts. The Files tab MUST be one card: the
folder's files with SKILL.md first beside the open file's header bar and body,
whose edit mode refuses a stale save while keeping the text. A folder the skills
store holds that no skill claims, listed under Not in your library, MUST show its
files in the same locked tree and viewer, with its meta line saying how many files
it holds and when it was found.

The Requires tab MUST list what the skill declares in four groups: **Commands**,
each with its state and a link to the CLIs page, **Secrets** (spec skill-manager
"Declare the secrets a skill requires"), **Tools** — the MCP servers and
custom-tool groups it names under `requires: tools:` (spec skill-manager "Declare
the tools a skill requires"), each with its state and a link to its page — and
**Skills** it needs. **Check again** re-checks the commands. The rows carry no
install, copy-command or login step and no hand-off of their own: one banner
carries a single hand-off to an agent for every command that needs the person. A
secret that is not set MUST read "secret <name> is not set" and open the Secrets
page, with no hand-off to an agent, because setting a secret is the person's task.
A library row whose most urgent item is such a secret MUST read "Needs secret
<name> · not set", and the open skill MUST carry a banner naming each secret that
is not set with Open Secrets. A required tool that is off or failing puts the skill
under Needs attention with "Needs <tool> · off", a **Tool off** pill, and a banner
("<tool> is off, so <skill> can't call it", or why a failing group fails) with Open
<tool>, which opens the tool's own page; turning a tool on is the person's choice,
so the banner offers no hand-off.

A folder in the way of an agent's link, a delete Coffer refuses, a master folder
that is gone and a Git source to change MUST each be answered where they are
shown, with the choice confirmed before anything is written. When a delete is
refused because an agent's copy is a real folder Coffer did not make, the
confirmation MUST stay open, say "Nothing was deleted", name the folder and say
Coffer removes only what it made; its primary button then becomes **Delete, keep
<agent>'s folder**, which deletes the skill and leaves that folder where it is
(there is no Retry). A bulk delete MUST report each skill: the clean ones are
deleted, a refused one stays listed with the folder in the way, and the same
choice to keep that agent's folder is offered. The Add skill dialog is 640 wide,
validates its source inline and MUST carry the Available to reach control.

#### Scenario: a library row says what needs attention in place of its description
- **GIVEN** a skill whose declared command is missing and a Git skill with an update waiting
- **WHEN** the user opens the Skills page
- **THEN** the first row reads "Needs <command> · not installed" and the second "Update available" where their descriptions would be

#### Scenario: selected skills are set or deleted together from the bar above the list
- **GIVEN** the built-in skill and two of the user's skills
- **WHEN** the user ticks the two skills
- **THEN** the bar above the list reads "2 skills selected", the reading pane names both, says the built-in skill can't be selected and offers Check copies of 2 skills, and the one Delete button deletes both after one confirmation

#### Scenario: the library has no reach filter and groups skills by what they need
- **GIVEN** a skill that is on, one that is off and one needing attention
- **WHEN** the user opens the Skills page
- **THEN** they sit under Needs attention, In use and Off, and the list offers a search and no reach or kind filter

#### Scenario: a skill file changed on disk refuses the save and keeps the text
- **GIVEN** a skill file open for editing
- **WHEN** the save is refused because the file changed on disk
- **THEN** the header says Not saved, the edited text is still there, Reload, Compare and Copy my text are offered, and Save stays off

#### Scenario: the requires tab checks the commands again and keeps the hand-off out of its rows
- **GIVEN** a skill whose declared commands are missing or not logged in
- **WHEN** the user opens its Requires tab and chooses Check again
- **THEN** each command shows its state with a link to its CLI page, no install, Copy prompt or login step appears in a row, and every command is probed again

#### Scenario: a folder in the way of a skill's link is resolved by a confirmed choice
- **GIVEN** a skill whose link in one agent is a real folder Coffer did not make
- **WHEN** the user opens Review… from the skill's banner and chooses Adopt this folder
- **THEN** the dialog shows the difference first, and only the confirm button resolves that agent's copy by keeping its version

#### Scenario: a delete refused because a copy is not Coffer's stays open and offers to keep that folder
- **GIVEN** a skill whose delete the daemon refuses because an agent's copy is not Coffer's link
- **WHEN** the user confirms the delete
- **THEN** the dialog stays open, says "Nothing was deleted", names the folder and says Coffer only removes what it made
- **AND** its primary button becomes "Delete, keep Codex's folder", which deletes the skill and leaves that folder

#### Scenario: a bulk delete offers to keep the folder that stopped one skill
- **GIVEN** two selected skills of which one has a real folder in an agent where its link should be
- **WHEN** the user confirms the bulk delete
- **THEN** the dialog stays open listing the refused skill with the folder, and offers to delete it keeping that agent's folder

#### Scenario: a skill whose master folder is gone offers the ways forward
- **GIVEN** a skill whose master folder was removed outside Coffer
- **WHEN** the user opens it
- **THEN** its header pill says Master missing and a banner says the master folder is gone and offers Restore from History (not available while a skill's versions are not recorded) and Delete skill…, which opens the delete confirmation
- **AND** the Files tab says there are no files to show

#### Scenario: a folder no skill claims is added in place or moved out
- **GIVEN** a folder in the skills store that no skill claims
- **WHEN** the user opens it under Not in your library
- **THEN** it shows its path, whether its SKILL.md is valid and its file count, Delete folder… asks first, and Add to library… adds it and opens the new skill

#### Scenario: changing a skill's source shows the change before anything is replaced
- **GIVEN** a skill added from Git
- **WHEN** the user opens Change source…, enters another repository and chooses Check source
- **THEN** the dialog shows the change against the current version with a button to take it, and cancelling applies nothing and drops the staged source

#### Scenario: a skill is added with the reach chosen in the dialog
- **GIVEN** the Add skill dialog with Available to set to Disabled or to chosen agents
- **WHEN** the user adds the skill
- **THEN** each added skill is turned off, or scoped to the chosen agents, and with every agent nothing more is written

#### Scenario: the requires tab lists a skill's secrets and opens Secrets for a missing one
- **GIVEN** a skill declaring the command `jq` and the secrets `GITHUB_TOKEN`, which is set, and `NPM_TOKEN`, which is not
- **WHEN** the user opens its Requires tab
- **THEN** below the commands `GITHUB_TOKEN` reads Set and `NPM_TOKEN` reads "secret NPM_TOKEN is not set" with Open Secrets, which opens `/secrets`
- **AND** the secrets offer no Copy prompt and no command

#### Scenario: a skill that needs a secret that is not set says so and links to Secrets
- **GIVEN** a skill declaring `GITHUB_TOKEN`, which is not set, and `NPM_TOKEN`, which is
- **WHEN** the user opens the Skills page and the skill
- **THEN** its library row reads "Needs secret GITHUB_TOKEN · not set"
- **AND** a banner above its tabs says "secret GITHUB_TOKEN is not set." with Open Secrets linking to `/secrets`, and does not name `NPM_TOKEN`

#### Scenario: a skill whose tool is off says so in the list, the pill and a banner that opens the tool
- **GIVEN** a skill declaring the tool `github`, an MCP server that is off
- **WHEN** the user opens the Skills page and the skill
- **THEN** the row reads "Needs github · off" under Needs attention, the header pill reads Tool off, and a banner says github is off so the skill can't call it, with Open github linking to `/mcp-servers/github`
- **AND** the banner offers no Copy prompt or Ask an agent

### Requirement: Offer a found update in a card above the sidebar footer
In the desktop shell, when the shell's update check has found a newer version,
a card MUST sit above the sidebar's Settings row naming the version, with
**Restart** — which asks the shell to download, verify and install it and then
relaunch, the same install as Settings › About's (spec web-ui "Check for and
install updates on Settings › About") — and **What's new**, opening Settings ›
About with the release notes. The card is never a modal. It MUST be dismissible,
and a dismissed card MUST come back at the next launch. While the install runs
Restart MUST show that it is busy, and an install the shell refuses MUST leave
the card up with the reason. The collapsed icon rail shows no card, and a
browser shows none, because a page the daemon serves cannot replace the
application.

#### Scenario: a found update shows a dismissible card in the desktop shell only
- **GIVEN** the shell's update check reporting version 1.1.0 available
- **WHEN** the sidebar renders in the desktop shell, and then in a browser
- **THEN** the desktop sidebar shows a card above the Settings row naming v1.1.0 with Restart and What's new, and Restart asks the shell to install it
- **AND** after the user dismisses it the card is gone, while the browser never shows one

### Requirement: Suggest the closest page for an unknown address
An address no route matches MUST render a not-found page in the workspace,
with the shell around it, that names the address, suggests the sidebar page
closest to its first segment when one is close ("Did you mean /mcp-servers"),
and offers **Back to Overview** (outline) and **Search Coffer ⌘K** (ghost),
which opens the command palette over the page; the suggestion is a bordered card
with the page's icon, "Did you mean" over its path and a trailing chevron. The address of a page that belongs to a switched-off
experimental feature is an address no route matches: it MUST render this page,
with no notice that the feature is switched off (spec
[experimental-features](../experimental-features/spec.md) "Make a switched-off
feature look absent in the UI").

#### Scenario: an unknown address suggests the closest page
- **GIVEN** the user opens `/mcp/sentri`
- **WHEN** the route resolves
- **THEN** the page says nothing lives at `/mcp/sentri`, suggests `/mcp-servers`, and offers Back to Overview and Search Coffer
- **AND** Search Coffer opens the command palette

#### Scenario: a switched-off feature's address is not found
- **GIVEN** the `knowledge` feature switched off
- **WHEN** the user opens `/knowledge`
- **THEN** the not-found page shows, with no mention of the feature being switched off and no switch-on button

### Requirement: Send a memory-hook problem on Overview to the agent's Hooks tab
When Coffer's memory hook in an agent's own settings no longer matches what Coffer installs —
its command or events were changed by hand — and a reconciler pass tried to rewrite it and could
not, Overview's Needs you MUST list it as a row on that agent: the reason in a sentence, since when
the pass first saw it, and one action, **Repair hook**, opening the agent's Hooks tab, where the
hook's row carries Repair. A hand-edited hook that no pass has visited yet MUST NOT be listed: the
next pass rewrites it on its own. The hook's other problems the reconciler reports on the agent —
missing, not trusted or switched off in the agent, a settings file that does not parse — MUST open
the same tab.

#### Scenario: a memory hook changed by hand that coffer could not rewrite needs the user
- **GIVEN** Claude Code connected to Coffer, with the command of Coffer's memory hook changed by hand in its settings
- **WHEN** no reconciler pass has run yet, and then a pass tries to rewrite the hook and fails
- **THEN** before the pass the attention list holds no item for it, and after it the list holds one warning on Claude Code whose reason says the hook no longer matches what Coffer installs, with since set and the repair action for that change

#### Scenario: a memory hook changed by hand opens the agent's hooks tab from overview
- **GIVEN** the attention list holds the hand-edited memory hook of Claude Code
- **WHEN** the user opens Overview
- **THEN** Needs you shows a row on Claude Code with the reason and since when, its one action reads Repair hook and opens Claude Code's Hooks tab, its name opens Claude Code's page, and the row has the ⋯ menu

### Requirement: Let the user ignore any item on Overview
Every row of Needs you — whatever its severity — MUST carry a ⋯ menu whose last entry is
**Ignore**. The daemon MUST remember an ignored item on this machine, by the item's stable key
(its kind, resource and reason), and audit each ignore and each stop: `GET /api/v1/attention` then
lists it under `ignored`, out of `items` and `counts_by_kind`, so Needs you, the Agents health tile,
the sidebar's badges and the menu bar's count all leave it out alike. Overview MUST NOT list ignored
items or count them. A banner on the page an item belongs to MUST carry an **×** that is the same
Ignore, so ignoring from the page and from Overview are one act with one key; an
ignored item returns by itself when the situation it describes changes (a
different set of conflicts, say), because the key names the situation. The page an
ignored item belongs to (the page its name opens on Overview)
MUST show one muted line under its header — the item's reason, "ignored on Overview", and a
**Show it again** button that stops the ignore (`DELETE /api/v1/attention/ignored/{key}`) and
confirms with "Back on Overview". Ignoring changes nothing about the resource itself. Asking to ignore a key that
names no item in the list is refused with `ATTENTION_NOT_IGNORABLE`.

#### Scenario: an ignored item leaves needs you whatever its severity
- **GIVEN** Overview listing Codex as not connected and an MCP server that fails
- **WHEN** the user chooses Ignore in Codex's menu, then Ignore in the failing server's menu
- **THEN** each leaves Needs you in turn, and Overview shows no "ignored" line and no list of ignored items
- **AND** the daemon's attention list carries them only under `ignored`, its counts leave them out, and both changes are audited

#### Scenario: a page banner's × ignores the item on Overview too
- **GIVEN** a page banner for an item that Overview also lists
- **WHEN** the user presses the banner's ×
- **THEN** the banner goes, Overview and the sidebar badge stop listing and counting the item, and the page's header reads "… — ignored on Overview" with Show it again
- **AND** when the situation changes the item is listed again

#### Scenario: an ignored item can be shown again from its own page
- **GIVEN** an MCP server that fails and was ignored on Overview
- **WHEN** the user opens that server's page
- **THEN** under the header a muted line gives the reason and says it was ignored on Overview, with **Show it again**
- **AND** choosing it stops the ignore, the line goes, and the item is back on Overview

### Requirement: Hand installing an agent to the person when none is found
While no supported agent is installed on this machine, `GET /api/v1/agents/types` MUST carry
`install_handoff`, a prompt the daemon writes (see
[skill-manager](../skill-manager/spec.md) "Hand a required command to an agent with a prompt"
for the shape every hand-off takes) asking the person's assistant to install one of the
supported agents — naming each with its program and settings folder, this machine's OS and
architecture and the `PATH` Coffer looks programs up on — choosing the install method that fits
this machine, keeping any settings folder that already exists, confirming the program with
`--version`, leaving signing in to the person, and then coming back to Scan again; it MUST name
no installer, package manager or command, and it MUST be `null` once any supported agent is
installed. Overview's first run with no agent found MUST NOT offer that prompt: its agent rows
name each agent, so each one not found carries an **Install** link to the agent's official install
page (agent-registry "Report every supported type's detection state", `install_url`).

#### Scenario: with no agent found the install prompt is built by the daemon
- **GIVEN** neither supported agent's program is installed on this machine
- **WHEN** the types are read, and read again after one is installed
- **THEN** the first answer carries an install prompt naming both agents and their settings
  folders, no installer, and the standing rules every hand-off ends with
- **AND** the second carries none

#### Scenario: with no agent found overview links each agent's install page
- **GIVEN** a first run on a machine where no supported agent is found
- **WHEN** Overview renders
- **THEN** each agent row reads Not found with an Install link to that agent's official install page
- **AND** it offers no install prompt and no Ask an agent

### Requirement: Hand an agent's missing program to an agent on the agent pages
Wherever the web UI shows an agent type whose program is not found — its Agents list row and
its ⋯ menu, its detail page while it is not added, and the
Overview tab's problem states (config left behind, not found) — it MUST offer the daemon's
`install_handoff` prompt for that type (agent-registry "Hand installing an agent's program to an
agent") through **Copy prompt**, and through **Ask an agent** only while another managed agent
is available to run the conversation: the missing agent itself cannot. A list row has no button for it: Copy prompt, then Ask an agent, head the row's ⋯ menu, above a separator and the rest of the menu, because a button that copies text does not belong in a row. None
of these surfaces MUST show an install command or tell the person to restart Coffer. The
Plugins tab of a Claude Code agent whose program is not found, where Uninstall cannot run, MUST
say so and offer the same prompt. The Connect review MUST offer the hand-off a `SHIM_NOT_FOUND`
refusal carries beside Retry (agent-registry "Install Coffer's MCP server into an agent in one
action").

#### Scenario: an agent whose program is not found offers its install prompt
- **GIVEN** Codex not installed and no managed agent available
- **WHEN** the user opens the Codex row's ⋯ menu and chooses Copy prompt
- **THEN** the daemon's prompt is copied as given, no install command is shown anywhere, and the row carries no button of its own
- **AND** the menu offers no Ask an agent

#### Scenario: ask an agent is offered only while another managed agent is available
- **GIVEN** Claude Code's config left behind with its program gone, and Codex available as a managed agent
- **WHEN** the user opens the Claude Code row's ⋯ menu and chooses Ask an agent
- **THEN** New conversation opens, and nothing is written or sent
- **AND** with only Claude Code itself managed, the menu offers no Ask an agent

#### Scenario: a connect refused for a missing shim offers the daemon's prompt
- **GIVEN** a registered agent and a daemon that refuses its Connect with `SHIM_NOT_FOUND` carrying a hand-off
- **WHEN** the user applies the Connect review
- **THEN** the review shows the change as failed with copy that names no environment variable or command
- **AND** Copy prompt beside Retry copies the refusal's prompt as given

### Requirement: Offer an MCP server's hand-off beside Test and View log
An MCP server's page MUST offer the backend's hand-off (Copy prompt, and Ask an agent when a managed agent
is available) wherever the server's state is a chore for an agent, passing the prompt on as served and
never assembling it: the missing-launcher callout offers the status read's `handoff` in place of any install
command, and the failing callout and a failed test's result offer the diagnosis `handoff` beside View log
(or Show stderr) while Test stays in the header. The page MUST NOT show a package-manager command or an
"install it, then refresh" instruction. A failed test of an unsaved config in the Add and Edit dialogs offers the daemon's hand-off in the result when the failure depends on this machine, and the page never writes a prompt of its own.

#### Scenario: a missing launcher offers the hand-off, not an install command
- **GIVEN** an MCP server whose status names a missing launcher and carries a `handoff`
- **WHEN** its page opens
- **THEN** the launcher callout names the launcher and offers Copy prompt, which copies the served prompt, and shows no `brew install` line

#### Scenario: a rejected key reads Replace key
- **GIVEN** an MCP server whose status reads failing with `failure_reason` `auth_rejected`, and an Overview item with the verb `replace_key`
- **WHEN** the server's page opens and the Overview lists the item
- **THEN** the failing callout says the key was rejected and offers Replace key, which opens the edit dialog on its secret, and the Overview row's action reads Replace key and opens the server's page

#### Scenario: a failed test offers a diagnosis hand-off beside View log
- **GIVEN** an MCP server whose test just failed with an error and a `handoff`
- **WHEN** the result is shown
- **THEN** the result callout shows the error with View log and Copy prompt beside it, and the header still offers Test

### Requirement: Offer the hand-off a knowledge refusal carries beside it
When the daemon refuses a knowledge operation with a hand-off in the error's details
(`details.handoff.prompt`), the Knowledge page MUST offer that prompt as one **Ask an agent ▾**
control — Ask an agent opens a draft conversation with the prompt, and its menu holds Copy prompt,
which is the only action when no managed agent is available — passing the prompt on as served and
never assembling it. A History tab or Recent changes that cannot be read because git is not
installed MUST say so in one neutral row — **History needs git** or **Recent changes needs git**,
*Install git on this Mac to see versions. The document itself is fine.* — with **Check again** and
the hand-off, and no Retry or Open Activity. A refused **Undo this pass** MUST say in one sentence
which document was changed since and offer **Open its History**, which opens that document's
History tab, where the person restores a single version; it carries no hand-off. The page MUST NOT
show an install command.

#### Scenario: a refused pass undo points at the document's history
- **GIVEN** a curation pass whose undo the daemon refuses because a document it wrote was edited since
- **WHEN** the user undoes the pass from its page
- **THEN** one sentence names the document edited since and Open its History opens that document's History tab
- **AND** nothing is written and no prompt is shown

#### Scenario: a history that needs git offers the prompt for installing it
- **GIVEN** a machine with no git, whose history reads are refused with the install hand-off
- **WHEN** a document's History tab opens
- **THEN** it shows the row *History needs git* with Check again and Ask an agent ▾, whose menu copies the served prompt, and names no install command
- **AND** it offers no Retry and no Open Activity

#### Scenario: recent changes that need git offer the same row
- **GIVEN** a machine with no git, whose history reads are refused with the install hand-off
- **WHEN** Recent changes opens
- **THEN** it shows the row *Recent changes needs git* with Check again and Ask an agent ▾

### Requirement: Show, copy and rotate the access token on Settings › Security
Settings › Security MUST be the one place in the web UI that shows the daemon's access token. It
MUST be hidden until **Show** is chosen, offer **Copy**, and offer **Rotate**, which asks for
confirmation — saying that clients configured with the old token stop working — then calls
`POST /api/v1/daemon/rotate-token` (spec [daemon](../daemon/spec.md) "Rotate the token over REST"). The page MUST install the token the call returns and carry on without a
reload; the confirmation MUST close only on success, and a failed rotation MUST leave the dialog
open with the error and the old token in use. While the daemon cannot be reached, the controls are
disabled.

#### Scenario: rotating the token from settings security keeps the page working
- **GIVEN** Settings › Security open on a running daemon
- **WHEN** the user rotates the token and confirms
- **THEN** one `POST /api/v1/daemon/rotate-token` is sent and the dialog closes
- **AND** the page's next requests carry the new token and succeed, with no reload

#### Scenario: a failed rotation from settings security keeps the old token
- **GIVEN** Settings › Security open, and a rotation that the daemon answers with `503`
- **WHEN** the user confirms the rotation
- **THEN** the dialog stays open with a readable error
- **AND** the page keeps using the old token, and its next request succeeds

#### Scenario: the token is hidden until shown
- **GIVEN** Settings › Security open
- **WHEN** it renders, and then the user chooses Show and Copy
- **THEN** the token is masked until Show, and Copy puts it on the clipboard

#### Scenario: copy diagnostics carries no secret
- **GIVEN** Settings › About open
- **WHEN** the user chooses Copy diagnostics beside the version
- **THEN** the clipboard holds the version, host, daemon state and port and the enabled features, and no token or secret value

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
  [provider-switching](../provider-switching/spec.md) "Offer every connection operation on REST and the web").
- **Channels** is filed under Run, beside Conversations and not merged into it:
  Conversations is where a person reads and continues every conversation, a
  channel is an IM bot set up once and revisited rarely, and the conversations a
  channel carries are listed on the Conversations page with its badge (spec
  [chat](../chat/spec.md) "Show every conversation on the Conversations page");
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

### Requirement: Open the app on Overview
The app's index (`/`) MUST render the Overview page, the landing page, in place
rather than redirecting elsewhere, so a visitor lands on the whole of the vault
before any one part of it. This requirement fixes where the app lands; what the
Overview page shows is a requirement of its own. Agents live at `/agents` (list)
and `/agents/<type>` (detail, with each tab at `/agents/<type>/<tab>`), addressed
by the agent's type because an agent's name is fixed to its type, and
MUST NOT appear in the `/mcp-servers` kind browser.

#### Scenario: the index opens Overview
- **GIVEN** the app's route table
- **WHEN** the user opens `/`
- **THEN** the Overview page renders at `/` with no redirect, and the sidebar marks the Overview entry as current
- **AND** `/agents` still opens the Agents page, and the `/mcp-servers` list asks only for MCP servers, so no agent appears there

### Requirement: Keep daemon shutdown on the command line
No tab may expose a "Shutdown daemon" or "Stop daemon" control: stopping the
daemon from the web kills the very page it was asked from, and recovery then needs
a terminal anyway, where `coffer daemon stop` already is. Restarting is not
stopping — the desktop shell's restart waits for the replacement and hands the
page its connection (spec [desktop-app](../desktop-app/spec.md) "Restart by stopping the running daemon first").
The About tab MUST show the version (with the short commit a release build was
made from, when stamped), license, source, the data folder, the update check of "Check
for and install updates on Settings › About" and **Copy diagnostics** only —
which copies the version, host, daemon state and port, and
the enabled experimental features as plain text, and never a token or a
secret — with no language picker (the
sidebar already switches language) and no installed-resource-kind list
(developer detail). Remaining jargon is rewritten in plain language (e.g.
"prune" is phrased as clearing expired data).

#### Scenario: settings offers no shutdown control
- **GIVEN** the user opens the Settings tabs
- **WHEN** each tab is fully rendered
- **THEN** no tab exposes a "Shutdown daemon" or "Stop daemon" control
- **AND** the About tab shows version / license / source / data folder, the update check and Copy diagnostics only — no language picker, no resource-kind list

### Requirement: Set when the daemon runs on the Daemon tab
The Daemon tab MUST carry a card for when Coffer's daemon runs, with one control: a **Start at
login** switch. It MUST read and write it through
[daemon](../daemon/spec.md) "Change residency from the settings page".
A clicked switch MUST move to the clicked value at once and then settle on what the daemon reports:
the switch is disabled until the daemon has first answered, a successful write shows the value the
daemon answers with, the switch is shown unavailable rather than off on a host with no login
service, and a failed write MUST put the switch back to what the daemon last reported and show the
error beside it. The card MUST NOT offer an idle window or a stand-down choice, because the daemon
never stands down on its own.

#### Scenario: the settings daemon tab sets when the daemon runs
- **GIVEN** the daemon reports a login service that is supported and not installed
- **WHEN** the user turns on Start at login on the Daemon tab
- **THEN** one request is sent carrying `login_service_installed: true` and no idle window
- **AND** the card offers no idle-window or stand-down control
- **AND** when a later request fails, the switch goes back to what the daemon last reported and the error is shown beside it

### Requirement: Choose Coffer's model in Settings › General
Settings › General MUST carry a **Coffer's model** section that sets what Coffer's
own machinery runs on (spec [internal-engine](../internal-engine/spec.md) "Show and change Coffer's model in Settings › General").
It is machine-level configuration of Coffer itself rather than of any agent, so
it is a Settings section, not a tab of the Model providers page, whose tabs are Providers and Usage. The section
MUST carry two pickers — **Engine model** and **Speech to text** — each choosing
a provider first and then a model from that provider's list, and a **Test**
action for each that tries the chosen pair and shows the result beside it. Each
picker MUST show its state inline: *not set* (saying what Coffer does without
it — no internal pass runs; voice messages reach the agent as audio files),
*set*, or *failing* (the last test or call failed, with the error). The Model
providers page MUST carry no Coffer's model tab. Coffer has no embedding
configuration (search is literal-only), and the second picker is Speech to text.

#### Scenario: coffer's model is chosen in settings general
- **GIVEN** two connections, each with a list of models
- **WHEN** the user opens `/settings/general` and, in the Engine model picker, chooses a provider and then one of its models
- **THEN** the model list offers only the chosen provider's models, and the choice is saved without a Save button

#### Scenario: an unset picker says what coffer does without it
- **GIVEN** no speech-to-text model chosen
- **WHEN** the Coffer's model section renders
- **THEN** the Speech to text picker reads as not set and says voice messages reach the agent as audio files

#### Scenario: testing a picker shows a failing pair inline
- **GIVEN** an engine model chosen on a connection whose endpoint rejects the key
- **WHEN** the user chooses Test beside the Engine model picker
- **THEN** the picker reads as failing with the endpoint's error beside it
- **AND** the chosen pair is kept as it was

### Requirement: Show and manage the daemon on Settings → Daemon
The Daemon tab MUST show the daemon's state and carry the controls a user needs
for it, and nothing that stops it:

- **Status** — an ordinary section (a title over a hairline-topped row, not a box): state and the address it answers on, then one line: how long
  it has been up, its pid and how many agents carry Coffer's connection, all
  from the status probe. The version is on About.
- **Restart** — a Restart control in both hosts: in the desktop shell it runs the
  shell's restart (spec [desktop-app](../desktop-app/spec.md) "Restart by stopping the running daemon first");
  in a browser it asks the daemon to restart itself (spec [daemon](../daemon/spec.md) "Restart itself on request"),
  shows that it is restarting while the page waits for the successor to answer, and
  then reloads the page from the successor's origin — on the new port when one
  was saved — which hands it the successor's token. A successor that does not
  answer within 90 seconds is reported beside the control.
- **Port** — the port the daemon answers on, editable (spec [daemon](../daemon/spec.md) "Bind a fixed, settable port"):
  a value MUST be a whole number from 1024 to 65535 and a port no other process
  holds, each refused in place under the row's description otherwise. The row has
  no Save button: Enter, or leaving the field, applies an edited value, and a
  refused value is not sent again until it is edited. Applying writes it to the pre-database
  daemon config and the row then reads **takes effect after restart**, with
  **Restart now** — the same restart as the Restart control, in either host.
  Until the restart, the status keeps showing the port the daemon answers on.
- **Start at login** — see "Set when the daemon runs on the Daemon tab".

The tab has no token row (the token is on Settings › Security) and no
Troubleshooting section: the daemon log is read on Activity's Daemon tab, and
Copy diagnostics is on Settings › About.

While the status has not yet answered, the tab MUST keep its layout over
skeleton rows. While the daemon cannot be reached, the Status section MUST read
offline and name the host's recovery — the Restart control in the desktop shell,
the `coffer daemon start` command in a browser — and the Start at login and
Port controls MUST be disabled.

#### Scenario: the settings daemon tab shows the running daemon
- **GIVEN** a running daemon
- **WHEN** the user opens `/settings/daemon`
- **THEN** the Status section shows its state, port, uptime, pid and connected-agent count, matching `GET /api/v1/daemon/status`
- **AND** the tab carries no stop or shutdown control

#### Scenario: the settings daemon tab offers the host's restart
- **GIVEN** the Daemon tab open in a browser, and then in the desktop shell
- **WHEN** the restart row renders
- **THEN** both show a Restart control and neither shows a command to copy
- **AND** in the browser it asks the daemon to restart itself, and in the desktop shell it runs the shell's restart

#### Scenario: saving a valid port leaves it pending until restart
- **GIVEN** a daemon answering on port 38470, opened in the desktop shell
- **WHEN** the user sets the port to 8123 on the Daemon tab and presses Enter
- **THEN** 8123 is saved through `PUT /api/v1/daemon/port` (which writes it to `~/.coffer/daemon-config.json`), the row reads takes effect after restart with Restart now, and the status still shows 38470
- **AND** in a browser the row offers the same Restart now

#### Scenario: a browser restarts the daemon from the daemon tab
- **GIVEN** the Daemon tab open in a browser on a running daemon
- **WHEN** the user presses Restart
- **THEN** the page asks the daemon to restart itself, waits until its successor answers — a new start time on the same port, or an answer on the port that was saved — and reloads the page from the successor
- **AND** a successor that does not answer within 90 seconds is reported beside the control and nothing is reloaded

#### Scenario: a port in use is rejected
- **GIVEN** another process holding port 9000
- **WHEN** the user enters 9000, and then 80, on the Daemon tab
- **THEN** each is refused in place — 9000 as taken, naming what holds it, and 80 as outside 1024–65535 — and nothing is written

#### Scenario: the daemon tab has no token row and no troubleshooting section
- **GIVEN** the Daemon tab open on a running daemon
- **WHEN** it renders
- **THEN** it carries no token control, no daemon-log link and no Copy diagnostics

#### Scenario: the settings daemon tab keeps its layout while status loads
- **GIVEN** the Daemon tab opened before the status probe has answered
- **WHEN** the tab renders
- **THEN** it shows its Startup section and skeleton rows for the status rather than a blank pane or an offline state

#### Scenario: the settings daemon tab with the daemon offline
- **GIVEN** the daemon cannot be reached
- **WHEN** the user opens the Daemon tab
- **THEN** the status card reads offline and names the host's recovery
- **AND** the Start at login and Port controls are disabled

### Requirement: Guard unsaved edits when leaving a document editor
A document editor — a skill file, a knowledge document, an agent config file —
that holds edits not yet saved MUST register them with one shell-level guard, and
the guard MUST stop every way out of the page the edits live on: a route change
(a sidebar entry, a command-palette jump, the title bar's back and forward
arrows, a tab or file switch) and closing or reloading the window. Opening or
closing the Settings modal is not leaving, since the page stays mounted beneath
it. A clean editor MUST never be stopped.

A stopped route change opens one dialog, **Leave without saving?**, 460 wide,
naming the file and whose it is: "You edited SKILL.md in sentry-issue-triage. If
you leave now, those edits are lost." It carries **Discard changes** (an outline
danger button, left), **Keep editing** (ghost) and **Save and leave** (primary).
Discard changes goes on without saving; Keep editing stays with the edits intact;
Save and leave runs the editor's own save and then goes on, and a refused save
keeps the dialog open under "Couldn’t save <file>" with the reason. Closing or
reloading the window asks through the browser's own confirmation.

#### Scenario: a dirty editor stops leaving and asks first
- **GIVEN** a skill file with unsaved edits is open
- **WHEN** the user follows a link to another page
- **THEN** "Leave without saving?" names the file and the skill and the page does not change
- **AND** Keep editing closes the dialog with the user still on the page

#### Scenario: Discard changes leaves without saving
- **GIVEN** the dialog is open over a dirty editor
- **WHEN** the user chooses Discard changes
- **THEN** the navigation goes on and nothing was saved

#### Scenario: Save and leave saves, then goes on
- **GIVEN** the dialog is open over a dirty editor
- **WHEN** the user chooses Save and leave
- **THEN** the editor's save runs once and the navigation goes on

#### Scenario: a refused save keeps the guard open and says why
- **GIVEN** the dialog is open over a dirty editor whose save the daemon refuses
- **WHEN** the user chooses Save and leave
- **THEN** the dialog stays, titled "Couldn’t save" with the file name, and the user is still on the page

#### Scenario: a clean editor and the Settings modal are never stopped
- **GIVEN** an editor with no unsaved edits
- **WHEN** the user follows a link to another page
- **THEN** the page changes and no dialog opens

#### Scenario: closing or reloading the window with unsaved edits asks the browser
- **GIVEN** an editor holds unsaved edits
- **WHEN** the window is about to close or reload
- **THEN** the browser's confirmation is requested, and it is not once the edits are gone

### Requirement: Confirm a destructive action in one dialog that names its cost
A destructive or irreversible action MUST ask in the shell's one confirmation
dialog, 420 wide: a title naming the object ("Delete sentry?"), one sentence on
what cannot be undone, the consequences as a list of label and value rows where
there are several, and a confirm button that says the verb ("Delete server").
While the action runs the button reads its pending label ("Deleting…") and no
other way out of the dialog works. The dialog MUST close only when the action
succeeded; a failure stays in it under a title naming the verb and the object
("Couldn’t delete sentry") with the reason, and the button becomes Retry.

Deleting an MCP server MUST say which agents lose how many tools on their next
call and that its call history stays in Activity. A secret only this server cites
MUST be offered as an unticked **Also delete the secret** with its name and
"No other server uses it."; a secret anything else uses is never offered, so a
delete never takes a credential by surprise.

#### Scenario: Delete server says what it costs and offers its own secret
- **GIVEN** an MCP server that two agents reach and that cites one secret no other server uses and one that another does
- **WHEN** the user opens its Delete dialog
- **THEN** it says which agents lose how many tools and that the history stays in Activity, and offers an unticked Also delete the secret for the first secret only
- **AND** confirming without ticking it deletes the server and no secret

#### Scenario: a refused delete stays open under its error title
- **GIVEN** the daemon refuses to delete the server
- **WHEN** the user confirms
- **THEN** the dialog stays open under "Couldn’t delete" and the server's name, with the reason and a Retry button

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

### Requirement: Manage stored secrets on the Secrets page
The Secrets page (`/secrets`, under the sidebar's System group) MUST be the one
page in the web UI that lists and manages stored secrets. A secret is shared
infrastructure data — one reference can be cited by MCP servers, model
providers, channels and skills at once (spec
[secret](../secret/spec.md) "Address a secret by an opaque reference") —
so it gets a page of its own rather than a section of any one kind's page, and
it is not a Settings tab, because it holds data the user manages rather than a
preference. A secret field inside a resource's own dialog stays there: a secret
is still entered where the thing that needs it is configured.

The page MUST carry:

- **List** — one table of every secret the store holds or a resource cites, by
  its reference (a standalone secret by its name), sorted by name, with whether
  this Mac holds it, so a reference cited but missing reads as missing on this
  Mac (spec [secret](../secret/spec.md) "List every stored and cited secret with
  what uses it"). Search by name, and a status filter of All, In use and Not
  used, narrow it; its columns are Name, Used by, Last used and Created, the
  times relative ("3 h ago") and, past a week, a date ("Aug 12"). The page has
  no owner line, no owner-type filter, no by-owner view and no "Delete unused".
- **Used by** — for each secret, what cites it, by kind and current name, each
  opening that thing's page; a secret nothing cites reads Nothing and is found
  with the Not used filter.
- **Add and replace** — store a new secret at once, or replace the value of one
  that exists, at once and without the value ever being shown back (spec
  [secret](../secret/spec.md) "Store a secret through the API").
- **Reveal** — show one value behind an explicit, confirmed action, only in the
  desktop app, audited as `secret_revealed` (spec [secret](../secret/spec.md)
  "Release plaintext only to a present human in the desktop app"); in a
  browser the action is disabled and names the desktop app.
- **Delete** — refused while the secret is cited: the control MUST say what still
  uses it, naming each citer as the delete refusal does (spec
  [secret](../secret/spec.md) "Refuse to delete a secret still in use"), and
  the row MUST stay. Several rows can be ticked and deleted at once from the
  table's selection bar ("N of M selected"; Esc clears it); the confirmation
  names the secrets it deletes and skips those in use or waiting for approval.
- **Missing values** — a banner counting the secrets this Mac has no value for,
  with **Add values** (spec [secret](../secret/spec.md) "Show a secret this Mac
  cannot open as missing on this Mac"); it offers no master-key import.
- **Approvals** — a banner counting the changes waiting for approval, with
  **Review**, which opens the one approvals table (spec
  [secret](../secret/spec.md) "Approve several bindings in one confirmation").
  A rejection shows a toast; the page keeps no list of refused changes and has
  no "Ask again".
- **Find plaintext keys** — the entry point that moves plaintext secret files
  into the store (spec [secret](../secret/spec.md) "Move plaintext secret files
  into the store").

Each banner has an × that ignores it exactly as Ignore does on Overview, where
the same two situations are listed (spec [secret](../secret/spec.md) "List
secrets with no value here and waiting approvals on Overview"); the page's
header then says it is ignored on Overview and offers Show it again, and the
banner returns when the set changes. The help icon beside the title is gone: how
to run a command with a secret is in the documentation, not on the page.

This requirement fixes the page's place and its parts. What the store enumerates,
how each operation behaves, and the steps of finding plaintext keys are the
secret capability's, specified with it.

#### Scenario: the secrets page lists each secret with what uses it
- **GIVEN** a registered MCP server citing a stored reference, and a model provider citing a reference the store does not hold
- **WHEN** the user opens `/secrets`
- **THEN** both references are listed in one table, the first as present and the second as missing on this Mac
- **AND** each row names its citer by kind and current name, and choosing it opens that resource's page

#### Scenario: a secret in use cannot be deleted from the secrets page
- **GIVEN** a stored secret cited by a registered channel
- **WHEN** the user tries to delete it from the Secrets page
- **THEN** the delete is refused with the channel named as what still uses it
- **AND** the secret's row is still listed

#### Scenario: revealing a secret is an explicit, audited read
- **GIVEN** a stored secret listed on the Secrets page in the desktop app
- **WHEN** the page renders, and then the user chooses Reveal value on that row and confirms
- **THEN** no value is shown until the reveal is confirmed, and then only that secret's value is asked for and shown
- **AND** the page says the reveal is recorded as `secret_revealed`

### Requirement: Mark a sidebar entry whose kind needs attention
A sidebar entry MUST carry a count badge while the kind or tool behind it has
things that need the user, so they are seen from wherever the user is. The
sidebar speaks only through these badges, and only for things that need the
user — failures, drift, a held vault, a required CLI that is missing, too old or
not logged in; an informational count (how many servers, how many documents
waiting in a knowledge collection's inbox) MUST NOT become a badge. The badge
shows how many things need the user in the one danger-strong tone, capped at
"9+", rendered by one shared component with an accessible name that says the
entry needs attention. An item the user chose to ignore MUST NOT count. On the
collapsed icon rail it MUST shrink to a dot of the same colour on the icon, and
the row's tooltip carries the count ("MCP servers · 1 needs you").

What raises a signal and what clears it belongs to the capability that owns the
kind: the entries of Agents, Model providers, MCP servers, Skills and Channels
count the non-informational items the cross-kind attention list reports for their kind — so Agents counts an agent that needs repair, one whose config directory is left behind and one whose Coffer hook needs the person, and not one that is merely not connected
(spec [resource-framework](../resource-framework/spec.md) "Report what needs a
person across every kind"); Sync keeps its own signal, one situation cleared by
visiting the page (spec [vault-sync](../vault-sync/spec.md) "Say a vault needs a
human where the user already is"); CLIs counts the required commands that need
the user; Skills counts the skills on its Needs attention list plus the folders
in the skills store that no skill claims. Knowledge and Memory carry no badge. An entry whose kind declares no
signal MUST NOT carry a badge, and a signal that has not loaded, or whose read
failed, MUST leave no badge rather than an error in the sidebar.

#### Scenario: an entry whose kind needs attention carries a count badge
- **GIVEN** a sync round held for confirmation, and two MCP servers the attention list reports, one of them failing
- **WHEN** the user is on any page other than Sync
- **THEN** the Sync entry carries a badge of 1 and the MCP servers entry a badge of 2, both in the danger-strong tone, each with an accessible name saying it needs attention
- **AND** no other entry carries one

#### Scenario: the Skills badge counts skills needing attention plus folders no skill claims
- **GIVEN** a skill whose master folder is gone, one whose required tool is off, one that is fine, one with only a Git update waiting and a folder in the skills store that no skill claims
- **WHEN** the sidebar renders
- **THEN** the Skills entry carries a badge of 3, and none while the skills list has not answered

#### Scenario: the badge count caps at 9+
- **GIVEN** an entry whose kind reports twelve things that need the user
- **WHEN** the sidebar renders expanded
- **THEN** its badge reads "9+" in the danger-strong tone

#### Scenario: the attention dot stays on the collapsed rail
- **GIVEN** the MCP servers entry carrying a badge for one failing server
- **WHEN** the sidebar is collapsed to its icon rail
- **THEN** the MCP servers icon carries a dot of the same colour, and its tooltip reads "MCP servers · 1 needs you"

#### Scenario: an entry without a signal never carries a badge
- **GIVEN** every attention signal the kinds declare is raised, and documents waiting in a knowledge collection's inbox
- **WHEN** the sidebar renders
- **THEN** only the entries whose kinds declare a signal carry a badge, and Knowledge carries none
- **AND** an informational item of the attention list raises no badge

#### Scenario: an unreadable signal leaves no badge
- **GIVEN** the route behind a kind's attention signal failing, or not yet answered
- **WHEN** the sidebar renders
- **THEN** that entry carries no badge and the sidebar shows no error

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

### Requirement: Choose secrets in one field and one set of rows
Secrets live only in Coffer, so wherever a form takes a secret it MUST use the
one **secret field**: a single picker, "🔑 name ▾", that never shows the value
and offers no plain-text password input. The menu lists the stored secrets with
how many things use each and a **New secret…** item; pasting into the empty field
makes a new secret named after the thing being configured (with a suffix when the
name is taken) that is written to Secrets only when the form is saved; a chosen
name this Mac holds no value for reads **Missing**. Header and environment rows —
an MCP server's variables and headers, a custom-tool group's headers — MUST be
one component of key · value · delete rows: the value is plain text by default,
with a key button at the end of the field that picks a stored secret instead
(**Type a plain value** goes back), a plain value that looks like a secret offers
**Store it in Coffer?**, and a row that cites a secret nothing holds shows the
Missing warning. A secret bound to a header is the whole header value: the form
has no prefix field and no Secret | Plain toggle, so a bearer token is stored as
`Bearer <token>`.

#### Scenario: a pasted value becomes a new secret written when the form is saved
- **GIVEN** a secret field named for the thing being configured, whose default name is already taken
- **WHEN** the user pastes a value into it
- **THEN** it reads a new secret under the default name with a suffix, saved on Add, the value is not shown and nothing is written to Secrets until the form submits

#### Scenario: a header row's value is plain until a secret is picked
- **GIVEN** a header row `Authorization` with an empty value
- **WHEN** the user chooses the key button and picks `deploy-token`, then chooses Type a plain value
- **THEN** the row holds the stored secret `deploy-token`, and then a plain empty value again

#### Scenario: a secret-looking plain value offers to be stored in Coffer
- **GIVEN** a header row `X-Api-Token` with a plain value that looks like a secret
- **WHEN** the user chooses Store it in Coffer?
- **THEN** the row holds a new secret named from the key, saved with the form

### Requirement: Manage custom tools on their own page
The Custom tools page (`/custom-tools`, under Capabilities) MUST manage custom
tools, which have one type in 1.0 — **HTTP API**: a tool is one HTTP request
Coffer makes on an agent's behalf — and MUST manage them in **groups**. A group
is one `mcp_server` resource of the HTTP API transport, served through the same
gateway as every other MCP server, and carries:

- a **name**, fixed once the group exists, which is the prefix every agent sees:
  a tool reaches agents as `<group>__<tool>`, under the same name rules as any
  MCP server ([mcp-gateway](../mcp-gateway/spec.md) "Manage MCP servers as resources");
- a shared **base URL** its tools' paths are relative to;
- **header rows** — each a name and a value that is plain text or one stored
  secret holding the WHOLE header value (nothing is put around it, so a bearer
  token is stored as `Bearer <token>`), chosen by its name on the Secrets page
  or pasted to be saved there with the group (see "Choose secrets in one field
  and one set of rows"): Coffer's gateway adds each header when it calls the API,
  once a person has approved a secret for the group's host
  ([mcp-gateway](../mcp-gateway/spec.md) "Wait for approval before a custom tool
  sends its secret"), and neither a secret header's value nor the secret's
  reference is ever part of what an agent sees or sends;
- a **reach** (Off, All agents or Chosen agents), which each tool follows unless it has its own.

Each tool in a group MUST carry its own **on/off** switch, an optional **reach of
its own** (see "Reach an item inside a group through the group's reach"), and a
**changes data** flag — on by default for every method but
GET, and editable — which the gateway passes to agents as the tool's MCP
annotations (`readOnlyHint` false and `destructiveHint` true when it changes
data, `readOnlyHint` true otherwise), so each agent's own approval prompts apply
to it. The page MUST list the groups under Needs attention, Healthy and Off, the failing
ones first, each showing what is wrong in place of its tools, and an Off group
leaves its reach column empty. Its header MUST carry one action, **Add custom tool**,
whose flow asks first for the group. An existing group MUST only take a request
added by hand, which uses that group's base URL and secret; only a **new** group
offers the two ways in:

- **Import an OpenAPI spec** — from a URL or a file, into the new group; the user
  ticks which operations become tools, reads ticked and operations that change
  data unticked, and a review lists the ticked ones as the tools to create and the
  rest as **Skipped** before **Create group with N tools**. A spec that cannot
  be read says where: an unparseable file shows the lines around the failure, and a
  URL that does not answer names the reason (not found, refused, timed out), keeps
  **Review tools** off and offers Retry and the daemon's hand-off. A group made by
  an import MUST offer **Re-import**, which reads the spec again and lists the
  change first — operations it would add (reads become tools, switched on;
  operations that change data are listed but not ticked), tools whose request
  the spec changed (each with the operation's old and new text), and tools it
  would remove — before anything changes;
  applying keeps every unchanged tool's switch and reach override as they were.
- **Add one request by hand** — the new group's name, base URL, header rows and
  reach, then its first request: method, path, headers, body template
  and arguments.

Every request form MUST end with a **Test** section, whose Run runs the request as the form
holds it once and shows the answer — the status and time in a block, the response
in a viewer under it — the API's error body, a timeout, a failed
connection (each of these two with the daemon's hand-off and, for a timeout,
**Change timeout**) or a response cut short; nothing — neither a new group nor a tool — is
saved until the form's **Add** or **Save**. A request of a group that is not saved
yet is tested without its secret (see [mcp-gateway](../mcp-gateway/spec.md) "Test
a custom tool request before its group is saved"). With no group yet the page
MUST show only a first-run panel, with Add custom tool in the header and in the
panel. A group's header MUST carry the same actions whatever its state — **Reach** (whose
Off turns the group off), **Edit group** and a **⋯** menu that holds only Delete
group… — and each problem is answered in a banner under it, never in the header:
failing calls (with a link to Activity and the daemon's hand-off), a group that is
off (Turn on), a secret missing (Add secret, Choose another, no hand-off) and a
secret waiting for approval (Open approvals, the only button). Re-import is a
button in the definition of an imported group.

A group's detail page (`/custom-tools/<group>`, and no other route) MUST be one
page with no tabs: the group's **definition** (base URL, and the auth header with
the name of the secret it is bound to), its **reach**, a one-line summary of the
last 24 hours (calls and failures), and the **tools table** — each tool's
method and path, its switch, its changes-data flag and its reach in its own cell. Choosing
a tool opens its editor in a 640-wide **drawer** below the title bar, where the
request is edited — the headers the group already adds shown as "from the group",
no switch and no reach, which live in the table — with **Delete tool** and Cancel
beside it, and its **Test** section under the fields runs the tool with sample
arguments and shows the response. Script tools are not offered: they are deferred past 1.0.
How the gateway runs an HTTP API tool is mcp-gateway's ([mcp-gateway](../mcp-gateway/spec.md)
"Serve an HTTP API as a group of custom tools", "Make a custom tool's request in
the gateway").

#### Scenario: importing an OpenAPI spec creates a group with the chosen operations
- **GIVEN** an OpenAPI document with five operations, three that read data and two that change it
- **WHEN** the user chooses Add custom tool and New group, imports the document as the group `invoices`, unticks one read, ticks one operation that changes data, and reviews
- **THEN** the reads started ticked and the operations that change data unticked, and the review lists the three ticked as the tools to create and the other two as Skipped
- **AND** nothing is created until Create group with 3 tools, which creates `invoices` with only those three and opens its page

#### Scenario: re-importing a spec previews the operations it adds and removes
- **GIVEN** the `billing` group imported with three operations, one of them switched off and one with a reach override
- **WHEN** the spec now has one of those operations removed and a new one added, and the user chooses Re-import
- **THEN** a preview lists the operation to add and the tool to remove, and nothing changes until the user confirms
- **AND** after confirming, the kept tools keep their switch and reach override
- **AND** an added operation that reads data becomes a tool, while one that changes data is listed but not added

#### Scenario: a hand-made request joins an existing group
- **GIVEN** the `billing` group
- **WHEN** the user chooses Add custom tool, defines one request by hand and picks `billing` as its group
- **THEN** the tool is added to `billing`, using its base URL and auth header
- **AND** the flow offers no Import an OpenAPI spec for `billing`, only for a new group

#### Scenario: a new group made by hand is saved with its first request
- **GIVEN** no group named `search-api`
- **WHEN** the user chooses Add custom tool, picks New group and By hand, fills in `search-api` and its base URL, chooses Create group, then fills in the first request and tests it
- **THEN** nothing is saved until the user chooses Add to search-api, which creates `search-api` with that one tool
- **AND** the test ran without the group's secret

#### Scenario: the custom tools page with no group shows the first-run panel
- **GIVEN** no custom-tool group
- **WHEN** the user opens `/custom-tools`
- **THEN** the page shows no group list, only a first-run panel with Import an OpenAPI spec and Add one request by hand, and Add custom tool in the header and the panel

#### Scenario: a tool's reach is set from its row in the table
- **GIVEN** the `billing` group with two tools, one following the group and one narrowed to Claude Code
- **WHEN** the user opens the first tool's reach in the table and chooses All agents
- **THEN** the reach saves at once without opening the tool's drawer, the first reads Same as the group before and the narrowed one shows the Claude Code badge alone

#### Scenario: a narrowed tool goes back to Same as the group
- **GIVEN** a tool narrowed to Claude Code
- **WHEN** the user opens its reach and chooses Same as the group
- **THEN** the tool's own reach is cleared and it follows the group again

#### Scenario: a tool's reach override narrows one tool
- **GIVEN** the `billing` group reaching Claude Code and Codex
- **WHEN** the user overrides one tool's reach to Claude Code only
- **THEN** Codex no longer sees that tool and still sees the group's other tools
- **AND** Claude Code sees all of them

#### Scenario: an agent sees the group name as the tool prefix
- **GIVEN** the `billing` group with a tool named `list_invoices`, reaching Claude Code
- **WHEN** Claude Code lists or searches the gateway's tools
- **THEN** the tool is offered as `billing__list_invoices`

#### Scenario: the secret never reaches the agent
- **GIVEN** the `billing` group's auth header bound to a stored secret
- **WHEN** an agent calls `billing__list_invoices`
- **THEN** the gateway sends the request with the header's value added
- **AND** neither the tool's description and schema nor the result returned to the agent contains the secret's value or its reference

#### Scenario: the custom tools page lists groups by health
- **GIVEN** one group whose last call failed and two healthy groups
- **WHEN** the user opens `/custom-tools`
- **THEN** the failing group is listed first with its tools, and the page header carries one Add custom tool action whose flow asks for an existing or new group and offers Import an OpenAPI spec and Add one request by hand, and no Script type

#### Scenario: a group's page is one page with a tool drawer
- **GIVEN** the `billing` group with three tools
- **WHEN** the user opens `/custom-tools/billing` and chooses one tool
- **THEN** the page shows the definition with the bound secret's name, the reach, a one-line 24-hour summary and the tools table, with no tabs
- **AND** the tool opens in a drawer with its request and Test, and the address stays `/custom-tools/billing`

#### Scenario: a tool's drawer has no switch or reach, and Delete tool is outlined
- **GIVEN** the `billing` group with a tool
- **WHEN** the user opens the tool
- **THEN** the drawer shows no On switch and no reach, shows the group's header as from the group, and offers Delete tool and Cancel

#### Scenario: a spec that does not parse shows the lines around the failure
- **GIVEN** the import step with a file whose YAML breaks on line 3
- **WHEN** the file is read
- **THEN** the step says it couldn't read the spec and why, and shows the file with line 3 marked

#### Scenario: an unreachable spec URL names the reason and keeps Review tools off
- **GIVEN** the import step with a URL the daemon cannot reach
- **WHEN** the user chooses Load
- **THEN** the step names the host and the reason, marks the URL invalid, offers Retry and a hand-off, and Review tools stays off

#### Scenario: a tool that changes data is annotated for the agent
- **GIVEN** a group with a `GET /invoices` tool and a `POST /refunds` tool, and the user turning the changes-data flag off on a third, `POST /search`
- **WHEN** an agent lists the group's tools
- **THEN** `refunds` carries `readOnlyHint` false and `destructiveHint` true, while `invoices` and `search` carry `readOnlyHint` true, so the agent's own approval applies to `refunds`

### Requirement: Show every CLI a skill requires on the CLIs page
The CLIs page (`/clis`, under Capabilities) MUST list one row per command that
any skill requires or any enabled stdio MCP server starts with (spec
skill-manager "Check every required command where the agent runs"), with the
version found beside the minimum the skills ask for, the login state where the
command has one, and how many MCP servers and skills need it, problems first —
missing, older than the minimum, or not logged in, grouped under Needs you above
Ready — as a split view with the selected CLI's detail beside the list
(`/clis/<command>`). The detail's Needed by MUST list the MCP servers started
with the command, each opening that server's page and naming its launcher, and
the skills that declare it, each opening that skill's Requires tab; each row
carries its kind when both need it. The app MUST NOT show an install, update or
login command, a "run it in a terminal" instruction, or run any of them: a CLI
that needs the user says what it costs in a plain sentence — which servers can't
start and which skills fail — and its detail page and the skill's Requires tab
MUST offer the daemon's hand-off prompt (spec skill-manager "Hand a required
command to an agent with a prompt") through **Copy prompt** and **Ask an agent**
— the latter opens a new conversation with a Coffer-managed agent chosen in the
New conversation dialog, with the prompt in the composer and nothing sent until
the user presses Send; with no managed agent available only Copy prompt is
offered. The page's **Check again** probes every command afresh, and the banner that
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
- **THEN** `jq`, `gh` and `gcloud` are listed under Needs you above `uv` under Ready, `gh` shows 2.30.0 against 2.40, `gcloud` shows not logged in, and each row counts the skills that need it

#### Scenario: a CLI that needs the user offers a prompt for an agent
- **GIVEN** a required CLI that is missing and a Coffer-managed agent
- **WHEN** the user opens its detail page and chooses Ask an agent, then that agent
- **THEN** a new conversation opens with the prompt in the composer, and nothing is sent until the user presses Send
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

### Requirement: Resize every split view by its divider
Every split view — a list beside its detail, a file tree beside its file, a
conversation list beside its thread, and the sidebar beside the workspace — MUST
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

### Requirement: Show a knowledge document's history on its History tab
A knowledge document's pane MUST carry two tabs, **Document** (the default) and **History**, neither
with a count. History is **one list** of the document's versions, newest first — who wrote each (the
user, Coffer's curation naming the agent whose item it curated, or sync), when, and its added and
removed line counts — with a **See the pass** link on a curation's row. Choosing a row MUST expand it
in place to its diff, with a switch between **Changes in this version** (against the one before) and
**Compare with current**, and **Restore this version** on every version but the current one, which
writes a new version rather than rewriting the past (spec [knowledge](../knowledge/spec.md) "Keep
every document's history and undo a pass as a whole"); a long line wraps in the diff rather than
being cut. A history that cannot be read MUST say so in one **Load error** row inside the tab —
*Couldn't load the history*, the reason, **Retry** and **Open Activity** — leaving the Document tab
working; without git the row is *History needs git* (see "Offer the hand-off a knowledge refusal
carries beside it").

#### Scenario: the history tab lists versions with their writers
- **GIVEN** a document the user created, that curation then changed from a Codex item
- **WHEN** the user opens its History tab and chooses the older version's row
- **THEN** the tab lists both versions newest first with their writers, the row expands in place to its diff, and Restore this version is offered on it and not on the current version
- **AND** restoring it writes it back as a new version

#### Scenario: a history that fails to load leaves the document readable
- **GIVEN** the history read failing
- **WHEN** the user opens the History tab
- **THEN** the tab shows one Load error row with Retry and Open Activity, and the Document tab still renders

### Requirement: Follow knowledge changes in Recent changes
The Knowledge page MUST carry a **Recent changes** view: one timeline across every collection, newest
first, of curation passes and of documents people and agents wrote or deleted, with the items still
waiting and a quiet **Curate now** beside them (spec [knowledge](../knowledge/spec.md) "Run curation
on a sweep and on demand"). It MUST be filtered with **Collection** and **Author** filter pills and a
**Clear filters** control, the choice kept in the URL. A delete carries **Restore**. Choosing a pass
MUST show what it changed — each document it wrote or retired, with a diff — and offer **Undo this
pass**, which asks first and undoes the whole pass, reporting a refusal that names the document
changed since (see "Offer the hand-off a knowledge refusal carries beside it"). What became of each
item a manual Curate now could not curate is written on that change's row. An empty Inbox reads as one
quiet line. The wording is Curate / Curation (整理) throughout.

#### Scenario: recent changes shows a cross-collection timeline with waiting items
- **GIVEN** a pass in one collection, a person's edit in another, and an item waiting
- **WHEN** the user opens Recent changes
- **THEN** both changes are listed, each linking the documents it wrote, and the waiting item is shown with Curate now

#### Scenario: the filter pills narrow the timeline and live in the URL
- **GIVEN** changes in two collections by the user and by an agent
- **WHEN** the user picks one collection in the Collection pill and the agent in the Author pill, then chooses Clear filters
- **THEN** the timeline lists only that collection's changes by that agent and the URL carries both choices, and Clear filters empties both and the URL

#### Scenario: a pass is inspected and undone as a whole
- **GIVEN** a pass that changed two documents
- **WHEN** the user opens it from Recent changes, reviews the diffs and chooses Undo this pass
- **THEN** the pass's page lists each document it changed with its diff and a link to that document's history
- **AND** Undo this pass asks first, writes nothing until confirmed, and confirming undoes the whole pass in one request

### Requirement: Show memory delivery on the Memory page
The Memory page MUST show what memory delivery is doing, and the agent detail page MUST show only
the delivery hook's state:

- The **Memory overview** MUST list, for each agent, its deliveries in the last seven days — counted
  from the delivery-fire audit events (spec [memory](../memory/spec.md) "Audit every delivery fire")
  — how many distinct memories its sessions read in that time, counted from the file paths its
  transcripts record reading, never from their content, and when it was last delivered to. An agent
  with no delivery in that time reads **not delivered in the last 7 days**, with no hook detail; a
  count that cannot be computed reads as unavailable rather than zero.
- A **partition's page** has a **Delivered** tab (see memory "Present a partition as its memories")
  showing, read-only, the exact session-start text each agent receives in that partition's project
  (spec [memory](../memory/spec.md) "Deliver the index and the notes path at session start"), with a
  switch between agents.
- The delivery hook's state — installed and current, stale, missing, never fired, and Repair — MUST
  appear only on the agent detail page — on its Hooks tab, in the Overview's Coffer connection
  block ([agent-registry](../agent-registry/spec.md) "Show the Coffer connection on the agent pages") and, while the `memory` feature is on, in the **Coffer's memory** section that opens the agent's Memory tab, which links back to this page. Below that section the Memory tab lists the agent's own native memory stores.

#### Scenario: the memory overview lists deliveries per agent
- **GIVEN** Claude Code with 12 delivery fires in the last seven days, and transcripts recording reads of 5 distinct memories, and Codex with no delivery in that time
- **WHEN** the user opens the Memory page
- **THEN** Claude Code reads 12 deliveries, 5 memories read and when it was last delivered to, and Codex reads not delivered in the last 7 days with no hook detail

#### Scenario: a partition's delivered tab shows each agent's session-start text
- **GIVEN** a partition for the `coffer` repository and both agents connected
- **WHEN** the user opens the partition's Delivered tab and switches from Claude Code to Codex
- **THEN** the tab shows, read-only, the exact session-start text each agent receives in that project

#### Scenario: hook state appears only on the agent page
- **GIVEN** Claude Code's delivery hook stale
- **WHEN** the user opens the Memory page and then Claude Code's Memory tab
- **THEN** the Memory page shows no hook state or Repair action
- **AND** the Memory tab's Coffer's memory section shows the hook's state with Repair, above Claude Code's own native memory stores

### Requirement: Stream new Activity records while the list is at the top
The visible Activity tab MUST show new records as they are written, newest first, with no Pause /
Resume control. While the user is at the top of the list and has no record open, a new record MUST
be inserted at the top at once. While the user has scrolled down or has a record open, new records
MUST be held rather than inserted — so the row being read does not move — and a **N new** control
MUST appear, counting them; choosing it scrolls to the top and inserts them. Scrolling back to the
top by hand inserts them too. New records MUST honour the tab's filters: one the filters exclude is
neither inserted nor counted.

#### Scenario: new records stream in at the top
- **GIVEN** the MCP calls tab open at the top of its list, with no row open
- **WHEN** the gateway proxies two calls
- **THEN** both appear at the top of the table without any control being used, and the page has no Pause or Resume control

#### Scenario: new records are held while the user reads
- **GIVEN** the Changes tab scrolled down, or with one row expanded
- **WHEN** three new audit entries are written
- **THEN** the rows on screen do not move and a 3 new control appears
- **AND** choosing it scrolls to the top and inserts the three entries

### Requirement: Export the filtered Activity records from the header
The Activity page's header MUST carry a ghost **Export** menu offering **JSON**
and **CSV**, which save the records of the visible tab that match its current
filters — free text, time range and the tab's own filter — and nothing else, not
including a record's hand-off prompt. With no records at all there is no menu.

#### Scenario: export from the menu honours the filters
- **GIVEN** the MCP calls tab filtered by a search and to failed calls
- **WHEN** the user chooses CSV from the header's Export menu
- **THEN** the file holds exactly the calls that match those filters, one per row
- **AND** JSON saves the same records as JSON

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

### Requirement: Hand a machine-dependent problem to an agent with one split button
Installing, setting up, logging in and troubleshooting depend on the machine, so a problem whose fix
is outside Coffer and for which the backend wrote a concrete prompt MUST be handed over with one split
button, **Ask an agent ▾**, never two buttons: pressing the button opens a draft conversation with
the prompt typed in and sends nothing until the person presses Send; the menu's one item, **Copy
prompt**, copies the daemon's prompt as given for an agent outside Coffer and answers with a
"Prompt copied" toast. With no Coffer-managed agent installed only **Copy prompt** is offered, with
the one-sentence help beside it. The split button sits after the state's own buttons (Check again,
Retry, View log), appears once per problem, never on a healthy, success or empty state, and never for
a missing secret or an approval, which only the person can give. Wherever another requirement names
Copy prompt and Ask an agent together, they are this button's menu item and button. On a Needs you
row they are items of the ⋯ menu beside Ignore.

#### Scenario: the split button hands a prompt over or copies it
- **GIVEN** a problem with a prompt and a managed agent installed
- **WHEN** the person presses Ask an agent, and separately opens its menu and chooses Copy prompt
- **THEN** a draft conversation opens with the prompt typed in and nothing sent, and the prompt is copied as given with a "Prompt copied" toast
- **AND** with no managed agent installed only Copy prompt is offered

### Requirement: Keep Activity's filters in the address
The Activity page MUST keep its tab and every filter in the address, so a link
or a reload comes back to the same view: `tab`, `q` (the search), `range`
(a preset id or a custom range), `by` and `kind` (comma-joined), `status`,
`level` and `logger`; a value at its default is left out. A link from another
page — "View in Activity" with a name — opens already searching it. Moving to
another tab keeps the search, the time range the reader chose and who, and drops
the filters only the old tab had.

#### Scenario: a link opens already searching
- **GIVEN** the address `/activity?tab=mcp&q=github`
- **WHEN** the page opens
- **THEN** the MCP calls tab shows `github` in its search box and asks the route for calls matching it
- **AND** Clear filters empties the box and removes `q` from the address

### Requirement: Show the first run with nothing to filter
When Coffer has recorded nothing at all — no change, no call and no daemon
warning — the Activity page MUST hide the filter row and Export, keep its tabs,
and say "Changes you make in Coffer and the tools agents call through it show up
here." with **Connect an agent** and **Add an MCP server**. An empty time range
while older records exist is not the first run: it says so and keeps the filters.

#### Scenario: nothing recorded hides the filter row and Export
- **GIVEN** no audit entry, call or daemon record exists
- **WHEN** the user opens `/activity`
- **THEN** the page shows the empty state with its two actions and neither the filter row nor Export
- **AND** with a record older than the time range the filter row and Export stay

### Requirement: Hand an environment failure on Activity to an agent
Activity MUST offer the hand-off ([Ask an agent ▾]) only for a failure that depends
on this machine, with the prompt the backend wrote: the conclusion card of a
call's drawer for a call whose server never answered, and the first button of an
opened daemon ERROR about an external service or the environment. A denied call,
an error the server itself returned and a Coffer-internal error offer no
hand-off; a daemon error offers **Copy record** alone. The drawer's footer for a
call is the server's page; it carries no step to read the daemon log.

#### Scenario: an unanswered call and an environment error carry the hand-off
- **GIVEN** a call refused by its server, a denied call, and a daemon ERROR that is a refused connection beside one that is Coffer's own
- **WHEN** each is opened
- **THEN** the refused call's card and the environment error's button row lead with the hand-off, and the others have none
