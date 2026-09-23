# Feature Specification: Web UI

**Status**: Accepted
**Input**: The mcp-gateway UI shipped as a functional skeleton: bare tailwind defaults, ad-hoc spacing, no first-run onboarding. This spec turns the skeleton into a real product shell — a coherent visual language, an information architecture built on a single unifying concept (every managed entity is a _resource kind_), and the end-to-end flows that make the gateway usable for a first-time visitor (not just for Playwright fixtures that bypass auth).

**Scope note**: **This spec owns the web UI** — the information architecture, the visual language, the list and detail conventions every surface shares, and internationalisation. It adds no REST route and no backend of its own, so it has no `contracts/` directory and no separate `tasks.md` tracker. Every screen renders over routes and entities other specs own, and those are named where they are used: no single spec owns all of them. See [`plan.md`](plan.md) and [`quickstart.md`](quickstart.md) for the companion docs.

## Information Architecture

The sidebar is grouped **by role**, not on a single axis. Two concepts sit
side by side: **agents** are the _consumers_ (the agents you use, and the chat
you hold with one), and **resources** are the _assets_ those agents draw on —
named, configured, lifecycle-managed entities behind a kind-agnostic framework.
Each scoped kind gets its own list surface, so the navigation and each list page
carry no kind-specific branches. Agents are NOT a resource kind, so they live in
their own group, not under Resources.

**The sidebar shows only what Coffer can do today.** It does not list dead "not yet implemented" placeholders: a sidebar full of "soon" entries reads as an unfinished scaffold, not a product.

Today the sidebar's shipped surfaces are:

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

That listing is exhaustive: eleven entries in three groups, and no twelfth.

**RESOURCES holds one entry per resource kind that has a list UI, and that
correspondence is the rule** — six kinds (`mcp_server`, `skill`, `knowledge`,
`memory`, `provider`, `channel`), six entries. Two had drifted out of it and were
returned in 2026-09: **Model providers** was the only kind filed under Settings
(as "LLM connections"), and its old name described a page rather than the thing
it manages — a `provider` is `{protocol, base_url, credential_ref}`, a vendor
endpoint and its key; the model is not stored there and is chosen at the point
of use. **Channels** sat under AGENTS, but a channel is a credentialed
transport the vault owns, not a consumer of the vault; it belongs beside the
other assets rather than beside the agents that happen to answer on it. It is
named **「消息渠道 / Channels」** and nothing else — sidebar, page header,
welcome panel and dialogs all say the same words, because a surface the user
reaches two ways must not have two names.

AGENTS holds two entries, and Agents comes first: the agents are the subject,
and a chat is one thing you do with one of them. The group stays its own even
though it is the smallest — agents are the one thing in the product that *uses*
the vault rather than living in it, and collapsing the group would lose that
distinction to save two lines.

The app's index (`/`) redirects to `/agents`, so a first-time visitor lands on
the Agents surface. It is grouped into **Agents** (the consumers and the chat with one), **Resources** (the resource kinds), and **System** (cross-cutting tooling: Activity, Sync and Settings) so the navigation stays stable as Coffer grows. Agents live at `/agents` (list) and `/agents/:name` (detail) and do not appear in the `/mcp-servers` kind browser. (`/resources` and `/mcp-servers/mcp_server/:name` are kept as legacy redirects for old bookmarks.) The agent detail page's own tabs belong to spec agent-registry (FR-TBD — see `## Assumptions`), which owns what they show; this spec owns only that they are tabs on a detail page laid out like every other.

All list surfaces (agents, MCP servers, skills, knowledge, memory, model providers, channels, each Activity tab, each Sync tab) use one shared, searchable, filterable, paginated table: a row click opens that item's detail page, and row actions are an icon plus its label — never a bare icon, which reads as a different affordance from the labelled action beside it. Cards are reserved for welcome / empty states only.

Every list surface carries a **reach** column — named for what it holds, not for the on/off flag it replaced: one button, labelled with the answer it already holds — "Every agent", "2 agents", "Disabled", or "No agent selected" for a scope narrowed to nobody — which opens a panel where "who does this reach?" is a single choice between Disabled, Every agent and Only selected agents, the last over the scope's list of agents. Every detail page carries the same button in its header. The button states the reach so the reader learns it by reading, rather than by comparing which of three side-by-side segments looks pressed; a kind that declares no scope gets the same button over a two-choice Disabled / Enabled panel. The panel stages its agent list and writes exactly once, when it closes — the two whole-value choices close it themselves — so a panel that is opened and dismissed writes nothing, and no write can refetch the list and move the row the panel is anchored to. It is written once and mounted in three places (the row, the detail header, the selection bar), so the three can never drift into three different answers to one question. A multi-select applies that same choice to the whole selection: a bulk write is a new intent, so its button reads "Set reach…" and its panel opens with nothing chosen rather than on any one row's value, and a row that fails is reported in the batch's one summary rather than silently skipped. Delete stays its own button beside it.

