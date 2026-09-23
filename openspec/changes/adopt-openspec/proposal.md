## Why

Coffer's specs were laid out for Speckit, but the project has not worked the
Speckit way for months. Speckit writes one folder per feature and keeps it as a
record; Coffer keeps fifteen long-lived capability specs that are edited in
place as the system changes. That is OpenSpec's model — a `specs/` tree that
describes the system as it is now, and a `changes/` tree for work in flight —
except Coffer never had the `changes/` half.

Without it, the work of a change has nowhere to live. `plan.md` sits beside the
spec as if it were permanent and drifts from the code. `tasks.md` is written
into a long-lived folder and then deleted on ship, so no spec has one and there
is no record of how any behaviour was broken down or why. Requirements are
numbered `FR-001…` and cited by number from 611 files; renumbering them has
already gone wrong twice. Acceptance scenarios sit in one block at the end of
each spec with no link to the requirement they verify, so a requirement with
no scenario — and therefore no test — goes unnoticed.

OpenSpec fixes each of these by construction: every change carries its own
proposal, design and tasks, and is archived rather than deleted; requirements
are named, not numbered; every requirement owns at least one scenario, and the
official CLI validates all of it.

## What Changes

- Adopt OpenSpec as the project's spec methodology, driven by the official
  `@fission-ai/openspec` CLI (pinned) and its `/opsx:*` commands and skills,
  committed to the repository.
- Move the spec tree to `openspec/specs/<capability>/`. The nineteen specs
  (fifteen top-level, four children) keep their names and therefore their ids.
- Rewrite every `spec.md` in OpenSpec format: `## Purpose`, then
  `## Requirements` made of `### Requirement: <title>` blocks, each owning at
  least one `#### Scenario:`. Requirement numbers are dropped; titles are the
  identity. Existing scenario names are kept verbatim.
- Give every requirement that has no scenario today a new scenario, and every
  new scenario a real test carrying an acceptance marker.
- Keep `contracts/api.openapi.yaml` and `data-model.md` beside their spec.
  Fold `plan.md`, `research.md`, `quickstart.md`, user stories and edge cases
  into the architecture doc, ADRs, the docs site, or the requirements they
  describe, and delete them.
- Turn `.specify/memory/constitution.md` into `docs/principles.md`, and
  distil its writing rules into `openspec/config.yaml`; move
  `architecture.md` to `docs/architecture.md`; retire `roadmap.md` in favour
  of `openspec list`.
- Replace every `FR-<n>` citation in code, tests, ADRs and docs with the
  requirement's title or a link to its spec.
- Gate it: `openspec validate --all --strict` joins `make verify` and CI;
  `audit_acceptance.py` reads scenarios from the OpenSpec layout;
  `check_doc_numbering.py` rejects any `FR-<n>` token.
- Remove every Speckit trace: `.specify/`, `.agents/sdd.md`, the
  `coffer-spec` skill, and every mention across the repository's docs.

## Impact

- Affected docs: `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `README.md`,
  `.agents/*`, `docs/decisions/*`, `docs/research/*`, `docs-site/*`.
- Affected code: every file citing a requirement number (backend, frontend,
  desktop, e2e), the contract tests and frontend codegen that read
  `specs/**/contracts/`, and the three doc gates under `scripts/`.
- Affected tests: one new acceptance-marked test for every scenario the
  rewrite adds.
- No runtime behaviour changes.
