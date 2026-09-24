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
[Everything Is a Resource Kind](../../../docs/decisions/everything-is-a-resource-kind.md)
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
server, the zerolog of a cloudflared child, a tail written before the daemon's
own format was fixed — are normalised onto the same fields on the daemon's side
of the wire, escape sequences stripped, a traceback riding with the record that
raised it, and a line no format fits kept whole rather than dropped. The page
renders what it is given and must not invent: a row shows a dash where its line
stated no time, no level or no logger, and each record is one row.
Correlating the three records for an agent is `coffer__diagnose`'s job, not this
page's: the page deliberately never joins them — a single merged timeline could
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
MUST be left out — Knowledge for `knowledge`, Memory for `memory`, Sync for
`vault_sync` — and MUST appear on the next render after the feature is switched
on:

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
- **AND** every experimental feature is switched on
- **AND** `coffer daemon start` is running (so daemon.json exists in user HOME)
- **WHEN** they navigate to `http://localhost:5173/` in a real browser
- **THEN** the index redirects to `/agents` and the page renders the sidebar + main content area within 2 seconds
- **AND** the main content shows the Agents welcome view (no generic error card)
- **AND** the sidebar lists exactly Coffer's operational surfaces — Agents, Chat; MCP servers, Skills, Knowledge, Memory, Model providers, Channels; Activity, Sync, Settings — grouped under "Agents", "Resources", and "System" headings, with no other entry

#### Scenario: a switched-off feature leaves the sidebar
- **GIVEN** `knowledge` and `vault_sync` switched off
- **WHEN** the app shell is rendered
- **THEN** the sidebar lists Agents, Chat; MCP servers, Skills, Memory, Model providers, Channels; Activity, Settings — with no Knowledge and no Sync entry

### Requirement: Hold one Resources entry per listed resource kind
RESOURCES MUST hold exactly one entry per resource kind that has a list UI —
today six kinds (`mcp_server`, `skill`, `knowledge`, `memory`, `provider`,
`channel`), six entries. That correspondence is the rule: **Model providers**
is filed under Resources rather than Settings, because a `provider` is
`{protocol, base_url, credential_ref}`, a vendor endpoint and its key, and the
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
scope — knowledge, memory — MUST head the same column **Status** instead, and its
button MUST read "Enabled" or "Disabled", because enabled or disabled is the
whole of what it reports; see "Offer reach as one choice in a panel".

#### Scenario: the reach button states the reach it holds
- **GIVEN** resources that reach every agent, two agents, nobody selected, and one that is disabled
- **WHEN** each one's reach button renders
- **THEN** they read "Every agent", "2 agents", "No agent selected" and "Disabled"
- **AND** each is one button rather than a row of segments

### Requirement: Offer reach as one choice in a panel
The button MUST open a panel where "who does this reach?" is a single choice
between Disabled, Every agent and Only selected agents, the last over the
scope's list of agents. A kind that declares no scope gets the same button over
a two-choice Disabled / Enabled panel.

#### Scenario: the reach panel offers the reach states as one choice
- **GIVEN** a resource of a scoped kind and one of a kind that declares no scope
- **WHEN** each one's reach panel is opened
- **THEN** the scoped one offers Disabled, Every agent and Only selected agents with its current state chosen
- **AND** the unscoped one offers only Disabled and Enabled, with no agent list

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
question. A kind that declares no scope MUST head its filter **Status**, like its
column, and offer only Disabled and Enabled.

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
The Tools, Resources and Prompts tabs MUST be uniform — each carrying the same
search box, status filter and per-row enable toggle — and MUST keep that chrome
even when the upstream exposes none of that kind, rendering the empty state
inside the table rather than as a bare card. The server list likewise carries a
search box, a reach filter and a client-side pager so a large vault stays
navigable; the skills list works the same way.

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
at once, with a review step where the user confirms which `env` values are
secrets. Secrets MUST be lifted into the encrypted credential store with only
their refs kept in the resource config, and the server MUST be registered
before its secrets are written, so a failed registration leaves no orphan
credential entry.

#### Scenario: MCP server registration round-trip via JSON import
- **GIVEN** the user opens the "Add MCP server" dialog from the resources list
- **WHEN** they paste the standard `mcpServers` JSON and confirm the review step
- **THEN** the app posts each server to `/api/v1/resources`, then writes any secret env values to `/api/v1/credentials` (register-first ordering avoids orphan credential entries when registration fails)
- **AND** on success the dialog closes and (for a single server) the app navigates to the server's detail page `/mcp-servers/<uid>` showing the Overview tab
- **AND** the new server appears on the resources list with health "unknown" then "healthy" within 10 seconds

#### Scenario: add-server form navigates to detail then back to list shows card
- **GIVEN** the user completes the JSON-import dialog for a new MCP server
- **WHEN** they are taken to the server's detail page and then navigate back to `/mcp-servers`
- **THEN** the server card appears in the resources list

