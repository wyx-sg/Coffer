# Frontend — React / TypeScript / Vite

Coffer's frontend is the daemon-served web UI (`frontend/`): built to static
assets that the daemon serves at its own loopback origin in production, and
run from the Vite dev server (`make dev`) in development with `COFFER_DEV_CORS`
opted in. This file is the engineering convention for that surface — the
counterpart to [`stack.md`](./stack.md) (backend) and
[`visual-language.md`](./visual-language.md) (visual design).
Read it before touching `frontend/src`.

A UI change also updates its spec, its docs and the Claude Design canvas boards in
the same work item (AGENTS.md §3 "Four-way sync").

If this file and the code disagree, the code that matches the **canonical**
column below wins; fix the outlier. If a rule here blocks you, stop and raise
it — do not invent a parallel pattern.

## 1. Stack

- **React 18 + TypeScript 5** (strict), **Vite** build, **React Router v6**.
- **TanStack Query v5** for all server state. No Redux / Zustand / MobX.
- **openapi-typescript** generates wire types from every spec's OpenAPI
  contract, and that contract is itself generated from the backend's Pydantic
  models; **openapi-fetch** is the typed client over every capability's paths
  (`src/lib/api/types.ts` merges them). Every request function goes through it
  (§4).
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
src/lib/x/                       — pure helpers a feature owns (parsers, filters,
                                   save orchestration, state-to-words mappings)
