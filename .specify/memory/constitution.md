# Coffer Constitution

> Coffer is a local-first AI agent vault: a developer's accumulated AI assets
> live on-device, and any AI agent (Claude Code, Codex, future ones) reads
> and contributes through one safe interface.
>
> This constitution holds **scaffolding-level** invariants only: tech stack,
> workflow, licensing posture, and architectural style. Product behavior —
> the resource model, safety/approval rules, the surface roster, what gets
> persisted where — is defined per feature in `specs/`.

## Core Principles

### I. Local-First (NON-NEGOTIABLE)

All user data lives on the user's machine. Cloud services are LLM and tool
providers only — they never become the system of record for any vault state.
The HTTP API binds to `127.0.0.1`. Replicating user-state to a vendor-
controlled cloud requires a constitutional amendment.

### II. Spec-as-Truth (Spec-Driven Development)

Specifications under `specs/` are the canonical product contract. Every PR
that changes externally visible behavior updates the relevant spec **first**,
then the code. A spec is not "documentation" — it is the implementation's
contract; if the code disagrees with the spec, the code is wrong.

### III. Open-Source-Readiness from Day One

License (MIT), governance, contribution flow, and Conventional Commits are
present in the repository from v0.0.1, not retrofitted later. A change that
would shorten this list — adding a closed-source dependency without an
exception, omitting attribution for AI-authored content — violates this
principle and requires a constitutional amendment with explicit migration
plan.

## Technology & Architectural Constraints

- **Languages.** Python 3.12+ for backend, CLI, and any MCP shim;
  TypeScript 5.x for frontend. No other primary languages without a
  constitutional amendment.
- **Architecture.** Layered: `surfaces → application → domain → infrastructure`.
  `domain/` may not import `infrastructure/`, `surfaces/`, or external SDKs.
  `application/` may not import `surfaces/`. Cross-cutting modules are
  extracted only after the second feature needs them. (Exception: the
  Resource framework — see [ADR-001](../../docs/decisions/ADR-001-resource-framework-upfront.md).)
- **Persistence.** SQLite is the system of record for control-plane state.
  Bulk user content (when introduced per spec) is stored as files on the
  local file system; indexed on demand.
- **Credentials.** Only the credential module may access the OS keychain via
  `keyring`. All other code uses credential refs. No secret material reaches
  the database in plaintext.
- **Network defaults.** Loopback-only. Outbound HTTP, when introduced, goes
  through a SSRF-guarded client. Public-reachable surfaces, when introduced,
  run as a separate process limited to signed callback paths.

## Quality Gates

A change is "done" only when **all** of the following hold:

- The relevant `spec.md` is updated to match the code.
- Acceptance scenarios in `spec.md` cover the new behavior and pass.
- `make verify` passes locally and in CI.
- File-size limits hold (see `agents/stack.md`).
- Architectural boundaries are not violated.

## Governance

This constitution **supersedes** any conflicting guidance in `AGENTS.md`,
`CONTRIBUTING.md`, or per-spec documents. When they disagree, the constitution
wins.

**Amendments.** A change to any Core Principle, to the Technology &
Architectural Constraints, or to a Quality Gate requires:

1. A proposal PR describing motivation, current behavior, proposed behavior,
   downstream impact, alternatives.
2. Explicit decision recorded in the PR description.
3. The amending PR updates this file and bumps the **Version** field below.

**PR review.** Every PR description must, where applicable, name the
constitutional principles or constraints it affects, and explain why the
change respects (or formally amends) them.

**Version**: 0.1.0
