## Context

Today's layout, as of `9fa17740`:

- `specs/<name>/` — 15 top-level specs and 4 children
  (`agent-registry/{claude-code,codex}`, `channels/{telegram,seatalk}`).
  Files: `spec.md` ×19, `quickstart.md` ×15, `plan.md` ×14,
  `data-model.md` ×13, `contracts/api.openapi.yaml` ×13, `research.md` ×6.
- `spec.md` is Speckit-shaped: user stories with priorities, edge cases, a
  `### Functional Requirements` list of `- **FR-NNN**: System MUST …`
  (639 in total), and a trailing `## Acceptance Scenarios` block of
  `### Scenario: <name>` in Given/When/Then (515 in total). Scenarios are not
  linked to requirements.
- `.specify/templates/` (four Speckit templates) and `.specify/memory/`
  (`constitution.md`, `architecture.md`, `roadmap.md`).
- `.agents/sdd.md` documents the layout; `.claude/skills/coffer-spec/`
  scaffolds new specs.
- `FR-NNN` is cited 3220 times across 611 files: `backend/coffer` 259 files,
  `backend/tests` 165, `frontend/src` 83, `docs/decisions` 18, `desktop/src`
  10, plus specs, `.agents`, `e2e` and `docs/research`.
- Gates: `scripts/audit_acceptance.py` (every scenario has a marker, every
  marker a scenario), `scripts/check_doc_numbering.py` (no numbered
  ADRs/specs; unique FR ids), `scripts/check_architecture_doc.py` (reads
  `.specify/memory/architecture.md`).
- Hard-coded `specs/` paths: 9 contract tests under `backend/tests/contract/`,
  `frontend/scripts/codegen{,-check}.mjs`, generated clients and schema
  modules that name their source contract, `frontend/src/test/acceptance.ts`.

Verified against `@fission-ai/openspec` 1.13.1 in a scratch repository:

- `validate --all --strict` accepts extra `##` sections in a spec, extra files
  and directories beside `spec.md`, `**GIVEN**` steps, and nested capability
  paths (`channels/telegram` validates as its own spec).
- `archive` applies ADDED/MODIFIED deltas by requirement title, leaves extra
  sections and sibling files untouched, and moves the change to
  `changes/archive/YYYY-MM-DD-<id>/`.
- `init --tools claude` writes `.claude/commands/opsx/*.md` (six commands) and
  `.claude/skills/openspec-*/SKILL.md` (six skills).
- The only strict-mode complaint on a Coffer-shaped spec was a `## Purpose`
  under 50 characters.

## Goals / Non-Goals

**Goals**

- The official CLI validates and archives the whole tree with no Coffer
  wrapper.
- Every requirement owns at least one scenario, and every scenario is covered
  by a test that runs.
- New work goes through `openspec/changes/<id>/` and is archived, not deleted.
- No trace of Speckit or of requirement numbers remains.

**Non-Goals**

- Changing any runtime behaviour. Where rewriting a requirement reveals that
  code and spec disagree, the discrepancy is recorded in this change's
  `tasks.md` as a follow-up change, not fixed here.

## Decisions

### Directory layout

```
openspec/
├── config.yaml
├── specs/<capability>/
│   ├── spec.md
│   ├── data-model.md               # kept where it exists today
│   └── contracts/api.openapi.yaml  # kept where it exists today
└── changes/
    ├── <change-id>/{.openspec.yaml,proposal.md,design.md,tasks.md,specs/}
    └── archive/YYYY-MM-DD-<change-id>/
```

Capability names are unchanged, so every acceptance marker's `spec=` value
stays valid. Only the root moves from `specs/` to `openspec/specs/`.

### `spec.md` shape

```markdown
# <Capability title>

## Purpose
<What the capability is for and who relies on it — at least one full sentence.>

## Requirements

### Requirement: <Imperative title, unique within the spec>
The system SHALL|MUST <behaviour>. <Detail formerly in the FR body.>

#### Scenario: <name — existing names kept verbatim>
- **GIVEN** <state>
- **WHEN** <action>
- **THEN** <outcome>
- **AND** <further outcome>
```

Mapping rules for the rewrite:

- Each `FR-NNN` becomes one `### Requirement:`. Its title is a short
  imperative phrase naming the behaviour. The FR's bold group headings
  (`**Resource model**`) are dropped; OpenSpec has no grouping level and the
  titles carry the meaning.
- Each existing scenario moves under the requirement it primarily verifies,
  changing `###` to `####` and keeping its name byte-for-byte. A scenario
  that verifies several requirements goes under one; the others get their
  own scenario if they have none.
- A requirement left without a scenario gets a new one, written from the
  requirement's own text.
- User stories and edge cases: facts not already stated in a requirement move
  into `## Purpose` or into the requirement they qualify; the rest is
  dropped.
- Cross-spec references change from `<spec> FR-NNN` to a link to the spec
  plus the requirement title in quotes:
  ``[resource-framework](../resource-framework/spec.md) "Rename carries the label"``.

