# Frontend — React / TypeScript / Vite

Coffer's frontend is the daemon-served web UI (`frontend/`): built to static
assets that the daemon serves at its own loopback origin in production, and
run from the Vite dev server (`make dev`) in development with `COFFER_DEV_CORS`
opted in. This file is the engineering convention for that surface — the
counterpart to [`stack.md`](./stack.md) (backend) and
[`visual-language.md`](./visual-language.md) (visual design).
Read it before touching `frontend/src`.

If this file and the code disagree, the code that matches the **canonical**
column below wins; fix the outlier. If a rule here blocks you, stop and raise
it — do not invent a parallel pattern.

## 1. Stack

- **React 18 + TypeScript 5** (strict), **Vite** build, **React Router v6**.
- **TanStack Query v5** for all server state. No Redux / Zustand / MobX.
- **openapi-typescript** generates wire types from every spec's OpenAPI
  contract, and that contract is itself generated from the backend's Pydantic
  models; **openapi-fetch** is the typed client over every capability's paths
  (`src/lib/api/types.ts` merges them), and one shared hand-written `call<T>()`
  transport helper serves the modules not yet moved onto it (§4, §9).
- **shadcn/ui + Radix + Tailwind** for the design system (§6), themed by the
  Foundations tokens in `src/index.css` (light and dark).
- **react-hook-form + zod** for forms, **i18next** for copy, **lucide-react**
  for icons.

Feature-specific libraries are added by the spec that first needs them
(e.g. a markdown renderer), not pre-installed.

## 2. Folder Structure (canonical)

One scheme. A feature `X` lives in exactly these places:

```
src/pages/XPage.tsx              — list/index page; XDetailPage.tsx for detail
src/components/x/                 — feature components, dialogs, tables (PascalCase files)
src/lib/hooks/useX.ts            — ALL queries + mutations for X (see §3)
src/lib/api/x.ts                 — wire types + request functions for /api/v1/x
src/lib/api/queryKeys.ts         — every query key builder (see §3)
src/lib/x/                       — pure helpers a feature owns (parsers, filters)
src/i18n/locales/{en,zh}.json    — under the top-level "x" key
```

- **One documented naming exception**: the MCP-server list page is
  `pages/ResourcesPage.tsx` (with `ResourceDetailPage.tsx`), routed at
  `mcp-servers` in `router.tsx` — there is no `McpServersPage.tsx`. It kept the
  generic name from when the page was the resource index; a new feature follows
  the scheme above.
- **Data fetching lives in a hook file, never inline in a component.** A page or
  component calls `useX()`; it does not call `useQuery`/`useMutation` directly.
  (`lib/hooks/useKnowledge.ts` is the shape to copy: every query and mutation
  for the feature in one file.)
- **Every feature uses this layout, resource kinds included.** There is no
  per-kind registry and no `src/kinds/`: the MCP, knowledge, memory and channel
  UIs are ordinary `pages/` + `components/<kind>/` + `lib/hooks/useX.ts` +
  `lib/api/x.ts` sets, and `router.tsx` routes to their pages directly.
- Pages are code-split at the route (`lazyPage()` in `router.tsx`): the list
  pages a user lands on are eager, every detail page and every surface that
  pulls in the editor / highlighter / markdown pipeline loads on first visit.
  A new heavy page goes through `lazyPage()`; the vendor graphs it pulls in are
  named in `vite.config.ts` `manualChunks`.
- UI primitives live in `src/components/ui/` (shadcn). Cross-feature helpers go
  in `src/lib/`. Three already exist — reuse them, do not re-derive:
  - `lib/reachFilter.ts` — the one "Reach" filter every scoped list offers
    (MCP servers, skills, knowledge, memory, providers).
  - `lib/agents/display.ts` — the human-readable forms of agent wire values
    (product name for a registry key, home-relative path), shared by the
    table, the add form and the detail header.
  - `lib/chat/turnErrors.ts` — copy for a failed chat turn: pure mapping from
    error shape to actionable text, unit-tested without a component.
