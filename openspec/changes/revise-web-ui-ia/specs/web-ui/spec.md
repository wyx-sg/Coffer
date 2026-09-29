## RENAMED Requirements

- FROM: `### Requirement: Keep the sidebar to its eleven entries`
- TO: `### Requirement: Keep the sidebar to its thirteen entries`

## REMOVED Requirements

### Requirement: Keep the daemon out of the user's view
**Reason**: A daemon that is never shown leaves the user no way to see which build is answering,
on which port, since when, or whether it will start at login, short of a terminal. The offline
banner reported only the failure case, and "healthy" could not be told apart from "not yet
known". The daemon's state is now shown at all times in the shell footer and on Settings →
Daemon; starting it stays automatic.
**Migration**: See "Show the daemon's state in the shell footer" and "Show and manage the daemon
on Settings → Daemon". The acceptance marker for "settings shows no daemon tab and no daemon
status" is deleted with this requirement.

### Requirement: Open the app on the Agents page
**Reason**: The app now lands on Overview, which shows the whole vault before any one part of it.
**Migration**: See "Open the app on Overview". `/agents` keeps its route. The acceptance marker for
"the index opens the Agents page" moves to "the index opens Overview".

### Requirement: Leave daemon controls to the CLI
**Reason**: Token rotation moves into Settings → Daemon now that the daemon is visible; only
stopping the daemon stays on the command line.
**Migration**: See "Keep daemon shutdown on the command line" and "Show and manage the daemon on
Settings → Daemon". The acceptance marker for "settings drops the confusing controls" moves to
"settings offers no shutdown control".

### Requirement: Let the user choose when the daemon runs
**Reason**: The Start at login card moves from the General tab to the Daemon tab, beside the rest
of the daemon's state.
**Migration**: See "Set when the daemon runs on the Daemon tab". The acceptance marker for "the
general tab sets when the daemon runs" moves to "the settings daemon tab sets when the daemon runs".

### Requirement: Group the sidebar by role
**Reason**: Three role groups put seven entries under Resources once Secrets arrives, and nine
once Rules and Sources do; "resource" is the framework's word, not one a user navigates by. The
sidebar is now grouped by what the user comes to do, in five groups.
**Migration**: See "Group the sidebar by what the user comes to do". The acceptance marker for
"the sidebar groups agents, resources and system by role" moves to "the sidebar groups entries by
what the user comes to do".

### Requirement: Hold one Resources entry per listed resource kind
**Reason**: There is no Resources group any more; each listed resource kind still has one entry,
filed under the group that names what the user does with it.
**Migration**: See "Give each listed resource kind one sidebar entry". The acceptance marker for
"resources holds one entry per kind with a list" moves to "each listed resource kind has one
sidebar entry".

## MODIFIED Requirements

### Requirement: Keep the sidebar to its thirteen entries
The sidebar's entries MUST be exactly these, at these routes: one ungrouped entry
and five groups — thirteen today, and no fourteenth without a spec change.
Settings is not an entry: it is a modal opened from the sidebar footer (see
"Open Settings as a modal from the sidebar footer"). Usage's content is specified
with the change that meters it; this requirement fixes only its place. An
entry whose experimental feature is switched off (spec
[experimental-features](../experimental-features/spec.md) "Close every surface of a switched-off feature")
MUST be left out — today Knowledge for `knowledge`, Memory for `memory`, Sync for
`vault_sync` — and MUST appear on the next render after the feature is switched
on:

```
  Overview         /                  — the landing page
 AGENTS
  Agents           /agents            — the consumers (Bot icon)
  Model providers  /model-providers   — the endpoints agents' models are served from
 RUN
  Chat             /chat              — a conversation with an agent
  Channels         /channels          — the IM bots agents answer on
 CAPABILITIES
  MCP servers      /mcp-servers       — the aggregated upstream servers
  Skills           /skills            — what Coffer delivers to agents
 CONTEXT
  Knowledge        /knowledge         — the collections under ~/.coffer/knowledge/
  Memory           /memory            — the partitions aggregated from the agents' own stores
 SYSTEM
  Secrets          /secrets           — every stored secret and what uses it
  Activity         /activity          — what changed, what was called, what broke
  Usage            /usage             — token use and remaining quota per agent
  Sync             /sync              — converging this vault with a git remote
```

