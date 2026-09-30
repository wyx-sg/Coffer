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

The sidebar is grouped **by role**: **agents** are the _consumers_ (the agents
you use, and the chat you hold with one), and **resources** are the _assets_
those agents draw on — named, configured, lifecycle-managed entities behind a
kind-agnostic framework. See
[Sidebar Grouped by Role](../../../docs/decisions/sidebar-grouped-by-role.md)
(Amended 2026-05-30) for the decision behind this role-based information
architecture (agents as a separate consumer axis; rejected alternative: a
separate "surface" concept; sidebar policy: no "soon" placeholders).
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
`coffer log daemon`, and correlates them itself; the page deliberately never joins them — a single merged timeline could
only carry the three records' lowest common denominator, so a call's duration
and a record's level had nowhere to live.

## Requirements

### Requirement: Group the sidebar by role
The sidebar MUST be grouped by role rather than on one axis: AGENTS for the
consumers (the agents, and the chat held with one) and RESOURCES for the assets
those agents draw on, with SYSTEM for the cross-cutting tooling (Activity, Sync
and Settings), so the navigation stays stable as Coffer grows. Agents are not a
resource kind and MUST NOT be listed under Resources.

AGENTS holds two entries, and Agents comes first: the agents are the subject,
and a chat is one thing you do with one of them. The group stays its own even
though it is the smallest — agents are the one thing in the product that *uses*
the vault rather than living in it, and collapsing the group would lose that
distinction to save two lines.

#### Scenario: the sidebar groups agents, resources and system by role
- **GIVEN** the app shell is rendered
- **WHEN** the sidebar lists its entries
- **THEN** they sit under three headings in the order Agents, Resources, System
- **AND** Agents holds Agents then Chat, Resources holds no agent entry, and System holds Activity, Sync and Settings

### Requirement: Give every scoped resource kind its own list surface
Every scoped resource kind MUST have its own list surface, so the navigation and
each list page carry no kind-specific branch.

#### Scenario: every resource entry opens a list page of its own
- **GIVEN** the sidebar's Resources entries
- **WHEN** each entry's route is resolved against the app's route table
- **THEN** each resolves to its own list route rather than to "page not found"
- **AND** no two entries resolve to the same route

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

### Requirement: Keep the sidebar to its eleven entries
The sidebar's entries MUST be exactly these, in these three groups and at these
routes — eleven today, and no twelfth. An entry whose
experimental feature is switched off (spec
[experimental-features](../experimental-features/spec.md) "Close every surface of a switched-off feature")
MUST be left out, and MUST appear on the next render after the feature is
switched on. Knowledge, Memory and Sync are ordinary entries, owned by no
experimental feature:

```
 AGENTS
  Agents           /agents            — the consumers (Bot icon)
  Chat             /chat              — a conversation with one of them
 RESOURCES
  MCP servers      /mcp-servers       — the aggregated upstream servers
  Skills           /skills            — what Coffer delivers to agents
  Knowledge        /knowledge         — the collections under ~/.coffer/knowledge/
  Memory           /memory            — the partitions aggregated from the agents' own stores
  Model providers  /model-providers   — credentialed vendor endpoints
  Channels         /channels          — the IM transports agents answer on
 SYSTEM
  Activity         /activity          — what changed, what was called, what broke
  Sync             /sync              — converging this vault with a git remote
  Settings         /settings
```

#### Scenario: cold-start renders authenticated content
- **GIVEN** the user has never opened Coffer (localStorage is empty, no daemon.json in user HOME yet)
- **AND** `coffer daemon start` is running (so daemon.json exists in user HOME)
- **WHEN** they navigate to `http://localhost:5173/` in a real browser
- **THEN** the index redirects to `/agents` and the page renders the sidebar + main content area within 2 seconds
- **AND** the main content shows the Agents welcome view (no generic error card)
- **AND** the sidebar lists exactly Coffer's operational surfaces — Agents, Chat; MCP servers, Skills, Knowledge, Memory, Model providers, Channels; Activity, Sync, Settings — grouped under "Agents", "Resources", and "System" headings, with no other entry

#### Scenario: a switched-off feature leaves the sidebar
- **GIVEN** a sidebar entry owned by a registered experimental feature that is switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar leaves that entry out and lists every other entry
- **AND** with a registry that names no feature, the sidebar lists all eleven entries