**Observability** (system health / metrics) is planned but not shown today; it appears in the sidebar only once it ships. Activity is not it: a record of what happened is not a measurement of how the system is doing. The reverse rule holds too — an entry is removed when its feature is, and returns with it: **Machines** left the sidebar as a top-level fleet view and came back as a tab under Sync, where a machine is one participant in convergence rather than a surface of its own.

The sidebar collapses to an icon-only rail and back; the choice persists across sessions (localStorage).

See [Everything Is a Resource Kind](../../../docs/decisions/everything-is-a-resource-kind.md) (Amended 2026-05-30) for the architectural decision behind this role-based information architecture (agents as a separate consumer axis; rejected alternative: a separate "surface" concept; sidebar policy: no "soon" placeholders).

## User Scenarios & Testing

### User Story 1 — A first-time visitor lands in a usable app (Priority: P1)

A developer opens the web UI for the first time. They have never registered a server. The page renders content immediately — no broken "unexpected error" cards from a missing token, no empty page with no next action. The dev sees a welcome view that explains what Coffer is and offers one obvious next step: "Add your first MCP server."

**Why this priority**: This is the gate to every other flow. If the first screen looks broken or is silent on what to do next, the user closes the tab and the rest of the product doesn't matter.

**Independent Test**: Clear `localStorage`, open `http://localhost:5173/` after `make dev`. The page authenticates automatically via the dev-only token-injection plugin (`frontend/vite.config.ts`); the index redirects to `/agents` and the user sees the Agents welcome card with a primary "Add agent" button. The "Add MCP server" welcome lives one click away on `/mcp-servers`.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- cold-start renders authenticated content
- token-missing renders an actionable empty state (not generic error)
- empty resources list renders a welcome view

---

### User Story 2 — Day-to-day MCP work feels polished, not bare (Priority: P1)

A developer who already uses Coffer for MCP gateway aggregation wants the routine flows — registering a server, watching its health, browsing tools, toggling capabilities — to look and feel like a real product, not a scaffold. Headings are typographically distinct; spacing is consistent; per-server pages have a primary "what is this server doing?" view before the per-tool toggles; empty / error / loading states are first-class. The Tools, Resources, and Prompts tabs are uniform — each carries the same search box, status filter, and per-row enable toggle, and keeps that chrome even when the upstream exposes none of that kind (the empty state renders inside the table, not as a bare card). The server list carries a search box, a status filter, and a client-side pager so a large vault stays navigable. Its reach column is not an on/off switch: a server's reach is three-valued — Disabled, Every agent, Only selected agents — so the list carries the same one button the detail header does, stating that server's current reach and settable in place, and its filter offers those same states rather than a bare enabled/disabled. The column, its filter and the button all say *reach*, because they are all asking the one question. The skills list works the same way, for the same reason.

The **Invocations** tab lists every call the gateway proxied for this server,
newest first, filterable by status and time range, each row expanding to that
call's raw JSON record. It was removed once, on the argument that the traffic
is not the user's — every row is an agent calling a tool, so a person who wants
to know why a call failed asks that agent. That holds right up until the agent
is the thing that is broken, and then this table is the only account of what it
did. The tab reads the record the gateway always wrote; it is the same table
Activity's **MCP calls** tab renders (User Story 3), scoped to one server
instead of all of them, rather than a second table that would have to be kept
in step with the first.

"Add MCP server" is a modal where the user pastes the standard `mcpServers` JSON (one or many servers at once) — the same block every MCP server's README provides. A review step lets them confirm which `env` values are secrets; those are lifted into the encrypted credential store (only their refs kept in the config) rather than stored as plaintext in the config.

**Why this priority**: The MCP Gateway spec delivered the backend correctness but the UI shipped as bare tailwind defaults. The user-visible bar for "the MCP gateway is done" is the UI passing a real user (not a Playwright fixture).

**Independent Test**: Walk the MCP flows end-to-end in a real browser: open `/mcp-servers` (welcome or list), click "Add MCP server", fill the form, submit, land on the detail page, switch through the Overview / Tools / Resources / Prompts tabs, toggle a tool, return to the list, switch language between English and 中文. Every step shows polished content; no view dead-ends in a generic error.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- MCP server registration round-trip via JSON import
- capability toggle uses the redesigned tab layout
- language switcher round-trips correctly

