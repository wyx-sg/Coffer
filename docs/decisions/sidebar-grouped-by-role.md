# The Sidebar Is Grouped by Role: Agents, Resources, System

**Status**: Accepted
**Date**: 2026-09-15
**Deciders**: Yuxing Wu
**Related**: [Resource Framework Upfront](resource-framework-upfront.md),
[Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md),
spec web-ui "Group the sidebar by role",
spec web-ui "Hold one Resources entry per listed resource kind",
spec web-ui "List only shipped surfaces in the sidebar",
spec web-ui "Keep the sidebar to its eleven entries",
PR #386

## Context

The backend models every managed asset as a resource of some kind on one
kind-agnostic framework ([Resource Framework Upfront](resource-framework-upfront.md)):
MCP servers, skills, knowledge collections, memory partitions, model
providers, channels — and, in storage, the agents themselves (kind `agent`,
built by `make_agent_kind` in `application/agent/kind.py`). The web UI has to
decide how those kinds, plus things that are not resources at all (the
activity record, sync, settings), appear in the navigation, and how each
kind's pages are built.

Three forces act on it. The navigation should not be re-argued every time a
kind ships. It should read as what the product does today, not what it plans
to do. And the grouping has to survive the one entity that does not behave
like the others: an agent *uses* the vault rather than living in it.

## Options Considered

### Option A — three role groups; one Resources entry per asset kind; bespoke pages per kind (chosen)

`frontend/src/components/SidebarNav.tsx` holds three groups, in this order:

- **Agents** — the consumers: Agents (`/agents`) and Chat (`/chat`), a
  conversation held with one of them.
- **Resources** — the assets agents draw on, exactly one entry per resource
  kind with a list surface: MCP servers, Skills, Knowledge, Memory, Model
  providers, Channels. A channel sits here because it is a credentialed
  transport the vault owns, not a consumer; a model provider sits here rather
  than in Settings because it is a vendor endpoint and its key.
- **System** — cross-cutting tooling: Activity, Sync, Settings.

Agents are stored as resources of kind `agent` and get the framework's CRUD,
validation and audit, but the UI surfaces them on their own axis and never in
Resources. The sidebar lists only surfaces that ship: no "coming soon" rows,
and an entry belonging to a switched-off experimental feature (Knowledge,
Memory, Sync) is left out rather than shown disabled, and its routes are
gated the same way (`gated(...)` in `frontend/src/router.tsx`).

Each kind has its own bespoke list and detail pages under `pages/`, its
components under `components/<kind>/` and a lazy route in `router.tsx`; there is
no frontend kind registry. `ResourceDetailPage` is the `/mcp-servers/:uid`
route and always renders `McpServerDetailPage`.

Pros: the groups follow what a user is doing — choosing an agent, managing
what it can use, or looking after the system — so a new asset kind is one more
Resources row and never a new group; the consumer/asset distinction stays
visible; the sidebar is an honest inventory. Cons: "resource" is an internal
word, so every row is labelled with the kind's own noun; agents are a resource
in storage and not in the UI, which a contributor must learn; bespoke pages
mean each kind writes its own list and detail page, held consistent by shared
components and the web-ui conventions rather than by a registry.

### Option B — one axis: everything is a resource kind

The original design (2026-05-28): every managed entity is a resource kind in a
single Resources group, with a System group for fixed tooling. Pros: the UI
mirrors the backend abstraction exactly; no classification question per
feature. Cons: it forces agents — the consumers — into the same list as the
assets they consume, mislabelling the one entity that uses the vault. Lost on
2026-05-30, when agents shipped and needed a place of their own; the grouping
became "every **asset** is a resource kind" rather than "everything is".

### Option C — a surface axis beside the kind axis

Two unrelated groups, "Resources" and "Features", with a separate surface
registry for things that are not kinds. Pros: separates data management from
activities. Cons: every new capability must first decide "kind or feature?", a
question with no user-visible value, and the fixed cross-cutting surfaces are
already handled by a small System group. Lost: it doubles the IA without
answering anything a role grouping does not.

### Option D — one flat top-level entry per kind, no groups

Pros: fewest clicks, no taxonomy. Cons: with eleven entries a flat list stops
being scannable and hides the agent/asset/system distinction. Lost as the
number of kinds grew.

### Option E — show unbuilt kinds as "soon" placeholders

Pros: signals the roadmap. Cons: a sidebar of dead rows reads as an unfinished
scaffold, and the roadmap is already visible where it is maintained
(`npx openspec list`). Lost; the same reasoning is why a switched-off
experimental feature's entry disappears rather than greys out.

### Option F — a generic frontend kind registry

A kind registers a list/card UI and a config-centric detail view, and generic
pages render every registered kind. It shipped as the universal pattern, was
narrowed on 2026-06-11 when skills needed bindings, a file viewer and drift
checks the generic detail could not express, and was retired in PR #386
(2026-09-15): only three kinds had ever registered with it, the detail routes
already dispatched on kind directly, and its shared list view had no callers.
Pros: a new kind with a simple config could appear with no page code. Cons:
every kind that shipped since has a richer interaction model than a config
form, so the registry was an indirection nothing used. Lost: `frontend/src/kinds/`
was deleted and the layout convention replaced it.

## Decision

The sidebar is grouped by role — Agents (Agents, Chat), Resources (one entry
per asset kind with a list surface), System (Activity, Sync, Settings) — and
lists only surfaces that ship, leaving out the entries of any experimental
feature switched off on this machine. Agents are stored as resources but
surfaced on their own axis. Every kind has its own pages; there is no frontend
kind registry.

A new asset kind adds one Resources entry and its own pages. A new group
requires a new *role*, not a new kind.

## Consequences

- The entry set is pinned by spec web-ui "Keep the sidebar to its eleven
  entries"; adding a twelfth is a spec change, not a drive-by.
- Legacy routes (`/resources`, `/audit`, `/observability` and old settings
  paths) redirect rather than 404, so moving an entry never breaks a bookmark.
- Consistency across bespoke pages is carried by shared components and the
  frontend conventions in `.agents/frontend.md`, not by a registry; a reviewer
  has to check it.
- An agent's detail route is `/agents/:uid`, because resources are addressed
  by their immutable uid, not by name.
