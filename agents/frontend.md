# Frontend — React / TypeScript / Vite

> 中文版: [frontend.zh.md](./frontend.zh.md)

Coffer's frontend is the desktop app's web surface (`frontend/`), rendered in
the Tauri shell in production and the Vite dev server (`make dev`) in
development. This file is the engineering convention for that surface — the
counterpart to [`stack.md`](./stack.md) (backend) and
[`ui-shell/visual-language.md`](./ui-shell/visual-language.md) (visual design).
Read it before touching `frontend/src`.

If this file and the code disagree, the code that matches the **canonical**
column below wins; fix the outlier. If a rule here blocks you, stop and raise
it — do not invent a parallel pattern.

## 1. Stack

- **React 18 + TypeScript 5** (strict), **Vite** build, **React Router v6**.
- **TanStack Query v5** for all server state. No Redux / Zustand / MobX.
- **openapi-fetch + openapi-typescript** for the typed API client where the
  spec ships an OpenAPI contract; a shared hand-written helper otherwise (§4).
- **shadcn/ui + Radix + Tailwind** for the design system (§6).
- **react-hook-form + zod** for forms, **i18next** for copy, **lucide-react**
  for icons.

Feature-specific libraries are added by the spec that first needs them
(e.g. a markdown renderer), not pre-installed.

## 2. Folder Structure (canonical)

One scheme. A feature `X` lives in exactly these places:

```
src/pages/XPage.tsx              — list/index page; XDetailPage.tsx for detail
src/components/x/                 — feature components (PascalCase files)
src/lib/hooks/useX.ts            — ALL queries + mutations for X (see §3)
src/lib/api/x.ts                 — wire types + request functions for /api/v1/x
src/i18n/locales/{en,zh}.json    — under the top-level "x" key
```

- **Data fetching lives in a hook file, never inline in a component.** A page or
  component calls `useX()`; it does not call `useQuery`/`useMutation` directly.
  (Legacy debt: `src/kinds/knowledge_base` and `src/kinds/memory` inline their
  queries in the detail page — that is the pattern to migrate AWAY from, not to
  copy.)
- **`src/kinds/<name>/` is for the kind-registry UI modules only** (the
  `KindUIModule` that the resource framework auto-renders). New plain features
  use the `pages` + `components` + `hooks` + `api` layout above, not a
  `kinds/<name>/` module.
- UI primitives live in `src/components/ui/` (shadcn). Cross-feature helpers go
  in `src/lib/`.

## 3. State Management

| State kind | Where it lives |
| --- | --- |
| Server data (anything from the daemon) | TanStack Query, via a `useX` hook |
| Ephemeral UI state (open/collapsed, draft input) | local `useState` in the component |
| User preference that must survive reload | `localStorage` via `src/lib/preferences.ts` / `auth.ts` |
| **Addressable** app state (which conversation/resource is open) | the **URL** (router param), not `useState` |

The last row matters: anything a user would expect to survive a refresh, deep-link,
or back-button MUST be a route param (`/chat/:id`, `/agents/:name`), not local
state. "Which item is selected" is navigation, not UI state.

There is no global store. Cross-component server data is shared through the
query cache (same query key → same data), not through Context. The only Context
providers are `QueryClientProvider` and `ToastProvider`.

### Query keys

Hierarchical arrays, first segment = the feature noun. A detail/sub-resource
extends the parent key so a prefix invalidation catches the whole subtree:

```ts
["agents"]                       // list
["agents", name]                 // one agent
["agents", name, "config-files"] // a sub-resource of that agent
```

- **Do NOT use flat hyphenated keys** (`["kb-documents", name]`) — they cannot be
  invalidated as a group. Memory/KB currently do this; new code must not.
- Export the key builders from the hook file (`conversationKey(id)`,
  `messagesKey(id)`), don't inline string arrays at call sites.

## 4. API Layer

Every request module under `src/lib/api/` resolves base URL + token through
`src/lib/auth.ts` (`getCofferBaseUrl`, `getCofferToken`) and sends
`X-Coffer-Token` + `X-Coffer-Actor: "ui"`. **The actor is always `"ui"`** from
the web surface (the `"user"` in `kinds/memory/api.ts` is a known outlier).

Two request styles exist; pick by whether the spec shipped an OpenAPI contract:

- **Generated client** (`getApiClient()` over `src/lib/api/client.ts` + the
  codegen'd `types.ts`) — preferred when the surface is in the OpenAPI spec.
  Full path/response type safety.
- **Shared hand-written helper** otherwise. **Target state: one shared
  `call<T>()`** (URL building + 204 handling + `{error:{code,message}}` →
  `ApiError`). Today `call<T>()` is copy-pasted in `api/chat.ts`, `agents.ts`,
  `models.ts`, `skills.ts` — when you touch one, lift it to a shared
  `src/lib/api/call.ts` and have the module import it. Do not add a fifth copy.

All errors converge on `ApiError(code, message)` (`src/lib/api/errors.ts`).
Surface them with `translateApiError(t, error)`, which maps `errors.<CODE>`
i18n keys with the server message as fallback. Never show a raw error string.

Streaming (chat SSE) is the one path outside TanStack Query: a typed
async-generator in `src/lib/chat/streamClient.ts`. Keep wire-event parsing
there; accumulate into view state in a hook (`useChatTurn`), not in components.

## 5. Mutations & Cache Invalidation

Default pattern — invalidate on success, toast on error:

```ts
return useMutation({
  mutationFn: (vars) => xApi.update(vars),
  onSuccess: () => void qc.invalidateQueries({ queryKey: ["x"] }),
  onError: (e) => toast.error(translateApiError(t, e)),
});
```

- **`onError` → toast is the default**, not optional. (Several existing hooks
  omit it — that is a gap, not a precedent.)
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
  `green/amber/emerald` palette classes. (`statusColors.ts`, `ToolCallCard`,
  `ApprovalCard` currently bypass this — fix on touch.)
- **Type scale only** — `text-sm`/`text-xs`/… never `text-[11px]`. Radius from
  the prescribed set (`rounded-lg` cards, `rounded-md` controls, `rounded-sm`
  chips). See [`ui-shell/visual-language.md`](./ui-shell/visual-language.md).
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

1. **One `call<T>()`** in `src/lib/api/call.ts`; the four hand-written API
   modules import it instead of each owning a copy.
2. **Hook-file data fetching everywhere** — extract the inline `useQuery`/
   `useMutation` out of `kinds/knowledge_base` and `kinds/memory` detail pages
   into `useKnowledgeBase` / `useMemoryStore` hooks.
3. **Hierarchical query keys everywhere** — `["memory", …]` / `["kb", …]`
   replacing the flat `["memory-facts", …]` / `["kb-documents", …]` keys.
4. **Actor header `"ui"` everywhere** — fix `kinds/memory/api.ts`.
5. **`onError` toast on every mutation** that can fail visibly.
