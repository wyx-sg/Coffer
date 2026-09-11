# Feature Specification: UI Shell & Visual Language

**Feature Branch**: `feature/002-mcp-gateway-web` (PR #23 on top of `feature/mcp-gateway`)
**Status**: Accepted
**Input**: The mcp-gateway UI shipped as a functional skeleton: bare tailwind defaults, ad-hoc spacing, no first-run onboarding. This spec turns the skeleton into a real product shell — a coherent visual language, an information architecture built on a single unifying concept (every managed entity is a _resource kind_), and the end-to-end flows that make the gateway usable for a first-time visitor (not just for Playwright fixtures that bypass auth).

**Scope note**: Coffer's specs are split along the backend/frontend line. `mcp-gateway` owns the daemon, MCP gateway, REST API, and CLI. **This spec owns the web UI** — the visual language, the information architecture, and internationalisation. This is a **pure UI redesign on top of 001**: it adds no new backend, so the data model lives in `specs/mcp-gateway/data-model.md` and no separate `tasks.md` tracker is kept here. See [`plan.md`](./plan.md) and [`quickstart.md`](./quickstart.md) for the companion docs.

## Information Architecture

The sidebar is grouped **by role**, not on a single axis. Two concepts sit
side by side: **agents** are the _consumers_ (the agents you use), and
**resources** are the _assets_ those agents draw on — named, configured,
lifecycle-managed entities behind a kind-agnostic framework. `mcp_server` is
the resource kind that ships today, surfaced through a per-kind registry so the
navigation and the resources page carry no kind-specific branches. Agents are
NOT a resource kind, so they live in their own group, not under Resources.

**The sidebar shows only what Coffer can do today.** It does not list dead "not yet implemented" placeholders: a sidebar full of "soon" entries reads as an unfinished scaffold, not a product.

Today the sidebar's shipped surfaces are:

```
 AGENTS
  Agents           /agents            — the consumers (Bot icon)
 RESOURCES
  MCP servers      /mcp-servers       — the aggregated upstream servers
  Skills           /skills            — what Coffer delivers to agents
  Knowledge        /knowledge         — one page per knowledge scope
  Model providers  /model-providers   — credentialed vendor endpoints
  Channels         /channels          — the IM transports agents answer on
 SYSTEM
  Settings         /settings
```

**RESOURCES holds one entry per resource kind that has a list UI, and that
correspondence is the rule** — five kinds (`mcp_server`, `skill`, `knowledge`,
`provider`, `channel`), five entries. Two had drifted out of it and were
returned in 2026-09: **Model providers** was the only kind filed under Settings
(as "LLM connections"), and its old name described a page rather than the thing
it manages — a `provider` is `{protocol, base_url, credential_ref}`, a vendor
endpoint and its key; the model is not stored there and is chosen at the point
of use. **Channels** sat under AGENTS, but a channel is a credentialed
transport the vault owns, not a consumer of the vault; it belongs beside the
other assets rather than beside the agents that happen to answer on it.

That leaves AGENTS holding a single entry. The asymmetry is deliberate: agents
are the one thing in the product that *uses* the vault rather than living in
it, and collapsing the group would lose that distinction to save one line.

The app's index (`/`) redirects to `/agents`, so a first-time visitor lands on
the Agents surface. It is grouped into **Agents** (the consumers), **Resources** (the resource kinds), and **System** (cross-cutting tooling: Settings) so the navigation stays stable as Coffer grows. Agents live at `/agents` (list) and `/agents/:name` (detail) and do not appear in the `/mcp-servers` kind browser. (`/resources` is kept as a legacy redirect to `/mcp-servers` for old bookmarks.) The agent detail page is a simple **Overview + Config files** detail page: an Overview tab summarising the agent's registered config and a Config files tab that surfaces its known config files read-only, with no create / edit / delete / enable.

All list surfaces (agents, MCP servers, skills, knowledge, model providers, channels) use one shared, searchable, filterable, paginated table: a row click opens that item's detail page, and row actions are compact icons. Cards are reserved for welcome / empty states only.

**Observability** (system health / metrics) is planned but not shown today; it appears in the sidebar only once it ships. The reverse rule holds too — an entry is removed when its feature is, which is how Chat, Machines and the Audit log left.

The sidebar collapses to an icon-only rail and back; the choice persists across sessions (localStorage).

See [Everything Is a Resource Kind](../../docs/decisions/everything-is-a-resource-kind.md) (Amended 2026-05-30) for the architectural decision behind this role-based information architecture (agents as a separate consumer axis; rejected alternative: a separate "surface" concept; sidebar policy: no "soon" placeholders).

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

A developer who already uses Coffer for MCP gateway aggregation wants the routine flows — registering a server, watching its health, browsing tools, toggling capabilities — to look and feel like a real product, not a scaffold. Headings are typographically distinct; spacing is consistent; per-server pages have a primary "what is this server doing?" view before the per-tool toggles; empty / error / loading states are first-class. The Tools, Resources, and Prompts tabs are uniform — each carries the same search box, status filter, and per-row enable toggle, and keeps that chrome even when the upstream exposes none of that kind (the empty state renders inside the table, not as a bare card). The server list carries a search box, a status filter, and a client-side pager so a large vault stays navigable.

There is no **Invocations** tab, and the Overview no longer carries a "Last
invocation" row. The tab shipped — a filtered, paged table of every call the
gateway proxied, each row expanding to that call's raw JSON record — and it has
the same problem the audit log's page had, one story down: the traffic on it is
not the user's. Every row is an agent calling a tool through the gateway, and a
person who wants to know why one of those calls failed asks that agent rather
than reading the gateway's table over its shoulder.

The record is untouched. The gateway still writes every call to the invocation
log, and both `GET /api/v1/resources/mcp_server/{name}/invocations` and
`coffer mcp invocations` still read it back — for an agent that can call the
route, and for scripting. What goes is the page.

"Add MCP server" is a modal where the user pastes the standard `mcpServers` JSON (one or many servers at once) — the same block every MCP server's README provides. A review step lets them confirm which `env` values are secrets; those are lifted into the encrypted credential store (only their refs kept in the config) rather than stored as plaintext in the config.

**Why this priority**: The MCP Gateway spec delivered the backend correctness but the UI shipped as bare tailwind defaults. The user-visible bar for "the MCP gateway is done" is the UI passing a real user (not a Playwright fixture).

**Independent Test**: Walk the MCP flows end-to-end in a real browser: open `/mcp-servers` (welcome or list), click "Add MCP server", fill the form, submit, land on the detail page, switch through the Overview / Tools / Resources / Prompts tabs, toggle a tool, return to the list, switch language between English and 中文. Every step shows polished content; no view dead-ends in a generic error.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- MCP server registration round-trip via JSON import
- capability toggle uses the redesigned tab layout
- language switcher round-trips correctly

---

### User Story 3 — The audit log is read by an agent, not browsed by a person (Priority: P2)

The audit log had a page: a filtered, paged table of plain-language activity
lines under System at `/audit`. **It is removed.** In practice nobody opened it.
A person does not sit down to browse "what changed in my vault" — they notice
something is broken and ask whoever is helping them, and that is an agent.

So the log keeps its reader and loses its page. `coffer__diagnose` gives an
agent both records at once — the audit log (what changed, and who changed it)
and the daemon's own log (what happened, including the failures) — on one
newest-first timeline. The agent already holds the tool, needs no file path,
and gets the two sides already correlated instead of two things to join.

The REST route and `coffer audit` stay for scripting. What goes is the page,
its plain-language rendering, and the 39 translated event strings that existed
so a zh reader would not see a raw `event_type` on a row. Nothing renders a row
any more, and an agent wants the wire value.

**Why this priority**: P2 — this is a removal plus one tool, not a surface.

**Independent Test**: `/audit` is not routed and no sidebar entry links to it;
an agent calling `coffer__diagnose` gets recent changes and recent log records
back in one response.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- an agent reads recent changes and failures in one call

---

### User Story 4 — Settings is organised around the user, not the daemon (Priority: P2)

A developer opens Settings and finds tabs grouped by what they manage, not by how Coffer is built: **General** (display preferences — the default rows-per-page for list tables, and the preferred external editor for opening managed files), **Data** (retention policy and manual prune), and **About** (version, license, source). Settings opens on the General tab. The daemon is an implementation detail — there is no "Daemon" tab and no read-only daemon-status panel. A user never needs to know Coffer runs a background daemon.

The **General** tab MUST expose the default page-size preference (the rows-per-page every list table seeds from), persisted in `localStorage`. It MUST also expose a **preferred external editor** preference — the application Coffer uses when the user opens a managed file (or its containing folder) from a read-only file viewer. The default is the operating system's default application; the user MAY override it by **picking an editor the daemon detected as installed** (enumerated via `GET /api/v1/fs/editors`, spec agent-registry FR-039 — a browser can't list installed apps) or by entering a custom application / launch command. Like the other display preferences the chosen value is persisted in `localStorage` and never sent to the daemon (except transiently as the target when opening a file).