---

### User Story 3 — Three records, one page, one table each (Priority: P2)

Coffer keeps three accounts of what happened: the **audit log** (what changed
in the vault, and who changed it), the **MCP invocation log** (every call the
gateway proxied), and the **daemon log** (what Coffer itself did, including
what broke). The audit log's page was removed because nobody browses "what
changed in my vault"; the invocation tab was removed because every row in it
belongs to an agent. Both were right about their own surface and wrong about
the need behind it: when something is misbehaving the question is never "what
changed" or "what was called" or "what errored" — it is *what happened*, and
answering it meant holding three records and joining them by hand.

So the three get one home. **Activity** (under System, at `/activity`) is one
page carrying one tab per record — **Changes**, **MCP calls**, **Daemon** —
each a newest-first table of its own, with the columns that record actually
has: an activity line and its actor; a call's server, capability, duration and
outcome; a log record's level, logger and message. Every tab filters by free
text and time range plus the one filter its record affords (actor, call
status, errors only), and any row expands to its raw underlying record,
pretty-printed in a monospace, scrollable block.

They were briefly merged into a single timeline, which is what made the
column problem visible: one table can only carry the three records' lowest
common denominator, so a "detail" column meant the actor, the server and the
logger by turns, and a call's duration and a record's level had nowhere to
live. Correlating across the three stays `coffer__diagnose`'s job — it returns
them already joined, for the reader who asked "what happened" rather than
"show me all of X".

Only the visible tab queries. A record whose route fails renders its error
inside its own tab: one failing lane must not take the other two down with
it. There is no manual refresh control — switching tab or changing a filter
changes the query and refetches.

The page is a consumer of three routes it does not own, and they have three
different owners: `GET /api/v1/audit` is the resource framework's record,
written for every kind; `GET /api/v1/mcp/invocations` (cross-server, each row
naming its server) is spec mcp-gateway's; and `GET /api/v1/daemon/logs` is spec
daemon's. This spec adds no route of its own — which is not the same claim as
every route in the product belonging to whichever spec's UI came first. What
the page needs of the three, and does not itself provide, is recorded under
`## Assumptions`.

`coffer audit` and `coffer mcp invocations` stay as they are — a script that
read the log before this page existed still does.

**The daemon log has one writer whose format the page can rely on, and several
it cannot.** What *Coffer* writes is one format — one JSON object per line
carrying the time, the level, the logger and the message, for every record
inside the daemon process, its own modules and the libraries' alike (spec
daemon FR-022). That is what fills the Daemon tab's four columns. What the
*other processes* sharing the file write is theirs to decide, because
`daemon.log` is also where a detached daemon's output is redirected: uvicorn's
default, rich's output from an upstream MCP server, the zerolog of the
cloudflared child a tunnel respawns — some of it colour-escaped, because a
child process writing to a pipe is not always convinced it is not a terminal.
A tail written before the daemon's own format was fixed holds a fourth shape
as well, so reading one still has to cope with it.

So every writer's format is normalised onto the same fields before it reaches
the page, escape sequences are stripped, and a traceback rides with the record
that raised it instead of becoming a run of rows with nothing in them. A line
no format fits is still kept whole rather than dropped — it is often the
interesting one. What the page must *not* do is invent: a row shows a dash
where its line stated no time, no level or no logger, rather than a plausible
value, and each record is one row — a log line the daemon wrote twice would
otherwise read as two things happening.

Event types are rendered as plain-language activity lines again ("Enabled
demo-fs"), so their translations return in both locales, guarded the way error
codes are: a new event type without a string fails CI rather than showing a zh
reader a raw `resource_enabled`.

**Why this priority**: P2 — one surface over three records that already exist;
nothing new is captured.

**Independent Test**: open `/activity` — three tabs render, each showing its
own record in its own columns; expanding a row shows its raw record; a tab
whose route is unavailable shows that inside itself while the others still
work; the legacy `/audit` URL redirects here.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- activity gives each record its own tab
- the daemon tab reads every writer in the log
- activity row expands to its raw record
- a failing record shows its error inside its own tab
- legacy /audit redirects to activity
- an agent reads recent changes and failures in one call

---

### User Story 4 — Settings is organised around the user, not the daemon (Priority: P2)

A developer opens Settings and finds tabs grouped by what they manage, not by how Coffer is built: **General** (display preferences — the default rows-per-page for list tables, and the preferred external editor for opening managed files), **Coffer's model** (at `/settings/engine` — Coffer's own machinery: the internal LLM connection and model its own passes run on, and the switch and interval of each of those passes), **Data** (retention policy and manual prune), **Security** (where the master encryption key lives — beside the database, or in the OS keychain), and **About** (version, license, source). Settings opens on the General tab.

