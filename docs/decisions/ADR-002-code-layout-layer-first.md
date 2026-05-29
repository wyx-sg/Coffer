# ADR-002: Code Layout — Layer-First with Kind Subdirectories

**Status**: Accepted
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: `.specify/memory/constitution.md` (Architectural Constraints), [ADR-001](ADR-001-resource-framework-upfront.md)

## Context

[ADR-001](ADR-001-resource-framework-upfront.md) commits Coffer to a Resource framework as part of spec
`001-mcp-gateway`. Two layouts can realise it while honouring the
constitutional layered architecture (`surfaces → application → domain` with
`infrastructure` underneath):

- **Layer-first with kind subdirectories** — each top-level layer holds
  kind-agnostic files at its root and one `<kind>/` subdirectory per kind.
- **Vertical slice** — a new top-level `kinds/` directory, each kind a complete
  vertical slice with its own internal `domain/ application/ infrastructure/
surfaces/`.

Both can satisfy the constitution if importlinter contracts enforce dependency
direction. The choice is about navigability, conventions, and how the
"extract-on-second-feature" rule plays out.

## Decision

**Layer-first with kind subdirectories.**

```
backend/coffer/
├── domain/                       # kind-agnostic core
│   ├── resource.py
│   ├── audit.py
│   └── mcp/                      # MCP-specific value objects
├── application/
│   ├── resource_service.py       # kind-agnostic CRUD
│   ├── audit_service.py
│   ├── retention_service.py
│   └── mcp/                      # MCP-specific services
├── infrastructure/
│   ├── persistence/
│   ├── credentials/
│   ├── daemon/
│   └── mcp/                      # subprocess, http upstream client
└── surfaces/
    ├── http/
    │   ├── app.py                # composition root
    │   ├── resource_routes.py
    │   └── mcp/                  # MCP HTTP routes
    ├── cli/
    │   ├── main.py
    │   ├── resource_cmd.py
    │   └── mcp.py
    └── shim/                     # coffer-mcp-shim (MCP-only by nature)
```

Each kind is registered at the composition root via an explicit `KindModule`
dataclass — no global registry, no import side effects, no `kinds/` directory.

## Consequences

**Positive**

- Mirrors the constitutional `surfaces → application → domain (← infrastructure)`
  layering literally in the file system. The architecture document reads the
  same as the directory tree.
- Familiar layout for Python/FastAPI conventions; new contributors recognise
  it immediately.
- When a cross-kind concern surfaces, the question is "which layer does it
  belong in" — one decision, naturally placed at the layer root.
- Small kinds pay no ceremony (`domain/profile.py` is a single file; in a
  vertical slice it would be `kinds/profile/domain/profile.py`).
- Importlinter rules read naturally:
  - `domain → infrastructure | surfaces` forbidden
  - `*/mcp → */<other_kind>` forbidden
  - `domain/*` (kind-agnostic) → `domain/<kind>/*` forbidden

**Negative**

- Code for one kind spans 4–5 directories. Mitigation: IDE search and grep make
  this a non-issue; the user has confirmed acceptance.
- Importlinter contracts must enforce two rule families (layered + cross-kind),
  not one.

## Alternatives Considered

**Vertical slice (`kinds/<x>/{domain,application,infrastructure,surfaces}/`)**.
Rejected.

- Adds a fifth top-level concept (`kinds/`) alongside the constitutional four
  layers; the architecture document would have to explain both.
- Introduces dual-decision pain on every cross-kind extraction: "does this
  belong in the top-level layer, or in `kinds/<x>/<layer>/`?" — two questions
  to answer instead of one.
- Mostly fits the DDD-bounded-context / modular-monolith pattern, which is
  motivated by team isolation, independent deploy cadence, or microservice
  extraction — none of which apply to a single-user local-first OSS app.
- The "vertical slice is more discoverable" advantage collapses under IDE
  search; the cost (layout duality) does not.

**Flat per-kind module (no internal layering within the kind)**. Rejected.
Some kinds will grow large (the MCP kind is already projected at ~1500 lines).
Importlinter inside a flat module cannot enforce the layered direction.

**Plugin architecture (each kind a loadable plugin with manifest, isolation,
discovery)**. Considered and deferred: see [ADR-001](ADR-001-resource-framework-upfront.md). Not a layout decision in
itself; relevant here only as the "heaviest" comparator we considered and
rejected.
