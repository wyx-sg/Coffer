# Architecture Decision Records (ADR)

Coffer records every major technical or architectural decision as an
ADR. ADRs capture **why** — code shows _what_, this directory shows
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

- Filename: `short-kebab-case-title.md` — the title, in kebab case, with no
  number. Numbers were dropped because deleting an ADR left a hole in the
  sequence, and compacting those holes would have made every surviving
  reference to a retired number point silently at an unrelated live decision —
  which had already happened once. A name cannot do that, and chronology is
  carried by each ADR's own `Date`.
- This directory records the **live** design, not a chronological archive. A
  reader must be able to learn today's answer by reading the ADRs present, never
  by replaying a chain of supersessions. So:
  - When a decision changes, **rewrite the ADR that owns it**.
  - When the thing an ADR decided is **removed outright**, delete the ADR.
  - Keep an ADR marked `Superseded by <title>` only when the superseded design
    still explains a constraint the live one inherits.
  Git history is the archive: `git log --follow docs/decisions/` recovers any
  decision this directory no longer states.
- One decision per file.
- Keep each ADR short — usually under 200 lines. If you need more, you're
  describing implementation, not the decision.

## Status values

| Status                  | Meaning                                             |
| ----------------------- | --------------------------------------------------- |
| `Proposed`              | Drafted, not yet adopted.                           |
| `Accepted`              | In effect.                                          |
| `Superseded by <title>` | No longer the live answer; link to its replacement. |
| `Deprecated`            | Withdrawn without replacement (rare).               |

## Template (Michael Nygard format)

```markdown
# <short title in title case>

**Status**: Proposed | Accepted | Superseded by [<title>](<file>.md)
**Date**: YYYY-MM-DD
**Deciders**: <names / roles>
**Related**: [<ADR title>](<file>.md), spec/…, issue/PR/…

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

| ADR | Title | Status |
| --- | --- | --- |
| [`resource-framework-upfront`](resource-framework-upfront.md) | Resource Framework Designed Upfront | Accepted |
| [`code-layout-layer-first`](code-layout-layer-first.md) | Code Layout — Layer-First with Kind Subdirectories | Accepted |
| [`resource-identifier-format`](resource-identifier-format.md) | Resource Identifier Format — `<kind>:<name>`, Not URN | Accepted |
| [`capability-state-model`](capability-state-model.md) | MCP Capability State — Preferences in DB, List Live-Queried From Upstream | Accepted |
| [`session-subprocess-model`](session-subprocess-model.md) | One Upstream Subprocess Set Per Downstream Client Session | Accepted |
| [`daemon-detect-or-spawn`](daemon-detect-or-spawn.md) | Daemon Detect-or-Spawn Pattern | Accepted |
| [`daemon-serves-the-token-in-the-page`](daemon-serves-the-token-in-the-page.md) | The Daemon Serves Its Token in the Page, Guarded by the Host Header | Accepted |
| [`everything-is-a-resource-kind`](everything-is-a-resource-kind.md) | Information Architecture — Everything Is a Resource Kind | Amended (2026-05-30, 2026-06-11) |
| [`distribution-pyinstaller`](distribution-pyinstaller.md) | Distribution — PyInstaller-Bundled Daemon, Shim, and CLI | Accepted |
| [`cross-platform-skill-delivery`](cross-platform-skill-delivery.md) | Cross-Platform Skill Delivery — Symlink / Junction / Copy-Fallback | Accepted |
| [`files-as-truth-sqlite-retrieval`](files-as-truth-sqlite-retrieval.md) | Retrieval Stack — Markdown Files as Truth, SQLite FTS5 + sqlite-vec, Configurable Embeddings | Superseded by [Knowledge Is Plain Files](knowledge-is-plain-files.md) |
| [`knowledge-is-plain-files`](knowledge-is-plain-files.md) | The knowledge layer is a directory of files, not an index | Accepted |
| [`agent-native-shared-memory`](agent-native-shared-memory.md) | One Shared Knowledge Store Across Agents | Accepted — projection half superseded by [Memory via MCP](memory-via-mcp-not-native-projection.md) |
| [`channel-adapter-framework`](channel-adapter-framework.md) | Channel Adapter Framework | Accepted |
| [`envelope-encrypted-credential-store`](envelope-encrypted-credential-store.md) | Envelope-Encrypted Credential Store | Accepted |
| [`vault-export-import`](vault-export-import.md) | Vault Export and Import | Accepted |
| [`industrial-grade-harness-in-layers`](industrial-grade-harness-in-layers.md) | Industrial-Grade Harness, Built in Layers | Proposed |
| [`tool-retrieval-for-overload`](tool-retrieval-for-overload.md) | Tool Retrieval for Aggregation Overload | Accepted — amended by [Built-in Agent Is Internal](builtin-agent-is-internal-capability.md) and [Budget-Driven Tool Tiering](budget-driven-tool-tiering.md) |
| [`close-the-eval-flywheel`](close-the-eval-flywheel.md) | Close the Eval Flywheel (Loop Engineering) | Accepted |
| [`channel-entrypoint-differentiation`](channel-entrypoint-differentiation.md) | Channel Entrypoint Differentiation Layer | Accepted |
| [`builtin-agent-is-internal-capability`](builtin-agent-is-internal-capability.md) | The Built-in Agent Is an Internal Capability, Not a Chat Persona | Accepted |
| [`remove-tool-approval`](remove-tool-approval.md) | Remove the Tool-Approval System; Owner-Pairing Is the Gate | Accepted |
| [`memory-via-mcp-not-native-projection`](memory-via-mcp-not-native-projection.md) | Memory via MCP, not native projection | Accepted |
| [`skill-content-trust-layer`](skill-content-trust-layer.md) | Skill Content Trust Layer (Heuristic Scan, Warn-Don't-Block) | Reverted (2026-06-20) |
| [`consume-official-mcp-registry`](consume-official-mcp-registry.md) | Consume the official MCP Registry for server discovery | Reverted (2026-06-20) |
| [`provider-switching`](provider-switching.md) | Provider Switching | Proposed |
| [`daemon-proxies-os-file-actions`](daemon-proxies-os-file-actions.md) | Local Daemon Proxies OS File Actions | Accepted |
| [`retrieval-mode-is-internal`](retrieval-mode-is-internal.md) | Retrieval mode is an internal engine detail; external surfaces expose query→answer | Superseded by [Knowledge Is Plain Files](knowledge-is-plain-files.md) |
| [`channel-media`](channel-media.md) | Channel media — reference in the DB, materialise per agent at send | Accepted — the v1 "defer a persisted attachment block" decision is superseded by [Persisted Attachment Reference](persisted-attachment-reference.md) |
| [`persisted-attachment-reference`](persisted-attachment-reference.md) | Persist channel attachments as a reference block, re-materialise from history | Accepted |
| [`per-agent-resource-scope`](per-agent-resource-scope.md) | Per-Agent Resource Scope | Accepted |
| [`budget-driven-tool-tiering`](budget-driven-tool-tiering.md) | Budget-Driven Tool Tiering at the Gateway | Accepted |
| [`seatalk-websocket-inbound`](seatalk-websocket-inbound.md) | SeaTalk Inbound Over WebSocket, With an Operator-Supplied SDK | Accepted |