### Requirement: Hold one Resources entry per listed resource kind
RESOURCES MUST hold exactly one entry per resource kind that has a list UI —
today six kinds (`mcp_server`, `skill`, `knowledge`, `memory`, `provider`,
`channel`), six entries. That correspondence is the rule: **Model providers**
is filed under Resources rather than Settings, because a `provider` is
`{protocol, base_url, secret_ref}`, a vendor endpoint and its key, and the
model is not stored there but chosen at the point of use; **Channels** is filed
under Resources rather than Agents, because a channel is a credentialed
transport the vault owns, not a consumer of the vault.

#### Scenario: resources holds one entry per kind with a list
- **GIVEN** the app shell is rendered
- **WHEN** the Resources group is read
- **THEN** it holds exactly MCP servers, Skills, Knowledge, Memory, Model providers and Channels, in that order

### Requirement: Call a surface by one name everywhere
A surface MUST carry one name in every place it is named — sidebar, page header,
welcome panel and dialogs — because a surface the user reaches two ways must not
have two names. Channels, for one, is named **「消息渠道 / Channels」** and nothing
else.

#### Scenario: a surface carries one name in the sidebar and on its page
- **GIVEN** the UI in English and then in 中文
- **WHEN** each sidebar entry's label is compared with the title its page shows
- **THEN** the two are the same words for every surface in both languages

### Requirement: Collapse the sidebar to a remembered icon rail
The sidebar MUST collapse to an icon-only rail and back, and that choice MUST
persist across sessions (`localStorage`).

#### Scenario: the collapsed sidebar stays collapsed after a reload
- **GIVEN** the user collapses the sidebar to its icon rail
- **WHEN** the shell is rendered again, as after a reload
- **THEN** it opens as the icon rail
- **AND** expanding it again is likewise remembered

### Requirement: Open the app on the Agents page
The app's index (`/`) MUST redirect to `/agents`, so a first-time visitor lands
on the Agents surface. Agents live at `/agents` (list) and `/agents/:uid`
(detail), addressed by uid like every other detail route, and MUST NOT appear in the `/mcp-servers` kind browser.

#### Scenario: the index opens the Agents page
- **GIVEN** the app's route table
- **WHEN** the user opens `/`
- **THEN** the app lands on `/agents`
- **AND** the `/mcp-servers` list asks only for MCP servers, so no agent appears there

### Requirement: Redirect legacy resource paths
The legacy path `/resources` MUST resolve as a redirect to the MCP server
surface rather than as a "page not found" view. Name-based detail URLs are not
translated: every detail route is addressed by the resource's immutable `uid`,
and translating an old name would need the lookup by name that addressing
removed.

#### Scenario: legacy resource paths redirect instead of 404ing
- **GIVEN** a user follows an old bookmark to `/resources`
- **WHEN** the route resolves
- **THEN** the app redirects to the MCP server surface and no "page not found" view is shown

### Requirement: Use one shared table for every list surface
Every list surface — agents, MCP servers, skills, knowledge, memory, model
providers, channels, each Activity tab, Sync's Runs tab — MUST use one shared
searchable, filterable, paginated table, and a row click MUST open that item's
detail page. Sync's Setup tab is not a list surface: it is configuration cards,
and the machine registry it carries is a small plain table.

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

#### Scenario: detail pages share one tab layout
- **GIVEN** two detail pages of different kinds
- **WHEN** each is opened with a tab named in its URL
- **THEN** each renders its tabs in the shared tab strip with that tab selected
- **AND** switching tab rewrites the URL the same way on both

### Requirement: Show reach as a labelled button on every list and detail page
Every list surface of a scoped kind MUST carry a **reach** column — named for what it holds, not
for the on/off flag it replaced: one button labelled with the answer it already
holds — "Every agent", "2 agents", "Disabled", or "No agent selected" for a
scope narrowed to nobody — so the reader learns the reach by reading it rather
than by comparing which of three side-by-side segments looks pressed. Every
detail page MUST carry the same button in its header. A kind that declares no
scope — an agent, a knowledge collection, a memory partition — MUST carry neither
the column, the button, nor a bulk reach action; see "Offer reach as one choice in a panel".

