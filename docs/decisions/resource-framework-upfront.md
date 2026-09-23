# Resource Framework Designed Upfront

**Status**: Accepted
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: [`docs/principles.md`](../principles.md) (II Spec-as-Truth, Technology & Architectural Constraints), [Layer-First Code Layout](code-layout-layer-first.md), spec `mcp-gateway`

## Context

Coffer is committed to managing several resource kinds over time. The first
spec (`mcp-gateway`) ships `mcp_server` as the only concrete kind. The
decision is whether to design the **Resource abstraction** now — while only
one kind is concrete — or to delay until a second kind lands.

The principles state:

> Cross-cutting modules are extracted only after the second feature needs them.

This default biases toward _late_ abstraction. We have to decide whether the
Resource framework is "a cross-cutting module" (subject to that rule) or "a
core domain concept" (not subject to it).

Counter-pressure: the user has explicitly named the next several kinds with
confidence. The cost of refactoring this spec's DB schema, audit pipeline,
retention framework, and surface routing once a _second_ kind lands is
non-trivial. The question is whether "design once now" is cheaper than
"design twice and refactor".

## Decision

Design the Resource framework as **core domain** in spec `mcp-gateway`:

- `Resource` is a top-level domain entity with kind-agnostic identity
  (`<kind>:<name>`), lifecycle (register / update / enable / disable / delete),
  audit, and per-kind config validation. [The identity is now an immutable
  `uid` and the name is a mutable label —
  [Resource Identity Is an Immutable `uid`](resource-identity-is-an-immutable-uid.md),
  which wholly supersedes Resource Identifier Format. That it is *kind-agnostic*,
  which is what this decision turned on, is unchanged; if anything the change
  bears it out, since making rename a framework field rather than one kind's
  private endpoint is exactly the mechanical plug-in this ADR argued for.]
- The framework unifies **identity + lifecycle + audit + metadata**. It does
  **not** unify behaviour — invocation semantics differ per kind.
- The MCP gateway is the first concrete kind plugged into this framework, not
  a one-off feature.

The principles' clause about cross-cutting modules does **not** apply,
because Resource is part of the project's core domain model, not a cross-cutting
infrastructure module (such as logging, telemetry, or auth middleware).

## Consequences

**Positive**

- Future kinds plug in mechanically: write `<layer>/<new_kind>/`, have its
  `make_<new_kind>_kind()` factory return a frozen `Kind`, and let the
  composition root register that `Kind` and mount the kind's routers/CLI
  groups through a per-kind wiring module — no schema migration, no audit
  rewiring, no retention plumbing rework.
- Audit, retention, and resource-list UI are kind-agnostic from day one.
- The first refactor cost (extracting Resource from MCP-specific code on the
  arrival of the second kind) is avoided.
- The boundary between framework and kind is made explicit from the start,
  reducing the risk of MCP-specific assumptions leaking into framework code.

**Negative**

- This spec carries the abstraction's overhead with only one concrete kind to justify it.
- The framework's behavioural boundary must be guarded: the temptation to unify
  invocation semantics across kinds (a "god `invoke()` method") would be a
  defect, not a feature. See alternatives below.
- [Layer-First Code Layout](code-layout-layer-first.md) is forced to be a same-spec decision because the
  framework spans every layer.

**Follow-ons**

- The first time a _cross-kind_ concern surfaces inside the kind code (e.g., MCP
  and skill both needing subprocess supervision), apply the principles'
  "extract on second feature" rule normally — the Resource framework is not a
  blanket licence to pre-abstract everything.

## Alternatives Considered

**Extract on second feature (the principles' default)**. Rejected: a generic
Resource framework cannot be extracted cleanly from MCP-specific code without
also re-modelling the audit table, the surface routing, and the retention
framework. The "second feature" cost would be a substantial refactor, not a
modest extraction.

**Full plugin architecture (third-party loadable kinds)**. Rejected: a usable
plugin contract can only be designed against ≥ 2 concrete implementations;
designing one against MCP alone would either over-fit to MCP or be too generic
to enforce anything. Coffer is a single-user local-first OSS tool — there is no
realistic third-party plugin ecosystem to serve at this scope.

**Per-kind silos with no shared abstraction**. Rejected: the user has named ≥ 4
future kinds with high confidence, all of which share identity, lifecycle,
audit, and surface-level CRUD. Building those four times would be both more
code and more drift risk than one framework.