Coffer's model and Security are here because both configure Coffer ITSELF rather than anything served to an agent, and because both do something on a timer or at every start that the user should be able to see and change: a pass that rewrites their own files, and a key whose location decides what the OS asks for on every daemon launch. Neither is a daemon-status readout. The daemon remains an implementation detail — there is no "Daemon" tab and no read-only daemon-status panel, and a user never needs to know Coffer runs a background daemon.

The **General** tab MUST expose the default page-size preference (the rows-per-page every list table seeds from), persisted in `localStorage`. It MUST also expose a **preferred external editor** preference — the application Coffer uses when the user opens a managed file (or its containing folder) from a read-only file viewer. The default is the operating system's default application; the user MAY override it by **picking an editor the daemon detected as installed** (enumerated via `GET /api/v1/fs/editors`, spec daemon FR-TBD — see `## Assumptions`; a browser can't list installed apps) or by entering a custom application / launch command. Like the other display preferences the chosen value is persisted in `localStorage` and never sent to the daemon (except transiently as the target when opening a file).

**Why this priority**: P2 — the underlying controls already function; this story is reorganisation and subtraction, not new capability. An unorganised Settings page is exactly the "feels like a scaffold" signal US2 fights, and the user flagged it as confusing.

Removed — none of these is something a user needs to operate or see:

- **Shutdown daemon** — clicking it from the web kills the very page you are on, and recovery needs a terminal anyway; daemon shutdown belongs on the CLI.
- **Token rotation** — a security action a single-user local app needs maybe once ever; `coffer daemon rotate-token` covers it on the CLI.
- **The read-only daemon-status panel** (status / version / port) — an implementation detail; a healthy daemon needs no UI, and the failure case is owned by the offline banner.
- **The duplicate language selector and the "Installed resource kinds" dump** — the sidebar already switches language, and the kind list is developer detail.

Remaining jargon is rewritten in plain language (e.g. "prune" is phrased as clearing expired data).

**Independent Test**: open `/settings` — it lands on General. The tab list reads General / Coffer's model / Data / Security / About. There is no "Daemon" tab and no daemon-status panel; no tab exposes a "Shutdown" or "Rotate token" control.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- settings layout uses the redesigned tabbed sidebar
- settings drops the confusing controls
- general tab persists the preferred editor

---

## Acceptance Scenarios

### Scenario: activity gives each record its own tab

- **Given** Coffer has recorded an audit entry, an MCP invocation and a daemon log record
- **When** the user opens `/activity` and moves through its three tabs
- **Then** each tab renders that record's own newest-first table with the columns that record has — an activity line and actor; a call's server, capability, duration and outcome; a log record's level, logger and message
- **And** a change reads as a plain-language line, not a raw event code

### Scenario: the daemon tab reads every writer in the log

- **Given** `daemon.log` holds lines from several writers at once — Coffer's own JSON, the format the daemon itself wrote before FR-022 was met, uvicorn, rich, and the cloudflared child's zerolog — with a colour-escaped line among them and a traceback written under the record that raised it
- **When** the user opens the Daemon tab
- **Then** each row carries the time, level and logger its own line stated, and nothing carries a time or a level it never stated
- **And** no message renders a terminal escape sequence as text
- **And** the traceback rides with the record that raised it rather than becoming rows of its own
- **And** the errors-only filter judges each line by its own level rather than treating every non-JSON line as an error

### Scenario: activity row expands to its raw record

- **Given** an Activity tab has at least one row
- **When** the user clicks (or presses Enter/Space on) that row
- **Then** an expanded region renders its raw record — the full underlying JSON, pretty-printed in a monospace, scrollable block

### Scenario: a failing record shows its error inside its own tab

- **Given** one of the three routes is unavailable (an older daemon that does not serve it)
- **When** the user opens `/activity`
- **Then** the failing record's tab renders a readable error
- **And** the other two tabs still render their rows

### Scenario: legacy /audit redirects to activity

- **Given** a user follows an old bookmark to `/audit`
- **When** the route resolves
- **Then** the app redirects to `/activity` and no "page not found" view is shown

### Scenario: an agent reads recent changes and failures in one call

- **Given** Coffer has recorded audit entries and written daemon log records
- **When** an agent calls `coffer__diagnose`
- **Then** it receives both timelines in one response, newest first — the audit
  entries as `changes` and the log records as `log` — with no secret values in
  either

### Scenario: cold-start renders authenticated content

