# Implementation Plan: UI Shell & Visual Language

**Spec**: [./spec.md](./spec.md)
**Status**: Accepted

## Summary

Turn the bare functional skeleton that shipped with `mcp-gateway` into a
real product shell: a coherent visual language, a role-based information
architecture (Agents / Resources / System) decided in
[Everything Is a Resource Kind](../../docs/decisions/everything-is-a-resource-kind.md) (assets are resource kinds; agents are a separate consumer axis),
and end-to-end flows that make the gateway usable for a first-time visitor.

It adds **no backend surface of its own**. Every screen renders over REST
routes another spec owns, and the entities behind them are documented where
they are owned: the kind-agnostic ones (`Resource` — its `scope` field
included — `Kind`, `AuditEntry`, `MCPInvocation`, `RetentionPolicy`) in
[`specs/mcp-gateway/data-model.md`](../mcp-gateway/data-model.md), and each
kind's own config in that kind's spec. The **reach** control this spec
specifies more than any other element is a view of exactly two of those
fields — `Resource.enabled` and `Resource.scope` — read and written through
`GET`/`PUT /resources/{kind}/{name}/scope`; its wire shapes are `ScopeOut`,
`ResourceScopeOut` and `ResourceScopeUpdate` in
[`specs/mcp-gateway/contracts/api.openapi.yaml`](../mcp-gateway/contracts/api.openapi.yaml).
It belongs there rather than here because scope is a property of the
resource framework, not of the UI; this spec owns only how it is presented.
For the same reason there is no separate `tasks.md` tracker in this folder —
the work is structured around the user stories in [spec.md](./spec.md)
`## User Scenarios & Testing`.

See [./spec.md](./spec.md) for the user-visible contract,
[./quickstart.md](./quickstart.md) for the end-user walkthrough, and
[Everything Is a Resource Kind](../../docs/decisions/everything-is-a-resource-kind.md) for the IA decision.

## Technical Context