#### Scenario: cold-start renders authenticated content
- **GIVEN** the user has never opened Coffer (localStorage is empty, no daemon.json in user HOME yet)
- **AND** every experimental feature is switched on
- **AND** `coffer daemon start` is running (so daemon.json exists in user HOME)
- **WHEN** they navigate to `http://localhost:5173/` in a real browser
- **THEN** the index renders the Overview page at `/`, with the sidebar and main content area, within 2 seconds
- **AND** the main content shows the Overview page (no generic error card)
- **AND** the sidebar lists exactly Coffer's operational surfaces — Overview; Agents, Model providers; Chat, Channels; MCP servers, Skills; Knowledge, Memory; Secrets, Activity, Usage, Sync — with Overview under no heading and the rest grouped under "Agents", "Run", "Capabilities", "Context" and "System" headings, with no other entry
- **AND** no sidebar entry is Settings; the sidebar footer carries the Settings gear beside the daemon status

#### Scenario: a switched-off feature leaves the sidebar
- **GIVEN** `knowledge` and `vault_sync` switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar lists Overview; Agents, Model providers; Chat, Channels; MCP servers, Skills; Memory; Secrets, Activity, Usage — with no Knowledge and no Sync entry

### Requirement: Give every scoped resource kind its own list surface
Every scoped resource kind MUST have its own list surface, so the navigation and
each list page carry no kind-specific branch.

#### Scenario: every resource entry opens a list page of its own
- **GIVEN** the sidebar's entries for resource kinds (see "Give each listed resource kind one sidebar entry")
- **WHEN** each entry's route is resolved against the app's route table
- **THEN** each resolves to its own list route rather than to "page not found"
- **AND** no two entries resolve to the same route

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
| Chat | 聊天 |
| Channels | 消息渠道 |
| Capabilities (group) | 能力 |
| MCP servers | MCP 服务器 |
| Skills | 技能 |
| Context (group) | 上下文 |
| Knowledge | 知识 |
| Memory | 记忆 |
| System (group) | 系统 |
| Secrets | 密钥 |
| Activity | 活动 |
| Usage | 用量 |
| Sync | 同步 |
| Settings | 设置 |

In Chinese an agent MUST be called **智能体** everywhere the UI names one —
headings, page titles, buttons, dialogs and prose — never "Agent" or 代理.

#### Scenario: a surface carries one name in the sidebar and on its page
- **GIVEN** the UI in English and then in 中文
- **WHEN** each sidebar entry's label is compared with the title its page shows
- **THEN** the two are the same words for every surface in both languages
- **AND** in 中文 the group headings read 智能体, 运行, 能力, 上下文 and 系统, and no zh string names an agent as "Agent"

### Requirement: Show a self-clearing offline banner
When an authenticated request fails to connect while the app is open, a
daemon-offline banner MUST render above the workspace, naming the recovery the
host can offer — in a browser the `coffer daemon start` command, in the desktop
shell a Restart control, because only one of the two can spawn a daemon. The
banner MUST clear itself once the daemon is reachable again, with no manual page
reload. The banner owns the failure case; the shell footer reports the daemon's
state at all times (see "Show the daemon's state in the shell footer"), and the
two MUST agree: the footer never reads as running while the banner is shown.

#### Scenario: daemon-offline banner appears when daemon is unreachable
- **GIVEN** the daemon is not running (no reachable `127.0.0.1:<port>` from `~/.coffer/daemon.json`, or the file is absent)
- **WHEN** the user has the app open and any authenticated request to the daemon fails to connect
- **THEN** a daemon-offline banner renders at the top of the workspace naming the recovery the host can actually offer — in a browser, the `coffer daemon start` command to run, because the page cannot start a daemon; in the desktop shell, a Restart control, because it can
- **AND** the shell footer reads as offline for as long as the banner is shown
- **AND** the banner disappears automatically once the daemon becomes reachable again, without a manual page reload

