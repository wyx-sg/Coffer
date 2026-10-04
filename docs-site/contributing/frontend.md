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
| API types | openapi-typescript, generated from each capability's OpenAPI contract, which is generated from the backend's models |
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
- Imports only point down: `pages` to `components` to `lib`. `src/lib/**` never imports `src/components/**` or `src/pages/**`, and `src/components/**` never imports `src/pages/**`; ESLint enforces both. A type or pure helper that both layers need (a status tone, a reach mode, a save orchestration) lives in `lib/`. The one exception is `useToast`, a UI primitive hook the mutation hooks call. Test kits shared by several suites live in `src/test/`.
- Shared primitives live in `src/components/ui/`, and shared surfaces (`PageHeader`, `DataTable`, `EmptyState`) in `src/components/`. Reuse the cross-feature helpers that already exist: `lib/agents/display.ts` and `lib/chat/turnErrors.ts`.
- Routes are code-split with `lazyPage()` in `router.tsx`. List pages load eagerly. Detail pages, and anything that pulls in the editor or the markdown pipeline, load on first visit.
- One naming exception is kept for history: the MCP server list is `pages/ResourcesPage.tsx`, routed at `mcp-servers`.
- A page of an experimental feature is wrapped in `FeatureGate`. It renders the not-found page when the feature is switched off on this machine, because a switched-off feature looks absent: its sidebar and palette entries are left out through the same registry, with no notice and no switch-on button. See [Experimental features](/guides/experimental-features).

The file-size gate applies here too: a page ≤ 200 lines, a component ≤ 250 lines, a hook or utility ≤ 300 lines.

## The API layer

Every request leaves through one module, `src/lib/api/client.ts`. It resolves the base URL and token through `src/lib/auth.ts` and sends `X-Coffer-Token` and `X-Coffer-Actor: ui`. Nothing else in `src` calls `fetch`. The one exception is the chat event stream.

- **Generated types.** Every capability's contract is generated from the backend's models, and `npm run codegen` (or `make frontend-codegen`; `make contracts` runs both steps) runs openapi-typescript over every one of them and writes `src/lib/api/generated/<capability>.ts`. Never edit `generated/` by hand. `npm run lint` starts with `codegen:check`, so a contract regenerated without regenerating the types fails CI.
- **The typed client** (`getApiClient()` in `src/lib/api/client.ts`, over openapi-fetch) knows every capability's paths, so a call through it is checked for its path, parameters, body and response.
- **Request functions** in `src/lib/api/x.ts` call the typed client and settle the result with `unwrap` (the 2xx body), `unwrapOptional` (a body or `204`) or `unwrapVoid` (no body), which turn `{ error: { code, message, details } }` into an `ApiError`. There is no other transport and no second helper, and a hook or component never calls `getApiClient()` or `fetch` itself.
- **No hand-written wire types.** A wire type in `src/lib/api/x.ts` is an alias of the generated schema, for example `components["schemas"]["ProviderOut"]`. When the contract is not what the backend really sends, fix the backend model and regenerate, never the TypeScript. `codegen:check` refuses an exported interface, or a type spelling an object shape, in those modules or under `src/lib/hooks/`, and an object-literal type argument on an `unwrap*` call. A type that never crosses the wire carries a `@ui-only` tag saying so; that tag is the only exemption.

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
| A preference that survives reload | `localStorage`, guarded with try/catch so blocked storage falls back to the default (`src/lib/preferences.ts` for page size and editor) |
| Which item is open | A route parameter: `/conversations/:id`, `/agents/:type` |
| Which detail tab is selected | The last path segment: `/<kind>/<id>/<tab>`, the default tab at the bare path (`src/lib/detailTabs.ts`) |
| Which file is selected | A search parameter (`?file=`) through `useSearchParams` |

Anything a user expects to survive a refresh, a deep link or the back button belongs in the URL.

## Design system

Build screens from the shadcn primitives in `src/components/ui/`: `Button`, `Dialog`, `Select`, `Tabs`, `Tooltip`, `Skeleton`, `ConfirmDialog` and the rest. Do not hand-roll a control a primitive already covers. Use `Tooltip` rather than a native `title=`, and `Skeleton` rather than a custom pulsing block. Row actions are explicit buttons. The one menu is `Menu` (`src/components/ui/menu.tsx`), the "⋯" on an agent row and the agent header: a short list of commands over the `Popover` primitive, with arrow-key navigation and destructive items in the danger role.

