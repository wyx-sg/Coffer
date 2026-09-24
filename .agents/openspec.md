# OpenSpec — How Coffer Writes Specs

Coffer's product contract is written with [OpenSpec](https://github.com/Fission-AI/OpenSpec).
`openspec/specs/` says what the system does **now**; `openspec/changes/` holds
the work that will change it. Every PR that changes externally visible
behaviour carries an OpenSpec change and archives it before it merges, so the
specs on `main` always describe the code on `main`.

The CLI is pinned in the root `package.json`; `make install` fetches it, and
`npx openspec …` runs it. Its Claude Code commands and skills are checked in:
`/opsx:explore`, `/opsx:propose`, `/opsx:apply`, `/opsx:update`, `/opsx:sync`
and `/opsx:archive` under `.claude/commands/opsx/`, and the matching
`openspec-*` skills under `.claude/skills/`. Refresh both with
`npx openspec update` after bumping the pinned version. The skills call a bare
`openspec`, so either install the pinned version globally
(`npm install -g @fission-ai/openspec@<version>`) or put `node_modules/.bin` on
your `PATH`. `openspec/config.yaml` carries the project context and the writing
rules the CLI injects into every planning request.

## Layout

```
openspec/
  config.yaml                    # Context + per-artifact rules for planning.
  specs/<capability>/
    spec.md                      # REQUIRED. Purpose, requirements, scenarios.
    data-model.md                # Entities, fields, relationships. — when it has state
    contracts/api.openapi.yaml   # The wire contract, hand-authored and
                                 #   PR-reviewed; one per capability family.
                                 #                                  — when it has endpoints
    <child>/spec.md              # A CHILD capability; its id is `<capability>/<child>`.
  changes/<change-id>/
    .openspec.yaml               # schema, created date (+ skip_specs for no-delta work)
    proposal.md                  # Why, and what changes.
    design.md                    # How — when the change is not obvious.
    tasks.md                     # The checklist `/opsx:apply` works through.
    specs/<capability>/spec.md   # Deltas: ADDED / MODIFIED / REMOVED / RENAMED.
  changes/archive/YYYY-MM-DD-<change-id>/   # Every shipped change, kept.
```

That is the whole vocabulary. A capability is named, never numbered. Its id is
its path under `openspec/specs/`, so a child's is `<parent>/<child>`; that id
is what acceptance markers name. Plans, research and usage prose are not
long-lived capability files: a change's plan is its `design.md`, background
worth keeping becomes an ADR under `docs/decisions/`, and user-facing usage
belongs in `docs-site/guides/`.

A child exists to hold what varies by type. What every sibling shares — the
wire contract, the entities, the common requirements — stays in the parent, so
there is one `contracts/` per family, not one per type.

## The Change Workflow

1. **Propose** — `/opsx:propose "<intent>"`, or write the folder by hand. The
   change id is kebab-case and verb-led: `add-telegram-topics`,
   `tighten-skill-import`. Write `design.md` whenever there is a choice a
   reviewer would want explained; skip it when the tasks make the change
   obvious.
2. **Apply** — `/opsx:apply`. Implement task by task and tick each one in
   `tasks.md` as it lands. A task that is dropped is struck through with a
   reason, not deleted.
3. **Archive** — `/opsx:archive` (`npx openspec archive <id> --yes`) in the
   **same PR**, once the code is done and `make verify` passes. The deltas
   merge into `openspec/specs/` and the folder moves to `changes/archive/`.
   Nothing is deleted: the archive is the record of why each behaviour is the
   way it is.

A change that alters no requirement — a refactor, tooling, docs — gets a change
folder when it has a plan worth reviewing, with `skip_specs: true` in its
`.openspec.yaml`. A one-line fix needs none.

## Writing `spec.md`

```markdown
# <Capability title>

## Purpose
<What the capability is for and who relies on it.>

## Requirements

### Requirement: <imperative title, unique within the spec>
The system SHALL <behaviour>.

#### Scenario: <verb-led short name, unique within the spec>
- **GIVEN** <precondition>
- **WHEN** <action>
- **THEN** <observable outcome>
- **AND** <additional assertion>
```

- Every requirement states its rule with **SHALL** or **MUST** and owns **at
  least one scenario**; `openspec validate --all --strict` fails otherwise.
- A requirement is identified by its **title** — there are no requirement
  numbers. Renaming one is a `RENAMED` delta, so the rename is reviewed like
  any other change. Cite one from outside its spec as a link plus its title:
  ``[skill-manager](../openspec/specs/skill-manager/spec.md) "Keep one master folder per skill and carry it through a rename"``,
  or in a code comment as ``spec skill-manager "Keep one master folder per skill and carry it through a rename"``.
  `scripts/check_spec_citations.py` (run by `make lint`) resolves every such
  citation against the `### Requirement:` headings under `openspec/specs/`, so
  a rename fails the gate until its citations follow. A title an in-flight
  change adds or renames to is accepted and listed until that change is
  archived.
- A scenario is identified by its **name**, which an acceptance marker quotes;
  renaming a scenario means renaming its markers.
