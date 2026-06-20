# Implementation Plan: 002 — UI Shell & Visual Language

**Branch**: `feature/002-mcp-gateway-web`
**Spec**: [./spec.md](./spec.md)
**Status**: Accepted

## Summary

Turn the bare functional skeleton that shipped with `001-mcp-gateway` into a
real product shell: a coherent visual language, a role-based information
architecture (Agents / Resources / System) decided in
[ADR-007](../../docs/decisions/ADR-007-everything-is-a-resource-kind.md) (assets are resource kinds; agents are a separate consumer axis),
and end-to-end flows that make the gateway usable for a first-time visitor.

This is a **pure UI redesign on top of 001**: it adds no new backend
surface. Every screen is rendered over the same REST API and CLI that
`001-mcp-gateway` already exposes; the data model (`Resource`, `Kind`,
`Capability`, `AuditEvent`, `Invocation`, `RetentionPolicy`) is unchanged
and lives in [`specs/001-mcp-gateway/data-model.md`](../001-mcp-gateway/data-model.md).
For the same reason there is no separate `tasks.md` tracker in this folder
— the work is structured around the user stories in
[spec.md](./spec.md) `## User Scenarios & Testing` and tracked at the PR
level.

See [./spec.md](./spec.md) for the user-visible contract,
[./quickstart.md](./quickstart.md) for the end-user walkthrough, and
[ADR-007](../../docs/decisions/ADR-007-everything-is-a-resource-kind.md) for the IA decision.

## Technical Context