### Requirement: Organise Settings into five tabs
Settings — the modal of "Open Settings as a modal from the sidebar footer" —
MUST carry exactly five tabs, in this order, grouped by what they manage rather
than by how Coffer is built, and MUST open on General:

- **General** (`/settings/general`) — display preferences (the default page size
  and the preferred external editor) and the **Coffer's model** section: the
  model Coffer's own engine runs on and the speech-to-text model (see "Choose
  Coffer's model in Settings › General").
- **Security** (`/settings/security`) — what is about this machine only: where
  the master encryption key lives, beside the database or in the OS keychain.
  It lists and edits no stored secret; those are on the Secrets page (see
  "Manage stored secrets on the Secrets page").
- **Data** (`/settings/data`) — retention policy and manual prune.
- **Daemon** (`/settings/daemon`) — the daemon's state and the controls a user
  needs for it (see "Show and manage the daemon on Settings → Daemon").
- **About** (`/settings/about`) — version, license, source, and whether a newer
  version is available (see "Check for and install updates on Settings › About").

Clicking a tab
swaps the modal's right pane without a full page reload and without closing the
modal.

#### Scenario: settings layout uses the redesigned tabbed sidebar
- **GIVEN** the user navigates to `/settings`
- **WHEN** the route resolves
- **THEN** the Settings modal opens on the General tab
- **AND** the modal's tab list shows General, Security, Data, Daemon, and About — exactly those five, in that order — with the current route highlighted
- **AND** clicking a tab swaps the right pane content without a full page reload and the modal stays open

#### Scenario: the security tab keeps only machine-level settings
- **GIVEN** stored secrets cited by a registered MCP server and a model provider
- **WHEN** the user opens `/settings/security`
- **THEN** the tab shows where the master key lives and its move control
- **AND** it lists no stored secret and offers no control that adds, reveals or deletes one

## ADDED Requirements

### Requirement: Group the sidebar by what the user comes to do
The sidebar MUST be grouped by what the user comes to Coffer to do, so that each
heading names one intent and a new entry has one obvious home. There are five
groups, under headings in this order:

- **AGENTS** — set up the agents and the models they run on: Agents, then Model
  providers. Agents come first because they are the subject of the product; a
  provider is the endpoint and key each agent's model is served from.
- **RUN** — put an agent to work, directly or through an IM bot: Chat, then
  Channels.
- **CAPABILITIES** — give agents things they can do: MCP servers, then Skills.
- **CONTEXT** — give agents things they know: Knowledge, then Memory.
- **SYSTEM** — look after Coffer and what every other part shares: Secrets,
  Activity, Usage, then Sync.

Settings sits in no group: it is machine-level configuration visited rarely, so
it opens as a modal from the sidebar footer rather than taking an entry (see
"Open Settings as a modal from the sidebar footer").

**Overview**, the landing page, MUST sit above the five groups under no heading:
it summarises all of them, so filing it under one would misname it.

A new entry MUST join the group that names what the user comes to it for, and no
group may grow past five entries; growth that is more of an existing thing — one
more agent, channel or custom tool — is a row inside that thing's page, not an
entry. A group whose every entry is left out (see "Keep the sidebar to its
thirteen entries") MUST leave its heading out too, so no heading stands over
nothing. The decision and the options it was weighed against are in
[The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md).

#### Scenario: the sidebar groups entries by what the user comes to do
- **GIVEN** the app shell is rendered with every experimental feature switched on
- **WHEN** the sidebar lists its entries
- **THEN** Overview comes first, under no heading, and the rest sit under five headings in the order Agents, Run, Capabilities, Context, System
- **AND** Agents holds Agents then Model providers, Run holds Chat then Channels, Capabilities holds MCP servers then Skills, Context holds Knowledge then Memory, and System holds Secrets, Activity, Usage and Sync

#### Scenario: a group with every entry switched off leaves the sidebar
- **GIVEN** `knowledge` and `memory` both switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar shows no Context heading, and the other four headings and their entries are unchanged

### Requirement: Give each listed resource kind one sidebar entry
Every resource kind with a list UI MUST have exactly one sidebar entry — today six
kinds (`mcp_server`, `skill`, `knowledge`, `memory`, `provider`, `channel`), six
entries — filed by what the user comes to do with it rather than under one
Resources heading, because "resource" is the framework's storage word, not a
word a user navigates by:

- **Model providers** is filed under Agents, not Capabilities or Settings: a
  `provider` is `{protocol, base_url, credential_ref}`, the endpoint and key an
  agent's model is served from, and the connection and model are chosen per
  agent on that agent's page (spec
  [provider-switching](../provider-switching/spec.md) "Offer every connection operation on REST, CLI and web").