- When a capability has children, **a requirement lives at the level that owns
  it**: what every sibling shares stays in the parent, and only what is
  specific to one type moves into that child.
- **One capability per behaviour, not per layer.** A capability covers the
  whole vertical slice — backend plus whatever surfaces deliver it (CLI, MCP /
  shim, REST, web). Do not split one behaviour into per-surface specs.
- `spec.md` is the user-visible contract. Don't restate architecture in it;
  link [`docs/architecture.md`](../docs/architecture.md) or an ADR. Plain
  English, no time annotations (`Day N`, `Last updated`).

Tests cover each scenario through the `acceptance(spec, scenario)` marker — see
[testing.md](./testing.md) "Acceptance Scenarios — Cross-Tier Markers".
`scripts/audit_acceptance.py` fails a scenario no test covers, a marker naming
a scenario that does not exist, and a scenario name used twice in one spec.

## Keep the Docs in Sync With the Code

When a change alters behaviour, its spec deltas **and every related doc** change
in the same PR — before or alongside the code, never as a follow-up:

- the spec deltas in the change folder, archived into `openspec/specs/`;
- `contracts/api.openapi.yaml` — add, rename or remove endpoints and schemas
  to match the code, then re-run frontend codegen;
- `data-model.md` when an entity changes;
- the cross-cutting docs the change touches: the relevant `docs/decisions/`
  ADR, [`docs/architecture.md`](../docs/architecture.md), `docs-site/`, and any
  affected `.agents/*` convention.

A pure refactor or a frontend-only change with no contract impact needs no spec
edit — but if behaviour, an endpoint, a schema or the IA changes, the docs
change with it.

## Shared Mechanisms and Whose Spec They Are

Cross-cutting mechanisms get one shared module rather than a copy inside each
kind that uses them; "extract only after the second feature needs them" is an
invariant in [`docs/principles.md`](../docs/principles.md). Being shared says
nothing about **whose spec** a mechanism is:

