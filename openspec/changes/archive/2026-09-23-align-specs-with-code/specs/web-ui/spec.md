## MODIFIED Requirements

### Requirement: List only shipped surfaces in the sidebar
The sidebar MUST list only surfaces that have shipped. It MUST NOT carry "not
yet implemented" placeholders — a sidebar full of "soon" entries reads as an
unfinished scaffold, not a product; an entry leaves the sidebar when its
feature does, and returns with it. **Machines** left the sidebar as a top-level
fleet view and came back under Sync's Setup tab, where a machine is one
participant in convergence rather than a surface of its own.

#### Scenario: the sidebar carries no placeholder entries
- **GIVEN** the app shell is rendered
- **WHEN** every sidebar entry is inspected
- **THEN** each is a link to a route the app serves
- **AND** none is marked as coming soon or not yet implemented

### Requirement: Open the app on the Agents page
The app's index (`/`) MUST redirect to `/agents`, so a first-time visitor lands
on the Agents surface. Agents live at `/agents` (list) and `/agents/:uid`
(detail), addressed by uid like every other detail route, and MUST NOT appear in the `/mcp-servers` kind browser.

#### Scenario: the index opens the Agents page
- **GIVEN** the app's route table
- **WHEN** the user opens `/`
- **THEN** the app lands on `/agents`
- **AND** the `/mcp-servers` list asks only for MCP servers, so no agent appears there

### Requirement: Show reach as a labelled button on every list and detail page
Every list surface of a scoped kind MUST carry a **reach** column — named for what it holds, not
for the on/off flag it replaced: one button labelled with the answer it already
holds — "Every agent", "2 agents", "Disabled", or "No agent selected" for a
scope narrowed to nobody — so the reader learns the reach by reading it rather
than by comparing which of three side-by-side segments looks pressed. Every
detail page MUST carry the same button in its header. A kind that declares no
scope — knowledge, memory — MUST head the same column **Status** instead, and its
button MUST read "Enabled" or "Disabled", because enabled or disabled is the
whole of what it reports; see "Offer reach as one choice in a panel".

#### Scenario: the reach button states the reach it holds
- **GIVEN** resources that reach every agent, two agents, nobody selected, and one that is disabled
- **WHEN** each one's reach button renders
- **THEN** they read "Every agent", "2 agents", "No agent selected" and "Disabled"
- **AND** each is one button rather than a row of segments

### Requirement: Filter lists by the same reach states
For a scoped kind, the list's reach filter MUST offer the same states the panel
does, rather than a bare enabled / disabled pair, and the column, the filter and
the button MUST all use the word *reach*, because they are all asking the one
question. A kind that declares no scope MUST head its filter **Status**, like its
column, and offer only Disabled and Enabled.

#### Scenario: the reach filter offers the panel's states under the reach name
- **GIVEN** a list surface of a scoped kind
- **WHEN** its reach filter is built
- **THEN** it offers Disabled, Every agent and Only selected agents, labelled as the reach button labels them
- **AND** the filter is headed Reach, the word the column and the button use

### Requirement: Gather the three records on one Activity page
The three records Coffer keeps — the audit log (what changed in the vault, and
who changed it), the MCP invocation log (every call the gateway proxied) and the
daemon log (what Coffer itself did, including what broke) — MUST reach a person
through one page at `/activity`, under System, carrying one tab per record —
Changes, MCP calls, Daemon — each a newest-first table with the columns that
record actually has: an activity line and its actor; a call's server,
capability, duration and outcome; a log record's level, logger and message.

#### Scenario: activity gives each record its own tab
- **GIVEN** Coffer has recorded an audit entry, an MCP invocation and a daemon log record
- **WHEN** the user opens `/activity` and moves through its three tabs
- **THEN** each tab renders that record's own newest-first table with the columns that record has — an activity line and actor; a call's server, capability, duration and outcome; a log record's level, logger and message
- **AND** a change reads as a plain-language line, not a raw event code

#### Scenario: the daemon tab reads every writer in the log
- **GIVEN** `daemon.log` holds lines from several writers at once — Coffer's own JSON, the format the daemon itself wrote before [daemon](../daemon/spec.md) "Write one bounded daemon log in one format" was met, uvicorn, rich, and the cloudflared child's zerolog — with a colour-escaped line among them and a traceback written under the record that raised it
- **WHEN** the user opens the Daemon tab
- **THEN** each row carries the time, level and logger its own line stated, and nothing carries a time or a level it never stated
- **AND** no message renders a terminal escape sequence as text
- **AND** the traceback rides with the record that raised it rather than becoming rows of its own
- **AND** the severity-floor filter judges each line by its own level rather than treating every non-JSON line as an error

