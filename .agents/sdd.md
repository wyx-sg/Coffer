# SDD — Spec-Driven Development

Coffer's spec layout and conventions come from [Speckit](https://github.com/github/spec-kit). Every PR that changes externally visible behavior updates the relevant `spec.md` first, then the code.

**The `/speckit-*` slash commands are not part of this repository.** `.claude/commands/` is gitignored, so cloning gets you none of them; they exist only if you installed Speckit locally yourself. Nothing in this doc requires them — every file below is written by hand. What the repo does track is `.specify/templates/` (the section templates) and `.claude/skills/coffer-spec/` (the checked-in scaffolder, see [`harness.md`](./harness.md)).

## Folder Layout

A spec lives at `specs/<short-name>/`, named for the feature rather than numbered. There is one kind of spec — no foundation / capability / quality split. Nineteen specs exist today: fifteen top-level, plus four that are children of another (`specs/<parent>/<child>/`). A spec's id is its path under `specs/`, so a child's is `<parent>/<child>` (`scripts/audit_acceptance.py` reads `spec.md` at any depth), and a child numbers its own FR ids from FR-001 inside that path instead of continuing its parent's.

Cross-cutting mechanisms get one shared module rather than a copy inside each kind that uses them; the "extract only after the second feature needs them" rule is the invariant in [`.specify/memory/constitution.md`](../.specify/memory/constitution.md). Being shared says nothing about **whose spec** a mechanism is, and the answer differs per row: three of those below are the subject of [`specs/resource-framework/`](../specs/resource-framework/spec.md), which owns the kind-agnostic half of the resource model every kind plugs into, and the rest belong to a spec that owns something larger, or to none. The mechanisms that actually exist today:

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

```
specs/<short-name>/
  spec.md              # REQUIRED. The user-visible contract, including the
                       #   "## Acceptance Scenarios" section (scenarios live
                       #   in spec.md, NOT in a separate .feature file).
  plan.md              # Implementation plan.            — usual
  quickstart.md        # How to use this feature.         — usual
  data-model.md        # Entities, fields, relationships. — usual
  contracts/
    api.openapi.yaml   # The wire contract, hand-authored and PR-reviewed.
                       #   Exactly one file per spec — no events.json,
                       #   no tools.json.                 — when it has endpoints
  research.md          # Background, alternatives.        — when useful
  tasks.md             # TRANSIENT work breakdown, deleted when the spec
                       #   ships (see below).             — while building
  <child-name>/        # A CHILD SPEC, same vocabulary all the way down.
    spec.md            #   Its id is the path: `<short-name>/<child-name>`.
    ...                #                                  — when the feature
                       #                                    splits by type
```

That is the whole vocabulary of *durable* files — plus the transient
`tasks.md` described below, nothing else appears under a spec. The fifteen
top-level specs are `agent-registry`, `channels`, `chat`, `credentials`,
`daemon`, `desktop-app`, `internal-engine`, `knowledge`, `mcp-gateway`,
`memory`, `provider-switching`, `resource-framework`, `skill-manager`,
`vault-sync`, `web-ui`. Twelve carry the full set (`contracts/ data-model.md
plan.md quickstart.md spec.md`, six of those plus `research.md`); `desktop-app`
and `web-ui` have `plan.md quickstart.md spec.md` because neither adds
endpoints of its own; `memory` has everything but `plan.md`.

The four children are `agent-registry/claude-code`, `agent-registry/codex`,
`channels/telegram` and `channels/seatalk`, and each carries `spec.md` alone. A
child exists to hold what varies by type, so the wire contract, the entities and
the plan that every sibling shares stay in the parent — one `contracts/` per
family, not one per type.

