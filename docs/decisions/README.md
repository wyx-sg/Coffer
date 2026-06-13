# Architecture Decision Records (ADR)

Coffer records every major technical or architectural decision as a numbered,
immutable ADR. ADRs capture **why** — code shows _what_, this directory shows
_why we chose what we chose_.

## When to write an ADR

Write one for any decision that meets at least one of these:

- Hard to change later without breaking compatibility or rewriting large areas.
- Affects more than one module, or imposes structural constraints on future work.
- Has non-obvious trade-offs that future engineers (or future you) will question.
- Diverges from a default, a popular convention, or a project rule
  (constitution clause, prior ADR).

Do **not** write an ADR for:

- Library version bumps that don't change API surface.
- Routine bug fixes.
- Scope decisions that belong in a spec's `## Assumptions` or `## Out of Scope`.
- Naming or formatting preferences.

## File naming and lifecycle

- Filename: `ADR-NNN-short-kebab-case-title.md` — NNN is a zero-padded ordinal
  (`ADR-001-…`, `ADR-002-…`, …). Never renumber.
- ADRs are append-only. To change a decision, write a new ADR that **Supersedes**
  the old one; mark the old one `Status: Superseded by ADR-NNN`.
- One decision per file.
- Keep each ADR short — usually under 200 lines. If you need more, you're
  describing implementation, not the decision.

## Status values

| Status                  | Meaning                                             |
| ----------------------- | --------------------------------------------------- |
| `Proposed`              | Drafted, not yet adopted.                           |
| `Accepted`              | In effect.                                          |
| `Superseded by ADR-NNN` | No longer the live answer; link to its replacement. |
| `Deprecated`            | Withdrawn without replacement (rare).               |

## Template (Michael Nygard format)

```markdown
# ADR-NNN: <short title in title case>

**Status**: Proposed | Accepted | Superseded by ADR-NNN
**Date**: YYYY-MM-DD
**Deciders**: <names / roles>
**Related**: ADR-…, spec/…, issue/PR/…

## Context

<What forces are at play? What problem are we solving? Existing constraints,
related ADRs, relevant constitutional clauses.>

## Decision

<The choice, in one or two clear sentences. Then the supporting reasoning.>

## Consequences

<What becomes easier? What becomes harder? What new obligations or follow-ons?>

## Alternatives Considered

<Each rejected option with a one-paragraph reason for rejection. This is the
section that future readers most often want — don't skip it.>
```

## Index

| ADR                                                      | Title                                                                                       | Status                                                                                                        |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| [001](ADR-001-resource-framework-upfront.md)             | Resource framework designed upfront, not after the second feature                           | Accepted                                                                                                      |
| [002](ADR-002-code-layout-layer-first.md)                | Code layout: layer-first with kind subdirectories                                           | Accepted                                                                                                      |
| [003](ADR-003-resource-identifier-format.md)             | Resource identifier format: `<kind>:<name>`, not URN                                        | Accepted                                                                                                      |
| [004](ADR-004-capability-state-model.md)                 | MCP capability state: preferences in DB, list live-queried from upstream                    | Accepted                                                                                                      |
| [005](ADR-005-session-subprocess-model.md)               | One upstream subprocess set per downstream client session                                   | Accepted                                                                                                      |
| [006](ADR-006-daemon-detect-or-spawn.md)                 | Daemon detect-or-spawn pattern; daemon outlives any single client                           | Accepted                                                                                                      |
| [007](ADR-007-everything-is-a-resource-kind.md)          | Information architecture: every managed entity is a resource kind                           | Accepted                                                                                                      |
| [008](ADR-008-distribution-pyinstaller-tauri-sidecar.md) | Distribution: PyInstaller-bundled daemon + shim as Tauri sidecars                           | Accepted                                                                                                      |
| [009](ADR-009-cross-platform-skill-delivery.md)          | Cross-platform skill delivery: symlink / junction / copy-fallback                           | Accepted                                                                                                      |
| [010](ADR-010-llamaindex-rag-engine.md)                  | RAG engine: LlamaIndex behind an application port                                           | Superseded by [012](ADR-012-files-as-truth-sqlite-retrieval.md)                                               |
| [011](ADR-011-mem0-memory-engine.md)                     | Memory engine: mem0 behind an application port                                              | Superseded by [012](ADR-012-files-as-truth-sqlite-retrieval.md), [013](ADR-013-agent-native-shared-memory.md) |
| [012](ADR-012-files-as-truth-sqlite-retrieval.md)        | Retrieval stack: markdown files as truth, SQLite FTS5 + sqlite-vec, configurable embeddings | Accepted                                                                                                      |
| [013](ADR-013-agent-native-shared-memory.md)             | Agent-native shared memory projection                                                       | Accepted                                                                                                      |
| [014](ADR-014-channel-adapter-framework.md)              | Channel adapter framework: thin adapters over the chat platform seams                       | Accepted                                                                                                      |
| [015](ADR-015-envelope-encrypted-credential-store.md)    | Envelope-encrypted credential store (Fernet ciphertext in SQLite, file-default master key)  | Accepted                                                                                                      |
| [016](ADR-016-multi-machine-sync.md)                     | Multi-machine sync over a user-owned git repository                                          | Accepted                                                                                                      |
| [017](ADR-017-industrial-grade-harness-in-layers.md)     | Industrial-grade harness, built in layers                                                    | Proposed                                                                                                      |
