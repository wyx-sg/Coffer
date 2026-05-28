# ADR-008: Information Architecture — Everything Is a Resource Kind

**Status**: Accepted
**Date**: 2026-05-28
**Deciders**: Yuxing Wu
**Related**: [ADR-001](ADR-001-resource-framework-upfront.md), spec `002-ui-shell`

## Context

Spec `001-mcp-gateway` introduced the `mcp_server` resource kind on top of a
kind-agnostic Resource framework (see [ADR-001](ADR-001-resource-framework-upfront.md)).
That framework was designed in anticipation of more kinds (`skill`, `memory`,
`knowledge_base`, `channel`, `agent`, plus the built-in `chat` surface).

Spec `002-ui-shell` has to decide how those future kinds — and other
user-facing concepts that are not strictly "resources" in the domain sense
(integrations, channels, the chat surface, the audit log) — surface in the
navigation. The naïve approach is to introduce a second top-level concept in
the IA: a "surface" axis sitting next to the "resource kind" axis, so the
sidebar reads as two unrelated groups (Resources vs Features). The redesign
goal was the opposite: **one consistent navigation model that scales as
more kinds ship, without re-doing the IA each time.**

A related question is what to do with planned-but-unbuilt kinds in the
sidebar. The temptation is to list them as "coming soon" placeholders so
users see what's planned. In practice this fills two-thirds of the sidebar
with dead entries and makes the product look like an unfinished scaffold.

## Decision

**Adopt a single-axis information architecture: every user-facing managed
entity is a resource kind, surfaced through the same sidebar group.**

Concrete consequences:

- The sidebar has exactly two groups today — **Resources** (resource kinds)
  and **System** (cross-cutting tooling: Observability, Settings). When a
  new kind ships, it appears in the Resources group; no new group is
  introduced.
- Concepts that are not obviously "resources" in the colloquial sense — a
  Seatalk channel, an agent, the built-in Chat — are modelled as resource
  kinds too. A **channel** is a registered, configured integration with its
  own lifecycle. An **agent** is a resource that both consumes capabilities
  and (when exposed) provides them; the dual-role is a property of the
  agent resource, not a reason to split the navigation.
- The future built-in **Chat** surface gets a pinned entry above the two
  groups when it ships; pinning is a visual concession, not a separate IA
  axis.
- **Sidebar policy: no "soon" placeholders.** Planned kinds are not shown
  in the sidebar until their feature spec ships. The IA documentation
  (spec.md `## Information Architecture`) records the planned kinds for
  forward visibility; the rendered UI shows only what works today.

## Consequences

**Positive**

- Future specs (003 desktop shell, 004 agent registry, 005 skill manager,
  006 knowledge base, 007 memory, etc.) plug into the same Resources group
  with a single nav entry each — no IA renegotiation per spec.
- The sidebar always reads as "here is what Coffer does", not "here is what
  Coffer plans to do." A first-time visitor sees a product, not a backlog.
- The Resource framework from [ADR-001](ADR-001-resource-framework-upfront.md)
  is the only abstraction the UI needs to understand; the UI does not need
  a separate "surface" registry.

**Negative**

- "Resource" is forced to carry concepts (channels, agents-as-providers,
  chat) that are not always called "resources" in user conversation. Specs
  must spend a line up front explaining the term. Mitigated by the
  user-facing label being the kind's own noun (MCP server, Skill, Channel,
  Agent, Chat), not the word "resource".
- The rule "don't show planned kinds in the sidebar" trades discoverability
  of the roadmap for a less noisy day-one UI. Users who want the roadmap
  read `.specify/memory/roadmap.md`, not the sidebar.

## Alternatives Considered

**Add a separate "surface" concept alongside resource kinds.** Rejected.

- Doubles the IA complexity without buying anything: every "surface" we
  considered (Chat, Observability, Settings) either is a single fixed entry
  (Observability, Settings — handled by the System group) or is itself
  better modelled as a kind (Chat sits on top of an agent resource).
- Forces every future spec to first decide "is this a kind or a surface?"
  — a decision that adds no user-visible value.

**Show planned kinds in the sidebar as disabled / "soon" placeholders.**
Rejected.

- Reads as an unfinished scaffold (the explicit anti-goal in spec 002's
  motivation). Two-thirds of the sidebar would be inert on day one.
- The forward-visibility benefit is real but small, and already provided by
  `.specify/memory/roadmap.md` and the spec's own `## Information
Architecture` section.

**Per-kind separate top-level navigation (no Resources group).** Rejected.

- Works for one kind (today), but with five named future kinds the sidebar
  becomes a flat list with no obvious grouping. The Resources / System
  split lets the sidebar stay readable as kinds are added.