**Why this priority**: P2 — the underlying controls already function; this story is reorganisation and subtraction, not new capability. An unorganised Settings page is exactly the "feels like a scaffold" signal US2 fights, and the user flagged it as confusing.

Removed — none of these is something a user needs to operate or see:

- **Shutdown daemon** — clicking it from the web kills the very page you are on, and recovery needs a terminal anyway; daemon shutdown belongs on the CLI.
- **Token rotation** — a security action a single-user local app needs maybe once ever; `coffer daemon rotate-token` covers it on the CLI.
- **The read-only daemon-status panel** (status / version / port) — an implementation detail; a healthy daemon needs no UI, and the failure case is owned by the offline banner.
- **The duplicate language selector and the "Installed resource kinds" dump** — the sidebar already switches language, and the kind list is developer detail.

Remaining jargon is rewritten in plain language (e.g. "prune" is phrased as clearing expired data).

**Independent Test**: open `/settings` — it lands on General. The tab list reads General / Data / About. There is no "Daemon" tab and no daemon-status panel; no tab exposes a "Shutdown" or "Rotate token" control.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- settings layout uses the redesigned tabbed sidebar
- settings drops the confusing controls
- the General tab persists a preferred-editor choice

---

## Acceptance Scenarios

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
- **And** the sidebar lists Coffer's operational surfaces — Agents, MCP servers, Skills, Knowledge, Model providers, Channels, Settings — grouped under "Agents", "Resources", and "System" headings