- **The app shell** (docs-site `architecture/app-shell.md`) has one home per concern:
  - `lib/navigation.ts` — the one list of sidebar entries (`NAV_GROUPS`) and
    Settings tabs (`SETTINGS_TABS`); the sidebar, the palette's Pages group and
    the Settings modal all read it. A new entry or tab is added here, nowhere else.
  - `lib/settingsModal.ts` — `useOpenSettings`, `useCloseSettings`,
    `usePageLocation` (the background page under the modal). Open Settings only
    through it, never with a hand-built `navigate("/settings/…")`.
  - `components/palette/` — the palette: navigation only; objects come from
    each kind's existing list hook, never an aggregate route.
  - `components/shell/` — `SidebarFooter` (Settings row, daemon state,
    language); `useDaemonFooterState` reads the same `useDaemonStatus` poll as
    `DaemonOfflineBanner` (no second timer); `AttentionDot`, fed by
    `lib/hooks/useAttentionSignals.ts` — a kind that declares an attention
    signal adds its hook to that map, keyed by its entry's route.
  - `components/SplitView` / `SplitDivider` + `lib/hooks/useResizableWidth.ts`
    for every resizable split; widths are per-browser conveniences.
  - `components/PlaceholderPage` — temporary, for sidebar pages not yet built.
  - `lib/events/eventStream.ts` + `lib/hooks/useDaemonEvents.ts` — the one reader of
    the daemon's change feed (`GET /api/v1/events`): reconnects with `Last-Event-ID`,
    backs off while the daemon is down, invalidates the keys each envelope's kind is
    read through (`attention` → `attentionKey`, `resync` → everything). A page that
    shows live state mounts `useDaemonEvents()` instead of polling; Overview and
    Activity do.

## 3. State Management

| State kind                                                      | Where it lives                                          |
| --------------------------------------------------------------- | ------------------------------------------------------- |
| Server data (anything from the daemon)                          | TanStack Query, via a `useX` hook                       |
| Ephemeral UI state (open/collapsed, draft input)                | local `useState` in the component                       |
| User preference that must survive reload                        | `localStorage` via `src/lib/preferences.ts`             |
| **Addressable** app state (which conversation/resource is open) | the **URL** (router param), not `useState`              |
| Detail-page tab                                                 | the **path** (`/<kind>/<id>/<tab>`) via `useDetailTab` (`lib/detailTabs.ts`) |
| Selected file; tab on a page not yet rebuilt                    | the **URL search param** (`?file=`, `?tab=`) via `useSearchParams` |

The API token is deliberately not in that table: it is read from
`window.__COFFER_TOKEN__`, injected into the served page by whoever served it
(`src/lib/auth.ts`). Persisting it would outlive the daemon that minted it.

The URL rows matter: anything a user would expect to survive a refresh, deep-link,
or back-button MUST be a route param (`/conversations/:id`, `/agents/:type`), not local
state. "Which item is selected" is navigation, not UI state. The same holds one
level down. A detail page's tab lives in the path — `/<kind>/<id>` for the
default tab, `/<kind>/<id>/<tab>` otherwise — through `useDetailTab`
(`lib/detailTabs.ts`), which also redirects old `?tab=` links; skills and MCP
servers are keyed by their fixed name, agents by their type, renamable kinds
by uid. Skills, MCP servers, model providers, agents, knowledge
(`/knowledge/<uid>/history`, `/knowledge/<uid>/inbox`) and memory partitions
(`/memory/<uid>/delivered`) follow it; Sync and Activity still use `?tab=`
until their rebuild, and the open file in a tree is always `?file=`. The default tab is never spelled out (`/overview`, `?tab=overview`).

There is no global store. Cross-component server data is shared through the
query cache (same query key → same data), not through Context. The only Context
providers are `QueryClientProvider`, `ToastProvider` and the `TooltipProvider`
that `Layout` mounts once for the Tooltip primitive.

### Query keys

Every key is built by `src/lib/api/queryKeys.ts` — one module, one builder per
query, hierarchical arrays whose first segment is the feature noun. A
detail/sub-resource extends the parent key so a prefix invalidation catches the
whole subtree:

```text
["agents"]                       // list
["agents", uid]                  // one agent
["agents", uid, "config-files"]  // a sub-resource of that agent
```

