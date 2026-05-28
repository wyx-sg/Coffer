# Feature Specification: UI Shell & Visual Language

**Feature Branch**: `feature/002-mcp-gateway-web` (PR #23 on top of `feature/mcp-gateway`)
**Status**: Draft
**Input**: The 001-mcp-gateway UI shipped as a functional skeleton: bare tailwind defaults, ad-hoc spacing, no first-run onboarding. This spec turns the skeleton into a real product shell — a coherent visual language, an information architecture built on a single unifying concept (every managed entity is a _resource kind_), and the end-to-end flows that make the gateway usable for a first-time visitor (not just for Playwright fixtures that bypass auth).

**Scope note**: Coffer's specs are split along the backend/frontend line. `001-mcp-gateway` owns the daemon, MCP gateway, REST API, and CLI. **This spec owns every user-facing surface** — the web UI, the Tauri desktop shell, the visual language, the information architecture, and internationalisation. Anything a user sees or clicks is specified here. This is a **pure UI redesign on top of 001**: it adds no new backend, so the data model lives in `specs/001-mcp-gateway/data-model.md` and no separate `tasks.md` tracker is kept here. See [`plan.md`](./plan.md) and [`quickstart.md`](./quickstart.md) for the companion docs.

## Information Architecture

Coffer manages exactly one kind of thing: a **resource** — a named, configured, lifecycle-managed entity. `mcp_server` is the resource kind that ships today; `skill`, `knowledge_base`, `memory`, `channel`, and `agent` are planned. There is no second-class "surface" concept:

- A **channel** (Seatalk, Slack) is a resource — a registered, configured integration with its own lifecycle.
- An **agent** is a resource too, and a dual-role one: an agent both _consumes_ capabilities (it is a gateway client) and can itself be _exposed_ as a callable capability to other agents (a sub-agent / agent-as-tool). From the gateway's view an exposed agent is just another capability provider, no different from an upstream MCP server. That duality is a property of the agent resource — surfaced on the agent's own detail page when that kind ships — not a reason to split the navigation.

**The sidebar shows only what Coffer can do today.** Planned kinds are _not_ listed as dead "not yet implemented" placeholders: a sidebar two-thirds full of "soon" entries reads as an unfinished scaffold, not a product. Each kind — and the planned built-in **Chat** surface — re-adds its own navigation entry when its feature spec ships. The resource model above is the design intent that keeps those additions cheap; here it is documentation, not rendered UI.

Today the sidebar is:

```
 RESOURCES
  MCP servers      operational
 SYSTEM
  Observability    the audit log
  Settings
```

It is grouped from the start — **Resources** (resource kinds) and **System** (cross-cutting tooling) — so a future kind slots into the Resources group without re-doing the navigation. A pinned **Chat** entry will sit above the groups when the built-in agent ships. The planned kinds (skills, knowledge bases, memory, channels, agents) and the Chat surface are recorded for re-introduction, but deliberately not built ahead of the features they would describe.

The sidebar collapses to an icon-only rail and back; the choice persists across sessions (localStorage).

See [`ADR-008: everything is a resource kind`](../../docs/decisions/ADR-008-everything-is-a-resource-kind.md) for the architectural decision behind this single-axis information architecture (rejected alternative: a separate "surface" concept; sidebar policy: no "soon" placeholders).

## User Scenarios & Testing

### User Story 1 — A first-time visitor lands in a usable app (Priority: P1)

A developer opens the web UI (or the Tauri desktop window) for the first time. They have never registered a server. The page renders content immediately — no broken "unexpected error" cards from a missing token, no empty page with no next action. The dev sees a welcome view that explains what Coffer is and offers one obvious next step: "Add your first MCP server."

**Why this priority**: This is the gate to every other flow. If the first screen looks broken or is silent on what to do next, the user closes the tab and the rest of the product doesn't matter.

**Independent Test**: Clear `localStorage`, open `http://localhost:5173/` after `make dev`. The page authenticates automatically via the dev-only token-injection plugin (`frontend/vite.config.ts`); the user lands on `/resources` and sees a welcome card with a primary "Add MCP server" button.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- cold-start renders authenticated content
- token-missing renders an actionable empty state (not generic error)
- empty resources list renders a welcome view

---

### User Story 2 — Day-to-day MCP work feels polished, not bare (Priority: P1)

A developer who already uses Coffer for MCP gateway aggregation wants the routine flows — registering a server, watching its health, browsing tools, toggling capabilities, viewing invocations — to look and feel like a real product, not a scaffold. Headings are typographically distinct; spacing is consistent; per-server pages have a primary "what is this server doing?" view before the per-tool toggles; empty / error / loading states are first-class. The server list carries a search box, a status filter, and a client-side pager so a large vault stays navigable.

"Add MCP server" is a modal where the user pastes the standard `mcpServers` JSON (one or many servers at once) — the same block every MCP server's README provides. A review step lets them confirm which `env` values are secrets; those are lifted into the OS keychain rather than stored in the config.

**Why this priority**: Spec 001 delivered the backend correctness but the UI shipped as bare tailwind defaults. The user-visible bar for "the MCP gateway is done" is the UI passing a real user (not a Playwright fixture).

**Independent Test**: Walk the MCP flows end-to-end in a real browser: open `/resources` (welcome or list), click "Add MCP server", fill the form, submit, land on the detail page, switch through the Overview / Tools / Resources / Prompts / Invocations tabs, toggle a tool, return to the list, switch language between English and 中文. Every step shows polished content; no view dead-ends in a generic error.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- MCP server registration round-trip via JSON import
- capability toggle uses the redesigned tab layout
- invocations table renders the redesigned empty + populated states
- language switcher round-trips correctly

---

### User Story 3 — Observability: the audit log has a home (Priority: P2)

A developer wants to see what changed in their Coffer vault — which resources and capabilities were added, enabled, disabled, or removed, by whom, and when. The **Observability** entry gives them that: an audit log of every lifecycle event where each row is a plain-language activity line ("Enabled demo-fs", "Discovered tool write_file on demo-fs") rather than a raw `event_type` code. It filters by time range and actor, pages client-side, and expands any row to its exact recorded detail.

**Why this priority**: P2 — the audit log already shipped in spec 001; this story is the redesigned filter + table and the `Observability` home. Cross-server invocation history and upstream health/metrics are planned to join here later (see Out of Scope), but each is a future increment and is not shown until built.

**Independent Test**: open `/observability` — the Observability section's audit-log view renders with the "Audit log" heading, a filter bar (time range / actor), and a paged table where each row is a readable activity line; clicking a row expands its exact detail. Navigate to the legacy `/audit` URL — the app redirects to `/observability`.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- observability route renders the audit log
- legacy /audit redirects to Observability

---

### User Story 4 — Settings is organised around the user, not the daemon (Priority: P2)

A developer opens Settings and finds tabs grouped by what they manage, not by how Coffer is built: **Data** (retention policy, manual prune, and backups) and **About** (version, license, source); the desktop app adds an **App** tab (launch-at-login). The daemon is an implementation detail — there is no "Daemon" tab and no read-only daemon-status panel. A user never needs to know Coffer runs a background daemon.

**Why this priority**: P2 — the underlying controls already function; this story is reorganisation and subtraction, not new capability. An unorganised Settings page is exactly the "feels like a scaffold" signal US2 fights, and the user flagged it as confusing.

Removed — none of these is something a user needs to operate or see:

- **Shutdown daemon** — clicking it from the web kills the very page you are on, and recovery needs a terminal anyway; daemon shutdown belongs on the CLI.
- **Token rotation** — a security action a single-user local app needs maybe once ever; `coffer daemon rotate-token` covers it on the CLI.
- **The read-only daemon-status panel** (status / version / port) — an implementation detail; a healthy daemon needs no UI, and the failure case is owned by the offline banner.
- **The duplicate language selector and the "Installed resource kinds" dump** — the sidebar already switches language, and the kind list is developer detail.

Remaining jargon is rewritten in plain language (e.g. "prune" is phrased as clearing expired data).

**Independent Test**: open `/settings` — it lands on Data. The tab list reads Data / About in the browser (the desktop app adds an App tab). There is no "Daemon" tab and no daemon-status panel; no tab exposes a "Shutdown" or "Rotate token" control.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- settings layout uses the redesigned tabbed sidebar
- settings drops the confusing controls

---

### User Story 5 — Desktop shell: always-on and out of the way (Priority: P3)

After initial setup, the developer expects Coffer to be present whenever any MCP client starts — no manual launch — and to stay out of the way when they are not actively managing it. The Tauri desktop app supervises the local daemon (starting it and reconnecting transparently), runs in the system tray, restores its window from the tray on click, and offers optional launch-at-login.

**Why this priority**: P3 — quality-of-life polish. The daemon and shim (spec 001) work without the desktop app; this story is the convenience layer that makes Coffer a daily-driver desktop product. It moved here from spec 001 as part of the backend/frontend spec split — the desktop shell is a user-facing surface, so it belongs in 002.

**Independent Test**: enable "launch at login", log out and back in — the daemon is running and the tray icon is present. Close the main window — the daemon stays alive, the tray icon remains, and an MCP client still works; reopening from the tray shows the same state.

**Representative scenarios** (full list under `## Acceptance Scenarios`):

- launch at login
- close to tray, not exit

---

## Acceptance Scenarios

### Scenario: cold-start renders authenticated content

- **Given** the user has never opened Coffer (localStorage is empty, no daemon.json in user HOME yet)
- **And** `coffer daemon start` is running (so daemon.json exists in user HOME)
- **When** they navigate to `http://localhost:5173/` in a real browser
- **Then** the page renders the sidebar + main content area within 2 seconds
- **And** the main content shows the resources welcome view (no generic error card)
- **And** the sidebar lists Coffer's operational surfaces — MCP servers, Observability, Settings — grouped under "Resources" and "System" headings

### Scenario: token-missing renders an actionable empty state

- **Given** `~/.coffer/daemon.json` does not exist (daemon is not running)
- **When** the user navigates to `http://localhost:5173/`
- **Then** the page shows a "Daemon not running" view with one obvious next step (the exact `coffer daemon start` command, copyable)
- **And** the sidebar is still visible so the user can orient themselves
- **And** no view shows the literal text "unexpected error" or `INTERNAL_ERROR`

### Scenario: empty resources list renders a welcome view

- **Given** the daemon is running and zero resources are registered
- **When** the user opens `/resources`
- **Then** the page renders a welcome card with a short pitch and a primary "Add MCP server" button
- **And** the welcome card does NOT show an empty table or a placeholder ghost row

### Scenario: MCP server registration round-trip via JSON import

- **Given** the user opens the "Add MCP server" dialog from the resources list
- **When** they paste the standard `mcpServers` JSON and confirm the review step
- **Then** the app posts each server to `/api/v1/resources`, then writes any secret env values to `/api/v1/keychain` (register-first ordering avoids orphan keychain entries when registration fails)
- **And** on success the dialog closes and (for a single server) the app navigates to `/resources/mcp_server/<name>` showing the Overview tab
- **And** the new server appears on the resources list with health "unknown" then "healthy" within 10 seconds

### Scenario: add-server form navigates to detail then back to list shows card

- **Given** the user completes the JSON-import dialog for a new MCP server
- **When** they are taken to the server's detail page and then navigate back to `/resources`
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

### Scenario: invocations table renders the redesigned empty + populated states

- **Given** a registered server with no invocations
- **When** the user opens the server's Invocations tab on its detail page
- **Then** the empty state shows "No invocations yet" with a hint about how to trigger one
- **Given** the same server with at least one invocation in the DB
- **When** the Invocations tab loads
- **Then** the table renders timestamp / type / capability / status / latency columns
- **And** the status filter dropdown is operable

### Scenario: invocation status filter dropdown exposes selectable options

- **Given** a registered server
- **When** the user opens the Invocations tab and clicks the status filter combobox
- **Then** at least the "All" option renders inside the dropdown portal

### Scenario: observability route renders the audit log

- **Given** at least one audit event exists
- **When** the user opens `/observability`
- **Then** the Observability section's audit-log view renders with the "Audit log" heading
- **And** it renders a filter bar (time range, actor) and a paged table where each row is a plain-language activity line, not a raw event code
- **And** clicking a row expands its exact detail (absolute time, event code, payload)
- **And** the filters narrow the visible rows live

### Scenario: audit log row expand shows detail panel

- **Given** the audit log has at least one row
- **When** the user clicks a row on the Observability page
- **Then** an expanded detail panel renders the event label for that row

### Scenario: audit log free-text filter narrows rows

- **Given** the audit log contains rows for at least two distinct server names
- **When** the user types one server name in the search box
- **Then** only rows containing that name remain visible and rows for the other name disappear

### Scenario: audit log pagination controls appear and advance page

- **Given** the audit log contains more entries than the default page size
- **When** the user opens the Observability page and clicks the Next button
- **Then** the page indicator advances to "Page 2 of …" and the Previous button becomes enabled

### Scenario: legacy /audit redirects to Observability

- **Given** a user follows an old bookmark to `/audit`
- **When** the route resolves
- **Then** the app redirects to `/observability`
- **And** no "page not found" view is shown

### Scenario: settings layout uses the redesigned tabbed sidebar

- **Given** the user navigates to `/settings`
- **When** the page resolves
- **Then** it lands on the Data tab
- **And** the settings sidebar shows Data and About (the desktop app adds an App tab), with the current route highlighted
- **And** clicking a tab swaps the right pane content without a full page reload

### Scenario: settings drops the confusing controls

- **Given** the user opens the Settings tabs
- **When** each tab is fully rendered
- **Then** no tab exposes a "Shutdown daemon" control or a "Rotate token" control
- **And** there is no "Daemon" tab and no read-only daemon-status panel
- **And** the About tab shows version / license / source only — no language picker, no resource-kind list

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
- **Then** a daemon-offline banner renders at the top of the workspace with the literal `coffer daemon start` command as a copyable affordance
- **And** the banner disappears automatically once the daemon becomes reachable again, without a manual page reload

### Scenario: JSON import shows readable error for malformed JSON

- **Given** the user opens the "Add MCP server" dialog
- **When** they paste a payload that is not valid JSON (or a valid JSON document that does not match the `mcpServers` shape) and submit
- **Then** the dialog stays open and renders a readable error explaining what is wrong (parse error location for malformed JSON, or the failing field for shape-mismatch)
- **And** no request is sent to `/api/v1/resources` or `/api/v1/keychain`
- **And** the dialog never shows the literal text "unexpected error" or `INTERNAL_ERROR`

---

## Deferred Acceptance Scenarios (US5 Desktop Shell)

The two scenarios below cover User Story 5 (desktop shell — launch-at-login, close-to-tray). They are out of scope for the web-shell PR and are deferred to the desktop spec (`003-mcp-gateway-desktop`), which ships the Tauri wrapper and tray supervision. They are listed here for traceability; the desktop spec's acceptance audit will pick them up. The web PR includes the desktop-only AppSettings React component behind an `isTauri()` guard so spec 003 can wire it up; the autostart toggle itself is exercised only in spec 003.

<!-- audit-traceability: copy these two scenarios verbatim into 003-mcp-gateway-desktop/spec.md when it lands -->

### Scenario: launch at login

- **Given** the user has enabled launch-at-login in settings
- **When** the user logs back into their machine
- **Then** Coffer starts in the background and the system tray icon appears

### Scenario: close to tray, not exit

- **Given** Coffer is running with the main window open
- **When** the user closes the window
- **Then** the window hides, the daemon and tray icon remain, and any MCP client can still use coffer; reopening the window from the tray shows the same state

---

## Out of Scope

- Implementation of the skills / knowledge bases / memory / channels / agents resource kinds — each is a separate future spec. They are not shown in the navigation until their feature ships.
- Implementation of the **Chat experience** — conversing with any agent Coffer manages, and aggregating direct + channel conversation history in one place — is a future spec; the Chat entry is not shown until then.
- The **agent dual-role provider toggle** (exposing a registered agent as a callable capability to other agents) — described in the IA section as the rationale for the model, but built as part of the future `agent` kind spec.
- The Observability **Invocations** (cross-server call view) and **Metrics** (health / latency / error-rate) views — planned to join Observability later; each is a future increment, not shown until built. The per-server Invocations tab on the MCP server detail page is unaffected and remains operational.
- An in-app "connect a client" guide — the MCP-client config snippets (Claude Code / Claude Desktop / Cursor) are static and live in the project README, not the UI. The shim self-discovers the daemon, so the snippets need no per-machine parameterisation.
- Theme switching (light / dark) — the redesigned visual language is intentionally light-only for now. A dark theme is a future spec.
- Mobile responsive layout — the sidebar collapses gracefully below 1024 px but mobile-first design is deferred.

## Success Criteria

- Every scenario above has at least one covering test (unit, integration, or e2e) and the `audit_acceptance` script passes 002 alongside 001.
- A first-time user can register an MCP server and reach a working gateway in-app; pointing an MCP client at the shim is documented in the project README.
- The sidebar shows only operational surfaces (MCP servers, Observability, Settings); no planned-but-unbuilt feature appears as a dead "soon" entry.
- Observability provides the redesigned audit log filter + table; the legacy `/audit` URL still resolves.
- Settings groups data controls (retention, prune, backup) under a Data tab; the daemon is never surfaced as a user-facing concept, and no tab exposes a shutdown or token-rotation control.
- The Tauri desktop shell supervises the daemon, runs in the system tray, and supports launch-at-login.
- `make verify` + `make verify-e2e` are green.
