# Code Layout Is Layer-First, With One Subdirectory per Kind

**Status**: Accepted
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: [principles](../../docs-site/architecture/principles.md) (Technology & architectural constraints — the layering), [The Resource Framework Is Core Domain](resource-framework-upfront.md), [Composition Root With Explicit Wiring](composition-root-explicit-wiring.md), [Layering & boundaries](../../docs-site/architecture/layering.md), PR #386

## Context

[The Resource Framework Is Core Domain](resource-framework-upfront.md) commits
Coffer to a kind-agnostic core with per-kind code plugged into it, in the same
spec as the first kind. The principles fix the layering —
`surfaces → application → domain`, with `infrastructure` adapting ports that
`application` defines and wired only at the composition root — but not how the
files are arranged. Two axes have to be expressed at once: the layer a module
belongs to, and the kind (if any) it belongs to.

Whatever layout is chosen must let two families of rules be enforced
mechanically by import-linter (`backend/pyproject.toml`): the layer direction,
and the rule that one kind does not import another. It also has to survive
scale: today there are seven kinds plus two cross-cutting slices that are
fenced like kinds (`chat`, the turn platform, and `sync`), and the smallest
kind (`provider`) is about 2,900 lines across its domain, application and
infrastructure packages while the largest (`channel`) is about 11,700. The
backend has a 400-line file cap (`scripts/check_file_sizes.py`), so every kind
is many files.

## Options Considered

### Option A — Layer-first, with a `<kind>/` subdirectory inside each layer (chosen)

Each top-level layer holds its kind-agnostic modules at its root and one
subdirectory per kind:

```
backend/coffer/
├── domain/            resource.py, scope.py, audit.py, …   + agent/ channel/ mcp/ skill/ …
├── application/       resource_service.py, audit_service.py, retention_service.py, …
│                      + agent/ channel/ knowledge/ mcp/ memory/ provider/ skill/ sync/ chat/ …
├── infrastructure/    persistence/ credentials/ daemon/ net/ llm/ agent_files/ …
│                      + agent/ channel/ mcp/ skill/ sync/ chat/ …
└── surfaces/
    ├── http/          app.py, *_wiring.py, resource_routes.py, dependencies.py, … + mcp/ knowledge/ memory/ chat/
    ├── cli/           main.py, resource_cmd.py, <kind>_cmd.py, …
    └── shim/          coffer-mcp-shim
```

- **Pros.** The tree reads the same as the layering diagram, so the layer
  rule is a prefix rule (`coffer.domain` may not import `coffer.application`,
  …). The cross-kind rule is also a prefix rule, one contract per kind naming
  that kind's packages as sources and every other kind's as forbidden. When a
  concern turns out to be shared, there is one question — which layer — and the
  answer is that layer's root. It is the layout Python/FastAPI contributors
  expect.
- **Cons.** One kind's code spans four or five directories. Surface modules
  for a kind are not always in a subdirectory (`surfaces/http/skill_routes.py`,
  `surfaces/cli/skill_cmd.py`), so the per-kind contracts list them one by one
  and the lists must be kept symmetric by hand.
- **Why it wins.** Both rule families become cheap, prefix-based contracts, and
  the cost (spread across directories) is a navigation cost that search
  removes, not a correctness cost.

### Option B — Vertical slice: `kinds/<kind>/{domain,application,infrastructure,surfaces}/`

A fifth top-level directory where each kind is a complete slice with its own
internal layers.

- **Pros.** Everything about one kind is in one folder; deleting a kind is
  deleting a folder. It is the modular-monolith / bounded-context shape.
- **Cons.** It adds a fifth top-level concept beside the four layers the
  principles fix, so the architecture has to explain both. Every extraction
  becomes two questions — top-level layer, or `kinds/<x>/<layer>/`? — and the
  layer contracts have to be written once per slice. The motivations for the
  pattern (team ownership, independent deploys, a path to services) do not
  exist in a single-user, single-process app.
- **Why it loses.** It doubles the layering rules to buy discoverability that
  IDE search already gives.

### Option C — Flat per-kind module (one package per kind, no internal layering)

