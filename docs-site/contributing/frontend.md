---
title: Frontend
description: Conventions for Coffer's React web UI — stack, folder layout, the generated API client, TanStack Query keys and hooks, the design system, i18n, shared page patterns and tests.
---

# Frontend

This page summarises the conventions for `frontend/`, the React app that the daemon serves as the web UI and that the desktop shell hosts. Read it before you touch `frontend/src`. The binding rules are in [`.agents/frontend.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/frontend.md) (engineering) and [`.agents/visual-language.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/visual-language.md) (visual design). If a rule blocks you, raise it in the pull request rather than inventing a parallel pattern.

## Stack

| Concern | Choice |
| --- | --- |
| UI | React 18 and TypeScript 5 (strict, `noUnusedLocals`, `noUnusedParameters`), built with Vite |
| Routing | React Router v6, with routes in `src/router.tsx` |
| Server state | TanStack Query v5. There is no Redux, Zustand or other global store |
| API types | openapi-typescript, generated from each capability's OpenAPI contract |
| Components | shadcn/ui over Radix primitives, styled with Tailwind |
| Forms | react-hook-form and zod |
| Copy | i18next, with English and Chinese catalogues |
| Icons | lucide-react |
| Tests | Vitest and Testing Library (jsdom) |

A feature-specific library arrives with the change that first needs it. Nothing is pre-installed "just in case".

The same built bundle runs in three hosts: served by the daemon at its own origin, served by Vite during development, and loaded as a local asset by the [desktop shell](/guides/desktop-app). `src/lib/auth.ts` hides which host you are in: every host supplies the API base URL and token through the same two globals. The token is never persisted, because the daemon mints a new one on each start.

## Folder layout

A feature `X` lives in exactly these places:

```text
src/pages/XPage.tsx               list page; XDetailPage.tsx for the detail page
src/components/x/                 feature components, dialogs, tables
src/lib/hooks/useX.ts             every query and mutation for X
src/lib/api/x.ts                  request functions and wire types for /api/v1/x
src/lib/api/queryKeys.ts          every query key builder, for all features
src/lib/x/                        pure helpers the feature owns
src/i18n/locales/{en,zh}.json     copy under the top-level "x" key
```

