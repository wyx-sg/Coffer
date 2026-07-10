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

All user data lives on the user's machines — one vault, every machine
holding the full state. Cloud services are LLM and tool providers only —
they never become the system of record for any vault state. The HTTP API
binds to `127.0.0.1`. Replicating user-state to a vendor-controlled cloud
requires a constitutional amendment.

**Exception — user-controlled sync medium.** Synchronising vault state to a
**user-owned, user-controlled medium** (e.g. the user's own git repository) is
permitted, provided **all** of the following hold:

1. **No new system of record.** Every participating machine holds the full
   vault state; the medium serves only as transport and history. It never
   becomes the sole or authoritative system of record — wipe the medium and
   each machine still has its complete vault.
2. **Ciphertext-only secrets.** Any credential material that leaves a machine
   does so only as Fernet ciphertext. The encryption master key **never** leaves
   the machine through the sync medium; it is bootstrapped onto each machine
   out-of-band.
3. **User opt-in and ownership.** Sync is off by default and points at a remote
   the user supplies and controls. Coffer ships no hosted/vendor sync endpoint;
   doing so would still require a further amendment.

This exception does not weaken the prohibition on vendor-controlled clouds as a
system of record; it authorises only user-owned transport that satisfies the
three conditions above.

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
- **Credentials.** Secrets live **only** as Fernet ciphertext in the
  `credentials` table; plaintext exists in memory solely between decrypt and
  the spawn/header-injection that consumes it. The Fernet master key is
  managed exclusively by `coffer.infrastructure.credentials` — a `0600` file
  beside the DB by default, the OS keychain via `keyring` when opted in.
  `keyring` import stays confined to that module. All other code uses
  credential refs. No secret plaintext reaches the database, logs, audit, or
  any structured event.
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

**Version**: 0.3.1

> **0.3.0 amendment (spec 010-sync).** Added the *user-controlled sync medium*
> exception to Principle I, authorising multi-machine sync over a user-owned
> git repository under three conditions (no new system of record, ciphertext-
> only secrets, user opt-in/ownership). Motivation: enable a single user to
> keep one vault consistent across their own machines without ceding local-
> first guarantees. Current behaviour: multi-machine sync was an explicit
> non-goal. Proposed behaviour: permitted under the bounded exception above.
> Downstream impact: new spec 010-sync (sync engine, CLI/HTTP surfaces, daemon
> auto-sync worker); no change to credential-at-rest or loopback-binding rules.
> Alternatives considered: peer-to-peer (Syncthing-style) and user-owned object
> storage — rejected in favour of git for built-in history, diff, and merge.
> Decision recorded by the project owner.

> **0.3.1 amendment (editorial).** Reworded Principle I's opening line to
> match the multi-machine reality the 0.3.0 exception already authorised.
> Motivation: ADR-045 (machine × agent resource scope) extends multi-machine
> sync further into the framework, underscoring that "local" has matured from
> a single machine into the user's fleet — one vault, every machine holding
> the full state — and the principle's opening sentence had not caught up.
> Current wording: "All user data lives on the user's machine." Proposed
> wording: "All user data lives on the user's machines — one vault, every
> machine holding the full state." Downstream impact: none — editorial;
> Principle I's rule and the 0.3.0 exception's three conditions are
> unchanged. Decision recorded by the project owner.
