---
name: coffer-spec
description: Start a new Coffer feature spec following Spec-Driven Development (SDD), in the correct folder with the required sections.
disable-model-invocation: true
allowed-tools: Bash, Read, Write
---

Help start a new Coffer spec the SDD way. Read `agents/sdd.md` first for the canonical folder layout and the end-to-end deliverable rule.

1. Confirm scope with the user, then agree a `<short-name>` for the feature. Specs are **named, never numbered** — `scripts/check_doc_numbering.py` fails `make lint` on any spec directory whose name starts with a digit, so an `NNN-` prefix is rejected outright.
2. Decide whether this is a new top-level spec or a child of an existing one, then create its `spec.md`:
   - top-level: `specs/<short-name>/spec.md`
   - a variant of an existing feature: `specs/<parent>/<short-name>/spec.md` (e.g. `specs/channels/telegram/spec.md` sits under `specs/channels/spec.md`). A child spec's id is the path under `specs/`, so this one is `channels/telegram` — that is the string its tests' acceptance markers must use.

   Give it these sections: `## Summary`, `## Acceptance Scenarios` (each independently testable), `## Assumptions`, `## Out of Scope`.
3. Remember the project rule (constitution): every completed spec must be an end-to-end deliverable — frontend + backend + real testability + real usage. Reflect that in the acceptance scenarios.
4. Do NOT start implementation here — this skill only scaffolds the contract. Implementation follows the workflow in `agents/workflow.md`.