### Requirement: Reject malformed server JSON in the dialog
A payload that is not valid JSON, or a valid JSON document that does not match
the `mcpServers` shape, MUST keep the dialog open with a readable error — the
parse location, or the failing field — and MUST NOT send a request.

#### Scenario: JSON import shows readable error for malformed JSON
- **GIVEN** the user opens the "Add MCP server" dialog
- **WHEN** they paste a payload that is not valid JSON (or a valid JSON document that does not match the `mcpServers` shape) and submit
- **THEN** the dialog stays open and renders a readable error explaining what is wrong (parse error location for malformed JSON, or the failing field for shape-mismatch)
- **AND** no request is sent to `/api/v1/resources` or `/api/v1/credentials`
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

### Requirement: Read each Activity record from its owner's route
The Activity page MUST add no route of its own: each tab reads the read-only
route belonging to whichever capability owns that record (see Purpose). An agent
that asks "what happened" gets the audit entries and the log records already
joined, newest first and with no secret values, from the built-in
`coffer__diagnose` tool under the reserved `coffer__` prefix
([mcp-gateway](../mcp-gateway/spec.md)); this capability assumes that tool and
specifies nothing about it.

#### Scenario: an agent reads recent changes and failures in one call
- **GIVEN** Coffer has recorded audit entries and written daemon log records
- **WHEN** an agent calls `coffer__diagnose`
- **THEN** it receives both timelines in one response, newest first — the audit
  entries as `changes` and the log records as `log` — with no secret values in
  either

### Requirement: Keep the command-line record readers
Bringing the three records onto one page MUST NOT change or withdraw the
command-line readers — `coffer audit list` and `coffer mcp invocations <server>` keep working
as they are, and scripts keep `GET /api/v1/audit`, so a script that read a
record before this page existed still does.

#### Scenario: the command-line readers still read the records
- **GIVEN** a running daemon that has recorded an audit entry and an MCP invocation
- **WHEN** a script runs `coffer audit list` and `coffer mcp invocations <server>`
- **THEN** each exits successfully and prints that record's entry

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
manage rather than by how Coffer is built — **General** (display preferences, when the daemon runs, and which
experimental features are switched on),
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
covers. The About tab MUST show version, license and source only, with no
language picker (the sidebar already switches language) and no
installed-resource-kind list (developer detail). Remaining jargon is rewritten
in plain language (e.g. "prune" is phrased as clearing expired data).

#### Scenario: settings drops the confusing controls
- **GIVEN** the user opens the Settings tabs
- **WHEN** each tab is fully rendered
- **THEN** no tab exposes a "Shutdown daemon" control or a "Rotate token" control
- **AND** there is no "Daemon" tab and no read-only daemon-status panel
- **AND** the About tab shows version / license / source only — no language picker, no resource-kind list

### Requirement: Switch language from the sidebar
The sidebar MUST carry the English / 中文 switcher, so it is reachable from every
screen. Every sidebar label, page title and form label MUST switch on the very
next render, with no full page reload, and the choice MUST persist in
`localStorage` under `coffer.language`.

#### Scenario: language switcher round-trips correctly
- **GIVEN** the UI is in English
- **WHEN** the user selects 中文 in the sidebar language switcher
- **THEN** all sidebar labels, page titles, and form labels switch to Chinese without a full page reload, on the very next render
- **AND** the preference persists across reloads (localStorage `coffer.language`)

### Requirement: Let the user choose when the daemon runs
The General tab MUST carry a card for when Coffer's daemon runs, with two
controls: a **Start at login** switch and a **Stand down after** choice of idle
window that offers a set of hour values and **Never** as its own option, never
as a number. It MUST read and write both through
[daemon](../daemon/spec.md) "Change residency from the settings page or the command line",
and every change MUST send both halves in one request. A clicked control MUST
move to the clicked value at once and then settle on what the daemon reports:
the controls are disabled until the daemon has first answered, a successful
write shows the values the daemon answers with, a window set from the command
line that the list does not offer is still shown, the switch is shown
unavailable rather than off on a host with no login service, and a failed write
MUST put the controls back to what the daemon last reported and show the error
beside them.

#### Scenario: the general tab sets when the daemon runs
- **GIVEN** the daemon reports a login service that is supported and not installed, and an idle window of 12 hours
- **WHEN** the user turns on Start at login, and then picks Never as the idle window
- **THEN** each change sends one request carrying both halves — first `login_service_installed: true` with `idle_shutdown_hours: 12`, then `login_service_installed: true` with `idle_shutdown_hours: null`
- **AND** the idle window offers 1, 4, 12, 24 and 72 hours and Never
- **AND** when the second request fails, the idle window goes back to 12 hours and the error is shown beside it