- **Given** the user has never opened Coffer (localStorage is empty, no daemon.json in user HOME yet)
- **And** `coffer daemon start` is running (so daemon.json exists in user HOME)
- **When** they navigate to `http://localhost:5173/` in a real browser
- **Then** the index redirects to `/agents` and the page renders the sidebar + main content area within 2 seconds
- **And** the main content shows the Agents welcome view (no generic error card)
- **And** the sidebar lists exactly Coffer's operational surfaces — Agents, Chat; MCP servers, Skills, Knowledge, Memory, Model providers, Channels; Activity, Sync, Settings — grouped under "Agents", "Resources", and "System" headings, with no other entry

### Scenario: token-missing renders an actionable empty state

- **Given** `~/.coffer/daemon.json` does not exist (daemon is not running)
- **When** the user navigates to `http://localhost:5173/`
- **Then** the page shows a "Daemon not running" view naming the one recovery a browser can offer — the `coffer daemon start` command to run (the Restart control belongs to the desktop shell, which can actually spawn a daemon)
- **And** the sidebar is still visible so the user can orient themselves
- **And** no view shows the literal text "unexpected error" or `INTERNAL_ERROR`

### Scenario: empty resources list renders a welcome view

- **Given** the daemon is running and zero resources are registered
- **When** the user opens `/mcp-servers`
- **Then** the page renders a welcome card with a short pitch and a primary "Add MCP server" button
- **And** the welcome card does NOT show an empty table or a placeholder ghost row

### Scenario: MCP server registration round-trip via JSON import

- **Given** the user opens the "Add MCP server" dialog from the resources list
- **When** they paste the standard `mcpServers` JSON and confirm the review step
- **Then** the app posts each server to `/api/v1/resources`, then writes any secret env values to `/api/v1/credentials` (register-first ordering avoids orphan credential entries when registration fails)
- **And** on success the dialog closes and (for a single server) the app navigates to `/mcp-servers/<name>` showing the Overview tab (the old kind-segment path `/mcp-servers/mcp_server/<name>` survives only as a redirect to it)
- **And** the new server appears on the resources list with health "unknown" then "healthy" within 10 seconds

### Scenario: add-server form navigates to detail then back to list shows card

- **Given** the user completes the JSON-import dialog for a new MCP server
- **When** they are taken to the server's detail page and then navigate back to `/mcp-servers`
- **Then** the server card appears in the resources list

### Scenario: capability toggle uses the redesigned tab layout

- **Given** a registered MCP server with at least one tool and one resource
- **When** the user opens the server's detail page and clicks the Tools tab
- **Then** each tool renders as a row with its name, description, and an enabled/disabled switch
- **And** toggling a tool's switch persists the change (capability preference) and re-fetches the tool list
- **And** the same flow works for the Resources tab and the Prompts tab

### Scenario: resource capability toggle works via the Resources tab

- **Given** a registered MCP server that exposes at least one resource URI
- **When** the user navigates to the Resources tab and disables a resource via its toggle
- **Then** the resource switch reflects the disabled state

### Scenario: prompt capability toggle works via the Prompts tab

- **Given** a registered MCP server that exposes at least one prompt
- **When** the user navigates to the Prompts tab and disables a prompt via its toggle
- **Then** the prompt switch reflects the disabled state

### Scenario: capability search box narrows the tool list

- **Given** a registered MCP server with multiple tools
- **When** the user types a partial name in the capability search box on the Tools tab
- **Then** only matching tools remain visible and non-matching tools are hidden

### Scenario: settings layout uses the redesigned tabbed sidebar

- **Given** the user navigates to `/settings`
- **When** the page resolves
- **Then** it lands on the General tab
- **And** the settings sidebar shows General, Coffer's model, Data, Security, and About — exactly those five, in that order — with the current route highlighted
- **And** clicking a tab swaps the right pane content without a full page reload

### Scenario: settings drops the confusing controls

- **Given** the user opens the Settings tabs
- **When** each tab is fully rendered
- **Then** no tab exposes a "Shutdown daemon" control or a "Rotate token" control
- **And** there is no "Daemon" tab and no read-only daemon-status panel
- **And** the About tab shows version / license / source only — no language picker, no resource-kind list

### Scenario: general tab persists the preferred editor

- **Given** the user opens the General settings tab
- **When** they set a preferred external editor (by picking a detected editor or entering a custom launch command)
- **Then** reloading the page shows the same preferred-editor value
- **And** clearing the override restores the operating-system default

### Scenario: retention period persists across reload