- **Channels** is filed under Run, beside Chat and not merged into it: Chat is
  where a person holds conversations every day, a channel is an IM bot set up
  once and revisited rarely, and the conversations a channel carries are already
  listed on the Chat page (spec [chat](../chat/spec.md) "Show every conversation on the Chat page").
- **MCP servers** and **Skills** are filed under Capabilities; **Knowledge** and
  **Memory** under Context.

Agents are stored as resources of kind `agent` but are the consumers of the
others, so the Agents entry heads the Agents group and no agent is listed on a
Capabilities or Context page. **Secrets** is not a resource kind — it is the
credential store every kind cites into — and sits under System (see "Manage
stored secrets on the Secrets page").

#### Scenario: each listed resource kind has one sidebar entry
- **GIVEN** the app shell is rendered with every experimental feature switched on
- **WHEN** the entries for resource kinds are read
- **THEN** MCP servers, Skills, Knowledge, Memory, Model providers and Channels each appear exactly once, under Capabilities, Capabilities, Context, Context, Agents and Run respectively
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
The About tab MUST show version, license, source and the update check of "Check
for and install updates on Settings › About" only, with no language picker (the
sidebar already switches language) and no installed-resource-kind list
(developer detail). Remaining jargon is rewritten in plain language (e.g.
"prune" is phrased as clearing expired data).

#### Scenario: settings offers no shutdown control
- **GIVEN** the user opens the Settings tabs
- **WHEN** each tab is fully rendered
- **THEN** no tab exposes a "Shutdown daemon" or "Stop daemon" control
- **AND** the About tab shows version / license / source and the update check only — no language picker, no resource-kind list

### Requirement: Set when the daemon runs on the Daemon tab
The Daemon tab MUST carry a card for when Coffer's daemon runs, with one control: a **Start at
login** switch. It MUST read and write it through
[daemon](../daemon/spec.md) "Change residency from the settings page or the command line".
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
- **AND** when the request fails, the switch goes back to off and the error is shown beside it

### Requirement: Choose Coffer's model in Settings › General
Settings › General MUST carry a **Coffer's model** section that sets what Coffer's
own machinery runs on (spec [internal-engine](../internal-engine/spec.md) "Show and change Coffer's model in Settings › General").
It is machine-level configuration of Coffer itself rather than of any agent, so
it is a Settings section, not a tab of the Model providers page. The section
MUST carry two pickers — **Engine model** and **Speech to text** — each choosing
a provider first and then a model from that provider's list, and a **Test**
action for each that tries the chosen pair and shows the result beside it. Each
picker MUST show its state inline: *not set* (saying what Coffer does without
it — no internal pass runs; voice messages reach the agent as audio files),
*set*, or *failing* (the last test or call failed, with the error). The Model
providers page MUST carry no Coffer's model tab. The legacy `/settings/engine`
path MUST open the Settings modal on General rather than resolve to a "page not
found" view, and so MUST `/settings/embedding`, which the router already keeps
only as a redirect for old bookmarks: Coffer has no embedding configuration
(search is literal-only), and the second picker is Speech to text.

#### Scenario: coffer's model is chosen in settings general
- **GIVEN** two connections, each with a list of models
- **WHEN** the user opens `/settings/general` and, in the Engine model picker, chooses a provider and then one of its models
- **THEN** the model list offers only the chosen provider's models, and the choice is saved without a Save button
- **AND** the Model providers page shows no Coffer's model tab

