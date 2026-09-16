# Implementation Plan: [FEATURE]

**Spec**: `[short-name]` (the folder name under `specs/`, named for the feature — never numbered) | **Branch**: `feature/[short-name]`
**Input**: Feature specification from `specs/[short-name]/spec.md`

<!--
  No date field: `agents/sdd.md` forbids time annotations in spec / plan /
  research / data-model / quickstart. Chronology lives in git and in
  `.specify/memory/roadmap.md`.

  A child spec's plan lives beside its own spec.md
  (`specs/<parent>/<child>/plan.md`) and its spec id is the path,
  e.g. `channels/telegram`.
-->

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]  
**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]  
**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]  
**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]  
**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]
**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]  
**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]  
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]  
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

[Gates determined based on constitution file]

## Project Structure

### Documentation (this feature)

```text
specs/[short-name]/
├── spec.md              # The user-visible contract (authored first)
├── plan.md              # This file
├── research.md          # Background and alternatives, when the choice needs one
├── data-model.md        # Entities, fields, relationships
├── quickstart.md        # How to use the finished feature
└── contracts/
    └── api.openapi.yaml # The wire contract — hand-authored, PR-reviewed
```

See [`agents/sdd.md`](../../agents/sdd.md) for which of these are required and
which are written only when the feature needs them.

### Source Code

<!--
  Coffer's layout is fixed, not chosen per feature. Name the real directories
  this feature touches; do not invent a parallel structure.

  The layering is enforced, not advisory: `scripts/check_architecture_doc.py`
  fails `make lint` when a package exists on disk but is not named in
  `.specify/memory/architecture.md`, and the import-linter contracts in
  `backend/pyproject.toml` enforce the import direction — `domain/` imports
  nothing, `application/` does not import `infrastructure/` or `surfaces/`,
  and `infrastructure/` adapts to ports defined in `application/` and is wired
  only at the composition root.
-->

```text
backend/coffer/
├── domain/<slice>/        # Pure types + business rules. No I/O, no SDKs.
├── application/<slice>/   # Services, orchestration, ports, Kind wiring.
├── infrastructure/<slice>/# DB, transports, filesystem, credential store.
└── surfaces/              # http/ (FastAPI), cli/ (Typer), mcp shim, callback/

backend/tests/{unit,integration,contract}/   # Mirrors the package tree

frontend/src/
├── pages/                 # Route-level pages
├── components/<feature>/  # Feature components, dialogs, tables
└── lib/{hooks,api}/       # Queries + mutations, and the typed wire client

e2e/                       # Playwright web suite + MCP shim round-trip
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