The tokens come from [`frontend/tailwind.config.js`](https://github.com/wyx-sg/Coffer/blob/main/frontend/tailwind.config.js), and the vocabulary built on them from [`.agents/visual-language.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/visual-language.md):

- **Colour: semantic roles only.** Use the Foundations roles: `surface` (with `sidebar`, `raised`, `sunken`, `selected`, `hover`, `footer`), `border` / `border-subtle`, `text` / `text-muted` / `text-subtle`, `accent` (with `soft`, `text`, `foreground`), and the status roles `success`, `warning`, `danger` and `neutral`, each with a `-soft` fill. The shadcn names (`background`, `card`, `primary`, `destructive` and the rest) remain as aliases that point at a role. Health colour comes only through `src/lib/statusColors.ts`, which maps a tone (`ok`, `warn`, `error`, `muted`) onto the status roles. Raw palette classes such as `green-500` do not appear in `src`.
- **Type: the config's scale.** Use `text-2xs` (11 px) to `text-xl`, plus `display` for the brand only, never `text-[11px]`. The app runs on 13 px, and hierarchy comes from weight (`font-book`, `font-label`, `font-bold`, `font-heavy`) and colour. `font-sans` is for UI, `font-mono` for code and identifiers.
- **Spacing:** Tailwind's default 4 px scale. `max-w-content` (72 rem) caps a workbench page, and `max-w-prose` (60 ch) caps running text.
- **Radius:** fixed steps that grow with the surface: `rounded-xs` (4 px) for the smallest marks, `rounded-md` (7 px) for every control, `rounded-2xl` (12 px) for what floats over the page.
- **Light and dark.** Every colour token has a light and a dark value in `src/index.css`. `src/lib/theme.ts` resolves the viewer's choice (system, light or dark) onto `<html data-theme>`, and the dark set re-points the variables, so do not add `dark:` variants.
- Use `cn()` for conditional classes, and `formatDateTime` from `src/lib/utils` for every timestamp.

When a token is missing, add it to the Tailwind config in the same pull request and explain it in the description. Do not inline magic numbers.

## Page patterns

| Pattern | Use |
| --- | --- |
| `PageHeader` | The one header for list and detail pages: the title, `badges` beside it, `actions` on the right and one `subtitle` line. It has no back button: pages never carry a "← list" link, and the title bar's back and forward arrows are the only history controls. Detail actions keep a fixed order: reach, test or refresh, edit, delete |
| `DataTable` | The one list table. Pass `isLoading` so the header stays mounted over skeleton rows, and `emptyAction` for the call to action. The reach column's header is `resources.cols.reach` on every table |
| Reach | Three modes everywhere: **Off**, **All agents**, **Chosen agents**. The control saves as you change it and its trigger shows a badge, never "N of M agents". There is no Reach filter on a list: rows show a badge and the list groups by state |
| Secrets | Only from Coffer. `SecretField` picks a stored secret or takes a pasted value that is saved to Secrets with the form; a header or env row (`KeyValueSecretRows`) is plain text with a 🔑 picker at the end of the field. No Secret/Plain toggle, no Replace button, no Stored badge |
| Hand-off | One split button, **Ask an agent ▾** (`AgentHandoff`): the button opens a draft conversation, the ▾ menu holds **Copy prompt**. The prompt always comes from the daemon. Never for what Coffer does itself (Retry, Test, Check again) |
| Drawer | 640 wide, starts below the title bar |
| Toast | A title, and optionally a second line (`description`) saying what was kept or added |
| `EmptyState` | Every empty list, not-found page and zero-result search: icon, title, description, action |
| `Skeleton` | Loading states keep the real shape of the surface. Never show a blank screen or a "Loading…" card |
| `ConfirmDialog` | Every irreversible confirmation, never `window.confirm`; a delete that can be restored (a knowledge document or collection) skips it and shows a toast with **Undo**. It receives `pending` while the mutation runs and closes only in `onSuccess`, so a failed delete stays open with its error under `errorTitle` ("Couldn’t delete sentry"); the resting `confirmLabel` never changes, `pendingLabel` is the working text |
| `Alert` (`warning` variant) | A non-fatal caution, such as an unusual but working configuration. Not a toast, and not a destructive alert |
| Save on change | Settings, reach and providers write as the control changes and report a failed write under the control; there are no Save buttons. Only document editors (`SKILL.md`, knowledge documents, raw agent config files) keep an explicit Save and the unsaved-changes guard (`useUnsavedGuard`, one dialog mounted around the shell). A dialog's Cancel is a ghost button |
| Tabs in the URL | Detail pages keep their tab in the path, `/<kind>/<id>/<tab>` |
| Title over name | A resource of a kind that carries a title (provider, channel) shows its `title` when set and its `name` otherwise. Agents, MCP servers, skills, knowledge collections and memory partitions carry no title and always show their name: an MCP server's and a skill's name is fixed once registered (`409 NAME_IMMUTABLE`), and an agent's is its type, so their edit forms offer neither a rename nor a title |

Code style: named exports only, and one component per file. The first line of each file is a comment with its path and purpose, such as `// src/components/EmptyState.tsx — …`. Props are declared as a local `interface Props`. Type-only imports use `import type`. There is no `any` in `src`. Use `unknown` and narrow it.

## Internationalisation

The UI ships English and Simplified Chinese from `src/i18n/locales/en.json` and `zh.json`. English is the fallback language. This is a product feature. The docs site and the README are bilingual too; every other repository doc is English only (see [Contributing](/contributing/#docs-site-in-two-languages)).

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
- [Development setup](/contributing/development#wire-contracts-and-frontend-codegen)
- [`web-ui` spec](https://github.com/wyx-sg/Coffer/blob/main/openspec/specs/web-ui/spec.md)