- **Given** the user opens the Data settings tab
- **When** they turn off "Keep forever" for a log table, set a specific number of retention days, and click Save
- **Then** reloading the page shows the same retention-days value that was saved

### Scenario: language switcher round-trips correctly

- **Given** the UI is in English
- **When** the user selects 中文 in the sidebar language switcher
- **Then** all sidebar labels, page titles, and form labels switch to Chinese without a full page reload, on the very next render
- **And** the preference persists across reloads (localStorage `coffer.language`)

### Scenario: daemon-offline banner appears when daemon is unreachable

- **Given** the daemon is not running (no reachable `127.0.0.1:<port>` from `~/.coffer/daemon.json`, or the file is absent)
- **When** the user has the app open and any authenticated request to the daemon fails to connect
- **Then** a daemon-offline banner renders at the top of the workspace naming the recovery the host can actually offer — in a browser, the `coffer daemon start` command to run, because the page cannot start a daemon; in the desktop shell, a Restart control, because it can
- **And** the banner disappears automatically once the daemon becomes reachable again, without a manual page reload

### Scenario: JSON import shows readable error for malformed JSON

- **Given** the user opens the "Add MCP server" dialog
- **When** they paste a payload that is not valid JSON (or a valid JSON document that does not match the `mcpServers` shape) and submit
- **Then** the dialog stays open and renders a readable error explaining what is wrong (parse error location for malformed JSON, or the failing field for shape-mismatch)
- **And** no request is sent to `/api/v1/resources` or `/api/v1/credentials`
- **And** the dialog never shows the literal text "unexpected error" or `INTERNAL_ERROR`

---

## Requirements

### Functional Requirements

**Information architecture**

- **FR-001**: The sidebar MUST be grouped by role rather than on one axis: AGENTS for the consumers (the agents, and the chat held with one) and RESOURCES for the assets those agents draw on, with SYSTEM for the cross-cutting tooling. Agents are not a resource kind and MUST NOT be listed under Resources.
- **FR-002**: Every scoped resource kind MUST have its own list surface, so the navigation and each list page carry no kind-specific branch.
- **FR-003**: The sidebar MUST list only surfaces that have shipped. It MUST NOT carry "not yet implemented" placeholders; an entry leaves the sidebar when its feature does, and returns with it.
- **FR-004**: The sidebar's entries MUST be exactly the ones listed under `## Information Architecture`, in those three groups and at those routes — eleven today, and no twelfth.
- **FR-005**: RESOURCES MUST hold exactly one entry per resource kind that has a list UI — today six kinds, six entries.
- **FR-006**: A surface MUST carry one name in every place it is named — sidebar, page header, welcome panel and dialogs — because a surface the user reaches two ways must not have two names.
- **FR-007**: The sidebar MUST collapse to an icon-only rail and back, and that choice MUST persist across sessions (`localStorage`).

**Routing**

- **FR-008**: The app's index (`/`) MUST redirect to `/agents`. Agents live at `/agents` (list) and `/agents/:name` (detail), and MUST NOT appear in the `/mcp-servers` kind browser.
- **FR-009**: The legacy paths `/resources` and `/mcp-servers/mcp_server/:name` MUST resolve as redirects rather than as a "page not found" view.

**List and detail conventions**

- **FR-010**: Every list surface MUST use one shared searchable, filterable, paginated table, and a row click MUST open that item's detail page.
- **FR-011**: A row action MUST be an icon plus its label, never a bare icon — a bare icon reads as a different affordance from the labelled action beside it. Cards are reserved for welcome and empty states.
- **FR-012**: Every detail page MUST lay its tabs out the same way as every other. What a tab shows belongs to the spec that owns that kind — the agent detail page's tabs are spec agent-registry FR-TBD's.

**Reach control**

- **FR-013**: Every list surface MUST carry a **reach** column: one button labelled with the answer it already holds — "Every agent", "2 agents", "Disabled", or "No agent selected" for a scope narrowed to nobody — so the reader learns the reach by reading it rather than by comparing which of three side-by-side segments looks pressed. Every detail page MUST carry the same button in its header.
- **FR-014**: The button MUST open a panel where "who does this reach?" is a single choice between Disabled, Every agent and Only selected agents, the last over the scope's list of agents. A kind that declares no scope gets the same button over a two-choice Disabled / Enabled panel.
- **FR-015**: The panel MUST stage its agent list and write exactly once, when it closes — the two whole-value choices close it themselves — so a panel that is opened and dismissed writes nothing, and no write can refetch the list and move the row the panel is anchored to.
- **FR-016**: The reach control MUST be one component mounted in three places — the list row, the detail header and the multi-select bar — so the three can never drift into three different answers to one question.
- **FR-017**: A multi-select MUST apply that same choice to the whole selection. A bulk write is a new intent, so its button reads "Set reach…" and its panel opens with nothing chosen rather than on any one row's value, and a row that fails MUST be reported in the batch's one summary rather than silently skipped. Delete stays its own button beside it.
- **FR-018**: The list's reach filter MUST offer the same states the panel does, rather than a bare enabled / disabled pair, and the column, the filter and the button MUST all use the word *reach*, because they are all asking the one question.

