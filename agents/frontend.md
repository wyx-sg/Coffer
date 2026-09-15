# Frontend — React / TypeScript / Vite

> 中文版: [frontend.zh.md](./frontend.zh.md)

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
  contract; **openapi-fetch** is the typed client for the mcp-gateway paths and
  one shared hand-written `call<T>()` covers the rest (§4).
- **shadcn/ui + Radix + Tailwind** for the design system (§6).
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
  in `src/lib/`.

## 3. State Management

| State kind                                                      | Where it lives                                          |
| --------------------------------------------------------------- | ------------------------------------------------------- |
| Server data (anything from the daemon)                          | TanStack Query, via a `useX` hook                       |
| Ephemeral UI state (open/collapsed, draft input)                | local `useState` in the component                       |
| User preference that must survive reload                        | `localStorage` via `src/lib/preferences.ts`             |
| **Addressable** app state (which conversation/resource is open) | the **URL** (router param), not `useState`              |

The API token is deliberately not in that table: it is read from
`window.__COFFER_TOKEN__`, injected into the served page by whoever served it
(`src/lib/auth.ts`). Persisting it would outlive the daemon that minted it.

The last row matters: anything a user would expect to survive a refresh, deep-link,
or back-button MUST be a route param (`/chat/:id`, `/agents/:name`), not local
state. "Which item is selected" is navigation, not UI state.

There is no global store. Cross-component server data is shared through the
query cache (same query key → same data), not through Context. The only Context
providers are `QueryClientProvider` and `ToastProvider`.

### Query keys

Every key is built by `src/lib/api/queryKeys.ts` — one module, one builder per
query, hierarchical arrays whose first segment is the feature noun. A
detail/sub-resource extends the parent key so a prefix invalidation catches the
whole subtree:

```text
["agents"]                       // list
["agents", name]                 // one agent
["agents", name, "config-files"] // a sub-resource of that agent
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
the web surface. Nothing else in `src` calls `fetch` — the only exception is
the chat SSE stream (below).

- **Generated types for every contract.** `npm run codegen`
  (`frontend/scripts/codegen.mjs`) runs openapi-typescript over each
  `specs/*/contracts/api.openapi.yaml` into `src/lib/api/generated/<spec>.ts`
  — six of the seven today; `skill-manager` joins the list once its contract
  defines the `ErrorOut` schema it references (§9.1); `src/lib/api/types.ts` re-exports the
  mcp-gateway one so `components["schemas"][…]` keeps working. `npm run lint`
  runs `codegen:check` first, so a contract edit without a regenerate fails CI;
  never hand-edit `generated/` (it is prettier-ignored, 4-space indented).
- **Generated client** (`getApiClient()` over `src/lib/api/client.ts`) for the
  mcp-gateway paths — full path/response type safety.
- **One hand-written helper** — `call<T>(path, { method, body })` in
  `src/lib/api/call.ts` (URL building, headers, 204 → `undefined`,
  `{error:{code,message,details}}` → `ApiError`, `FormData` bodies). Every
  other `src/lib/api/x.ts` module is request functions over `call` plus its
  wire types, which alias the generated schema where the contract matches
  (`export type Provider = components["schemas"]["ProviderOut"]`) and stay
  hand-written — with a comment saying why — only where the contract is
  narrower than what the backend really sends. Do not add a second helper.

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
  mutationFn: (vars) => xApi.update(vars),
  onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.x.all() }),
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

## 6. Components & Design System

- **Build from `src/components/ui/` primitives** (shadcn: `Button`, `Dialog`,
  `Select`, `Textarea`, …). Don't hand-roll a control a primitive already covers.
- **Named exports only.** `export function Foo()`. No default exports.
- **File header comment**: first line `// src/path` + one line of purpose.
- **`cn()`** (`src/lib/utils`) for conditional classes. No inline `style` except
  a documented theming bridge.
- **Semantic tokens only** (`text-muted-foreground`, `bg-card`, `border-border`).
  Health/status surfaces use the `status.ok|warn|err` tokens — **not** raw
  `green/amber/emerald` palette classes. (`statusColors.ts`, `ToolCallCard`
  currently bypass this — fix on touch.)
- **Type scale only** — `text-sm`/`text-xs`/… never `text-[11px]`. Radius from
  the prescribed set (`rounded-lg` cards, `rounded-md` controls, `rounded-sm`
  chips). See [`visual-language.md`](./visual-language.md).
- **Light-only.** Do not add `dark:` variants — there is no dark token set; they
  are dead styles.
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

1. **`specs/skill-manager/contracts/api.openapi.yaml` defines no `ErrorOut`**,
   so it is skipped by codegen and `src/lib/api/skills.ts` keeps hand-written
   types. Add the schema to the contract, add the spec to
   `frontend/scripts/codegen.mjs`, then alias the types. Likewise the other
   hand-written wire types the contract does not match (listed in the header
   comment of each `src/lib/api/x.ts` that keeps one): fix the contract when
   the backend is right, then replace the type with the generated alias.
2. **`statusColors.ts` / `ToolCallCard`** still use raw palette classes (§6).
3. **The `codemirror` vendor chunk (~590 kB)** is one file; split the language
   modes out of it if a page that needs only one mode becomes a landing page.
