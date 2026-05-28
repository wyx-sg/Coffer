# ADR-007: Information Architecture — Everything Is a Resource Kind

**Status**: Accepted
**Date**: 2026-05-28
**Deciders**: Yuxing Wu
**Related**: [ADR-001](ADR-001-resource-framework-upfront.md), spec `002-ui-shell`

## Context

Spec `001-mcp-gateway` introduced the `mcp_server` resource kind on top of a
kind-agnostic Resource framework (see [ADR-001](ADR-001-resource-framework-upfront.md)).
`mcp_server` is the kind that ships today.

Spec `002-ui-shell` has to decide how resource kinds — and cross-cutting
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
- The Resource framework from [ADR-001](ADR-001-resource-framework-upfront.md)
  is the only abstraction the UI needs to understand; the UI does not need
  a separate "surface" registry.

**Negative**

- "Resource" is forced to carry concepts that are not always called
  "resources" in user conversation. Mitigated by the user-facing label being
  the kind's own noun (e.g. "MCP server"), not the word "resource".
- The rule "don't show unbuilt kinds in the sidebar" trades roadmap
  discoverability for a less noisy day-one UI. Users who want the roadmap
  read `.specify/memory/roadmap.md`, not the sidebar.

## Alternatives Considered

**Add a separate "surface" concept alongside resource kinds.** Rejected.

- Doubles the IA complexity without buying anything: the cross-cutting
  surfaces we have (Observability, Settings) are single fixed entries
  handled by the System group.
- Forces every future spec to first decide "is this a kind or a surface?"
  — a decision that adds no user-visible value.

**Show unbuilt kinds in the sidebar as disabled / "soon" placeholders.**
Rejected.

- Reads as an unfinished scaffold (the explicit anti-goal in spec 002's
  motivation).
- The forward-visibility benefit is real but small, and already provided by
  `.specify/memory/roadmap.md`.

**Per-kind separate top-level navigation (no Resources group).** Rejected.

- Works for one kind, but degrades into a flat, ungrouped list as kinds are
  added. The Resources / System split keeps the sidebar readable.