#### Scenario: the reach button states the reach it holds
- **GIVEN** resources that reach every agent, two agents, nobody selected, and one that is disabled
- **WHEN** each one's reach button renders
- **THEN** they read "Every agent", "2 agents", "No agent selected" and "Disabled"
- **AND** each is one button rather than a row of segments

#### Scenario: a kind that cannot be disabled shows no status control
- **GIVEN** the knowledge and memory list pages and one collection's and one partition's page
- **WHEN** each renders
- **THEN** no list has a Status or Reach column and no header carries a reach or status button

### Requirement: Offer reach as one choice in a panel
The button MUST open a panel where "who does this reach?" is a single choice
between Disabled, Every agent and Only selected agents, the last over the
scope's list of agents.

#### Scenario: the reach panel offers the reach states as one choice
- **GIVEN** a resource of a scoped kind
- **WHEN** its reach panel is opened
- **THEN** it offers Disabled, Every agent and Only selected agents with its current state chosen
- **AND** choosing Only selected agents shows the list of agents to pick from

### Requirement: Write the reach once, when the panel closes
The panel MUST stage its agent list and write exactly once, when it closes — the
two whole-value choices close it themselves — so a panel that is opened and
dismissed writes nothing, and no write can refetch the list and move the row the
panel is anchored to.

#### Scenario: a dismissed reach panel writes nothing
- **GIVEN** a reach panel opened on a resource
- **WHEN** the user dismisses it without choosing, and then opens it again and ticks two agents before closing it
- **THEN** the dismissal writes nothing
- **AND** the two ticks are written once, when the panel closes

### Requirement: Mount one reach control in three places
The reach control MUST be one component mounted in three places — the list row,
the detail header and the multi-select bar — so the three can never drift into
three different answers to one question.

#### Scenario: row, header and selection bar mount the same reach control
- **GIVEN** an MCP server that reaches every agent
- **WHEN** its list row, its detail header and the list's selection bar render
- **THEN** each carries the same reach button, which opens the same reach panel

### Requirement: Apply reach to a whole selection
A multi-select MUST apply that same choice to the whole selection. A bulk write
is a new intent, so its button reads "Set reach…" and its panel opens with
nothing chosen rather than on any one row's value, and a row that fails MUST be
reported in the batch's one summary rather than silently skipped. Delete stays
its own button beside it.

#### Scenario: a bulk reach write starts blank and reports failures in one summary
- **GIVEN** several selected rows, one of which will fail to update
- **WHEN** the user opens the selection bar's reach control and chooses a reach
- **THEN** the button reads "Set reach…" and its panel opened with nothing chosen
- **AND** every other row is still written, and the one failure is reported in a single summary for the batch

### Requirement: Filter lists by the same reach states
For a scoped kind, the list's reach filter MUST offer the same states the panel
does, rather than a bare enabled / disabled pair, and the column, the filter and
the button MUST all use the word *reach*, because they are all asking the one
question.

#### Scenario: the reach filter offers the panel's states under the reach name
- **GIVEN** a list surface of a scoped kind
- **WHEN** its reach filter is built
- **THEN** it offers Disabled, Every agent and Only selected agents, labelled as the reach button labels them
- **AND** the filter is headed Reach, the word the column and the button use

### Requirement: Make empty, loading and error states first-class
No surface may render a blank page, or a generic error, where a next action
exists. Empty, loading and error states MUST be first-class on every surface,
not an afterthought on some of them.

#### Scenario: a list surface shows first-class loading and error states
- **GIVEN** a list surface whose query is still pending, and then one whose query fails
- **WHEN** each renders
- **THEN** the pending one keeps its page header over skeleton rows rather than a blank page
- **AND** the failed one shows an error card with a readable message rather than an empty page

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
- **THEN** the page renders a welcome card with a short pitch and a primary "Add MCP server" button
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
When an authenticated request fails to connect while the app is open, a
daemon-offline banner MUST render above the workspace, naming the recovery the
host can offer — in a browser the `coffer daemon start` command, in the desktop
shell a Restart control, because only one of the two can spawn a daemon. The
banner MUST clear itself once the daemon is reachable again, with no manual page
reload. A healthy daemon needs no UI; this banner owns the failure case.