src/i18n/locales/{en,zh}.json    — under the top-level "x" key
```

- **Imports only point down: `pages` -> `components` -> `lib`.** `src/lib/**`
  must not import `src/components/**` or `src/pages/**`; `src/components/**`
  must not import `src/pages/**` (ESLint `no-restricted-imports`, in
  `frontend/eslint.config.js`). A type or pure helper that both layers need
  (a status tone, a reach mode, a channel schema, a save orchestration) lives
  in `lib/` and the component imports it from there; there are no re-export
  shims. The one exception is `useToast` (`components/ui/toast`), a UI
  primitive hook the mutation hooks call. Test files are exempt; a test kit
  shared by several suites lives in `src/test/`, not in a component or page
  folder. A page's sections and dialogs are components, so they live in
  `components/<x>/`, not beside the page.

- **One documented naming exception**: the MCP-server list page is
  `pages/ResourcesPage.tsx`, which serves both the list and a server's detail,
  routed at `mcp-servers` in `router.tsx` — there is no `McpServersPage.tsx`. It kept the
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
  in `src/lib/`. Two already exist — reuse them, do not re-derive (there is no
  list-level Reach filter any more: a scoped list shows each row's reach as a
  badge and groups by state instead):
  - `lib/agents/display.ts` — the human-readable forms of agent wire values
    (product name for a registry key, home-relative path), shared by the
    table, the add form and the detail header.
- **The app shell** (docs-site `architecture/app-shell.md`) has one home per concern:
  - `lib/navigation.ts` — the one list of sidebar entries (`NAV_GROUPS`) and
    Settings tabs (`SETTINGS_TABS`); the sidebar, the palette's Pages group and
    the Settings modal all read it. A new entry or tab is added here, nowhere else.
  - `lib/settingsModal.ts` — `useOpenSettings`, `useCloseSettings`,
    `usePageLocation` (the background page under the modal). Open Settings only
    through it, never with a hand-built `navigate("/settings/…")`.
  - `components/palette/` — the palette: navigation only; objects come from
    each kind's existing list hook, never an aggregate route.
  - `components/shell/` — `WindowTitleStrip` (the 44px desktop strip: traffic
    lights, sidebar toggle, history arrows) and `useShellShortcuts` (⌘\ toggles
    the sidebar, ⌘[ / ⌘] walk the app's history, ⌘, opens Settings);
    `SidebarFooter` (update card and a gear + "Settings" row that always opens
    Settings › General — no daemon state, no version menu; theme and language
    live only in Settings › General);
    `daemonConnection.ts` — `useDaemonConnectionDriver`, mounted once in
    `Layout`, turns the one `useDaemonStatus` poll into the ok / reconnecting /
    offline phase with its backoff, and every reader (`DaemonOfflineBanner`'s
    bar and offline state, the Settings › Daemon status) calls
    `useDaemonConnection` — no second timer; `paletteRequest.ts` for a page that opens the palette;
    the sidebar carries no attention marks — no badges, dots or tooltip text;
    what needs the person is on Overview's Needs you and the menu bar's count.
  - `components/SplitView` / `SplitDivider` + `lib/hooks/useResizableWidth.ts`
    for every resizable split; widths are per-browser conveniences.
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
| User preference that must survive reload                        | `localStorage`, every read and write wrapped in try/catch (`src/lib/preferences.ts` holds the editor, terminal and hand-off agent; other modules own their key) |
| **Addressable** app state (which resource is open) | the **URL** (router param), not `useState`              |
| Detail-page tab                                                 | the **path** (`/<kind>/<id>/<tab>`) via `useDetailTab` (`lib/detailTabs.ts`) |
| Selected file; tab on a list page (Sync, Activity)              | the **URL search param** (`?file=`, `?tab=`) via `useSearchParams` |

The API token is deliberately not in that table: it is read from
`window.__COFFER_TOKEN__`, injected into the served page by whoever served it
(`src/lib/auth.ts`). Persisting it would outlive the daemon that minted it.

The URL rows matter: anything a user would expect to survive a refresh, deep-link,
or back-button MUST be a route param (`/agents/:type`, `/skills/:name`), not local
state. "Which item is selected" is navigation, not UI state. The same holds one
level down. A detail page's tab lives in the path — `/<kind>/<id>` for the
default tab, `/<kind>/<id>/<tab>` otherwise — through `useDetailTab`
(`lib/detailTabs.ts`), which sends an unknown `:tab` to the bare address; skills and MCP
servers are keyed by their fixed name, agents by their type, renamable kinds
by uid. Skills, MCP servers, agents, knowledge
(`/knowledge/<uid>/inbox`) and memory partitions
(`/memory/<uid>/delivered`) follow it; the tabs of a list page that has no
detail to nest under (Sync, Activity) are `?tab=`, and the open file in a tree is always `?file=`. The default tab is never spelled out (`/overview`, `?tab=overview`).

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
  (`["settings", "secrets"]`) nests under the feature that owns the page.
- A hook file may re-export the builders it uses for its tests; new code
  imports from `queryKeys.ts` directly.

## 4. API Layer

Every request leaves through one module, `src/lib/api/client.ts`, which resolves base URL +
token through `src/lib/auth.ts` (`getCofferBaseUrl`, `getCofferToken`) and send
`X-Coffer-Token` + `X-Coffer-Actor: "ui"`. **The actor is always `"ui"`** from
the web surface. Nothing else in `src` calls `fetch` — the one exception is
the daemon's change feed (`lib/events/eventStream.ts`), an SSE reader.

- **Generated types for every contract.** `npm run codegen`
  (`frontend/scripts/codegen.mjs`) runs openapi-typescript over each
  `openspec/specs/*/contracts/api.openapi.yaml` into `src/lib/api/generated/<spec>.ts`
  — every contract that has one is discovered (there is no list to maintain);
  `src/lib/api/types.ts` intersects every module's `components` and `paths`, so
  `components["schemas"][…]` keeps working. `npm run lint`
  runs `codegen:check` first, so a contract edit without a regenerate fails CI;
  never hand-edit `generated/` (it is prettier-ignored, 4-space indented).
- **Generated client** (`getApiClient()` over `src/lib/api/client.ts`) over
  every capability's paths (keyed without the `/api/v1` prefix the base URL
  carries) — full path/response type safety. There is no other transport:
  every request function in `src/lib/api/x.ts` calls the client and settles
  the result with `unwrap` (2xx body), `unwrapOptional` (200 body or 204) or
  `unwrapVoid` (no body), which turn `{error:{code,message,details}}` into an
  `ApiError`. Wire types are aliases of the generated schema
  (`export type Provider = components["schemas"]["ProviderOut"]`). No wire type
  is hand-written: when the contract is narrower than what the backend really
  sends, the fix is in the backend model (and the contract regenerated from
  it), not a hand-written interface. Types that exist only in the UI and never
  cross the wire are fine. Do not add a second helper, and do not call
  `getApiClient()` or `fetch` from a hook or component: add a request function.
- **Direction.** Pydantic models → generated `contracts/api.openapi.yaml` →
  generated client (Principles, "II. Spec-as-Truth"; ADR
  `docs/decisions/wire-contract-generated-from-the-pydantic-models.md`). The
  contracts are regenerated with `make contracts` (models → contracts →
  `generated/`). `codegen:check` (in `npm run lint`) also runs
  `scripts/check-wire-types.mjs`: an exported `interface`, or an exported
  `type` spelling an object shape, in a `src/lib/api/*.ts` module or anywhere
  under `src/lib/hooks/` fails unless it carries a `@ui-only` JSDoc tag (it
  never crosses the wire); so does an object-literal type argument on
  `unwrap` / `unwrapOptional` / `unwrapVoid`. `@ui-only` is the only
  exemption.

All errors converge on `ApiError(code, message)` (`src/lib/api/errors.ts`).
Surface them with `translateApiError(t, error)`, which maps `errors.<CODE>`
i18n keys with the server message as fallback. Never show a raw error string.

The daemon's change feed (`lib/events/eventStream.ts` + `useDaemonEvents`) is
the one stream outside TanStack Query; it only invalidates query keys. The web
has no chat stream: a conversation or session opens in the person's terminal.

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

- **A tooltip only names an icon-only control** (its name, plus its shortcut when
  it has one — one or two words: `More actions`, `Back ⌘[`, `Hide sidebar ⌘\`)
  **or shows the full text of something truncated.** A button or menu item that
  carries words gets no tooltip; a tooltip never explains what will happen — that
  goes in a menu item's `description` (its second line) or behind a `HelpTip`.
  The shared `ActionMenu` trigger carries `More actions` while its `aria-label`
  stays the caller's specific label.
- **Build from `src/components/ui/` primitives** (shadcn: `Button`, `Dialog`,
  `Select`, `Textarea`, `Tooltip`, `Skeleton`, `ConfirmDialog`, …). Don't
  hand-roll a control a primitive already covers — no native `title=` hints
  where `Tooltip` fits, no bespoke pulsing block where `Skeleton` does. Row actions
  are explicit buttons (`RowDeleteButton`, `ScopeControl`); the one "⋯" menu is
  `ActionMenu` (`components/ui/menu.tsx`, over `Popover`), used where the design
  gives an object a menu of secondary commands (an agent's row and header).
  There is no `DropdownMenu`.
- **Shared surfaces above the primitives**, used the same way everywhere:
  - `PageHeader` is the one page header, list and detail alike: the title (18/650), `badges` beside it, `actions` on the
    right and one `subtitle` line under the row (there is no title icon: the sidebar entry already carries it, and no `back`:
    pages carry no back button or "← list" link — the title bar's global ← → (⌘[ / ⌘]) are the only back/forward). Detail-page actions keep one fixed order: reach → test/refresh →
    edit → delete. The title bar holds only window controls.
  - `DataTable` is the one list table. Pass `isLoading` so the header stays
    mounted over skeleton rows (never a "Loading…" card in the table's place)
    and `emptyAction` for the call-to-action under the empty message. The reach
    column's header key is `resources.cols.reach` on every table.
  - **Reach** (`components/reach/`) is three modes everywhere: **Off**,
    **All agents**, **Chosen agents**. `ReachControl` saves on every change
    ("Applying…" → "✓ Saved") — no Save button — and its trigger shows only a
    badge (the agents' marks, "All agents" or "Off"), never "N of M agents".
    "All agents" is stored as such, so it covers agents added later. A table row of
    an object that is off leaves its Reach cell empty. Bulk reach on selected
    rows is `BulkReachActions` (a 340-wide popover, old → new counts, a partial
    failure kept inside it).
  - **Secrets come only from Coffer** (`components/secret/`; principle 22).
    `SecretField` is a field whose whole value is a secret (a provider key, a
    channel or sync token, a custom-tool group's auth): it picks a stored
    secret or takes a pasted value that is saved to Secrets with the form;
    the value never shows. `KeyValueSecretRows` is the one header / env row
    list (key · value · delete): the value is plain text and a 🔑 button at the
    end of the field picks a stored secret; a value that looks like a secret
    offers to be stored. There is no Secret|Plain toggle, Replace button or
    Stored badge. A custom-tool group's auth is such a header row whose secret
    holds the whole header value (`Bearer <token>`), so nothing prefixes it.
  - **A drawer** (`ui/sheet.tsx`) is 640 wide and starts below the title bar
    (`--titlebar-inset`), scrim included.
  - **A toast can carry a second line**: `toast.success(title, { description })`
    for what was kept or added ("Added 2 servers" / "Kept the folder").
  - **A list has one loading interaction: scroll.** Two classes:
    - **A list that can hold more than ~100 rows pages by cursor and loads on
      scroll — never everything at once.** It opens on one small page
      (`FIRST_PAGE` 30), reads the next `MORE_PAGE` 50 when its end scrolls into
      view, and search and filters are query parameters of the route (debounced,
      with the stale request aborted), not a filter over what happens to be
      loaded. Build it from `useInfiniteList` (`lib/hooks/useInfiniteList.ts`: an
      infinite query over the server's `next_cursor`, the abort signal passed to
      the request function) and, under the rows, `LoadMoreFooter` with
      `autoLoad` (`components/ui/load-more.tsx`: the `LoadMoreSentinel` plus the
      always-visible "N loaded · Load more" fallback) and a `Skeleton` row while
      a page loads. A live list re-reads only its first page and holds what
      arrives above the reader's scroll position behind a "↑ N new" control.
    - **A list that is bounded by nature (a few dozen skills, MCP servers,
      providers, tools) is in memory and shows whole.** `DataTable` does this
      itself; any other in-memory list uses `useGrowingList`
      (`lib/hooks/useGrowingList.ts`) with a `LoadMoreSentinel` under the rows.
      As a safety net, past `RENDER_BATCH` (100) rows the first 100 render and
      the rest are added 100 at a time when the end scrolls into view — no
      button, no count, no page-size preference. A bounded list that in real
      use exceeds ~200 rows is not bounded: move it to cursor paging. Its list
      endpoint returns summary fields only (detail is read per item), so a
      first page stays small.
  - Every button inside a table — row actions and selection-bar actions
    alike — is a `TableActionButton` (`components/table/`): small outline
    button, icon + text label, `destructive` for anything that removes. Row
    delete is `RowDeleteButton`, bulk delete `BulkDeleteButton`, both built on
    it. No ghost, solid or text-only buttons in a table.
  - A table cell whose content can be long (names, descriptions, paths, ids,
    URLs, commands) is one line with an ellipsis and the full text in a
    tooltip: `TruncatedText` / `TruncatedPath` (`components/ui/truncated-text.tsx`;
    a path keeps its last segment visible), in a `<DataTable fixed>` whose
    columns carry explicit widths (`w-[34%]`, `w-[150px]`). Never `break-all`
    in a table cell — rows keep one height whatever the content.
  - A settings-style form that is a stack of titled blocks is built from
    `SettingsSection` + `SettingRow` (`components/settings/SettingsLayout.tsx`):
    each section is unboxed (`<section aria-labelledby>`, h3 title or h2 via
    `headingLevel`, one visible `description` line, optional `meta`, `action`)
    over hairline-divided rows; a row is its label with its own helper line on
    the left and its control on the right (`layout="stack"` for a wide control).
    A tab opens with `SettingsTabHeader` (title 18/650 + one 13 intro line).
    Wrap the stack in `SETTINGS_STACK` (32px between sections); a destructive or
    rare action is the last section. Settings tabs and a channel's Settings use
    it. `Section` is the same heading for read-only overviews.
  - **Page grammar.** A bordered box is for *a group of things* (a list of rows,
    a table, a set of cards); unboxed hairline-separated rows are for *one
    thing's properties*. A section title is 15/600 with one visible description
    line under it (12, muted) — the explanation is shown, not hidden behind a
    "?"; `HelpTip` is only for the overflow of a long explanation. 32px between
    sections. A tab's own title is 18/650 with a 13 intro line. Page content
    padding is 16 top / 32 sides (`Layout`).
  - `EmptyState` is the shared "nothing here yet" card (icon, title,
    description, action).
  - A file/session browser (tree or list beside a viewer) ends at the bottom
    of the window and scrolls inside: put `useFillToBottom()` from
    `components/filePane.ts` on the split, give columns `FILE_PANE_COLUMN` /
    `FILE_PANE_BODY` with one `FILE_PANE_SCROLL` / `CodeView fill` region, and
    keep headers and footers `shrink-0`. It measures against the page's real
    scroller (the overflow wrapper inside `<main>`), floor 320px; never a
    `max-h-*` cap on such a pane.
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
- **A ⋯ menu never repeats what is already on the surface.** Visible buttons are
  the frequent, high-value actions; the ⋯ menu holds the rare ones. An item that
  does what a visible button, switch, link or row click does — or what another
  tab or settings area of the same page offers — does not belong in the menu
  (a "Send test message" under a "Send test" button, "Delete" in both the header
  and Settings). A menu left with nothing in it is removed.
- **A page only when there is a page's worth.** A thing with a lot to show or
  do — tabs, several blocks, a file tree, its own actions (a managed skill, a
  managed MCP server, an agent) — gets its own detail page. A thing with one or
  two facts to read or a short form — a direct MCP entry's JSON, a custom tool,
  an unmanaged item's summary — opens as a dialog over its list, with its
  actions in the footer. Do not mint a route for a page that would hold a
  single card.
- Keep files focused. `scripts/check_file_sizes.py` (in `make lint`) enforces
  the limits: a page (`src/pages/**`) ≤ 200 lines, a component
  (`src/components/**`) ≤ 250, a hook or utility (`src/lib/**`) ≤ 300. One
  component per file, test colocated (§8).

- **An agent's state is one word, one pill.** Connected · Not connected · Needs
  repair · Hook not approved · Off · Config left behind (and Not installed / Not
  found on the list). The list row and the detail header read the same word
  (`lib/agents/rowState.ts`); a newly found agent and a disconnected one are the
  same off state, Not connected. The visible button is only ever the fix Coffer
  can make — Connect, Repair or Turn on — and a healthy row has none; Disconnect
  and Turn off live in ⋯. The detail header never turns into a fix button: its
  fix sits in the Overview's Connection section. Overview's Needs you
  lists only agents that need you (repair, config left behind, Coffer hook not
  approved or never fired), never Not connected.
- **A write to an agent's own files goes through Review changes → Apply**
  (`components/change-preview/ChangePreview`, 1060 wide): Connect, Repair,
  Disconnect, moving a connected agent's config directory, and Change model. The
  preview shows the daemon's own lines; Apply sends the fingerprints the preview
  read and a file edited since is refused (`CONFIG_FILE_STALE`) with Reload
  preview. Every diff of changed lines (these previews, a History tab's
  versions, skill copy and folder reviews, a custom-tool re-import) is drawn by
  the one `FileDiff` renderer. Deleting a provider something runs on is the same shape.
- **Detail pages with many tabs: six, then More ⌄.** `components/DetailTabsMore`
  keeps the six most used in the strip and puts the rest in a More menu; while a
  tab inside More is open the trigger wears its name and the underline, and a
  warning dot says a tab inside needs you. An agent has no Model tab — the model
  is a section of its Overview.
- **Coffer's part first, then the item's own** on the agent's Skills, MCP
  servers, Hooks and Memory tabs: Coffer-managed items are never listed one by
  one there, only as one *From Coffer* row linking to the global list narrowed to
  the agent (`useAgentFilter`, `AgentFilterPill`); the agent's own items follow
  in a section with a search. No owner column or filter.

### Saving, counts, dialogs and shortcuts

- **Save on change everywhere** — settings, reach, providers, channel options,
  feature switches: the control writes as it changes (text on Enter/blur, once
  valid) and a failed write is said under the control ("Couldn't save the
  change: …"). No Save buttons and no unsaved-changes guard: the web UI has no
  document editor. `SKILL.md`, knowledge documents, memories and agent config
  files are read-only, with **Open in editor** and **Reveal in Finder**
  (`fileActions`); the person's editor does the editing.
- **Count badges** — tab and list counts that mean "needs you" are all
  `danger-strong`, capped at `9+`.
- **Dialogs** — Cancel is a `ghost` button beside the primary action.
- **Shortcuts** — ⌘\ sidebar toggle, ⌘[ / ⌘] history back / forward, ⌘, Settings,
  ⌘K palette (Ctrl on other platforms); handled once in `useShellShortcuts`.
- **Experimental** tags sit beside the page title and in Settings › Features,
  never on a sidebar row (the collapsed rail's tooltip names it).

### Hand a chore to an agent

Coffer is AI-native: a chore that is open-ended and depends on the machine —
installing, setting up, troubleshooting, logging in — is not run by the UI or
the daemon but handed to the person's agent.

A page never shows an install command, a setup script or a manual step list
for work that depends on the person's machine: it renders `<AgentHandoff>`
with the prompt the daemon returned. It keeps a plain button for work Coffer
does itself, and shows the hand-off beside the manual controls in conflict,
merge and repair flows.

- **Use `AgentHandoff`** (`components/handoff/`) for it (`size="sm"` in a
  dense row). Use
  a plain button instead when Coffer can do the work itself, deterministically
  (Check again, enable, delete).
- **The prompt comes from the backend**, as a `handoff: {prompt}` field on the
  response (`HandoffOut`, built by `backend/coffer/domain/handoff.py`). The
  frontend never assembles or edits the text; it only shows or passes it on.
- **`AgentHandoff` is one split control, Hand off to <Agent> ▾**: the main
  half starts the default hand-off agent (Settings › General › Hand-off agent)
  in the preferred terminal (Settings › General › Preferred terminal) with the
  prompt as the first message, through `POST /api/v1/fs/terminal`, with no
  confirmation. The ▾ menu holds Hand off to <other agent> (when it is
  available) and Copy prompt (toast "Prompt copied"); with no managed agent it
  is a plain Copy prompt. `help={false}` drops the "?" in a
  row that already says what the problem is (Knowledge and Memory failures,
  after their own Retry / Check again). `prompt` may be a request the control
  makes when picked, for a hand-off the daemon records (Sync conflicts).
- **The prompt never travels on a command line.** The daemon writes it to a
  private temporary file and the agent reads it from there, so it stays out of
  shell history and process listings. The frontend sends the prompt (or the
  session id) to the daemon and never builds a terminal command itself;
  Tidy / Tidy all on Knowledge and Memory use the same path. There are no draft
  conversations, composer or Send step in the web.
- **A surface with room for one button** (an Overview Needs you row, whose
  attention item carries `handoff`) uses `useAgentHandoff` and puts Copy
  prompt / Hand off to <Agent> in its ⋯ menu instead (every Needs-you row gets one
  primary button plus a ⋯ menu: Copy prompt · Hand off to <Agent> · Ignore). An
  Agents-list row whose program is not on this Mac does the same: no button,
  the install prompt heads its ⋯ menu above a separator.

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
  (`handoff.promptCopied`). **en and zh stay at exact key parity** — add to
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
| Activity | 活动 | Usage (a tab of Model providers, not an entry) | 用量 |
| Sync | 同步 | Settings | 设置 |

In zh an agent is always **智能体** — never "Agent" or 代理.

### Action glossary (one wording per action)

The same action carries the same words on the row button, the ⋯ menu item, the
dialog title and confirm button, the progress line, the toast and the banner.
A menu item ends in `…` only when a dialog follows. Progress in zh is
`正在X…` (never `X中…`).

| Action | English | 中文 | Not |
| --- | --- | --- | --- |
| Take an agent's own skill/MCP entry under Coffer | Adopt / Adopted | 纳入托管 / 已纳入托管 | 收编, 纳管, 接管 |
| Under Coffer's care / not | Managed / Unmanaged | 托管 / 未托管 | 受管, 非托管 |
| Link an agent to Coffer | Connect / Disconnect — a newly found agent is Not connected with **Connect**, never "Not added / Add" | 连接 / 断开连接 | 接入 (an agent), 连到, 添加 (an agent) |
| Re-establish a lost link | Reconnect | 重新连接 | 重连 |
| Switch a resource or agent on / off | Turn on / Turn off; state On / Off | 开启 / 关闭; 已开启 / 已关闭 | Enable/Disable, 启用/停用/禁用, 打开 (as on) |
| Destroy a thing | Delete | 删除 | |
| Take a thing out of a list/agent/Coffer, keeping the thing | Remove | 移除 | |
| Put something in the list (never an agent: the Agents list always holds both rows) | Add | 添加 (diff tag `+ 添加`) | 注册, 登记, 新增 |
| Make a new object from nothing | Create / New | 创建 / 新建 | |
| Redo a failed operation | Retry | 重试 | Try again, 再试一次 |
| Run a check again | Check again | 重新检查 | 再检查一次, 再次检查 |
| Test again | Test again | 重新测试 | 再测一次, 再次测试 |
| Swap a value for another | Replace | 替换 | 更换, 换成 |
| Who gets a resource (three modes) | Reach: Off / All agents / Chosen agents | 生效范围：关闭 / 所有智能体 / 指定智能体 | Disabled, Every agent, Only selected agents, 已停用, 只限选中的 |
| Hand a machine-bound chore to an agent | Hand off to <Agent> ▾ (menu: Hand off to <other agent>, Copy prompt, toast "Prompt copied") | 交给 <Agent> ▾（菜单：交给 <另一个智能体>，复制提示词，提示“已复制提示词”） | Two separate buttons, Ask an agent, 询问智能体 |
| Pick another source/machine/directory | Change | 更改 | 更换 |
| A change (noun) | change | 改动 | 变更, 更改 |
| Look over before applying | Review | 查看 | 审阅, 检查 (that is Check) |
| The preview of what a write to an agent's config will change, then **Apply** (Connect, Repair, Disconnect, moving the config directory, Change model) | Review changes | 审阅改动 (the one place Review reads 审阅) | |
| Pick another provider/model for an agent (Overview › Model › Change…) | Change model (dialog title "Change <Agent>’s model") | 更改模型 | Switch provider, Model tab |
| Coffer's own items on an agent's Skills / MCP servers tab | From Coffer (one row, linking to `/skills?agent=` or `/mcp-servers?agent=`) | 来自 Coffer | Owner filter, All / Coffer’s / The agent’s own |
| An agent's own items there | <Agent>’s own skills / MCP servers / hooks | <智能体> 自己的技能 / MCP 服务器 / 钩子 | |
| Rename | Rename | 重命名 | 改名 |
| Held deletions (sync) | held | 暂扣 | 暂停, 拦下 |
| Jump to the audit log | View in Activity | 在活动中查看 | 在活动中打开 |
| Reveal a file in the OS file manager | Reveal in Finder | 在访达中显示 | Show in Finder, Finder |

## 8. Testing

- **Vitest + Testing Library**, `*.test.tsx` colocated next to the unit.
- Test **behaviour through the component/hook**, not implementation. Render with
  a real `QueryClientProvider`; mock only the network boundary (the `api`
  module).
- A new component or hook ships with its test in the same commit. Acceptance-
  scenario coverage follows [`testing.md`](./testing.md) markers.
- Run `cd frontend && npx vitest run <file>` for a focused check; `make verify`
  runs the suite + lint + tsc.

## 9. Convergence Backlog (known debt → target state)

When you work near these, migrate toward the target; don't extend the debt:

1. **Per-hook polling.** The daemon-wide change feed
   (`GET /api/v1/events`, fetch-read with the token header) is the replacement for per-hook `refetchInterval` polling: a
   rebuilt page mounts `useDaemonEvents()`, which invalidates the query keys an
   envelope's `kind` names. The audit and MCP call logs are not on it (they are
   not resources), so Activity re-reads their newest page on a short poll.
2. **The `codemirror` vendor chunk (~590 kB)** is one file; split the language
   modes out of it if a page that needs only one mode becomes a landing page.
