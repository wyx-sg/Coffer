## RENAMED Requirements

- FROM: `### Requirement: Keep the sidebar to its eleven entries`
- TO: `### Requirement: Keep the sidebar to its twelve entries`

- FROM: `### Requirement: Organise Settings into five tabs`
- TO: `### Requirement: Organise Settings into six tabs`

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

## MODIFIED Requirements

### Requirement: Group the sidebar by role
The sidebar MUST be grouped by role rather than on one axis: AGENTS for the
consumers (the agents, and the chat held with one) and RESOURCES for the assets
those agents draw on, with SYSTEM for the cross-cutting tooling (Activity, Sync
and Settings), so the navigation stays stable as Coffer grows. Agents are not a
resource kind and MUST NOT be listed under Resources.

**Overview**, the landing page, MUST sit above the three groups under no heading.
It summarises all three roles, so filing it under any one of them would misname
it, and it is the one entry that is not a kind or a tool.

AGENTS holds two entries, and Agents comes first: the agents are the subject,
and a chat is one thing you do with one of them. The group stays its own even
though it is the smallest — agents are the one thing in the product that *uses*
the vault rather than living in it, and collapsing the group would lose that
distinction to save two lines.

#### Scenario: the sidebar groups agents, resources and system by role
- **GIVEN** the app shell is rendered
- **WHEN** the sidebar lists its entries
- **THEN** Overview comes first, under no heading, and the rest sit under three headings in the order Agents, Resources, System
- **AND** Agents holds Agents then Chat, Resources holds no agent entry, and System holds Activity, Sync and Settings

### Requirement: Keep the sidebar to its twelve entries
The sidebar's entries MUST be exactly these, at these routes: one ungrouped entry
and three groups — twelve today, and no thirteenth. An entry whose experimental
feature is switched off (spec
[experimental-features](../experimental-features/spec.md) "Close every surface of a switched-off feature")
MUST be left out — today Knowledge for `knowledge`, Memory for `memory`, Sync for
`vault_sync` — and MUST appear on the next render after the feature is switched
on:

```
  Overview         /                  — the landing page
 AGENTS
  Agents           /agents            — the consumers (Bot icon)
  Chat             /chat              — a conversation with one of them
 RESOURCES
  MCP servers      /mcp-servers       — the aggregated upstream servers
  Skills           /skills            — what Coffer delivers to agents
  Knowledge        /knowledge         — the collections under ~/.coffer/knowledge/
  Memory           /memory            — the partitions aggregated from the agents' own stores
  Model providers  /model-providers   — credentialed vendor endpoints, and Coffer's own model
  Channels         /channels          — the IM transports agents answer on
 SYSTEM
  Activity         /activity          — what changed, what was called, what broke
  Sync             /sync              — converging this vault with a git remote
  Settings         /settings
```

#### Scenario: cold-start renders authenticated content
- **GIVEN** the user has never opened Coffer (localStorage is empty, no daemon.json in user HOME yet)
- **AND** every experimental feature is switched on
- **AND** `coffer daemon start` is running (so daemon.json exists in user HOME)
- **WHEN** they navigate to `http://localhost:5173/` in a real browser
- **THEN** the index renders the Overview page at `/`, with the sidebar and main content area, within 2 seconds
- **AND** the main content shows the Overview page (no generic error card)
- **AND** the sidebar lists exactly Coffer's operational surfaces — Overview; Agents, Chat; MCP servers, Skills, Knowledge, Memory, Model providers, Channels; Activity, Sync, Settings — with Overview under no heading and the rest grouped under "Agents", "Resources", and "System" headings, with no other entry

#### Scenario: a switched-off feature leaves the sidebar
- **GIVEN** `knowledge` and `vault_sync` switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar lists Overview; Agents, Chat; MCP servers, Skills, Memory, Model providers, Channels; Activity, Settings — with no Knowledge and no Sync entry

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

### Requirement: Organise Settings into six tabs
Settings MUST carry exactly six tabs, in this order, grouped by what they manage
rather than by how Coffer is built, and MUST open on General:

- **General** (`/settings/general`) — display preferences: the default page size
  and the preferred external editor.
- **Features** (`/settings/features`) — which experimental features are switched
  on for this machine (spec
  [experimental-features](../experimental-features/spec.md) "List and switch the features on the Features tab").
