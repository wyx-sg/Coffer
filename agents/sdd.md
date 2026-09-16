# SDD — Spec-Driven Development

Coffer's spec layout and conventions come from [Speckit](https://github.com/github/spec-kit). Every PR that changes externally visible behavior updates the relevant `spec.md` first, then the code.

**The `/speckit-*` slash commands are not part of this repository.** `.claude/commands/` is gitignored, so cloning gets you none of them; they exist only if you installed Speckit locally yourself. Nothing in this doc requires them — every file below is written by hand. What the repo does track is `.specify/templates/` (the section templates) and `.claude/skills/coffer-spec/` (the checked-in scaffolder, see [`harness.md`](./harness.md)).

## Folder Layout

A spec lives at `specs/<short-name>/`, named for the feature rather than numbered. There is one kind of spec — no foundation / capability / quality split. All nine specs are top-level today; the tooling also accepts a spec that is a child of another (`specs/<parent>/<child>/`), and a spec's id is its path under `specs/`, so a child's is `<parent>/<child>` (`scripts/audit_acceptance.py` reads `spec.md` at any depth).

Cross-cutting mechanisms get shared modules rather than their own specs; the "extract only after the second feature needs them" rule is the invariant in [`.specify/memory/constitution.md`](../.specify/memory/constitution.md). The ones that actually exist today:

| Mechanism | Where it lives |
|---|---|
| Audit log | `domain/audit.py`, `application/audit_service.py` |
| Credentials | `application/credentials/`, `infrastructure/credentials/` |
| Storage | `infrastructure/persistence/` (SQLAlchemy + Alembic; the only data-access path) |
| Resource framework (kinds, scope, delete) | `domain/resource.py`, `domain/scope.py`, `application/resource_service.py` + `resource_scope_ops.py` / `resource_delete_ops.py` |
| Retention | `domain/retention.py`, `application/retention_registry.py` / `retention_service.py` / `retention_worker.py` |
| Structured logging | `infrastructure/logging/` |
| Kind-agnostic adapters two kinds share | `infrastructure/net/`, `infrastructure/agent_files/`, `domain/connection.py` |

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
`tasks.md` described below, nothing else appears under a spec. The nine
specs are `agent-registry`, `channels`, `knowledge`, `mcp-gateway`, `memory`,
`provider-switching`, `skill-manager`, `ui-shell`, `vault-sync`. Seven carry the
full set (`contracts/ data-model.md plan.md quickstart.md spec.md`, five of
those plus `research.md`); `ui-shell` has `plan.md quickstart.md spec.md` because
it adds no endpoints of its own; `memory` has everything but `plan.md`.

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

An id is therefore only unique *within* the spec that carries it. Cite one from
outside as `<spec-id> FR-00N` (e.g. `mcp-gateway FR-026`), never as a bare
`FR-026`.

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
- Cross-cutting docs the change touches: the relevant `docs/decisions/` ADR, `.specify/memory/architecture.md`, and any affected `agents/*` convention such as `agents/visual-language.md`.

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

## End-to-End Deliverable Rule

Every feature, on completion, must deliver a usable end-to-end product: backend persistence + the surfaces that expose it (CLI, MCP / `coffer-mcp-shim`, REST) — all wired so the user can really operate the feature.

A spec is "shipped" only when the end-to-end deliverable works AND every acceptance scenario has at least one covering test.

## Markdown Style for spec.md

- `spec.md` is for the user-visible contract; ≤ 300 lines preferred.
- Don't restate architecture in `spec.md`; reference `.specify/memory/constitution.md`.
- Use plain English. Avoid jargon.
- No time annotations (`Day N`, `Last updated`, etc.) in spec / plan / research / data-model / quickstart.
