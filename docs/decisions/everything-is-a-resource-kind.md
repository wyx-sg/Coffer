# Information Architecture — Everything Is a Resource Kind

**Status**: Accepted
**Date**: 2026-05-28
**Deciders**: Yuxing Wu
**Related**: [Resource Framework Upfront](resource-framework-upfront.md), spec `web-ui`

The live decision is the one below **as narrowed by both amendments** at the end
of this file: every *asset* is a resource kind under **Resources**, consumers
(agents) and cross-cutting tooling (System) are their own role-based groups, and
a kind chooses at design time between the generic kind registry and a bespoke
page-set. Read the amendments as part of the Decision, not as history.

## Context

Spec `mcp-gateway` introduced the `mcp_server` resource kind on top of a
kind-agnostic Resource framework (see [Resource Framework Upfront](resource-framework-upfront.md)).
`mcp_server` is the kind that ships today.

Spec `web-ui` has to decide how resource kinds — and cross-cutting
user-facing concepts that are not resources in the domain sense (the audit
log, settings) — surface in the navigation. The naïve approach is to
introduce a second top-level concept in the IA: a "surface" axis sitting
next to the "resource kind" axis, so the sidebar reads as two unrelated
groups (Resources vs Features). The redesign goal was the opposite: **one
consistent navigation model that does not have to be re-litigated as the
product grows.**

A related question is what to do in the sidebar with a kind that is not
built yet. The temptation is to list it as a "coming soon" placeholder. In
practice this fills the sidebar with dead entries and makes the product look
like an unfinished scaffold.

## Decision

**Adopt a single-axis information architecture: every user-facing managed
entity is a resource kind, surfaced through the same sidebar group.**

Concrete consequences:

- The sidebar has exactly two groups today — **Resources** (resource kinds)
  and **System** (cross-cutting tooling: Observability, Settings). When a
  new kind ships, it appears in the Resources group; no new group is
  introduced.
- The kind-agnostic Resource framework is the only abstraction the UI
  models; there is no separate "surface" registry sitting beside it.
- **Sidebar policy: no "soon" placeholders.** A kind is not shown in the
  sidebar until it works. The rendered UI shows only what works today.

## Consequences

**Positive**

- A new kind plugs into the same Resources group with a single nav entry —
  no IA renegotiation per kind.
- The sidebar always reads as "here is what Coffer does", not "here is what
  Coffer plans to do." A first-time visitor sees a product, not a backlog.
- The Resource framework from [Resource Framework Upfront](resource-framework-upfront.md)
  is the only abstraction the UI needs to understand; the UI does not need
  a separate "surface" registry.

**Negative**

- "Resource" is forced to carry concepts that are not always called
  "resources" in user conversation. Mitigated by the user-facing label being
  the kind's own noun (e.g. "MCP server"), not the word "resource".
- The rule "don't show unbuilt kinds in the sidebar" trades roadmap
  discoverability for a less noisy day-one UI. Users who want the roadmap
  run `npx openspec list`, not the sidebar.

## Alternatives Considered

**Add a separate "surface" concept alongside resource kinds.** Rejected.

- Doubles the IA complexity without buying anything: the cross-cutting
  surfaces we have (Observability, Settings) are single fixed entries
  handled by the System group.
- Forces every future spec to first decide "is this a kind or a surface?"
  — a decision that adds no user-visible value.

**Show unbuilt kinds in the sidebar as disabled / "soon" placeholders.**
Rejected.

- Reads as an unfinished scaffold (the explicit anti-goal in spec web-ui's
  motivation).
- The forward-visibility benefit is real but small, and already provided by
  `npx openspec list`.

**Per-kind separate top-level navigation (no Resources group).** Rejected.

- Works for one kind, but degrades into a flat, ungrouped list as kinds are
  added. The Resources / System split keeps the sidebar readable.

## Amendment (2026-05-30)

The original decision modelled **every** user-facing managed entity as a
resource kind on a single axis. Implementation surfaced a concept that does
not fit that mould: **agents** (the Claude Code / Codex / built-in agents you
use). An agent is a _consumer_ of vault assets, not an asset the vault
manages — so collapsing it onto the resource-kind axis mislabels it. The
shipped IA therefore keeps the kind-agnostic Resource framework but adds a
second axis for consumers, and groups the sidebar by **role** rather than by
"is this a kind?".

What changed:

- **Agents are a separate axis, not a resource kind.** They are surfaced at
  `/agents` (list) and `/agents/:uid` (detail; `:name` until
  [Resource Identity Is an Immutable UID](resource-identity-is-an-immutable-uid.md))
  under their own **Agents** sidebar group. They are NOT shown in the `/resources` kind browser, because
  they are not vault assets.