`coffer/mcp/`, `coffer/skill/`, … each a flat package, with the kind-agnostic
core beside them.

- **Pros.** Least ceremony; a small kind could be one or two files.
- **Cons.** No kind is small: at 2,900 to 11,700 lines under a 400-line cap,
  every kind is dozens of files, and import-linter cannot enforce a layer
  direction inside a flat package. Kind code would import SQLAlchemy and FastAPI
  from wherever it liked.
- **Why it loses.** It gives up the layering the principles require for the
  code that most needs it.

### Option D — Loadable plugin per kind

Each kind a package discovered at runtime, with a manifest and isolation.
This is a packaging and discovery choice rather than a layout, and it is argued
and rejected in [The Resource Framework Is Core Domain](resource-framework-upfront.md)
and [Composition Root With Explicit Wiring](composition-root-explicit-wiring.md);
it appears here only as the heaviest comparator.

## Decision

Layer-first with kind subdirectories. Kind-agnostic modules live at each
layer's root; a kind's modules live in `<layer>/<kind>/` (or, for a few surface
modules, a `<kind>_*.py` file at the surface root). The layout is enforced by
import-linter contracts in `backend/pyproject.toml`:

- **Layer direction.** "Layered architecture: surfaces > application > domain";
  "Infrastructure does not import surfaces"; "Application does not import
  infrastructure" (with two listed exceptions: `application.knowledge` and
  `application.memory` may use their own file substrate in `infrastructure`);
  "Domain is pure" (no project layer, no FastAPI/SQLAlchemy/sqlite3/httpx/keyring/anyio).
- **Cross-kind imports forbidden.** One symmetric contract per fenced slice —
  nine of them: `mcp`, `agent`, `skill`, `knowledge`, `channel`, `chat`,
  `provider`, `memory`, `sync`. The listed exceptions are a kind's pure domain
  vocabulary where another kind exists to act on it: `provider` and `memory`
  may import `domain.agent`, `channel` may import `domain.chat`. Imports under
  `TYPE_CHECKING` do not count. Everything else crosses through a port the
  consuming kind declares and the composition root satisfies.
- **Shared ground** that every kind may import: the kind-agnostic core
  (Resource, audit, retention, scope, `domain/connection.py`), Coffer's own
  engine (`application.engine` and the engine modules fenced in the core
  contract), the knowledge substrate (`domain.knowledge`,
  `infrastructure.knowledge`), and the kind-agnostic infrastructure packages
  `infrastructure.net` (the SSRF guard), `infrastructure.agent_files`
  (Claude Code transcript parsing), `infrastructure.llm` and
  `infrastructure.persistence`.
- **Kind-agnostic core does not import kind-specific code.** The core modules
  (and `surfaces/http/dependencies.py`) may import no kind. Its one listed
  exception is Alembic's `migrations/env.py`, which imports
  `infrastructure.channel.persistence` and `infrastructure.mcp.persistence`
  beside the kind-agnostic `infrastructure.persistence.models`, so those
  kinds' ORM models are on `Base.metadata`. The exception is listed per module,
  so a new kind that wants its tables there has to add itself on purpose.

Only the composition root may see two kinds at once; how it does so is
[Composition Root With Explicit Wiring](composition-root-explicit-wiring.md).

## Consequences

- The architecture document and the directory tree describe the same thing;
  [Layering & boundaries](../../docs-site/architecture/layering.md) is the
  reader's guide.
- A package two kinds need moves to the layer root and becomes kind-agnostic
  (`infrastructure/net/`, `infrastructure/agent_files/`, `domain/connection.py`
  for `CODEX_ENV_KEY`), rather than one kind importing the other.
- Adding a kind means adding its packages to its own contract as sources and
  to every other contract's forbidden list, by hand; removing one means taking
  it out of all of them, and an `ignore_imports` entry that no longer matches
  fails `make verify`.
- `migrations/env.py` puts only the kind-agnostic models and the `channel`
  and `mcp` models on `Base.metadata`; `skill_agent_bindings`,
  `conversations` and `chat_messages` are declared in modules it does not
  import. No revision in the lineage is autogenerated, so `upgrade head` is
  unaffected, but autogenerate would not see those tables.