### The other per-spec files

| File | Outcome |
|---|---|
| `contracts/api.openapi.yaml` | Kept; paths updated in contract tests and codegen. |
| `data-model.md` | Kept. |
| `plan.md`, `research.md` | Conclusions still true of the code go to `docs/architecture.md` or an ADR; the files are deleted. From now on a change's plan lives in its `design.md`. |
| `quickstart.md` | Merged into the matching `docs-site/guide/` page, then deleted. |

### Project-level documents

| Today | Outcome |
|---|---|
| `.specify/memory/constitution.md` | Becomes `docs/principles.md`: the same principles, constraints, quality gates and amendment rule, with Principle II restated for OpenSpec. The version number and amendment log go; the file's git history is its record. The rules an agent applies while writing specs, designs and tasks are also distilled into `openspec/config.yaml` (`context:` and `rules:`), which the CLI injects into every planning request. |
| `.specify/memory/architecture.md` | Moved to `docs/architecture.md`; `check_architecture_doc.py` follows it. |
| `.specify/memory/roadmap.md` | Deleted. Work in flight is `openspec list`; shipped work is `openspec/changes/archive/`. |
| `.specify/templates/*` | Deleted. OpenSpec's schema supplies the templates. |
| `.agents/sdd.md` | Replaced by `.agents/openspec.md`: Coffer's conventions on top of OpenSpec — one capability per behaviour, parent/child ownership, acceptance markers, when a change needs `design.md`. |
| `.claude/skills/coffer-spec/` | Deleted; `/opsx:propose` replaces it. |

### Tooling

- The CLI is pinned in a root `package.json` (devDependency
  `@fission-ai/openspec`, exact version) with a committed lockfile. `make
  openspec-validate` runs `npx --no-install openspec validate --all --strict`,
  and `make verify` runs it.
- `openspec init --tools claude` output is committed. `.gitignore` keeps
  ignoring `.claude/commands/` but un-ignores `.claude/commands/opsx/`.
- CI gains a step running the same validate command.

### Gates

- `audit_acceptance.py` reads `openspec/specs/**/spec.md` and collects every
  `#### Scenario:` inside `## Requirements`. Spec id is the path under
  `openspec/specs/`. Marker syntax is unchanged. It also fails a spec whose
  scenario names are not unique, since the marker keys on the name.
- Requirement ownership of a scenario is now structural, so "every
  requirement has a scenario" is enforced by `openspec validate --strict`,
  and "every scenario has a test" by `audit_acceptance.py`. Together they
  close the gap where an unscenario'd requirement had no test.
- `check_doc_numbering.py` drops the unique-FR-id rule and adds: no `FR-<n>`
  token in any tracked file.
- A new check fails if `.specify/`, `specs/` at the root, or the words
  `speckit`/`spec-kit` reappear in a tracked file.

### Removing requirement numbers from code

Code and test comments that cite `FR-NNN` are rewritten to cite the
requirement title when the comment's reason depends on it, and lose the
citation when the number was decoration. Test names and docstrings follow the
same rule. The FR→title map is produced during the spec rewrite and kept in
the session scratchpad only; it is not committed.

## Delivery

Three PRs, merged in order, each green on its own:

1. **Tooling and scaffolding** — `openspec/config.yaml`, pinned CLI,
   committed `/opsx` commands and skills, `.agents/openspec.md`, gate changes
   written to accept both layouts for the duration of the migration, the
   project-document moves, and removal of Speckit from docs.
2. **Spec rewrite + new tests** — move and rewrite all nineteen specs, delete
   the folded files, write a test for every added scenario. These land
   together because a scenario without a test fails `audit_acceptance`.
3. **Numbers out** — remove every `FR-<n>` citation, tighten the gates to the
   OpenSpec layout only, delete the transitional code in the gates.

Then this change is archived with `openspec archive adopt-openspec`.

The spec rewrite and the new tests are split by capability across parallel
subagents; each capability's files are disjoint from every other's, so no two
agents write the same file.

## Risks / Trade-offs

- **Scenario attachment is judgement.** Moving 515 scenarios under 639
  requirements is manual. Mitigation: a reviewer pass per capability that
  checks every old scenario appears exactly once and every requirement has
  one.
- **New tests may expose real defects.** A new scenario can fail against
  today's code. Such a test is not weakened to pass; the defect is listed in
  `tasks.md` and fixed in its own change before phase 2 merges.
- **Titles can collide or drift.** OpenSpec keys deltas on titles, so a title
  edit is a RENAMED delta. Uniqueness within a spec is checked by the CLI.
- **`docs/decisions/fr-ids-reset-once.md`** records a rule about requirement
  numbers that no longer exist. Phase 3 deletes it with the numbers.
- **Losing the number as a stable handle.** A title is longer than `FR-013`
  and can be renamed. That is intended: a rename is an explicit, validated
  delta, whereas a renumber was silent.
- **`feature/workflow` branch** still carries the old layout and will need
  the same rewrite before it merges.