**First run, empty, loading and error states**

- **FR-019**: No surface may render a blank page, or a generic error, where a next action exists. Empty, loading and error states are first-class on every surface, not an afterthought on some of them.
- **FR-020**: No view may show the literal text "unexpected error" or `INTERNAL_ERROR`.
- **FR-021**: A list with nothing in it MUST render a welcome card — a short pitch and one primary action — and MUST NOT render an empty table or a placeholder ghost row.
- **FR-022**: When the daemon cannot be reached at all, the app MUST render a "Daemon not running" view naming the one recovery its host can actually offer, and the sidebar MUST stay visible so the user can orient themselves.
- **FR-023**: When an authenticated request fails to connect while the app is open, a daemon-offline banner MUST render above the workspace, naming the recovery the host can offer — in a browser the `coffer daemon start` command, in the desktop shell a Restart control, because only one of the two can spawn a daemon. The banner MUST clear itself once the daemon is reachable again, with no manual page reload.

**Visual language**

- **FR-024**: Every surface MUST be expressed in one visual language — a distinct typographic hierarchy and consistent spacing, drawn from the shared design tokens rather than restated per screen.

**MCP surfaces**

- **FR-025**: An MCP server's detail page MUST open on a primary "what is this server doing?" Overview, before the per-capability toggles.
- **FR-026**: The Tools, Resources and Prompts tabs MUST be uniform — each carrying the same search box, status filter and per-row enable toggle — and MUST keep that chrome even when the upstream exposes none of that kind, rendering the empty state inside the table rather than as a bare card.
- **FR-027**: "Add MCP server" MUST be a modal that takes the standard `mcpServers` JSON block, one server or many at once, with a review step where the user confirms which `env` values are secrets. Secrets MUST be lifted into the encrypted credential store with only their refs kept in the resource config, and the server MUST be registered before its secrets are written, so a failed registration leaves no orphan credential entry.
- **FR-028**: A payload that is not valid JSON, or a valid JSON document that does not match the `mcpServers` shape, MUST keep the dialog open with a readable error — the parse location, or the failing field — and MUST NOT send a request.
- **FR-029**: A server's **Invocations** tab MUST render the same table Activity's MCP calls tab renders, scoped to that one server, rather than a second table that would have to be kept in step with the first.

**Activity**

- **FR-030**: The three records Coffer keeps MUST reach a person through one page at `/activity`, under System, carrying one tab per record — Changes, MCP calls, Daemon — each a newest-first table with the columns that record actually has.
- **FR-031**: Every Activity tab MUST filter by free text and time range plus the one filter its own record affords (actor, call status, errors only), and any row MUST expand to its raw underlying record, pretty-printed in a monospace, scrollable block.
- **FR-032**: Only the visible tab queries. A record whose route fails MUST render its error inside its own tab, leaving the other two working, and there MUST be no manual refresh control — switching tab or changing a filter is what refetches.
- **FR-033**: The Activity page MUST add no route of its own: each tab reads the read-only route belonging to whichever spec owns that record. What those routes guarantee is recorded under `## Assumptions`, not required here.
- **FR-034**: Bringing the three records onto one page MUST NOT change or withdraw the command-line readers — `coffer audit` and `coffer mcp invocations` keep working as they are, so a script that read a record before this page existed still does.
- **FR-035**: Event types MUST render as plain-language activity lines ("Enabled demo-fs") in both locales, guarded the way error codes are: a new event type with no string fails CI rather than showing a reader a raw `resource_enabled`.
- **FR-036**: The legacy `/audit` and `/observability` paths MUST redirect to `/activity` rather than resolving to a "page not found" view.

**Settings**