- **Security** (`/settings/security`) — where the master encryption key lives:
  beside the database, or in the OS keychain.
- **Data** (`/settings/data`) — retention policy and manual prune.
- **Daemon** (`/settings/daemon`) — the daemon's state and the controls a user
  needs for it (see "Show and manage the daemon on Settings → Daemon").
- **About** (`/settings/about`) — version, license, source.

Coffer's own model is not a Settings tab: it sits beside the providers it is
chosen from (see "Show Coffer's model beside Model providers"). Clicking a tab
swaps the right pane without a full page reload.

#### Scenario: settings layout uses the redesigned tabbed sidebar
- **GIVEN** the user navigates to `/settings`
- **WHEN** the page resolves
- **THEN** it lands on the General tab
- **AND** the settings sidebar shows General, Features, Security, Data, Daemon, and About — exactly those six, in that order — with the current route highlighted
- **AND** clicking a tab swaps the right pane content without a full page reload

## ADDED Requirements

### Requirement: Open the app on Overview
The app's index (`/`) MUST render the Overview page, the landing page, in place
rather than redirecting elsewhere, so a visitor lands on the whole of the vault
before any one part of it. This requirement fixes where the app lands; what the
Overview page shows is a requirement of its own. Agents live at `/agents` (list)
and `/agents/:uid` (detail), addressed by uid like every other detail route, and
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
The About tab MUST show version, license and source only, with no language picker
(the sidebar already switches language) and no installed-resource-kind list
(developer detail). Remaining jargon is rewritten in plain language (e.g.
"prune" is phrased as clearing expired data).

#### Scenario: settings offers no shutdown control
- **GIVEN** the user opens the Settings tabs
- **WHEN** each tab is fully rendered
- **THEN** no tab exposes a "Shutdown daemon" or "Stop daemon" control
- **AND** the About tab shows version / license / source only — no language picker, no resource-kind list

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

### Requirement: Show Coffer's model beside Model providers
The Model providers page MUST carry two tabs: **Providers** (the list, and the
default) and **Coffer's model** (`/model-providers?tab=coffer-model`), which
holds what configures Coffer's own machinery — the internal model, speech to
text and the automatic upkeep passes (spec
[internal-engine](../internal-engine/spec.md) "Show and change the engine on the Coffer's model tab").
Coffer's model is a choice among the providers listed beside it, so it lives
where those providers are, not in Settings. The legacy `/settings/engine` path
MUST redirect to it rather than resolve to a "page not found" view.

#### Scenario: Coffer's model opens beside the providers
- **GIVEN** the user opens `/model-providers`
- **WHEN** the page renders
- **THEN** it shows the Providers tab selected and a Coffer's model tab beside it
- **AND** choosing Coffer's model rewrites the URL to `/model-providers?tab=coffer-model` and shows the engine's cards

#### Scenario: the old Coffer's model address redirects
- **GIVEN** a user follows an old bookmark to `/settings/engine`
- **WHEN** the route resolves
- **THEN** the app lands on `/model-providers?tab=coffer-model` and no "page not found" view is shown

### Requirement: Show the daemon's state in the shell footer
The shell MUST show the daemon's state at all times in a footer at the bottom of
the sidebar, read from the daemon's status probe (spec
[daemon](../daemon/spec.md) "Report the state the shell shows"). The footer MUST
name one of four states in plain words — connecting (no answer yet), running,
stopping (the daemon reports `draining`) or offline (it cannot be reached) — and,
while running, the port it answers on. In the desktop shell, a daemon from a
different app version MUST read as running with a version warning. Clicking the
footer MUST open Settings → Daemon. On the collapsed icon rail the footer MUST
shrink to a state icon whose tooltip carries the same words. Showing the state
MUST NOT make starting the daemon the user's job: every surface that can start
one still does so without asking.

#### Scenario: the footer shows a running daemon
- **GIVEN** a daemon answering its status probe with `status: "ready"` on port 8000
- **WHEN** the shell renders
- **THEN** the sidebar footer reads that the daemon is running on port 8000
- **AND** clicking it opens `/settings/daemon`

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
  sidebar and the tabs use (see "Call a surface by one name everywhere").
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