#### Scenario: an unset picker says what coffer does without it
- **GIVEN** no speech-to-text model chosen
- **WHEN** the Coffer's model section renders
- **THEN** the Speech to text picker reads as not set and says voice messages reach the agent as audio files

#### Scenario: testing a picker shows a failing pair inline
- **GIVEN** an engine model chosen on a connection whose endpoint rejects the key
- **WHEN** the user chooses Test beside the Engine model picker
- **THEN** the picker reads as failing with the endpoint's error beside it
- **AND** the chosen pair is kept as it was

#### Scenario: the old coffer's model address opens settings general
- **GIVEN** a user follows an old bookmark to `/settings/engine`
- **WHEN** the route resolves
- **THEN** the Settings modal opens on General and no "page not found" view is shown

### Requirement: Show the daemon's state in the shell footer
The shell MUST show the daemon's state at all times in a footer at the bottom of
the sidebar, read from the daemon's status probe (spec
[daemon](../daemon/spec.md) "Report the state the shell shows"). The footer MUST
name one of four states in plain words — connecting (no answer yet), running,
stopping (the daemon reports `draining`) or offline (it cannot be reached) — and,
while running, the port it answers on. In the desktop shell, a daemon from a
different app version MUST read as running with a version warning. Clicking the
state MUST open the Settings modal on its Daemon tab over the current page. The
footer also carries the Settings gear beside the state (see "Open Settings as a
modal from the sidebar footer"). On the collapsed icon rail the state MUST
shrink to an icon whose tooltip carries the same words, and the gear stays an
icon beside it. Showing the state
MUST NOT make starting the daemon the user's job: every surface that can start
one still does so without asking.

#### Scenario: the footer shows a running daemon
- **GIVEN** a daemon answering its status probe with `status: "ready"` on port 8000
- **WHEN** the shell renders
- **THEN** the sidebar footer reads that the daemon is running on port 8000
- **AND** clicking it opens the Settings modal on its Daemon tab at `/settings/daemon`, over the page the user was on

#### Scenario: the footer says connecting before the first answer
- **GIVEN** the shell has rendered and the daemon's status probe has not answered yet
- **WHEN** the footer renders
- **THEN** it reads as connecting, not as offline and not as running

#### Scenario: the footer shows an offline daemon
- **GIVEN** the daemon cannot be reached
- **WHEN** the footer renders
- **THEN** it reads as offline while the offline banner is shown
- **AND** clicking it still opens Settings → Daemon, which names the host's recovery

#### Scenario: the footer shows a stopping daemon
- **GIVEN** a daemon whose status probe reports `status: "draining"`
- **WHEN** the footer renders
- **THEN** it reads as stopping

#### Scenario: the collapsed rail keeps the daemon state
- **GIVEN** the sidebar collapsed to its icon rail and a running daemon
- **WHEN** the rail renders
- **THEN** the footer is a state icon whose tooltip reads that the daemon is running on its port

### Requirement: Show and manage the daemon on Settings → Daemon
The Daemon tab MUST show the daemon's state and carry the controls a user needs
for it, and nothing that stops it:

- **Status** — state, version, release channel, the port it answers on, when it
  started and the executable answering, all from the status probe.
- **Restart** — in the desktop shell, a Restart control that runs the shell's
  restart (spec [desktop-app](../desktop-app/spec.md) "Restart by stopping the running daemon first");
  in a browser, the `coffer daemon restart` command to copy, because a page the
  daemon serves cannot start the daemon that replaces it.
- **Port** — the port the daemon answers on, shown and not editable, beside the
  command that changes it (`coffer config set daemon.port <n>`, then
  `coffer daemon restart`), because the port is fixed before the database opens
  and is set where a taken port is diagnosed (spec [daemon](../daemon/spec.md) "Bind a fixed, settable port").
- **Start at login** — see "Set when the daemon runs on the Daemon tab".
- **Token** — a Rotate token control that asks for confirmation, saying that
  clients configured with the old token stop working, then calls
  `POST /api/v1/daemon/rotate-token` (spec [daemon](../daemon/spec.md) "Rotate the token from REST or the command line").
  The page MUST install the token the call returns and carry on without a reload;
  the confirmation MUST close only on success, and a failed rotation MUST leave the
  dialog open with the error and the old token in use.

While the status has not yet answered, the tab MUST keep its layout over
skeleton rows. While the daemon cannot be reached, the status card MUST read
offline and name the host's recovery — the Restart control in the desktop shell,
the `coffer daemon start` command in a browser — and the Start at login and
Rotate token controls MUST be disabled.

#### Scenario: the settings daemon tab shows the running daemon
- **GIVEN** a running daemon
- **WHEN** the user opens `/settings/daemon`
- **THEN** the status card shows its state, version, channel, port, start time and executable, matching `GET /api/v1/daemon/status`
- **AND** the tab carries no stop or shutdown control

#### Scenario: the settings daemon tab offers the host's restart
- **GIVEN** the Daemon tab open in a browser, and then in the desktop shell
- **WHEN** the restart row renders
- **THEN** the browser shows the `coffer daemon restart` command to copy and no restart button
- **AND** the desktop shell shows a Restart control that runs the shell's restart

#### Scenario: the settings daemon tab shows the port without editing it
- **GIVEN** a daemon answering on port 8123
- **WHEN** the Daemon tab renders
- **THEN** it shows port 8123 and the `coffer config set daemon.port` command beside it
- **AND** no control on the tab edits the port

#### Scenario: rotating the token from the settings daemon tab keeps the page working
- **GIVEN** the Daemon tab open on a running daemon
- **WHEN** the user rotates the token and confirms
- **THEN** one `POST /api/v1/daemon/rotate-token` is sent and the dialog closes
- **AND** the page's next requests carry the new token and succeed, with no reload

#### Scenario: a failed rotation from the settings daemon tab keeps the old token
- **GIVEN** the Daemon tab open, and a rotation that the daemon answers with `503`
- **WHEN** the user confirms the rotation
- **THEN** the dialog stays open with a readable error
- **AND** the page keeps using the old token, and its next request succeeds

#### Scenario: the settings daemon tab keeps its layout while status loads
- **GIVEN** the Daemon tab opened before the status probe has answered
- **WHEN** the tab renders
- **THEN** it shows its page header and skeleton rows rather than a blank pane or an offline state

#### Scenario: the settings daemon tab with the daemon offline
- **GIVEN** the daemon cannot be reached
- **WHEN** the user opens the Daemon tab
- **THEN** the status card reads offline and names the host's recovery
- **AND** the Start at login and Rotate token controls are disabled

### Requirement: Jump to any page or object from a command palette
The shell MUST offer a command palette, opened with ⌘K on macOS and Ctrl+K
elsewhere from any page, and from a search control in the sidebar. It MUST do
one thing — take the user somewhere — and MUST NOT carry an action that changes
state: no create, delete, enable, reach or run entry.

It MUST list two groups, filtered together by what the user types:

- **Pages** — every sidebar entry and every Settings tab, by the names the
  sidebar and the tabs use (see "Call a surface by one name everywhere"). A
  Settings tab opens in the Settings modal over the current page.
- **Objects** — the agents and the resources of every kind with a list surface,
  matched by title and by name, each opening its detail page.

A page or object of a switched-off experimental feature MUST NOT appear. The
palette MUST read the list routes the pages already read and add no route of its
own. Arrow keys MUST move the selection, Enter MUST open it, and Escape MUST
close the palette and return focus where it was.

The Pages group MUST be usable at once, whatever the daemon's state. While a
kind's objects are loading, its group MUST say so; a kind whose list fails MUST
show a readable error in its own group and leave the other groups working; while
the daemon cannot be reached, the palette MUST list Pages only and say that
objects need the daemon. A query that matches nothing MUST say so rather than
show an empty panel.

#### Scenario: the palette jumps to a page
- **GIVEN** the app open on any page
- **WHEN** the user presses ⌘K, types "act" and presses Enter
- **THEN** the app navigates to `/activity` and the palette closes

#### Scenario: the palette jumps to an object
- **GIVEN** a registered MCP server whose title differs from its name
- **WHEN** the user opens the palette and types part of its name, and then part of its title
- **THEN** each query lists the server under Objects
- **AND** choosing it opens `/mcp-servers/<uid>`

#### Scenario: the palette offers no actions
- **GIVEN** the palette open with an empty query
- **WHEN** every entry it can list is read
- **THEN** each entry is a page or an object that navigates somewhere
- **AND** choosing any of them sends no request that changes state

#### Scenario: the palette leaves out switched-off features
- **GIVEN** `knowledge` switched off and a knowledge collection on disk
- **WHEN** the user searches the palette for "knowledge" and for the collection's name
- **THEN** neither the Knowledge page nor the collection is listed

#### Scenario: the palette lists pages while objects load
- **GIVEN** the palette opened before the object lists have answered
- **WHEN** the user types a page's name
- **THEN** the page is listed and can be opened
- **AND** the Objects group says it is loading

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
[credentials](../credentials/spec.md) "Address a secret by an opaque reference") —
so it gets a page of its own rather than a section of any one kind's page, and
it is not a Settings tab, because it holds data the user manages rather than a
preference. A secret field inside a resource's own dialog stays there: a secret
is still entered where the thing that needs it is configured.