- **FR-037**: Settings MUST carry exactly five tabs, in this order — General, Coffer's model, Data, Security, About — and MUST open on General. Clicking a tab swaps the right pane without a full page reload.
- **FR-038**: The General tab MUST expose the default page-size preference — the rows-per-page every list table seeds from — persisted in `localStorage`.
- **FR-039**: The General tab MUST also expose a **preferred external editor**: the application Coffer uses when the user opens a managed file, or its containing folder, from a read-only file viewer. The default is the operating system's default application; the user MAY override it by picking an editor the daemon detected as installed (a browser cannot list installed applications — spec daemon FR-TBD) or by entering a custom application or launch command. Like the other display preferences the value is persisted in `localStorage` and never sent to the daemon, except transiently as the target when opening a file.
- **FR-040**: The Data tab MUST carry the retention policy per log table — Keep forever, or a number of days — and a manual prune, with a saved value surviving a reload.
- **FR-041**: The daemon MUST NOT be surfaced as a user-facing concept: there is no Daemon tab and no read-only daemon-status panel, and a user never needs to know Coffer runs a background daemon.
- **FR-042**: No tab may expose a "Shutdown daemon" or "Rotate token" control — both belong on the CLI — and the About tab shows version, license and source only, with no language picker and no installed-resource-kind list.

**Internationalisation**

- **FR-043**: The sidebar MUST carry the English / 中文 switcher, so it is reachable from every screen. Every sidebar label, page title and form label MUST switch on the very next render, with no full page reload, and the choice MUST persist in `localStorage` under `coffer.language`.

## Success Criteria

- Every scenario above has at least one covering test (unit, integration, or e2e) and `scripts/audit_acceptance.py` passes for this spec alongside the others.
- A first-time user can register an MCP server and reach a working gateway in-app; pointing an MCP client at the shim is documented in the project README.
- The sidebar shows only operational surfaces — Agents and Chat; MCP servers, Skills, Knowledge, Memory, Model providers and Channels; Activity, Sync and Settings — grouped by role, with nothing else in it and no feature appearing as a dead "soon" entry.
- The three records Coffer keeps — the audit log, the MCP invocation log and the daemon log — reach a person through one page at `/activity`, a tab and a table each, and an agent through one call to `coffer__diagnose`, which returns them joined; `/audit` and the legacy `/observability` URL redirect there rather than 404ing. Scripts keep `GET /api/v1/audit` / `coffer audit` and `coffer mcp invocations`. Observability (system health / metrics) is a reserved future surface, and is not this.
- Settings groups data controls (retention and prune) under a Data tab; the daemon is never surfaced as a user-facing concept, and no tab exposes a shutdown or token-rotation control.
- `make verify` + `make verify-e2e` are green.

## Assumptions

- **Each Activity tab's route belongs to the spec that owns that record, and this page only reads it.** The audit log is the resource framework's own record, written for every kind (see [`.specify/memory/constitution.md`](../../../.specify/memory/constitution.md)); the cross-server MCP invocation log is spec mcp-gateway's; the daemon log is spec daemon's. Three owners, not one — this spec adds no REST route, which is a different statement from every route belonging to whichever spec's UI came first. What the page needs of those routes, and does not itself provide: that the invocation and daemon-log routes exist as read-only, cross-cutting lanes, and that the daemon-log route is authenticated (the daemon router leaves `/status` open, and log contents are not status).
- **Normalising the daemon log onto one field set is spec daemon's work, not this page's.** The Daemon tab's columns only exist because every writer in `daemon.log` — Coffer's own structlog JSON, the stdlib formatter, uvicorn, rich, and the cloudflared child's zerolog — is normalised onto the same fields before it reaches the page, escape sequences are stripped, a traceback rides with the record that raised it, and a line no format fits is kept whole rather than dropped. That reading happens in the log route, on the daemon's side of the wire, and spec daemon owns it. This spec assumes it and renders what it is given; the Daemon-tab scenario under `## Acceptance Scenarios` still guards the result end to end.
- **Correlating the three records for an agent is `coffer__diagnose`'s job, not this page's.** The page deliberately never joins them — that is what made the merged-timeline attempt fail. An agent that asks "what happened" gets the audit entries and the log records already joined, newest first and with no secret values, from the built-in tool under the reserved `coffer__` prefix (spec mcp-gateway). This spec assumes the tool; it specifies nothing about it, and the scenario under `## Acceptance Scenarios` is kept because it guards the pairing a reader of this page depends on.
- **Three outbound citations are placeholders.** `FR-TBD` marks a requirement in another spec whose id is being reassigned by the same restructure that gave this spec its ids. Two are in this file: the agent detail page's tabs (FR-012, spec agent-registry) and the installed-editor enumeration behind `GET /api/v1/fs/editors` (FR-039, spec daemon, which is where the filesystem-action endpoints now live). The third is in [`quickstart.md`](quickstart.md), where the daemon's fixed-port refusal was cited as a bare `FR-028`. All three must be replaced with real ids once those specs settle; a wrong number would be worse than a visible gap.