| Dimension                | Value                                                                                                                                                                                                                                                                                |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Language / Version**   | TypeScript 5.x, React 18                                                                                                                                                                                                                                                             |
| **Primary Dependencies** | React 18 + Vite 5; TanStack Query 5 for server state; React Router 6 for routing; Tailwind CSS 3 + shadcn/ui (Radix-based primitives) for visual language; react-i18next + i18next for i18n; react-hook-form + zod for forms; openapi-typescript + openapi-fetch for the API client. |
| **Backend dependency**   | Pure consumer of the REST contract in [`specs/001-mcp-gateway/contracts/api.openapi.yaml`](../001-mcp-gateway/contracts/api.openapi.yaml). No new endpoints; no schema changes.                                                                                                      |
| **Storage**              | Browser localStorage only — sidebar collapsed state, selected language. No client-side persistence of user data.                                                                                                                                                                     |
| **Testing**              | `vitest` for unit/component tests; `Playwright` for e2e in `e2e/`. Acceptance markers (`acceptance("002-ui-shell", "…", …)`) bind tests to scenarios in [spec.md](./spec.md); coverage audited by `scripts/audit_acceptance.py`.                                                     |
| **Target Platforms**     | Modern evergreen browsers (Chromium / Firefox / Safari current-2).                                                                                                                                                                                                                   |
| **Project Type**         | SPA bundled by Vite; served by the daemon's static file route in production, served by `vite dev` against the daemon in development.                                                                                                                                                 |
| **Performance Goals**    | First content paint within 2 s on a cold load against a local daemon (spec's `cold-start renders authenticated content` scenario). Language switch on the very next render — no full page reload.                                                                                    |
| **Constraints**          | Local-first (the only HTTP origin is the daemon on `127.0.0.1:<port>`); no public-internet calls; no third-party analytics; no font CDN. Frontend component file size ≤ 250 LOC (enforced by `scripts/check_file_sizes.py`).                                                         |
| **Scale / Scope**        | Single-user; ≤ 30 registered resources; ≤ 100 capabilities per server (consistent with `001-mcp-gateway` plan limits).                                                                                                                                                               |

## Constitution Check

| Constitutional clause                     | Compliance | Notes                                                                                                                                                |
| ----------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First (NON-NEGOTIABLE)**       | OK         | Only HTTP origin is the local daemon; bundled assets are self-hosted; no CDN fonts; no analytics.                                                    |
| **II. Spec-as-Truth**                     | OK         | This plan implements [spec.md](./spec.md); spec committed before code. Each acceptance scenario has at least one covering test (acceptance audit).   |
| **III. Open-Source-Readiness**            | OK         | Tailwind / shadcn / Radix / TanStack Query / React are all permissive-licensed and in the existing dependency set introduced by 001.                 |
| **Languages**                             | OK         | TypeScript 5 only; no new languages.                                                                                                                 |
| **Architecture: layered**                 | OK         | Frontend folder layout mirrors the layer-first convention: `lib/` (cross-cutting), `kinds/<kind>/` (per-kind UI), `pages/` (compose into routes).    |
| **Persistence: SQLite for control plane** | OK         | This spec does not own persistence; the daemon does.                                                                                                 |
| **Credentials: encrypted store**          | OK         | The Add-MCP-server dialog posts to `/api/v1/credentials` for secret env values; the UI never persists credentials locally.                           |
| **Network defaults: loopback-only**       | OK         | The Vite dev server targets `http://127.0.0.1:<port>` from `~/.coffer/daemon.json`; production assets are served by the daemon on the same loopback. |

## Project Structure

### Documentation (this feature)

```text
specs/002-ui-shell/
├── spec.md           # user-visible contract (committed)
├── plan.md           # this file
└── quickstart.md     # end-user walkthrough (make dev → first server → invocations)
```

This folder deliberately has **no** `data-model.md` (the data model lives in
spec 001) and **no** `tasks.md` (the work is tracked at the user-story / PR
level — there's no atomic-task TDD breakdown because the unit of change is
"one redesigned screen", which doesn't decompose usefully).

### Source code (delivered in this PR)

```text
frontend/src/
├── App.tsx                                # global providers (QueryClient, i18n) + RouterProvider
├── main.tsx                               # bootstrap entry
├── router.tsx                             # createBrowserRouter route table
├── kinds.ts                               # composition root: registers each kind's UI module
├── i18n/
│   ├── index.ts                           # i18next config
│   └── locales/{en,zh}.json               # one flat catalogue per language
├── lib/
│   ├── api/                               # typed API client + per-resource modules (resources, agents, skills, fs)
│   ├── hooks/                             # TanStack Query hooks (useResources, useAudit, useAgents, …)
│   ├── components/                        # kindRegistry.ts + shared ResourceListView
│   ├── auth.ts                            # daemon-token loader (reads ~/.coffer/daemon.json via dev plugin)
│   ├── preferences.ts                     # default page-size preference (General settings)
│   ├── tauri.ts                           # isTauri() guard for desktop-only surfaces
│   └── queryClient.ts / statusColors.ts / timeRange.ts / utils.ts
├── components/                            # shared shell + table primitives
│   ├── Layout.tsx                         # AppShell + collapsible sidebar (localStorage "coffer.nav.collapsed")
│   ├── LanguageSwitcher.tsx
│   ├── DataTable.tsx / DataCardGrid.tsx / Pagination.tsx / SearchInput.tsx / …
│   ├── DaemonOfflineBanner.tsx
│   ├── agents/                            # agent-kind UI components (spec 004)
│   └── skills/                            # skill-kind UI components (spec 005)
├── kinds/
│   └── mcp/
│       ├── index.tsx                      # MCP_KIND_UI entry registered via kinds.ts
│       ├── McpServersTable.tsx / McpServerDetailPage.tsx / McpServerDetailTabs.tsx
│       └── AddMcpServerDialog.tsx / CapabilityList.tsx / InvocationsTable.tsx / …
└── pages/
    ├── ResourcesPage.tsx                  # /mcp-servers — kind-agnostic dispatcher (/resources redirects here)
    ├── ResourceDetailPage.tsx             # /mcp-servers/:kind/:name
    ├── AgentsPage.tsx / AgentDetailPage.tsx     # /agents, /agents/:name
    ├── SkillsPage.tsx / SkillDetailPage.tsx     # /skills, /skills/:name
    ├── audit/AuditLogPage.tsx             # /audit — audit-log view (/observability redirects here)
    └── settings/                          # SettingsLayout + GeneralSettings, DataSettings, AboutPage

frontend/
├── vite.config.ts                         # dev-only token-injection plugin (reads daemon.json)
├── tailwind.config.js                     # visual-language tokens (see agents/visual-language.md)
└── components.json                        # shadcn config
```

### Extension point: the kind registry

`frontend/src/lib/components/kindRegistry.ts` exposes `registerKindUI`; each
kind ships a self-contained UI module under `frontend/src/kinds/<kind>/` whose
`index.tsx` exports the kind's display label, sidebar icon, and list/detail
components. The composition root `frontend/src/kinds.ts` imports each module
and registers it; the kind-agnostic `ResourcesPage` dispatches by looking up
the registry — no per-kind branches in shared code. A new kind adds its own
module plus one import + `registerKindUI` call in `kinds.ts`; no other shared
file changes.

This is the UI mirror of the backend's `KindModule` composition pattern
established in [ADR-001](../../docs/decisions/ADR-001-resource-framework-upfront.md)
and [ADR-002](../../docs/decisions/ADR-002-code-layout-layer-first.md).

### Visual language

The Tailwind config (`frontend/tailwind.config.js`) is the single source of
truth for spacing, typography, and colour tokens. See
[`agents/visual-language.md`](../../agents/visual-language.md)
for the catalogue and the conventions agents should follow when adding new
screens.

### Internationalisation

`react-i18next` with two catalogues (`locales/en/*.json`,
`locales/zh/*.json`). Selected language persists in
`localStorage` under `coffer.language`; the sidebar carries the switcher
so it is reachable from every screen. The switch takes effect on the next
render — no full page reload — per the language-switcher acceptance
scenario.

## Phases (high-level)

Phases are **delivery boundaries**, not atomic-task breakdowns. They map to
the user-story priorities in [spec.md](./spec.md).

### Phase 1 — Visual language + AppShell (foundational)

Tailwind config (`frontend/tailwind.config.js`), shadcn primitives,
`AppShell` (sidebar + main content area), `Sidebar` / `SidebarGroup`,
language switcher, `DaemonOfflineBanner`, the i18n catalogues, the
openapi-fetch client and the dev-only token-injection plugin.

**Done when:** the AppShell renders against a running daemon, the sidebar
collapses + restores from localStorage, the language switcher round-trips
English ↔ 中文, and the daemon-offline banner appears when the daemon is
unreachable.

### Phase 2 — US1: First-time-visitor flow

Welcome view on `/mcp-servers` when no resources are registered (and the
Agents welcome on `/agents`, the index landing), the "Daemon not running"
view with a Reload recovery affordance (Restart in the desktop app), the
cold-start authenticated render via the dev token plugin.

**Done when:** US1's three representative scenarios pass.

### Phase 3 — US2: MCP day-to-day flows

`AddMcpServerDialog` (JSON-import, secret-env review step,
register-first-then-credential ordering — see spec scenario), the redesigned
server list (search / status filter / pager), the server detail page
(Overview / Tools / Resources / Prompts / Invocations tabs, where an
invocation row expands to its raw log JSON), capability toggles, the
redesigned empty / error / loading states.

**Done when:** US2's representative scenarios pass and `make verify-e2e`
green for the MCP flows.

### Phase 4 — US3: Audit log

`/audit` route with the audit-log view (filter bar, paged table,
a row that expands to its raw log JSON — the shared `RawLog` view also used
by the invocation log), legacy `/observability` → `/audit` redirect.
(Observability — system health / metrics — is a distinct future surface, not
this audit-log view.)

**Done when:** US3's representative scenarios pass.

### Phase 5 — US4: Settings reorganisation

Settings tabs sidebar, `DataSettings` (retention + prune + backup),
`AboutSettings`, removal of the Shutdown / Rotate-token / Daemon-status /
duplicate-language-picker / kind-list controls.

**Done when:** US4's representative scenarios pass.

### Phase 6 — Polish + verify

Acceptance audit, `make verify`, `make verify-e2e`, manual cross-browser
smoke, language QA pass.

**Done when:** `audit_acceptance: OK` for spec 002 and CI green.

## Complexity Tracking

| Decision                                                    | Why needed                                                                                                                                       | Simpler alternative rejected because                                                                                                                                         |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tailwind + shadcn over plain CSS                            | Visual language consistency is the headline goal of this spec; ad-hoc CSS is exactly the "feels like a scaffold" state US2 fights.               | Plain CSS would re-litigate spacing / typography / colour for every component; shadcn gives us audited Radix primitives without a heavyweight UI framework.                  |
| TanStack Query over raw fetch                               | The audit / invocation / capability tables all need stale-while-revalidate and refetch-on-toggle; rolling our own would re-implement that badly. | Plain fetch would force every page to hand-roll loading / error / refetch state.                                                                                             |
| Per-kind registry (`kindRegistry.ts`)                       | Future kinds plug in without touching shared code; mirrors the backend's `KindModule` pattern.                                                   | Per-kind `if (kind === "mcp_server") { … }` branches inside `ResourcesPage` would grow linearly with kind count and re-litigate the kind-agnostic invariant on every screen. |
| Register-first-then-credential ordering in AddMcpServerDialog | Avoids orphan credential entries when registration fails (chosen at impl time; see spec scenario).                                               | Credential-first ordering looked symmetric but leaves dead credential entries on registration failure — orphan cleanup is harder than re-trying registration.                |

## Cross-Reference Index

- Spec contract: [spec.md](./spec.md)
- Quickstart: [quickstart.md](./quickstart.md)
- IA decision: [ADR-007](../../docs/decisions/ADR-007-everything-is-a-resource-kind.md)
- Resource framework: [ADR-001](../../docs/decisions/ADR-001-resource-framework-upfront.md)
- Backend contract (consumed, not owned): [`specs/001-mcp-gateway/contracts/api.openapi.yaml`](../001-mcp-gateway/contracts/api.openapi.yaml)
- Backend data model (consumed, not owned): [`specs/001-mcp-gateway/data-model.md`](../001-mcp-gateway/data-model.md)
- Visual-language reference: [`agents/visual-language.md`](../../agents/visual-language.md)
- Architecture overview: [`.specify/memory/architecture.md`](../../.specify/memory/architecture.md)
- Constitution: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