| Dimension                | Value                                                                                                                                                                                                                                                                                |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Language / Version**   | TypeScript 5.x, React 18                                                                                                                                                                                                                                                             |
| **Primary Dependencies** | React 18 + Vite 5; TanStack Query 5 for server state; React Router 6 for routing; Tailwind CSS 3 + shadcn/ui (Radix-based primitives) for visual language; react-i18next + i18next for i18n; react-hook-form + zod for forms; openapi-typescript + openapi-fetch for the API client. |
| **Backend dependency**   | Pure consumer of the REST contract in [`specs/mcp-gateway/contracts/api.openapi.yaml`](../mcp-gateway/contracts/api.openapi.yaml). No new endpoints; no schema changes.                                                                                                      |
| **Storage**              | Browser localStorage only — sidebar collapsed state, selected language. No client-side persistence of user data.                                                                                                                                                                     |
| **Testing**              | `vitest` for unit/component tests; `Playwright` for e2e in `e2e/`. Acceptance markers (`acceptance("ui-shell", "…", …)`) bind tests to scenarios in [spec.md](./spec.md); coverage audited by `scripts/audit_acceptance.py`.                                                     |
| **Target Platforms**     | Modern evergreen browsers (Chromium / Firefox / Safari current-2).                                                                                                                                                                                                                   |
| **Project Type**         | SPA bundled by Vite; served by the daemon's static file route in production, served by `vite dev` against the daemon in development.                                                                                                                                                 |
| **Performance Goals**    | First content paint within 2 s on a cold load against a local daemon (spec's `cold-start renders authenticated content` scenario). Language switch on the very next render — no full page reload.                                                                                    |
| **Constraints**          | Local-first (the only HTTP origin is the daemon on `127.0.0.1:<port>`); no public-internet calls; no third-party analytics; no font CDN. Frontend component file size ≤ 250 LOC (enforced by `scripts/check_file_sizes.py`).                                                         |
| **Scale / Scope**        | Single-user; ≤ 30 registered resources; ≤ 100 capabilities per server (consistent with `mcp-gateway` plan limits).                                                                                                                                                               |

## Constitution Check

| Constitutional clause                     | Compliance | Notes                                                                                                                                                |
| ----------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **I. Local-First (NON-NEGOTIABLE)**       | OK         | Only HTTP origin is the local daemon; bundled assets are self-hosted; no CDN fonts; no analytics.                                                    |
| **II. Spec-as-Truth**                     | OK         | This plan implements [spec.md](./spec.md); spec committed before code. Each acceptance scenario has at least one covering test (acceptance audit).   |
| **III. Open-Source-Readiness**            | OK         | Tailwind / shadcn / Radix / TanStack Query / React are all permissive-licensed and in the existing dependency set spec mcp-gateway introduced.                 |
| **Languages**                             | OK         | TypeScript 5 only; no new languages.                                                                                                                 |
| **Architecture: layered**                 | OK         | Frontend folder layout mirrors the layer-first convention: `lib/` (cross-cutting), `kinds/<kind>/` (per-kind UI), `pages/` (compose into routes).    |
| **Persistence: SQLite for control plane** | OK         | This spec does not own persistence; the daemon does.                                                                                                 |
| **Credentials: encrypted store**          | OK         | The Add-MCP-server dialog posts to `/api/v1/credentials` for secret env values; the UI never persists credentials locally.                           |
| **Network defaults: loopback-only**       | OK         | The Vite dev server targets `http://127.0.0.1:<port>` from `~/.coffer/daemon.json`; production assets are served by the daemon on the same loopback. |

## Project Structure

### Documentation (this feature)

```text
specs/ui-shell/
├── spec.md           # user-visible contract (committed)
├── plan.md           # this file
└── quickstart.md     # end-user walkthrough (make dev → first server → invocations)
```

This folder deliberately has **no** `data-model.md` — every entity a screen
renders is owned by the spec that owns its behaviour (see Summary) — and **no**
`tasks.md`: the unit of change here is "one redesigned screen", which does not
decompose into an atomic-task TDD breakdown.

### Source code

```text
frontend/src/
├── App.tsx                                # global providers (QueryClient, i18n) + RouterProvider
├── main.tsx                               # bootstrap entry
├── router.tsx                              # createBrowserRouter route table + the legacy redirects
├── i18n/
│   ├── index.ts                            # i18next config
│   └── locales/{en,zh}.json                # one flat catalogue per language
├── lib/
│   ├── api/                                # typed client, per-kind modules, generated/<spec>.ts from each contract
│   ├── hooks/                              # TanStack Query hooks (useResources, useAgents, useScope, …)
│   ├── scope.ts / reachFilter.ts           # the reach control's request + filter logic
│   ├── tauri.ts                            # the desktop host's IPC handshake, absent in a browser
│   ├── auth.ts                             # daemon-token loader (window.__COFFER_TOKEN__, dev plugin, IPC)
│   ├── preferences.ts                      # page-size + preferred-editor preferences (General settings)
│   └── queryClient.ts / statusColors.ts / timeRange.ts / utils.ts
├── components/                             # shared shell + table primitives, and per-kind UI beside them
│   ├── Layout.tsx / SidebarNav.tsx         # AppShell + collapsible sidebar ("coffer.nav.collapsed")
│   ├── PageHeader.tsx / EmptyState.tsx / RawLog.tsx / RowActions.tsx
│   ├── DataTable*.tsx / Pagination.tsx / SearchInput.tsx / TimeRangePicker.tsx
│   ├── ScopeControl.tsx + reach/            # the one reach button, mounted in row, header and bulk bar
│   ├── FileEditor.tsx / FileActions.tsx / preview/   # the shared file viewer-editor
│   ├── DaemonOfflineBanner.tsx / LanguageSwitcher.tsx / PageFallback.tsx
│   ├── ui/ + table/                        # shadcn primitives and table building blocks
│   └── agents/ channel/ chat/ knowledge/ mcp/ memory/ settings/ skills/   # per-kind UI
└── pages/
    ├── ResourcesPage.tsx / McpServerDetailPage.tsx / ResourceDetailPage.tsx   # /mcp-servers, /mcp-servers/:name
    ├── AgentsPage.tsx / AgentDetailPage.tsx / AgentConversationPage.tsx / AgentMemoryStorePage.tsx
    ├── ChatPage.tsx                        # /chat, /chat/:id
    ├── SkillsPage.tsx / SkillDetailPage.tsx
    ├── KnowledgePage.tsx / KnowledgeDetailPage.tsx
    ├── MemoryPage.tsx / MemoryDetailPage.tsx
    ├── ModelProvidersPage.tsx / ProviderDetailPage.tsx
    ├── ChannelsPage.tsx / ChannelDetailPage.tsx
    ├── activity/                           # ActivityPage + ChangesTab / DaemonTab / filters (/audit, /observability redirect here)
    ├── sync/                               # SyncPage + Status / History / Machines tabs
    ├── settings/                           # SettingsLayout + General / Engine="Coffer's model" (+ Upkeep) / Data / Security / About
    └── NotFoundPage.tsx

frontend/
├── vite.config.ts                          # dev-only token-injection plugin (reads daemon.json)
├── scripts/codegen.mjs                     # regenerates lib/api/generated/<spec>.ts from specs/*/contracts
├── tailwind.config.js                      # visual-language tokens (see agents/visual-language.md)
└── components.json                         # shadcn config
```

The `kinds/<kind>/` tree the original plan described is gone with the per-kind
registry below: a kind's list page lives in `pages/`, its components in
`components/<kind>/`.

Every contract the frontend consumes is listed in `frontend/scripts/codegen.mjs`,
and `npm run lint` fails when `lib/api/generated/` is out of step with
`specs/*/contracts/api.openapi.yaml` — so a contract edit and its regenerated
types land in the same change.

### Extension point: one layout per kind (registry retired 2026-09-14)

The plan originally shipped a per-kind UI registry: one registration call
per kind, self-contained modules under `frontend/src/kinds/<kind>/`, a
composition root that imported and registered each one, and a shared list
view the kind-agnostic `ResourcesPage` dispatched through. It was retired on
2026-09-14: only three kinds ever registered, the detail routes bypassed the
registry and dispatched on `kind` directly, and the shared list view had no
callers. What replaced it is a convention, not a mechanism — every kind uses
the same layout: list pages in `pages/`, kind components, dialogs and detail
helpers in `components/<kind>/`, hooks in `lib/hooks/`, API modules and
generated types in `lib/api/` (codegen from every spec's contract into
`lib/api/generated/*.ts`), query keys in `lib/api/queryKeys.ts`, and routes
added lazily via `lazyPage()` in `router.tsx`. `pages/ResourceDetailPage.tsx`
dispatches on `kind` directly. A new kind adds its own files in those places
and nothing else; `agents/frontend.md` is the canonical statement of the
layout.

The backend went the same way the same day: its composition pattern is now a
`make_<kind>_kind()` factory plus one explicit wiring module per kind
([Resource Framework Upfront](../../docs/decisions/resource-framework-upfront.md),
[Layer-First Code Layout](../../docs/decisions/code-layout-layer-first.md)).

### Visual language

The Tailwind config (`frontend/tailwind.config.js`) is the single source of
truth for spacing, typography, and colour tokens. See
[`agents/visual-language.md`](../../agents/visual-language.md)
for the catalogue and the conventions agents should follow when adding new
screens.

### Internationalisation

`react-i18next` with one flat catalogue per language —
`i18n/locales/en.json` and `i18n/locales/zh.json`, one file each, not a
directory of namespaces. The app's English / 中文 switcher is a product
feature and stays; the repo's own documentation being English-only is a
separate decision that does not touch it. Selected language persists in
`localStorage` under `coffer.language`; the sidebar carries the switcher
so it is reachable from every screen. The switch takes effect on the next
render — no full page reload — per the language-switcher acceptance
scenario.

## What the shell is made of

The pieces below are a dependency order, not a schedule.

**The shell itself.** The Tailwind config and the shadcn primitives come first
because everything else is expressed in them. `Layout` + `SidebarNav` render the
three role groups and the collapse state (`localStorage`
"coffer.nav.collapsed"); the language switcher sits in the sidebar so it is
reachable from every screen; `DaemonOfflineBanner` is mounted once, above the
content, because "no daemon" is a condition of the whole app rather than of one
page.

**Two hosts, one frontend, one supplier seam.** The browser gets its token from
the `index.html` the daemon serves; the desktop shell, whose page is a local
asset nobody served, gets it over IPC; the dev server gets it from a Vite
plugin reading `daemon.json`. All three resolve to the same
`window.__COFFER_BASE_URL__` / `window.__COFFER_TOKEN__`, so the frontend gains
a second *supplier*, never a second code path. The only host-conditional UI in
the product is the offline banner's recovery control, and it is conditional
because only one host can actually restart a daemon.

**Every list surface is one table.** Search, filters, pagination, selection and
the bulk bar are the same components everywhere; a kind supplies columns. That
is what makes the reach control possible as ONE component mounted in three
places (row, detail header, bulk bar) rather than three that could drift into
three answers.

**The first-run path is part of the shell, not a page feature.** The index
redirect, the welcome panels, the empty states inside tables and the
"daemon not running" view are all the same requirement: never show a blank or a
generic error where a next action exists.

**Per-kind screens are a convention, not a mechanism** — see the extension
point above.

**Activity and Settings are compositions of routes this spec does not own.**
Activity renders three records through three read-only routes; Settings renders
preferences that live in `localStorage` alongside daemon-side settings routes.
Both are grouping decisions, which is why they belong to this spec at all.

## Complexity Tracking

| Decision                                                    | Why needed                                                                                                                                       | Simpler alternative rejected because                                                                                                                                         |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tailwind + shadcn over plain CSS                            | Visual language consistency is the headline goal of this spec; ad-hoc CSS is exactly the "feels like a scaffold" state US2 fights.               | Plain CSS would re-litigate spacing / typography / colour for every component; shadcn gives us audited Radix primitives without a heavyweight UI framework.                  |
| TanStack Query over raw fetch                               | The audit / invocation / capability tables all need stale-while-revalidate and refetch-on-toggle; rolling our own would re-implement that badly. | Plain fetch would force every page to hand-roll loading / error / refetch state.                                                                                             |
| Per-kind registry — retired 2026-09-14                      | Retired: only three kinds ever registered, the detail routes bypassed the registry and dispatched on `kind` directly, and the shared list view had no callers. | Chosen instead: one layout per kind (`pages/`, `components/<kind>/`, `lib/hooks/`, `lib/api/`) with `ResourceDetailPage` dispatching on `kind` directly — the branch count is the kind count, and nothing shared has to be registered with. |
| Register-first-then-credential ordering in AddMcpServerDialog | Avoids orphan credential entries when registration fails (chosen at impl time; see spec scenario).                                               | Credential-first ordering looked symmetric but leaves dead credential entries on registration failure — orphan cleanup is harder than re-trying registration.                |

## Cross-Reference Index

- Spec contract: [spec.md](./spec.md)
- Quickstart: [quickstart.md](./quickstart.md)
- IA decision: [Everything Is a Resource Kind](../../docs/decisions/everything-is-a-resource-kind.md)
- Resource framework: [Resource Framework Upfront](../../docs/decisions/resource-framework-upfront.md)
- Backend contract (consumed, not owned): [`specs/mcp-gateway/contracts/api.openapi.yaml`](../mcp-gateway/contracts/api.openapi.yaml)
- Kind-agnostic entities (consumed, not owned — `Resource`, its `scope`, `Kind`, `AuditEntry`, `MCPInvocation`, `RetentionPolicy`): [`specs/mcp-gateway/data-model.md`](../mcp-gateway/data-model.md)
- Visual-language reference: [`agents/visual-language.md`](../../agents/visual-language.md)
- Architecture overview: [`.specify/memory/architecture.md`](../../.specify/memory/architecture.md)
- Constitution: [`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)
