---
name: coffer-spec
description: Start a new Coffer feature spec following Spec-Driven Development (SDD), in the correct folder with the required sections.
disable-model-invocation: true
allowed-tools: Bash, Read, Write
---

Help start a new Coffer spec the SDD way. Read `agents/sdd.md` first for the canonical folder layout and the end-to-end deliverable rule.

1. Confirm scope with the user, then pick the next ordinal: inspect `specs/` for the highest `NNN-*` folder and use `NNN+1`.
2. Create `specs/<NNN>-<short-name>/spec.md` with these sections: `## Summary`, `## Acceptance Scenarios` (each independently testable), `## Assumptions`, `## Out of Scope`.
3. Remember the project rule (constitution): every completed spec must be an end-to-end deliverable — frontend + backend + real testability + real usage. Reflect that in the acceptance scenarios.
4. Do NOT start implementation here — this skill only scaffolds the contract. Implementation follows the workflow in `agents/workflow.md`.