The page MUST carry:

- **List** — every secret the store reports, by its reference, with whether the
  store holds it, so a reference cited but missing reads as missing (spec
  [credentials](../credentials/spec.md) "List every cited reference with its presence").
- **Used by** — for each secret, what cites it, by kind and current name, each
  opening that thing's page; a secret nothing cites is marked unused.
- **Add and replace** — store a new secret, or replace the value of one that
  exists, without the value ever being shown back.
- **Reveal** — show one value behind an explicit action, which is an audited
  read (spec [credentials](../credentials/spec.md) "Audit every read of a secret value").
- **Delete** — refused while the secret is cited: the control MUST say what still
  uses it, naming each citer as the delete refusal does (spec
  [credentials](../credentials/spec.md) "Refuse to delete a credential still in use"), and
  the row MUST stay.
- **Migration assistant** — the entry point that moves plaintext secret files into
  the store, shown once that assistant ships.

This requirement fixes the page's place and its parts. What the store enumerates
beyond cited references, how each operation behaves, and the migration
assistant's steps are the credentials capability's, specified with it.

#### Scenario: the secrets page lists each secret with what uses it
- **GIVEN** a registered MCP server citing a stored reference, and a model provider citing a reference the store does not hold
- **WHEN** the user opens `/secrets`
- **THEN** both references are listed, the first as present and the second as missing
- **AND** each row names its citer by kind and current name, and choosing it opens that resource's page