### Requirement: Filter each Activity tab and expand any row
Every Activity tab MUST filter by free text and time range plus the one filter
its own record affords (actor, call status, a severity floor), and any row MUST
expand to its raw underlying record, pretty-printed in a monospace, scrollable
block.

#### Scenario: activity row expands to its raw record
- **GIVEN** an Activity tab has at least one row
- **WHEN** the user clicks (or presses Enter/Space on) that row
- **THEN** an expanded region renders its raw record — the full underlying JSON, pretty-printed in a monospace, scrollable block

### Requirement: Keep the command-line record readers
Bringing the three records onto one page MUST NOT change or withdraw the
command-line readers — `coffer audit` and `coffer mcp invocations <server>` keep working
as they are, and scripts keep `GET /api/v1/audit`, so a script that read a
record before this page existed still does.

#### Scenario: the command-line readers still read the records
- **GIVEN** a running daemon that has recorded an audit entry and an MCP invocation
- **WHEN** a script runs `coffer audit` and `coffer mcp invocations <server>`
- **THEN** each exits successfully and prints that record's entry

### Requirement: Organise Settings into five tabs
Settings MUST carry exactly five tabs, in this order, grouped by what they
manage rather than by how Coffer is built — **General** (display preferences, and when the daemon runs),
**Coffer's model** (at `/settings/engine` — Coffer's own machinery: the internal
LLM connection and model its own passes run on, the speech-to-text connection
and model voice messages are transcribed on, and the switch and interval of each
of those passes), **Data** (retention policy and manual prune), **Security**
(where the master encryption key lives — beside the database, or in the OS
keychain), and **About** (version, license, source) — and MUST open on General.
Clicking a tab swaps the right pane without a full page reload.

#### Scenario: settings layout uses the redesigned tabbed sidebar
- **GIVEN** the user navigates to `/settings`
- **WHEN** the page resolves
- **THEN** it lands on the General tab
- **AND** the settings sidebar shows General, Coffer's model, Data, Security, and About — exactly those five, in that order — with the current route highlighted
- **AND** clicking a tab swaps the right pane content without a full page reload

### Requirement: Keep retention and prune on the Data tab
The Data tab MUST carry the retention policy per log table — Keep forever, or a
number of days — and a manual prune, with a saved value surviving a reload.
Edits auto-save, like every settings surface: there is no Save button.

#### Scenario: retention period persists across reload
- **GIVEN** the user opens the Data settings tab
- **WHEN** they turn off "Keep forever" for a log table, set a specific number of retention days, and commit the field (blur or Enter), which auto-saves
- **THEN** reloading the page shows the same retention-days value that was saved

### Requirement: Keep the daemon out of the user's view
The daemon MUST NOT be surfaced as a machine to inspect: there is no Daemon tab
and no read-only daemon-status panel (status / version / port / start time). A
healthy daemon needs no readout, and the failure case is owned by the offline
banner. The one daemon setting the UI carries is *when it runs* — whether it
starts at login and how long it stays up with nothing using it — on the General
tab (see "Let the user choose when the daemon runs"), because that is a question
about how the app behaves, asked where a user looks for why it was not running.

#### Scenario: settings shows no daemon tab and no daemon status
- **GIVEN** the user opens Settings
- **WHEN** every tab is rendered
- **THEN** there is no Daemon tab
- **AND** no tab shows a read-only readout of the daemon's status, port or start time

## ADDED Requirements

### Requirement: Let the user choose when the daemon runs
The General tab MUST carry a card for when Coffer's daemon runs, with two
controls: a **Start at login** switch and a **Stand down after** choice of idle
window that offers a set of hour values and **Never** as its own option, never
as a number. It MUST read and write both through
[daemon](../daemon/spec.md) "Change residency from the settings page or the command line",
and every change MUST send both halves in one request. The controls MUST show
what the daemon last reported rather than what was clicked: they are disabled
until the daemon has answered, a window set from the command line that the list
does not offer is still shown, the switch is shown unavailable rather than off
on a host with no login service, and a failed write MUST put the controls back to
what the daemon holds and show the error beside them.

#### Scenario: the general tab sets when the daemon runs
- **GIVEN** the daemon reports a login service that is supported and not installed, and an idle window of 12 hours
- **WHEN** the user turns on Start at login, and then picks Never as the idle window
- **THEN** each change sends one request carrying both halves — first `login_service_installed: true` with `idle_shutdown_hours: 12`, then `login_service_installed: true` with `idle_shutdown_hours: null`
- **AND** the idle window offers 1, 4, 12, 24 and 72 hours and Never
- **AND** when the second request fails, the idle window goes back to 12 hours and the error is shown beside it