`tasks.md` is the one **transient** slot: a checkbox list an agent ticks
through while building, deleted once the work ships, which is why no spec
carries one today (PR #334 removed the last of them as "documents that
describe work to be done, for work that is done"). It is supported rather
than merely tolerated — `docs-site/scripts/sync-reference.mjs:35` excludes
`tasks.md` by name from the published site and rewrites inbound links to it
as GitHub blob URLs — so keep that exact filename if you write one, and
delete it when the spec ships. `.specify/templates/tasks-template.md` is its
template.

No spec has ever had a `checklists/` directory — don't write one. Review and
release checks live in [`workflow.md`](./workflow.md) and `make verify`, which
is where they are actually enforced.

### Requirement ids

FR ids are numbered **per spec, starting at FR-001**, and are **never reused**:
a requirement that is removed leaves its number retired rather than letting the
next one inherit it. A recycled id is quietly wrong everywhere it is cited —
in an ADR, a test name, a commit message — in a way a retired one never is.

The rule was suspended **once**, for the restructure that split nine specs into
fifteen plus four children. Content moved between specs on a scale that left no
readable numbering — a requirement re-homed from `mcp-gateway` to `credentials`
would have opened its new spec at eleven with one through ten permanently
absent — so every spec renumbered from FR-001 in document order, from a reviewed
old→new mapping table. That reset is over. It does not extend to a future
restructure: a requirement that moves between specs from now on takes the next
free id in its new home and retires the old one. See
[FR Ids Reset Once](../docs/decisions/fr-ids-reset-once.md) for why the
exception was made explicit rather than left for a reader to mistake for a bug.

An id is therefore only unique *within* the spec that carries it. Cite one from
outside as `<spec-id> FR-00N` (e.g. `mcp-gateway FR-013`), never as a bare
`FR-013`.

When a spec has children, **a requirement lives at the level that owns it**:
what every sibling shares stays in the parent, and only what is specific to one
type moves into that child. A child numbers its own requirements from FR-001,
so `channels FR-012` and `channels/telegram FR-012` are two different
requirements and the spec id is what tells them apart.

**One spec per behavior, not per layer.** A spec covers the entire vertical slice — backend services plus whatever surfaces are needed to deliver that user-visible behavior (CLI, MCP / shim, REST). Do not split a single behavior into separate per-surface specs; that creates drift between two halves of the same contract.

**Skeleton-first phase**: When seeding a new spec, write `spec.md` first — it is the only required file. `plan.md`, `data-model.md`, `contracts/api.openapi.yaml` and `quickstart.md` are added by hand as the spec moves toward implementation; `research.md` only when the alternatives are worth recording.

## Keep the Docs in Sync With the Code

When a change alters behavior, update the spec **and every related doc in the same PR** — before or alongside the code, never as a follow-up. Spec-first: the spec is the source of truth and the code conforms to it. "Related docs" is the whole set, not just `spec.md`:

- `specs/<short-name>/spec.md` — the user-visible contract and its acceptance scenarios.
- `specs/<short-name>/contracts/api.openapi.yaml` — the wire contract; add/rename/remove endpoints and schemas to match the code.
- `specs/<short-name>/data-model.md`, `plan.md`, `quickstart.md` — entities, plan, and usage prose.
- Cross-cutting docs the change touches: the relevant `docs/decisions/` ADR, `.specify/memory/architecture.md`, and any affected `.agents/*` convention such as `.agents/visual-language.md`.

The acceptance audit (`scripts/audit_acceptance.py`, run by `make verify`) ties each `spec.md` scenario name to a test marker, so renaming/adding/removing a scenario means updating its `@pytest.mark.acceptance(... scenario=...)` / `acceptance(...)` marker too. A pure refactor or a frontend-only change with no contract impact needs no spec edit — but if behavior, an endpoint, a schema, or the IA changes, the docs change with it.

## Acceptance Scenarios — In `spec.md`, Gherkin-Style

Use Gherkin-style language inside the `## Acceptance Scenarios` section of `spec.md`. Each scenario maps to one or more tests (see [testing.md](./testing.md)).

```markdown
## Acceptance Scenarios

### Scenario: <verb-led short name>

- **Given** <precondition>
- **When** <action>
- **Then** <observable outcome>
- **And** <additional assertion>
```

Tests cover each scenario via the `acceptance(spec, scenario)` marker — see [testing.md](./testing.md) "Acceptance Scenarios — Cross-Tier Markers".

## Deciding What Is a Spec

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
constitution could not live there, because a constitution holds rules and not
routes, tables, entities or scenarios, so parking them would have deleted them
as requirements and left the rest of the framework homeless inside one kind's
spec. [`specs/resource-framework/spec.md`](../specs/resource-framework/spec.md)
carries both readings under its own "Why this is a spec".

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
4. **It is one behaviour.** FR clusters that share no state and no consumers are
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
  serves. If it is policy over several specs, it goes in this file or the
  constitution, never into a spec of its own.
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
  owns: cross-cutting *policy* with no state of its own is constitution or ADR,
  while a cross-cutting *mechanism* with its own tables and its own operable
  surfaces is a spec like any other. See the worked example above for the same
  subject read both ways.
- **"It governs how other specs deliver."** The rule belongs in this file. Where
  such a rule needs a test, the assertion may live as a requirement in the one
  spec whose scope is already cross-kind — the REST/CLI parity rule is stated
  below and made testable as `resource-framework FR-009` — but it is stated
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
| every kind | `resource-framework` — the framework contract each kind inherits (schema validation, lifecycle audit, per-table retention) is a *requirement* there, not a rule in the constitution, which holds no routes, tables, entities or scenarios. An ADR still carries the *why* |
| two kinds | the spec that owns the code; the other cites it |
| the specs' own delivery rules | this file |
| a family that varies by type | the parent spec, plus one child per type |

## End-to-End Deliverable Rule

Every feature, on completion, must deliver a usable end-to-end product: backend persistence + the surfaces that expose it (CLI, MCP / `coffer-mcp-shim`, REST) — all wired so the user can really operate the feature.

A spec is "shipped" only when the end-to-end deliverable works AND every acceptance scenario has at least one covering test.

**Every management operation is reachable from both REST and the CLI.** Whatever
a user can do to a spec's state through the management API they can also do
through `coffer`, sharing the same daemon and the same error model — and the
reverse. This is policy over every spec rather than a promise of any one of
them, which is why the rule is stated here: written into a single spec's prose
it would read as that spec's private promise, and the next spec would quietly
ship a REST-only half. A spec that cannot honour it records the gap in its
`## Assumptions` instead of leaving the omission to be discovered.

The **test** for it lives in
[`specs/resource-framework/spec.md`](../specs/resource-framework/spec.md) as
`resource-framework FR-009`, with the two acceptance scenarios "command line
covers every visual operation" and "command line surfaces same errors". That is
not a second statement of the rule — the assertion runs over the whole command
tree across every spec, so it has no narrower home, and `resource-framework` is
the only spec whose scope is already cross-kind. Stated once here, tested once
there: change the policy and you change this paragraph *and* that requirement,
never one of them.

## Markdown Style for spec.md

- `spec.md` is for the user-visible contract; ≤ 300 lines preferred.
- Don't restate architecture in `spec.md`; reference `.specify/memory/constitution.md`.
- Use plain English. Avoid jargon.
- No time annotations (`Day N`, `Last updated`, etc.) in spec / plan / research / data-model / quickstart.