#### Scenario: a secret in use cannot be deleted from the secrets page
- **GIVEN** a stored secret cited by a registered channel
- **WHEN** the user tries to delete it from the Secrets page
- **THEN** the delete is refused with the channel named as what still uses it
- **AND** the secret's row is still listed

#### Scenario: revealing a secret is an explicit, audited read
- **GIVEN** a stored secret listed on the Secrets page
- **WHEN** the page renders, and then the user chooses Reveal on that row
- **THEN** no value is shown until Reveal is chosen
- **AND** the reveal records a `credential_read` audit entry carrying the reference only

### Requirement: Mark a sidebar entry whose kind needs attention
A sidebar entry MUST carry a dot while the attention signal of the kind or tool
behind it is raised, so something that needs the user is seen from wherever they
are. It MUST be a dot and not a count — what is waiting is one situation to look
at — rendered by one shared component, with an accessible name that says the
entry needs attention, and it MUST stay visible on the collapsed icon rail. What
raises a signal and what clears it belongs to the capability that owns the kind;
today the one signal is Sync's (spec
[vault-sync](../vault-sync/spec.md) "Say a vault needs a human where the user already is"),
and a kind that declares a signal is marked by this same dot with no change to
the sidebar. An entry whose kind declares no signal MUST NOT carry a dot, and a
signal that has not loaded, or whose read failed, MUST leave no dot rather than
an error in the sidebar.