- **No literal key arrays at call sites.** `queryKey: ["…"]` outside
  `queryKeys.ts` is an ESLint error (`no-restricted-syntax` in
  `eslint.config.js`); hooks import the builder.
- **Do NOT use flat hyphenated keys** (`["knowledge-documents", path]`) — they
  cannot be invalidated as a group. A key that spans two features
  (`["settings", "credentials"]`) nests under the feature that owns the page.
- A hook file may re-export the builders it uses for its tests; new code
  imports from `queryKeys.ts` directly.

## 4. API Layer

Every request leaves through one of two modules, and both resolve base URL +
token through `src/lib/auth.ts` (`getCofferBaseUrl`, `getCofferToken`) and send
`X-Coffer-Token` + `X-Coffer-Actor: "ui"`. **The actor is always `"ui"`** from
the web surface. Nothing else in `src` calls `fetch` — the only exceptions are
the two SSE readers: the chat stream (below) and the daemon's change feed
(`lib/events/eventStream.ts`).

- **Generated types for every contract.** `npm run codegen`
  (`frontend/scripts/codegen.mjs`) runs openapi-typescript over each
  `openspec/specs/*/contracts/api.openapi.yaml` into `src/lib/api/generated/<spec>.ts`
  — every contract that has one (the `CONTRACTS` array in `codegen.mjs` is the
  list); `src/lib/api/types.ts` re-exports the
  mcp-gateway one so `components["schemas"][…]` keeps working. `npm run lint`
  runs `codegen:check` first, so a contract edit without a regenerate fails CI;
  never hand-edit `generated/` (it is prettier-ignored, 4-space indented).
- **Generated client** (`getApiClient()` over `src/lib/api/client.ts`) over
  every capability's paths (keyed without the `/api/v1` prefix the base URL
  carries) — full path/response type safety. New request functions use it.
- **One hand-written helper** — `call<T>(path, { method, body })` in
  `src/lib/api/call.ts` (URL building, headers, 204 → `undefined`,
  `{error:{code,message,details}}` → `ApiError`, `FormData` bodies). Every
  other `src/lib/api/x.ts` module is request functions over `call` plus its
  wire types, which are aliases of the generated schema
  (`export type Provider = components["schemas"]["ProviderOut"]`). No wire type
  is hand-written: when the contract is narrower than what the backend really
  sends, the fix is in the backend model (and the contract regenerated from
  it), not a hand-written interface. Types that exist only in the UI and never
  cross the wire are fine. Do not add a second helper.
- **Direction.** Pydantic models → generated `contracts/api.openapi.yaml` →
  generated client (Principles, "II. Spec-as-Truth"; ADR
  `docs/decisions/wire-contract-generated-from-the-pydantic-models.md`). The
  contracts are regenerated with `make contracts` (models → contracts →
  `generated/`). `codegen:check` (in `npm run lint`) also runs
  `scripts/check-wire-types.mjs`: an exported `interface`, or an exported
  `type` spelling an object shape, in a `src/lib/api/*.ts` module fails unless
  it carries a `@ui-only` JSDoc tag (it never crosses the wire) or is listed in
  `scripts/wire-types-allowlist.json` — the pre-generator debt the UI rebuild
  removes page by page (§9). The gate fails on a stale allow-list entry too.
  Never add to the allow-list.

All errors converge on `ApiError(code, message)` (`src/lib/api/errors.ts`).
Surface them with `translateApiError(t, error)`, which maps `errors.<CODE>`
i18n keys with the server message as fallback. Never show a raw error string.

Streaming (chat SSE) is the one path outside TanStack Query: a typed
async-generator in `src/lib/chat/streamClient.ts`. Keep wire-event parsing
there; accumulate into view state in a hook (`useChatTurn` + the reducer in
`lib/hooks/chatTurnEvents.ts`), not in components — the optimistic echo of a
sent prompt included, so the thread has one source of truth.

## 5. Mutations & Cache Invalidation

Default pattern — invalidate on success, toast on error:

