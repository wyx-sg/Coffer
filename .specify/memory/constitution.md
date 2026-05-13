# Coffer Constitution

> Coffer is a local-first AI agent vault. A developer's accumulated AI assets —
> MCP servers, CLIs, Skills, and Memorys — live on-device, and any AI agent
> (Claude Code, Codex, future ones) reads and contributes through one safe
> interface. The agents themselves, the chats they hold, and the channels
> they answer on are also vault state. Agents come and go; the vault persists.
> Memory is not locked to a vendor.
>
> This constitution is the **lasting** authority for what Coffer is and how it
> must behave. Principles, architectural invariants, and quality bars live here.

## Core Principles

### I. Local-First (NON-NEGOTIABLE)

All user data lives on the user's machine. Cloud services are LLM and tool
providers only — they never become the system of record for any vault resource
(MCP servers, CLIs, Skills, Memorys) or for user-facing state (agents, chats,
channels). The full HTTP API binds to `127.0.0.1`. Public ingress (channel
webhooks) is a separate process limited to signed callback paths. Any change
that would replicate user-state to a vendor-controlled cloud violates this
principle and requires a constitutional amendment.

### II. Spec-as-Truth (Spec-Driven Development)

Specifications under `specs/` are the canonical product contract. Every PR
that changes externally visible behavior updates the relevant spec **first**,
then the code. A spec is not "documentation" — it is the implementation's
contract; if the code disagrees with the spec, the code is wrong.

### III. Safety-by-Default (Approval Required for Mutations)

Every CLI / MCP tool / Skill invocation, every Memory write, every external
mutation carries a risk class: `read` / `write` / `destructive`. `write` and
`destructive` actions require explicit user confirmation through the
application-layer approval coordinator. Approval state is durable, idempotent,
and auditable. No surface (HTTP, CLI, MCP, channel) may bypass this for any
reason.

### IV. Surface Parity

The web workbench, CLI, MCP bridge, and channel webhook all call the same
application contracts. No surface owns hidden business logic. A behavior
added to one surface is reachable from all surfaces that expose the relevant
capability.

### V. Open-Source-Readiness from Day One

License (MIT), governance, contribution flow, and Conventional Commits are
present in the repository from v0.0.1, not retrofitted later. A change that
would shorten this list — adding a closed-source dependency without an
exception, omitting attribution for AI-authored content — violates this
principle and requires a constitutional amendment with explicit migration
plan.

## Technology & Architectural Constraints

- **Languages.** Python 3.12+ for backend, CLI, and the MCP stdio shim;
  TypeScript 5.x for frontend. No other primary languages without a
  constitutional amendment.
- **Architecture.** Layered: `surfaces → application → domain → infrastructure`.
  `domain/` may not import `infrastructure/`, `surfaces/`, or external SDKs.
  `application/` may not import `surfaces/`. Cross-cutting mechanisms (audit,
  credentials, events, jobs, storage, session) live as shared modules under
  `application/` or `infrastructure/`. Don't pre-extract — wait for the second
  use case.
- **Persistence.** SQLite is the system of record for control state (agents,
  chats, channels, audit log, job queue, sessions). User content (Memorys) is
  stored as files on the local file system; indexed on demand for retrieval.
- **Credentials.** Only the credential module may access the OS keychain via
  `keyring`. All other code uses credential refs. No secret material reaches
  the database in plaintext.
- **Network defaults.** Loopback-only. Outbound HTTP goes through a
  SSRF-guarded client. Public-reachable surfaces require signed callbacks.

## Quality Gates

A change is "done" only when **all** of the following hold:

- The relevant `spec.md` is updated to match the code.
- Acceptance scenarios in `spec.md` cover the new behavior and pass.
- `make verify` passes locally and in CI (lint + test).
- File-size limits hold (see `AGENTS.md` §3).
- Architectural boundaries are not violated.
- No mutation of an external system goes out without an approval-coordinator
  hand-off when the action is `write` or `destructive`.

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