#### Scenario: an entry whose kind needs attention carries a dot
- **GIVEN** `vault_sync` switched on and a sync round held for confirmation
- **WHEN** the user is on any page other than Sync
- **THEN** the Sync entry carries the attention dot, with an accessible name saying it needs attention
- **AND** no other entry carries one

#### Scenario: the attention dot stays on the collapsed rail
- **GIVEN** the Sync entry carrying the attention dot
- **WHEN** the sidebar is collapsed to its icon rail
- **THEN** the Sync icon still carries the dot

#### Scenario: an entry without a signal never carries a dot
- **GIVEN** every attention signal the kinds declare is raised
- **WHEN** the sidebar renders
- **THEN** only the entries whose kinds declare a signal carry a dot

#### Scenario: an unreadable signal leaves no dot
- **GIVEN** the route behind a kind's attention signal failing, or not yet answered
- **WHEN** the sidebar renders
- **THEN** that entry carries no dot and the sidebar shows no error

### Requirement: Open Settings as a modal from the sidebar footer
Settings MUST NOT be a sidebar entry. It MUST open as a large modal over the
current page from three places: a gear button at the bottom of the sidebar,
beside the daemon status (see "Show the daemon's state in the shell footer");
the ⌘, shortcut on macOS and Ctrl+, elsewhere, from any page; and the command
palette's Settings tabs. The gear and the shortcut open it on General; the
footer's daemon state opens it on Daemon. Settings is machine-level
configuration a user visits rarely, so it takes no place in the sidebar
beside the pages used every day, the convention of desktop applications' own
preferences windows.

The modal MUST stay addressable by route: each tab is `/settings/<tab>`
(General, Security, Data, Daemon, About — see "Organise Settings into five
tabs"), and while it is open the address bar and history carry that route,
so a deep link, a reload, a link from another page (such as the footer's link
to `/settings/daemon`) or the palette opens the modal on that tab.
Opening it from a page MUST keep that page rendered underneath, unchanged.
Closing it — the close control, Escape, or a click outside it — MUST return to
the page underneath at that page's own route. A deep link opened with no page
underneath, as on a fresh load of `/settings/daemon`, MUST render the modal over
Overview, and closing it lands on `/`. Browser Back from an open modal MUST
close it and return to the page underneath.

#### Scenario: the gear opens Settings over the current page
- **GIVEN** the user on `/mcp-servers`
- **WHEN** they click the Settings gear in the sidebar footer
- **THEN** the Settings modal opens on General, the URL reads `/settings/general`, and the MCP servers list stays rendered underneath
- **AND** the sidebar has no Settings entry and marks MCP servers as current

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
- **GIVEN** the user on `/skills`
- **WHEN** they open the palette, type "data" and press Enter
- **THEN** the Settings modal opens on its Data tab at `/settings/data`, with the Skills page underneath

### Requirement: Check for and install updates on Settings › About
In the desktop shell, the About tab MUST show the version running, when updates
were last checked, a **Check for updates** control, and the result of the
latest check — up to date, or a newer version available with its version number
and a **Download and restart** control. The check and the install are the
shell's (spec [desktop-app](../desktop-app/spec.md) "Check for updates against a signed release manifest"),
reached through the same module as the shell's other host affordances; the tab
only renders what the shell reports and asks it to act. While a check or a
download is running its control MUST show that it is busy and not accept a
second press; a check or a download that fails MUST show a readable error on
the tab, keep the last successful check's time, and leave the running version
untouched. In a browser, About MUST show the version and say that updates are
installed by the desktop app, with no update control, because a page the
daemon serves cannot replace the application.

#### Scenario: about shows the version and when updates were last checked
- **GIVEN** the desktop shell running version 1.0.0, last checked at launch, with no newer release
- **WHEN** the user opens `/settings/about`
- **THEN** the tab shows 1.0.0, the time of that check, that Coffer is up to date, and a Check for updates control

#### Scenario: checking by hand finds a newer version
- **GIVEN** the About tab open in the desktop shell and a newer signed release on the manifest
- **WHEN** the user chooses Check for updates
- **THEN** the control shows it is checking, then the tab shows the newer version number and a Download and restart control
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
- **AND** it shows no Check for updates or Download and restart control