### Scenario: token-missing renders an actionable empty state

- **Given** `~/.coffer/daemon.json` does not exist (daemon is not running)
- **When** the user navigates to `http://localhost:5173/`
- **Then** the page shows a "Daemon not running" view with one obvious recovery affordance (a Reload control)
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
- **And** on success the dialog closes and (for a single server) the app navigates to `/mcp-servers/mcp_server/<name>` showing the Overview tab
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
- **And** the settings sidebar shows General, Data, and About, with the current route highlighted
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
- **Then** a daemon-offline banner renders at the top of the workspace with a clear recovery affordance — a Reload control
- **And** the banner disappears automatically once the daemon becomes reachable again, without a manual page reload

### Scenario: JSON import shows readable error for malformed JSON

- **Given** the user opens the "Add MCP server" dialog
- **When** they paste a payload that is not valid JSON (or a valid JSON document that does not match the `mcpServers` shape) and submit
- **Then** the dialog stays open and renders a readable error explaining what is wrong (parse error location for malformed JSON, or the failing field for shape-mismatch)
- **And** no request is sent to `/api/v1/resources` or `/api/v1/credentials`
- **And** the dialog never shows the literal text "unexpected error" or `INTERNAL_ERROR`

---

## Success Criteria

- Every scenario above has at least one covering test (unit, integration, or e2e) and the `audit_acceptance` script passes 002 alongside 001.
- A first-time user can register an MCP server and reach a working gateway in-app; pointing an MCP client at the shim is documented in the project README.
- The sidebar shows only operational surfaces (Agents, MCP servers, Skills, Knowledge, Model providers, Channels, Settings), grouped by role; no feature appears as a dead "soon" entry.
- The audit log has no page: neither `/audit` nor the legacy `/observability` URL resolves, and no sidebar entry points at either. An agent reads the log through `coffer__diagnose`; scripts read it through the REST route and `coffer audit`. The MCP invocation log has no page either, and for the same reason — every row in it is an agent calling a tool, not a person — so it keeps its REST route and `coffer mcp invocations` and loses its tab. Observability (system health / metrics) is a reserved future surface, not the audit log.
- Settings groups data controls (retention and prune) under a Data tab; the daemon is never surfaced as a user-facing concept, and no tab exposes a shutdown or token-rotation control.
- `make verify` + `make verify-e2e` are green.