- **The sidebar is grouped by role**, not on a single resource-kind axis:
  - **Agents** — the consumers (`/agents`).
  - **Resources** — the assets agents draw on, modelled as kind-agnostic
    resource kinds and surfaced through the kind registry. The nav entry is
    labelled **"MCP servers"** and lists only the kinds that register a
    list/card UI (today just `mcp_server`); the route is `/mcp-servers`
    (`/resources` is kept as a legacy redirect for old bookmarks).
  - **System** — cross-cutting tooling: the **Audit log** (`/audit`) and
    **Settings** (`/settings`).
- **The audit log is a System entry, not an "Observability" one.** It was
  first routed at `/audit`, with `/observability` kept as a legacy redirect;
  it now lives under **Activity** (`/activity`), which carries the audit log,
  the MCP invocation log and the daemon log as three tabs. The point the
  amendment made stands: the audit log is a concrete System surface, and
  "observability" was never a second name for it.
- **List surfaces converge on one shared, searchable, paginated table.** All
  list views use a single `DataTable` component (built-in search / filter /
  pagination) where a row click opens that item's detail page and row actions
  are an icon plus its label, never a bare icon (spec
  [web-ui](../../openspec/specs/web-ui/spec.md) "Label every row action").
  Cards are reserved for welcome / empty states only. This
  supersedes the earlier card-grid description of resource lists.
- **Future groups/items** (Chat, Channels, Skills, Knowledge, Memory,
  Observability) are planned but not shown today. The "no soon placeholders"
  policy from the original decision still holds: the sidebar documents the
  role-based structure but adds no dead nav entries. _Since shipped, and each
  landed in exactly the role group this amendment predicted_: Chat joined
  Agents, and Skills, Knowledge, Memory, Channels and Model providers joined
  Resources. Observability is the one entry that never became a surface — the
  logs it would have shown are Activity's three tabs — so nothing is reserved
  for it.

What survives unchanged from the original decision: the kind-agnostic
Resource framework is still the only abstraction for _assets_; new resource
kinds still plug into the Resources group with a single nav entry; and the
sidebar still shows only what ships today. The amendment narrows "everything
is a resource kind" to "every **asset** is a resource kind, surfaced under
Resources; consumers (agents) and cross-cutting tooling (System) are their
own role-based groups."

## Amendment (2026-06-11) — frontend kind UI

The Skill Manager spec shipped **skills** as a backend resource kind (identity, lifecycle,
audit, `on_delete` cascade all ride the kind-agnostic framework) but as
**bespoke frontend pages** (`/skills`, `/skills/:name`) rather than through
the frontend kind registry. That left the UI in an undeclared half-state:
the registry promised "one generic browse surface per kind" while skills
quietly bypassed it.

This amendment settles the frontend pattern:

- **The backend axis is unchanged.** Every asset is a resource kind; the
  unify-identity/lifecycle/audit rule and the never-unify-invocation rule
  (ADR resource-framework-upfront) still hold for all kinds.
- **The frontend kind registry is scoped, not universal.** It serves kinds
  whose UI fits the generic browse pattern (card/table + config-centric
  detail) — today `mcp_server` under `/mcp-servers`. It is NOT a promise
  that every kind renders through it.
- **Asset kinds with richer interaction models ship bespoke page-sets.**
  Skills (per-agent bindings, file viewer, drift verify) live at `/skills`
  with their own pages. This is the sanctioned pattern, not an exception.
- **New kinds choose explicitly at design time**: register a kind UI for
  generic browsing, or ship a bespoke page-set under their own route. The
  spec for the kind must state which.

Consequence: "skills appear in the sidebar's Resources group" (the 2026-05-30
amendment's future-groups list) is now shipped — the Resources group contains
**MCP servers** (`/mcp-servers`, registry-driven) and **Skills** (`/skills`,
bespoke).

## Amendment (2026-09-15) — frontend kind registry retired

The scoped frontend kind registry above is gone. Only three kinds ever
registered with it, the detail routes bypassed it and dispatched on `kind`
directly, and its shared list view had no callers. Every kind now follows one
layout instead of registering anything: list and detail pages in `pages/`,
components in `components/<kind>/`, hooks in `lib/hooks/`, API modules in
`lib/api/`, and a lazy route in `router.tsx`, with `ResourceDetailPage`
dispatching on `kind`. `frontend/src/kinds/` no longer exists;
[`.agents/frontend.md`](../../.agents/frontend.md) is the canonical statement
of the layout.

## Implementation note — agents are stored as resources

"Not a resource kind" in the 2026-05-30 amendment is an information-architecture
statement. In storage an agent *is* a resource of kind `agent` in the generic
`resources` table, and it gets the framework's CRUD, validation and audit
(`make_agent_kind` in `application/agent/kind.py`); it is only kept out of the
kind browser and surfaced on its own axis. Its detail route is `/agents/:uid`,
not `/agents/:name`, because resources are addressed by their immutable uid and
the name is a label.