#### Scenario: daemon-offline banner appears when daemon is unreachable
- **GIVEN** the daemon is not running (no reachable `127.0.0.1:<port>` from `~/.coffer/daemon.json`, or the file is absent)
- **WHEN** the user has the app open and any authenticated request to the daemon fails to connect
- **THEN** a daemon-offline banner renders at the top of the workspace naming the recovery the host can actually offer — in a browser, the `coffer daemon start` command to run, because the page cannot start a daemon; in the desktop shell, a Restart control, because it can
- **AND** the banner disappears automatically once the daemon becomes reachable again, without a manual page reload

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
Overview, before the per-capability toggles.

#### Scenario: a server's detail page opens on its Overview
- **GIVEN** a registered MCP server
- **WHEN** its detail page is opened with no tab named in the URL
- **THEN** the Overview tab is the selected tab and its content is shown
- **AND** the Tools, Resources and Prompts tabs follow it

### Requirement: Keep the capability tabs uniform
The Tools, Resources and Prompts tabs MUST be uniform — each carrying its count of how many are on, a filter box, All on · All off and a per-row enable toggle, with each row's use in the last 24 hours — and MUST keep that chrome even when the upstream exposes none of that kind, saying so inside the tab rather than as a bare card. A tool row opens to its full description, its input parameters and the name agents see it by. The server list likewise carries a search box, a reach filter and a client-side pager so a large vault stays navigable; the skills list works the same way.

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

### Requirement: Import MCP servers from pasted JSON
"Add MCP server" MUST be a modal that takes the standard `mcpServers` JSON
block — the same block every MCP server's README provides — one server or many
at once, with a review step where the user confirms which values are secrets.
The review covers every server's `env` values and, for an HTTP server, the
values of its `headers` object too, read with the same secret detection as
`env` rather than ignored (a header and an `env` entry of the same name are one
header, the `headers` value winning). Secrets MUST
be lifted into the encrypted secret store with only their refs kept in the
resource config, and the server MUST be registered before its secrets are
written, so a failed registration leaves no orphan secret entry.

The review step MUST show each server's name, taken from its key in the pasted block, as the
name the server will keep: it cannot be changed after registration
([mcp-gateway](../mcp-gateway/spec.md) "Manage MCP servers as resources"). A name longer than
24 characters MUST be flagged in the review, before submit, with a message naming the limit, and
the dialog MUST NOT send that server's registration until the name is shortened in the pasted
block.

#### Scenario: MCP server registration round-trip via JSON import
- **GIVEN** the user opens the "Add MCP server" dialog from the resources list
- **WHEN** they paste the standard `mcpServers` JSON and confirm the review step
- **THEN** the app posts each server to `/api/v1/resources`, then writes any secret env values to `/api/v1/secrets` (register-first ordering avoids orphan secret entries when registration fails)
- **AND** on success the dialog closes and (for a single server) the app navigates to the server's detail page `/mcp-servers/<uid>` showing the Overview tab
- **AND** the new server appears on the resources list with health "unknown" then "healthy" within 10 seconds

#### Scenario: add-server form navigates to detail then back to list shows card
- **GIVEN** the user completes the JSON-import dialog for a new MCP server
- **WHEN** they are taken to the server's detail page and then navigate back to `/mcp-servers`
- **THEN** the server card appears in the resources list

#### Scenario: a pasted HTTP server's headers are reviewed for secrets
- **GIVEN** the user pastes an `mcpServers` block holding an HTTP server with a `headers` object that carries an `Authorization` value
- **WHEN** the review step is shown and confirmed
- **THEN** the header is offered as a secret, its value is written to the secret store, and the registered server keeps only its ref (`secret_refs`), never the value in `headers`

#### Scenario: the import review shows each server's fixed name
- **GIVEN** the user pastes an `mcpServers` block holding one server keyed with a 12-character name and one keyed with a 30-character name
- **WHEN** the review step is shown
- **THEN** each server's name is shown with a note that it cannot be changed after registration, and the 30-character name is flagged with the 24-character limit
- **AND** no request is sent to `/api/v1/resources` for the flagged server while its name is over the limit

### Requirement: Reject malformed server JSON in the dialog
A payload that is not valid JSON, or a valid JSON document that does not match
the `mcpServers` shape, MUST keep the dialog open with a readable error — the
parse location, or the failing field — and MUST NOT send a request.