| Mechanism | Where it lives | Whose spec |
|---|---|---|
| Audit log | `domain/audit.py`, `application/audit_service.py` | `resource-framework` |
| Credentials | `application/credentials/`, `infrastructure/credentials/` | `credentials` |
| Storage | `infrastructure/persistence/` (SQLAlchemy + Alembic; the only data-access path) | — (the startup migration run is `daemon`'s) |
| Resource framework (kinds, scope, delete) | `domain/resource.py`, `domain/scope.py`, `application/resource_service.py` + `resource_scope_ops.py` / `resource_delete_ops.py` | `resource-framework` |
| Retention | `domain/retention.py`, `application/retention_registry.py` / `retention_service.py` / `retention_worker.py` | `resource-framework` |
| Structured logging | `infrastructure/logging/` | — (the `daemon.log` file itself is `daemon`'s) |
| Kind-agnostic adapters two kinds share | `infrastructure/net/`, `infrastructure/agent_files/`, `domain/connection.py` | — |

Everything else is a kind (`mcp`, `agent`, `skill`, `knowledge`, `channel`, `chat`, `provider`, `memory`, `sync`) with its own subdir per layer. There is no `events`, `jobs` or `session` module — don't import one.

## Deciding What Is a Capability

"One spec per behavior, not per layer" and the End-to-End Deliverable Rule below
are two clauses of a single question — *is this thing a spec?* — that was never
written down as a procedure. The gap is not theoretical, and the worked example
is `resource-framework`, which failed the gate and then passed it.

**It failed as first proposed.** Drafted around the kind-agnostic lifecycle
alone, it would have owned no state: `coffer resource` has no create command,
the list route returns `[]` forever with zero kinds registered, and every
registration body gets a `4xx`. A spec whose whole subject is a dispatch seam
over other specs' tables fails test 1 — it is a rendering, not an owner — and
the draft was withdrawn.

**It passes now, on changed evidence rather than a better argument.** The
restructure moved the audit log and per-table retention into it, and
`audit_log` and `retention_policies` are durable state this spec seeds, reads,
configures and prunes rather than another spec's state it displays. With them it
is also independently operable — `coffer resource`, `coffer scope`,
`coffer audit` and `coffer retention` against a running daemon, with acceptance
scenarios that exercise each. The move was forced rather than convenient: the
three framework obligations the first audit would have parked in the
principles could not live there, because the principles hold rules and not
routes, tables, entities or scenarios, so parking them would have deleted them
as requirements and left the rest of the framework homeless inside one kind's
spec. [`resource-framework`](../openspec/specs/resource-framework/spec.md)
carries both readings in its `## Purpose`.

Two things are worth keeping from that. The gate is applied to **evidence**, so
the same subject can honestly fail it once and pass it later without anyone
having changed their mind. And a "no" is a statement about what the thing owns
today, never a permanent verdict on the name.

What follows is the procedure, recovered from that audit.

### The gate — five tests, all of them

1. **It owns state or behaviour** — not merely a rendering of another spec's
   state. A page that reads three other specs' tables and correlates them is a
   view, and belongs to whichever spec owns what it shows.
2. **Its boundary is provable from evidence** — its own route family, its own
   code packages, its own consumers, its own ADR. Not from prose, and not from
   the fact that the concept has a name.
3. **Its name is accurate.** If the name hides half of what it owns, either the
   name is wrong or the spec is two specs.
4. **It is one behaviour.** Requirement clusters that share no state and no consumers are
   a split waiting to happen, not a spec.
5. **It is independently implementable AND runnable** — persistence plus the
   surfaces that expose it, wired so a user can operate it. Depending on other
   specs is fine; delivering nothing operable is not. This is the End-to-End
   Deliverable Rule, applied as an admission test rather than a shipping test.

### The procedure for a new feature

- **Q1 — does it own durable state?** A table, a directory, a file family.
  No → it belongs to the spec that owns the state it renders. **Update that
  spec.**
- **Q2 — implemented alone, can a user do something?** Name the commands, the
  routes, the pages. No → it is substrate or a layer. Fold it into the spec it
  serves. If it is policy over several specs, it goes in this file or
  [`docs/principles.md`](../docs/principles.md), never into a spec of its own.
- **Q3 — where does its code want to live?** Four signals: route family, code
  packages, consumer list, ADR. Three or four pointing at an existing spec →
  **update that one**. Three or four pointing at a new name → **new spec**.
- **Q4 — one behaviour or several?** Several → split before writing, not after.
- **Q5 — does it vary by type?** Yes → the parent holds the common contract and
  children hold the per-type mechanics. **Cut the type axis only.** Cutting a
  second axis as well — the facet axis, say config files / MCP injection /
  plugins / native memory — produces a cartesian product of children, each too
  thin to own anything.

### Evidence, strongest first

1. **The import-linter fence in `backend/pyproject.toml`.** A `forbidden`
   contract with zero exceptions is a real boundary that someone has already
   defended. An `ignore_imports` waiver is a boundary being violated — the fix
   is to promote the shared thing to kind-agnostic substrate (the way
   `application/engine_ports.py` was) and delete the waiver, not to draw the
   spec around the violation.
2. **Who performs the write.** Far more reliable than whose concept it sounds
   like. Skill delivery sounds like it belongs to the agent that receives it;
   the code that writes the file is skill-manager's, and that settled it.
3. Route prefix, package path, consumer list, ADR — in that order.

### Anti-patterns, each one actually hit in this repo

- **"It has its own page."** Not a reason. Otherwise every page is a spec.
- **"Everything depends on it."** Not a reason *for* a spec — and, as
  `resource-framework` showed, not a reason against one either. Ask what it
  owns: cross-cutting *policy* with no state of its own belongs in the principles or an ADR,
  while a cross-cutting *mechanism* with its own tables and its own operable
  surfaces is a spec like any other. See the worked example above for the same
  subject read both ways.
- **"It governs how other specs deliver."** The rule belongs in this file. Where
  such a rule needs a test, the assertion may live as a requirement in the one
  spec whose scope is already cross-kind — the REST/CLI parity rule is stated
  below and made testable as a requirement of `resource-framework` — but it is stated
  once, in prose here, and tested once, there. Duplicating the prose into the
  spec would make this file advisory.
- **A requirement whose code lives in another package is misfiled**, whatever it
  feels like it belongs to.
- **Two specs pointing at each other for one requirement** means nobody owns it.
- **Duplicated prose in two specs** is one edit away from disagreeing. Keep one,
  cross-reference from the other.
- **A half that would own only a threshold constant, one column, or one GET
  route** is a thin half. Do not split it out.

### Where a shared requirement lives

| Shared by | Home |
| --- | --- |
| every kind | `resource-framework` — the framework contract each kind inherits (schema validation, lifecycle audit, per-table retention) is a *requirement* there, not a rule in the principles, which hold no routes, tables, entities or scenarios. An ADR still carries the *why* |
| two kinds | the spec that owns the code; the other cites it |
| the specs' own delivery rules | this file |
| a family that varies by type | the parent spec, plus one child per type |

## End-to-End Deliverable Rule

Every feature, on completion, must deliver a usable end-to-end product: backend persistence + the surfaces that expose it (CLI, MCP / `coffer-mcp-shim`, REST) — all wired so the user can really operate the feature.

A capability is "shipped" only when the end-to-end deliverable works AND every requirement's scenarios have at least one covering test.

**Every management operation is reachable from both REST and the CLI.** Whatever
a user can do to a spec's state through the management API they can also do
through `coffer`, sharing the same daemon and the same error model — and the
reverse. This is policy over every spec rather than a promise of any one of
them, which is why the rule is stated here: written into a single spec's prose
it would read as that spec's private promise, and the next spec would quietly
ship a REST-only half. A spec that cannot honour it records the gap in its
`## Purpose` instead of leaving the omission to be discovered.

The **test** for it lives in
[`resource-framework`](../openspec/specs/resource-framework/spec.md) as the
REST/CLI parity requirement, with the two acceptance scenarios "command line
covers every visual operation" and "command line surfaces same errors". That is
not a second statement of the rule — the assertion runs over the whole command
tree across every spec, so it has no narrower home, and `resource-framework` is
the only spec whose scope is already cross-kind. Stated once here, tested once
there: change the policy and you change this paragraph *and* that requirement,
never one of them.