```ts
return useMutation({
  mutationFn: (vars) => agentsApi.patch(vars.uid, vars.body),
  // `agentsKey` is the prefix of `agentKey(uid)`, so this also refreshes the detail query.
  onSuccess: () => void qc.invalidateQueries({ queryKey: agentsKey }),
  onError: (e) => toast.error(translateApiError(t, e)),
});
```

- **`onError` → toast is the default**, not optional. The only hooks without
  one render the failure inline themselves (a form's error line) — say so in a
  comment when you leave it out.
- **Optimistic `setQueryData`** only where the latency is user-visible and the
  shape is trivially patchable (e.g. rename, model switch). Always invalidate
  after, so the server stays authoritative.
- **Delete** removes the detail + sub keys (`removeQueries`) then invalidates the
  list, so a stale detail view can't refetch a 404.
- Bulk/table actions go through `src/lib/hooks/useBulkMutate.ts` (one summary
  toast + one invalidation burst), never a per-row toast loop.
- Prefix `qc.invalidateQueries(...)` calls with `void` (they're fire-and-forget).
- **Delete confirmations use `ConfirmDialog`** (`components/ui/confirm-dialog.tsx`,
  never `window.confirm`). The dialog closes only in the mutation's `onSuccess`
  and receives `pending` while the mutation runs, so a failed delete stays open
  with its error instead of vanishing as if it had worked.

## 6. Components & Design System

- **Build from `src/components/ui/` primitives** (shadcn: `Button`, `Dialog`,
  `Select`, `Textarea`, `Tooltip`, `Skeleton`, `ConfirmDialog`, …). Don't
  hand-roll a control a primitive already covers — no native `title=` hints
  where `Tooltip` fits, no bespoke pulsing block where `Skeleton` does. Row actions
  are explicit buttons (`RowDeleteButton`, `ScopeControl`); the one "⋯" menu is
  `ActionMenu` (`components/ui/menu.tsx`, over `Popover`), used where the design
  gives an object a menu of secondary commands (an agent's row and header).
  There is no `DropdownMenu`.
- **Shared surfaces above the primitives**, used the same way everywhere:
  - `PageHeader` is the one page header, list and detail alike: `icon` (list
    pages), `back` (detail pages), `badges` beside the title, `actions` on the
    right. Detail-page actions keep one fixed order: reach → test/refresh →
    edit → delete.
  - `DataTable` is the one list table. Pass `isLoading` so the header stays
    mounted over skeleton rows (never a "Loading…" card in the table's place)
    and `emptyAction` for the call-to-action under the empty message. The reach
    column's header key is `resources.cols.reach` on every table.
  - Every button inside a table — row actions and selection-bar actions
    alike — is a `TableActionButton` (`components/table/`): small outline
    button, icon + text label, `destructive` for anything that removes. Row
    delete is `RowDeleteButton`, bulk delete `BulkDeleteButton`, both built on
    it. No ghost, solid or text-only buttons in a table.
  - `EmptyState` is the shared "nothing here yet" card (icon, title,
    description, action).
  - `Button` icon sizes are `icon-sm` / `icon-md` (plus the default `icon`);
    pick from those, do not size an icon button by hand.
- **A resource shows its `title` when set, its `name` otherwise** — in tables,
  headers and pickers alike. An MCP server's and a skill's name is fixed once
  registered (the daemon answers `409 NAME_IMMUTABLE`), so their edit forms
  offer the title, not a rename; every other kind keeps a name field.
- **Dates always go through `formatDateTime`** (`src/lib/utils`) — never a raw
  `toLocaleString`, so every timestamp reads the same.
- **Named exports only.** `export function Foo()`. No default exports.
- **File header comment**: first line `// src/path` + one line of purpose.
- **`cn()`** (`src/lib/utils`) for conditional classes. No inline `style` except
  a documented theming bridge.
- **Theme roles only** (`bg-surface-raised`, `text-text-muted`,
  `border-border-subtle`, `text-danger`; the shadcn names such as
  `text-muted-foreground` are aliases and still work). No colour literal — hex,
  `rgb()`/`hsl()`, Tailwind palette classes — outside `src/index.css`;
  `scripts/check_frontend_colors.py` fails `make lint` on one. `accent` is the
  indigo (action, focus, selection); hover is `bg-surface-hover`. Health/status
  colour comes only from `src/lib/statusColors.ts` and the `StatusWord` /
  `StatusPill` components, which map a tone onto the `success|warning|danger|
  neutral` roles — components never pick a status colour themselves.
- **Type and radius from the scale** — `text-2xs`…`text-xl` (13px base; see
  [`visual-language.md`](./visual-language.md)), never `text-[11px]`; radius
  from the Foundations set (`rounded-md` controls, `rounded-xl` cards,
  `rounded-2xl` dialogs, `rounded-sm` chips).
- **Light and dark, no `dark:` variants.** Roles are re-pointed under
  `<html data-theme="dark">` (`src/lib/theme.ts` resolves System / Light /
  Dark), so a component that uses roles is already themed. A `dark:` utility is
  a bug: it forks one component into two looks.
- **Show an agent with `AgentBadge`** (its official mark on a neutral tile),
  never initials or a per-agent colour; list agents in the Agents page's order.
- Keep files focused; a component growing past a few hundred lines is a signal to
  split. One component per file, test colocated (§8).

## 7. TypeScript & i18n

- **strict** + `noUnusedLocals/Parameters`. **Zero `any`** in `src` (not lint-
  enforced — discipline). Use `unknown` + narrowing instead.
- `interface` for props/object shapes, `type` for unions/aliases. Type-only
  imports use `import type`.
- Props: a local `interface Props { … }` destructured in the signature; JSDoc
  the non-obvious ones.
- **Every user-facing string goes through `t(...)`.** No hardcoded copy, no
  hardcoded aria-labels.
- Keys are nested camelCase dotted paths under a feature namespace
  (`chat.composer.placeholder`). **en and zh stay at exact key parity** — add to
  both in the same change; `src/i18n/locales.test.ts` guards it.

### en/zh glossary

One name per surface everywhere (spec web-ui "Call a surface by one name everywhere"):

| English | 中文 | English | 中文 |
| --- | --- | --- | --- |
| Overview | 总览 | Custom tools | 自定义工具 |
| Agents (group, entry) | 智能体 | Skills | 技能 |
| Model providers | 模型提供商 | CLIs | 命令行工具 |
| Run (group) | 运行 | Context (group) | 上下文 |
| Conversations | 对话 | Knowledge | 知识 |
| Channels | 消息渠道 | Memory | 记忆 |
| Capabilities (group) | 能力 | System (group) | 系统 |
| MCP servers | MCP 服务器 | Secrets | 密钥 |
| Activity | 活动 | Usage | 用量 |
| Sync | 同步 | Settings | 设置 |

In zh an agent is always **智能体** — never "Agent" or 代理.

## 8. Testing

- **Vitest + Testing Library**, `*.test.tsx` colocated next to the unit.
- Test **behaviour through the component/hook**, not implementation. Render with
  a real `QueryClientProvider`; mock only the network boundary (the `api`
  module or `streamClient`).
- A new component or hook ships with its test in the same commit. Acceptance-
  scenario coverage follows [`testing.md`](./testing.md) markers.
- Run `cd frontend && npx vitest run <file>` for a focused check; `make verify`
  runs the suite + lint + tsc.

## 9. Convergence Backlog (known debt → target state)

When you work near these, migrate toward the target; don't extend the debt:

1. **Hand-written wire types on the allow-list.** `scripts/wire-types-allowlist.json`
   names every wire type still declared by hand in `src/lib/api/`. When a
   page is rebuilt, replace each of its types with an alias of the generated
   schema (fixing the backend model first if the contract is not what the wire
   carries) and delete the entry. The daemon-wide change feed
   (`GET /api/v1/events`, fetch-read with the token header like the chat
   stream) is the replacement for per-hook `refetchInterval` polling: a
   rebuilt page mounts `useDaemonEvents()`, which invalidates the query keys an
   envelope's `kind` names. The audit and MCP call logs are not on it (they are
   not resources), so Activity re-reads their newest page on a short poll.
2. **The `codemirror` vendor chunk (~590 kB)** is one file; split the language
   modes out of it if a page that needs only one mode becomes a landing page.