#### Scenario: JSON import shows readable error for malformed JSON
- **GIVEN** the user opens the "Add MCP server" dialog
- **WHEN** they paste a payload that is not valid JSON (or a valid JSON document that does not match the `mcpServers` shape) and submit
- **THEN** the dialog stays open and renders a readable error explaining what is wrong (parse error location for malformed JSON, or the failing field for shape-mismatch)
- **AND** no request is sent to `/api/v1/resources` or `/api/v1/secrets`
- **AND** the dialog never shows the literal text "unexpected error" or `INTERNAL_ERROR`

### Requirement: Scope Activity's calls table to one server on its page
A server's **Invocations** tab MUST render the same table Activity's MCP calls
tab renders, scoped to that one server, rather than a second table that would
have to be kept in step with the first. It lists every call the gateway proxied
for this server, newest first, filterable by status and time range, each row
expanding to that call's raw JSON record — the only account of what an agent
did when the agent is the thing that is broken.

#### Scenario: a server's invocations tab is the Activity calls table scoped to it
- **GIVEN** a registered MCP server
- **WHEN** its Invocations tab and Activity's MCP calls tab each render
- **THEN** both render the one invocation table
- **AND** the server's tab asks only for that server's calls and drops the server column, while Activity's asks for every server's calls and names each row's server

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
- **GIVEN** `daemon.log` holds lines from several writers at once — Coffer's own JSON, the format the daemon itself wrote before [daemon](../daemon/spec.md) "Write one bounded daemon log in one format" was met, uvicorn and rich — with a colour-escaped line among them and a traceback written under the record that raised it
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

### Requirement: Query only the visible Activity tab and isolate failures
Only the visible tab queries. A record whose route fails MUST render its error
inside its own tab, leaving the other two working — one failing lane must not
take the other two down with it — and there MUST be no manual refresh control:
switching tab or changing a filter is what refetches.

#### Scenario: a failing record shows its error inside its own tab
- **GIVEN** one of the three routes is unavailable (an older daemon that does not serve it)
- **WHEN** the user opens `/activity`
- **THEN** the failing record's tab renders a readable error
- **AND** the other two tabs still render their rows

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

### Requirement: Redirect the legacy Activity paths
The legacy `/audit` and `/observability` paths MUST redirect to `/activity`
rather than resolving to a "page not found" view.

#### Scenario: legacy /audit redirects to activity
- **GIVEN** a user follows an old bookmark to `/audit`
- **WHEN** the route resolves
- **THEN** the app redirects to `/activity` and no "page not found" view is shown

### Requirement: Organise Settings into five tabs
Settings MUST carry exactly five tabs, in this order, grouped by what they
manage rather than by how Coffer is built — **General** (display preferences, when the daemon runs, and — while the
registry names any experimental feature — which of them are switched on),
**Coffer's model** (at `/settings/engine` — Coffer's own machinery: the internal
LLM connection and model its own passes run on, the speech-to-text connection
and model voice messages are transcribed on, and the switch and interval of each
of those passes), **Data** (retention policy and manual prune), **Security**
(where the master encryption key lives — beside the database, or in the OS
keychain), and **About** (version, license, source, and in the desktop app the
update check of "Check for and install updates on Settings › About") — and MUST
open on General.
Clicking a tab swaps the right pane without a full page reload.

#### Scenario: settings layout uses the redesigned tabbed sidebar
- **GIVEN** the user navigates to `/settings`
- **WHEN** the page resolves
- **THEN** it lands on the General tab
- **AND** the settings sidebar shows General, Coffer's model, Data, Security, and About — exactly those five, in that order — with the current route highlighted
- **AND** clicking a tab swaps the right pane content without a full page reload

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

### Requirement: Leave daemon controls to the CLI
No tab may expose a "Shutdown daemon" or "Rotate token" control — both belong on
the CLI: shutting the daemon down from the web kills the very page you are on
and recovery needs a terminal anyway, and token rotation is a security action a
single-user local app needs maybe once ever, which `coffer daemon rotate-token`
covers. The About tab MUST show version, license, source and the update check
of "Check for and install updates on Settings › About" only, with no
language picker (the sidebar already switches language) and no
installed-resource-kind list (developer detail). Remaining jargon is rewritten
in plain language (e.g. "prune" is phrased as clearing expired data).