- Components never call `useQuery` or `useMutation` directly. They call a hook from `src/lib/hooks/`. [`useSkills.ts`](https://github.com/wyx-sg/Coffer/blob/main/frontend/src/lib/hooks/useSkills.ts) is a compact example.
- Resource kinds follow the same layout. There is no per-kind registry.
- Shared primitives live in `src/components/ui/`, and shared surfaces (`PageHeader`, `DataTable`, `EmptyState`) in `src/components/`. Reuse the cross-feature helpers that already exist: `lib/reachFilter.ts`, `lib/agents/display.ts` and `lib/chat/turnErrors.ts`.
- Routes are code-split with `lazyPage()` in `router.tsx`. List pages load eagerly. Detail pages, and anything that pulls in the editor or the markdown pipeline, load on first visit.
- One naming exception is kept for history: the MCP server list is `pages/ResourcesPage.tsx`, routed at `mcp-servers`.
- A page of an experimental feature is wrapped in `FeatureGate`. It renders a notice instead of the page when the feature is switched off on this machine. See [Experimental features](/guides/experimental-features).

The file-size gate applies here too: a page ≤ 200 lines, a component ≤ 250 lines, a hook or utility ≤ 300 lines.

## The API layer

Every request leaves through one of two modules. Both resolve the base URL and token through `src/lib/auth.ts`, and both send `X-Coffer-Token` and `X-Coffer-Actor: ui`. Nothing else in `src` calls `fetch`. The one exception is the chat event stream.

- **Generated types.** `npm run codegen` (or `make frontend-codegen`) runs openapi-typescript over each contract listed in `frontend/scripts/codegen.mjs` and writes `src/lib/api/generated/<capability>.ts`. Never edit `generated/` by hand. `npm run lint` starts with `codegen:check`, so if you change a contract and do not regenerate, CI fails.
- **The typed client** (`getApiClient()` in `src/lib/api/client.ts`, over openapi-fetch) serves the mcp-gateway paths.
- **One hand-written helper**, `call<T>(path, { method, body })` in `src/lib/api/call.ts`, serves everything else. It builds the URL and headers, turns `204` into `undefined` and `{ error: { code, message, details } }` into an `ApiError`, and sends `FormData` bodies. Each `src/lib/api/x.ts` is a set of request functions over `call`. Its wire types alias the generated schema, for example `components["schemas"]["ProviderOut"]`. Do not add a second helper.

Errors converge on `ApiError(code, message)`. Show them with `translateApiError(t, error)`, which looks up `errors.<CODE>` in the catalogue and falls back to the server's message. Never show a raw error string.

Chat streaming is the one path outside TanStack Query. It uses a typed async generator in `src/lib/chat/streamClient.ts`. Its events are reduced into view state in `useChatTurn` and `lib/hooks/chatTurnEvents.ts`, not in components.

## Query keys and hooks

Every key comes from a builder in [`src/lib/api/queryKeys.ts`](https://github.com/wyx-sg/Coffer/blob/main/frontend/src/lib/api/queryKeys.ts). Keys are hierarchical arrays whose first segment is the feature noun. A detail extends its list key, so a prefix invalidation sweeps the whole subtree:

```ts
export const agentsKey = ["agents"] as const;
export const agentKey = (uid: string) => ["agents", uid] as const;
export const agentConfigFilesKey = (uid: string) => ["agents", uid, "config-files"] as const;
```

- A literal `queryKey: ["…"]` anywhere else is an ESLint error.
- Key on the resource's UID, never its name, so a rename does not strand the cache.
- Avoid flat hyphenated keys (`["knowledge-documents", path]`). They cannot be invalidated as a group.

Mutations invalidate on success and show a toast on error:

```ts
export function useRemoveSkill() {
  const qc = useQueryClient();
  const onError = useSkillToastError();          // toast.error(translateApiError(t, e))
  return useMutation({
    mutationFn: (uid: string) => skillsApi.remove(uid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: skillsKey });
    },
    onError,
  });
}
```

- The `onError` toast is the default. Leave it out only when the component renders the error inline, and say so in a comment.
- Use an optimistic `setQueryData` only where latency is visible and the patch is trivial, such as a rename. Invalidate afterwards anyway.
- A delete removes the detail and sub-resource queries, then invalidates the list, so a stale detail view cannot refetch a 404.
- Bulk table actions go through `useBulkMutate`: one summary toast and one invalidation burst.

### Where state lives

| State | Where |
| --- | --- |
| Anything from the daemon | TanStack Query, through a `useX` hook |
| Ephemeral UI (open, collapsed, draft input) | `useState` in the component |
| A preference that survives reload | `src/lib/preferences.ts` (`localStorage`) |
| Which item is open | A route parameter: `/chat/:id`, `/agents/:uid` |
| Which tab or file is selected | A search parameter (`?tab=`, `?file=`) through `useSearchParams`. The default tab is the absence of the parameter |

Anything a user expects to survive a refresh, a deep link or the back button belongs in the URL.

## Design system

Build screens from the shadcn primitives in `src/components/ui/`: `Button`, `Dialog`, `Select`, `Tabs`, `Tooltip`, `Skeleton`, `ConfirmDialog` and the rest. Do not hand-roll a control a primitive already covers. Use `Tooltip` rather than a native `title=`, and `Skeleton` rather than a custom pulsing block. There is deliberately no dropdown menu: row actions are explicit buttons.

The tokens come from [`frontend/tailwind.config.js`](https://github.com/wyx-sg/Coffer/blob/main/frontend/tailwind.config.js), and the vocabulary built on them from [`.agents/visual-language.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/visual-language.md):

- **Colour: semantic tokens only.** Use `background`, `foreground`, `card`, `muted`, `accent`, `primary`, `secondary`, `destructive`, `border`, `input`, `ring`, and `highlight` / `highlight-active` for "the one you are looking at". Health colour comes only through `src/lib/statusColors.ts`, which maps a tone onto `status.ok`, `status.warn` and `status.err`. Raw palette classes such as `green-500` do not appear in `src`.
- **Type: Tailwind's scale.** Use `text-xs` to `text-2xl`, never `text-[11px]`. `font-sans` is for UI, `font-serif` for long-form prose, `font-mono` for code and identifiers.
- **Spacing:** Tailwind's default 4 px scale. `max-w-content` (72 rem) caps a workbench page, and `max-w-prose` (60 ch) caps running text.
- **Radius:** `rounded-lg` for cards, `rounded-md` for controls, `rounded-sm` for chips. All derive from one `--radius` variable.
- **Light only.** There is no dark token set, so do not add `dark:` variants.
- Use `cn()` for conditional classes, and `formatDateTime` from `src/lib/utils` for every timestamp.

When a token is missing, add it to the Tailwind config in the same pull request and explain it in the description. Do not inline magic numbers.

## Page patterns

| Pattern | Use |
| --- | --- |
| `PageHeader` | The one header for list and detail pages: `icon` on list pages, `back` on detail pages, `badges` beside the title, `actions` on the right. Detail actions keep a fixed order: reach, test or refresh, edit, delete |
| `DataTable` | The one list table. Pass `isLoading` so the header stays mounted over skeleton rows, and `emptyAction` for the call to action. The reach column's header is `resources.cols.reach` on every table |
| `EmptyState` | Every empty list, not-found page and zero-result search: icon, title, description, action |
| `Skeleton` | Loading states keep the real shape of the surface. Never show a blank screen or a "Loading…" card |
| `ConfirmDialog` | Every destructive confirmation, never `window.confirm`. It receives `pending` while the mutation runs and closes only in `onSuccess`, so a failed delete stays open with its error |
| `Alert` (`warning` variant) | A non-fatal caution, such as an unusual but working configuration. Not a toast, and not a destructive alert |
| Tabs in the URL | Detail pages keep their tab in `?tab=` |

Code style: named exports only, and one component per file. The first line of each file is a comment with its path and purpose, such as `// src/components/EmptyState.tsx — …`. Props are declared as a local `interface Props`. Type-only imports use `import type`. There is no `any` in `src`. Use `unknown` and narrow it.

## Internationalisation

The UI ships English and Simplified Chinese from `src/i18n/locales/en.json` and `zh.json`. English is the fallback language. This is a product feature. The repository's docs, this site included, are English only.

- Every user-facing string goes through `t(...)`, including `aria-label`s.
- Keys are nested camelCase paths under the feature's top-level key, for example `chat.composer.placeholder`.
- Add each key to **both** catalogues in the same change. `src/i18n/locales.test.ts` fails on any key that exists in only one.
- Backend error codes and audit event types need entries as well: `errors.<CODE>` for each error. When you add a `CofferError` subclass or an `AuditEventType`, regenerate the fixture the parity test reads:

  ```sh
  PYTHONPATH=backend .venv/bin/python scripts/dump_i18n_backend_keys.py
  ```

  `make lint` runs the same script with `--check`, so a new code without its fixture entry, and therefore without its translations, fails CI.

## Testing

- Put `*.test.tsx` next to the module it covers, and ship a new component or hook with its test in the same commit.
- Test behaviour through the component or hook, not its implementation. Render with a real `QueryClientProvider`, and mock only the network boundary: the `src/lib/api/*` module, or `streamClient`.
- Tag scenario coverage with `acceptance(spec, scenario, fn)` from `@/test/acceptance`. See [Testing](/contributing/testing#acceptance-markers).
- Radix `Tabs` switch on `mousedown`, not `click`. In a test, use `fireEvent.mouseDown` on the tab trigger, or the tab does not change and a later assertion can pass for the wrong reason.
- Run one file with `cd frontend && npx vitest run src/path/File.test.tsx`. `make verify-unit` runs the whole suite, and `make lint` adds ESLint, `tsc` and knip. Use Node 20, as CI does.

Browser-level flows belong in the Playwright `web` project under `e2e/web/specs/`. See [End-to-end tests](/contributing/testing#end-to-end-tests-with-playwright).

## Related

- [Web UI guide](/guides/web-ui)
- [Testing](/contributing/testing)
- [Development setup](/contributing/development#frontend-api-codegen)
- [`web-ui` spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md)