#### Scenario: settings drops the confusing controls
- **GIVEN** the user opens the Settings tabs
- **WHEN** each tab is fully rendered
- **THEN** no tab exposes a "Shutdown daemon" control or a "Rotate token" control
- **AND** there is no "Daemon" tab and no read-only daemon-status panel
- **AND** the About tab shows version / license / source and the update check only — no language picker, no resource-kind list

### Requirement: Switch language from the sidebar
The sidebar MUST offer the English / 简体中文 switch from every screen: in the
version menu its footer opens (see "Show the daemon's state in the shell
footer"), each locale named in its own language, and in Settings › General.
Every sidebar label, page title and form label MUST switch on the very next
render, with no full page reload, and the choice MUST persist in `localStorage`
under `coffer.language`.

#### Scenario: language switcher round-trips correctly
- **GIVEN** the UI is in English
- **WHEN** the user opens the version menu from the sidebar footer and selects 简体中文
- **THEN** all sidebar labels, page titles, and form labels switch to Chinese without a full page reload, on the very next render
- **AND** the preference persists across reloads (localStorage `coffer.language`)

### Requirement: Let the user choose when the daemon runs
The General tab MUST carry a card for when Coffer's daemon runs, with one control: a **Start at
login** switch. It MUST read and write it through
[daemon](../daemon/spec.md) "Change residency from the settings page or the command line".
A clicked switch MUST move to the clicked value at once and then settle on what the daemon reports:
the switch is disabled until the daemon has first answered, a successful write shows the value the
daemon answers with, the switch is shown unavailable rather than off on a host with no login
service, and a failed write MUST put the switch back to what the daemon last reported and show the
error beside it. The card MUST NOT offer an idle window or a stand-down choice, because the daemon
never stands down on its own.

#### Scenario: the general tab sets when the daemon runs
- **GIVEN** the daemon reports a login service that is supported and not installed
- **WHEN** the user turns on Start at login
- **THEN** one request is sent carrying `login_service_installed: true` and no idle window
- **AND** the card offers no idle-window or stand-down control
- **AND** when the request fails, the switch goes back to off and the error is shown beside it

### Requirement: Read each Activity tab from its record owner's route
The Activity page MUST add no route of its own: each tab reads the read-only
route belonging to whichever capability owns that record (see Purpose) — the
Changes tab `GET /api/v1/audit`, the MCP calls tab `GET /api/v1/mcp/invocations`
and the Daemon tab `GET /api/v1/daemon/logs`. An agent or a script that asks
"what happened" reads the same three records from the command line (see "Keep
the command-line record readers").

#### Scenario: each activity tab reads its owner's route
- **GIVEN** a running daemon that has recorded an audit entry, an MCP invocation and a daemon log record
- **WHEN** the user opens each of the three Activity tabs in turn
- **THEN** the Changes tab requests only `GET /api/v1/audit`, the MCP calls tab only `GET /api/v1/mcp/invocations`, and the Daemon tab only `GET /api/v1/daemon/logs`
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
agent's badge beside its label, in the order of the Agents page, so the reader
sees who has it without opening the panel; the label and the panel's choices are
unchanged. The panel MUST show each agent of the pick-list by its badge and name.

#### Scenario: a reach narrowed to chosen agents shows their badges
- **GIVEN** a resource whose reach names one Claude Code agent
- **WHEN** its reach button renders
- **THEN** it reads the chosen reach's label with the Claude Code badge beside it
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
last lines it printed on stderr. Values typed into Secret rows are sent for
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
The Skills page MUST follow canvas 4.3: a compact header (title, count, help) over the library beside a reading pane. A library row MUST show, in place of its description, the one thing that needs the reader; rows ticked for bulk actions MUST show the selection both as a bar under the filter and in the reading pane (which skills, Set reach…, Delete N skills…). The open skill's Files tab MUST be one card — the folder's files with SKILL.md first beside the open file's header bar and body — whose edit mode refuses a stale save while keeping the text. The Requires tab MUST link each command to the CLIs page, and offer the same hand-off to an agent its CLI page does for a command that needs the user. A folder in the way of an agent's link, a delete Coffer refuses, a master folder that is gone and a Git source to change MUST each be answered where they are shown, with the choice confirmed before anything is written. The Add skill dialog MUST carry the Available to reach control.

#### Scenario: a library row says what needs attention in place of its description
- **GIVEN** a skill whose declared command is missing and a Git skill with an update waiting
- **WHEN** the user opens the Skills page
- **THEN** the first row reads "Needs <command> · not installed" and the second "Update available" where their descriptions would be

#### Scenario: selected skills are set or deleted together from the reading pane
- **GIVEN** the built-in skill and two of the user's skills
- **WHEN** the user ticks the two skills
- **THEN** the reading pane names both, says the built-in skill can't be selected, and Delete 2 skills… deletes both after one confirmation

#### Scenario: a skill file changed on disk refuses the save and keeps the text
- **GIVEN** a skill file open for editing
- **WHEN** the save is refused because the file changed on disk
- **THEN** the header says Not saved, the edited text is still there, Reload, Compare and Copy my text are offered, and Save stays off

#### Scenario: the requires tab links to the CLIs page and hands a command to an agent
- **GIVEN** a skill whose declared commands are missing or not logged in
- **WHEN** the user opens its Requires tab
- **THEN** each command shows its state, Open in CLIs, and Copy prompt / Ask an agent, and the tab offers no install, copy-command or login step of its own

#### Scenario: a folder in the way of a skill's link is resolved by a confirmed choice
- **GIVEN** a skill whose link in one agent is a real folder Coffer did not make
- **WHEN** the user opens Review… from the skill's banner and chooses Adopt this folder
- **THEN** the dialog shows the difference first, and only the confirm button resolves that agent's copy by keeping its version

#### Scenario: a delete refused because a copy is not Coffer's stays open and says why
- **GIVEN** a skill whose delete the daemon refuses because an agent's copy is not Coffer's link
- **WHEN** the user confirms the delete
- **THEN** the dialog stays open, names the folder, says Coffer won't remove it, and offers Try again

#### Scenario: a skill whose master folder is gone offers the ways forward
- **GIVEN** a skill whose master folder was removed outside Coffer
- **WHEN** the user opens it
- **THEN** a banner says the master folder is gone, and the Files tab offers Restore it from History (not available while a skill's versions are not recorded) and Remove the skill, which opens the delete confirmation

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
and offers **Back to Overview** and **Search Coffer**, which opens the command
palette over the page.

#### Scenario: an unknown address suggests the closest page
- **GIVEN** the user opens `/mcp/sentri`
- **WHEN** the route resolves
- **THEN** the page says nothing lives at `/mcp/sentri`, suggests `/mcp-servers`, and offers Back to Overview and Search Coffer
- **AND** Search Coffer opens the command palette

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
- **THEN** Needs you shows a row on Claude Code with the reason and since when, its one action reads Repair hook and opens Claude Code's Hooks tab, its name opens Claude Code's page, and the row has no menu

### Requirement: Let the user ignore an unconnected agent on Overview
An agent that Overview lists only because it is not connected to Coffer — an informational item of
the attention list — MUST carry a ⋯ menu with **Ignore** beside its Connect action. The daemon MUST
remember an ignored item on this machine, by the item's stable key (its kind, resource and reason),
and audit each ignore and each stop: `GET /api/v1/attention` then lists it under `ignored`, out of
`items` and `counts_by_kind`, so Needs you, the Agents health tile, the sidebar's badges and the
menu bar's count all leave it out alike. Overview MUST count the ignored items under the list as
**N ignored · Show**; Show lists them again, muted, each with **Stop ignoring** in its menu.
Ignoring changes nothing about the agent. Only an informational item can be ignored; asking to
ignore anything else is refused with `ATTENTION_NOT_IGNORABLE`, because something broken stays
until it is fixed.

#### Scenario: an ignored agent leaves needs you and is counted under it
- **GIVEN** Overview listing Codex as not connected and an MCP server that fails
- **WHEN** the user chooses Ignore in Codex's menu, then Show, then Stop ignoring on Codex
- **THEN** Codex leaves the list while the server stays and "1 ignored · Show" appears under it; Show lists Codex again under the list; after Stop ignoring Codex is back in Needs you and nothing is counted as ignored
- **AND** while Codex is ignored the daemon's attention list carries it only under `ignored`, its counts leave it out, both changes are audited, and ignoring the failing server is refused

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
installed. Overview's first run with no agent found MUST offer that prompt through **Copy
prompt** only: there is no agent of Coffer's to ask, and the page MUST carry no install link of
its own.

#### Scenario: with no agent found the install prompt is built by the daemon
- **GIVEN** neither supported agent's program is installed on this machine
- **WHEN** the types are read, and read again after one is installed
- **THEN** the first answer carries an install prompt naming both agents and their settings
  folders, no installer, and the standing rules every hand-off ends with
- **AND** the second carries none

#### Scenario: with no agent found overview offers the install prompt to copy
- **GIVEN** a first run on a machine where no supported agent is found
- **WHEN** Overview renders
- **THEN** beside Scan again it offers Copy prompt with the daemon's install prompt
- **AND** it offers no Ask an agent and no install link

### Requirement: Hand an agent's missing program to an agent on the agent pages
Wherever the web UI shows an agent type whose program is not found — its Agents list row and
the notice under a config-left-behind row, its detail page while it is not added, and the
Overview tab's problem states (config left behind, not found) — it MUST offer the daemon's
`install_handoff` prompt for that type (agent-registry "Hand installing an agent's program to an
agent") through **Copy prompt**, and through **Ask an agent** only while another managed agent
is available to run the conversation: the missing agent itself cannot. A list row, which has
room for one action, MUST make Copy prompt its action and put Ask an agent in its ⋯ menu. None
of these surfaces MUST show an install command or tell the person to restart Coffer. The
Plugins tab of a Claude Code agent whose program is not found, where Uninstall cannot run, MUST
say so and offer the same prompt. The Connect review MUST offer the hand-off a `SHIM_NOT_FOUND`
refusal carries beside Retry (agent-registry "Install Coffer's MCP server into an agent in one
action").

#### Scenario: an agent whose program is not found offers its install prompt
- **GIVEN** Codex not installed and no managed agent available
- **WHEN** the user chooses Copy prompt on the Codex row, then opens the row's ⋯ menu
- **THEN** the daemon's prompt is copied as given, no install command is shown anywhere
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
"install it, then refresh" instruction.

#### Scenario: a missing launcher offers the hand-off, not an install command
- **GIVEN** an MCP server whose status names a missing launcher and carries a `handoff`
- **WHEN** its page opens
- **THEN** the launcher callout names the launcher and offers Copy prompt, which copies the served prompt, and shows no `brew install` line

#### Scenario: a failed test offers a diagnosis hand-off beside View log
- **GIVEN** an MCP server whose test just failed with an error and a `handoff`
- **WHEN** the result is shown
- **THEN** the result callout shows the error with View log and Copy prompt beside it, and the header still offers Test

### Requirement: Offer the hand-off a knowledge refusal carries beside it
When the daemon refuses a knowledge operation with a hand-off in the error's details
(`details.handoff.prompt`), the Knowledge page MUST offer that prompt (Copy prompt, and Ask an
agent when a managed agent is available) where it shows the refusal, passing the prompt on as
served and never assembling it: a refused **Undo this pass** offers the prompt for undoing the
pass by hand in the note that names the document edited since, which still points at the
per-document History restore; and a History tab or Recent changes that cannot be read because
git is not installed offers the prompt for installing it beside Retry. The page MUST NOT show an
install command.

#### Scenario: a refused pass undo offers the prompt for undoing it by hand
- **GIVEN** a curation pass whose undo the daemon refuses because a document it wrote was edited since, with a hand-off in the refusal
- **WHEN** the user undoes the pass from its page
- **THEN** the note that names the document still points at restoring a single document from its History, and offers Copy prompt, which copies the served prompt

#### Scenario: a history that needs git offers the prompt for installing it
- **GIVEN** a machine with no git, whose history reads are refused with the install hand-off
- **WHEN** a document's History tab opens
- **THEN** it says the history could not be read, with Retry and Copy prompt, which copies the served prompt, and names no install command

#### Scenario: recent changes that need git offer the prompt for installing it
- **GIVEN** a machine with no git, whose history reads are refused with the install hand-off
- **WHEN** Recent changes opens
- **THEN** it offers Retry and Copy prompt, which copies the served prompt
