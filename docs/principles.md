# Coffer Principles

> Coffer is a local-first AI agent vault: a developer's accumulated AI assets
> live on-device, and any AI agent (Claude Code, Codex, future ones) reads
> and contributes through one safe interface.
>
> This document holds **scaffolding-level** invariants only: tech stack,
> workflow, licensing posture, and architectural style. Product behavior —
> the resource model, the gate on who may drive an agent, the surface roster,
> what gets persisted where — is defined per capability in `openspec/specs/`.

## Core Principles

### I. Local-First (NON-NEGOTIABLE)

All user data lives on the user's machines — one vault, every machine holding
the full state. Cloud services are LLM and tool providers only — they never
become the system of record for any vault state. The HTTP API binds to
`127.0.0.1`. Replicating user-state to a vendor-controlled cloud requires an
amendment.

**Exception — user-owned sync remote.** Coffer may converge the vault with a
git remote the user owns, so that the user's own machines hold one vault rather
than several. The exception is bounded by three conditions, all of which must
hold: the remote is a **rendezvous, never a system of record** — each machine's
local vault stays authoritative and complete, so the remote can be deleted and
rebuilt from any single machine without losing anything; secrets travel **as
ciphertext only** and the master key never leaves the machine except through the
out-of-band key transfer; and the feature is **off by default**, enabled by the
user against a repository they own. A hosted endpoint Coffer itself operates
remains outside this exception.

Convergence is **bidirectional**: Coffer applies what the remote brought in as
well as pushing what this machine changed. It is authorised only under the
safety rules the sync spec carries — git's own three-way merge is the arbiter,
what gets applied is a **diff against the last state this vault provably held**
rather than a wholesale overwrite, and a round that would delete more than its
configured share stops and asks. A mechanism that writes the vault outside those
rules is not covered by this exception.

### II. Spec-as-Truth (OpenSpec)

Specifications under `openspec/specs/` are the canonical product contract. A
change to externally visible behavior starts as an OpenSpec change under
`openspec/changes/<id>/` whose spec deltas say what will be true afterwards,
lands with the code that makes it true, and is archived into `openspec/specs/`.
A spec is not "documentation" — it is the implementation's contract; if the
code disagrees with the spec, the code is wrong.

### III. Open-Source-Readiness from Day One

License (MIT), governance, contribution flow, and Conventional Commits are
present in the repository from v0.0.1, not retrofitted later. A change that
would shorten this list — adding a closed-source dependency without an
exception, omitting attribution for AI-authored content — violates this
principle and requires an amendment with an explicit migration plan.

## Technology & Architectural Constraints

- **Languages.** Python 3.12+ for backend, CLI, and any MCP shim;
  TypeScript 5.x for frontend. No other primary languages without an
  amendment.
- **Architecture.** Layered: `surfaces → application → domain`;
  `infrastructure` adapts to ports defined in `application` and is wired only
  at the composition root.
  `domain/` may not import `infrastructure/`, `surfaces/`, or external SDKs.
  `application/` may not import `surfaces/`. Cross-cutting modules are
  extracted only after the second feature needs them. (Exception: the
  Resource framework — see [Resource Framework Upfront](decisions/resource-framework-upfront.md).)
- **Persistence.** SQLite is the system of record for control-plane state.
  Bulk user content — knowledge collections, memory partitions — is stored as
  files on the local file system, and those files are the only copy: nothing
  indexes, chunks or embeds them.
- **Credentials.** Secrets live **only** as Fernet ciphertext in the
  `credentials` table; plaintext exists in memory solely between decrypt and
  the spawn/header-injection that consumes it. The Fernet master key is
  managed exclusively by `coffer.infrastructure.credentials` — a `0600` file
  beside the DB by default, the OS keychain via `keyring` when opted in.
  `keyring` import stays confined to that module. All other code uses
  credential refs. No secret plaintext reaches the database, logs, audit, or
  any structured event. Credential material leaves the machine only as Fernet
  ciphertext and only when the user asks for it explicitly; the master key is
  never written into anything the vault publishes, and reaches another machine
  only through the explicit out-of-band transfer (`/sync/key/export` and
  `/sync/key/import`, which move key material and nothing else).
- **Network defaults.** Loopback-only. Outbound HTTP goes through a
  SSRF-guarded client (`coffer.infrastructure.net.ssrf_guard`, which rejects
  loopback, private and link-local destinations). The one public-reachable
  surface runs as a separate process limited to signed callback paths
  (`coffer.surfaces.callback`, which verifies the platform signature and can
  reach nothing but the daemon over loopback).

## Quality Gates

A change is "done" only when **all** of the following hold:

- The relevant spec is updated to match the code, through an archived OpenSpec change.
- Every requirement owns a scenario, and every scenario is covered by a passing test.
- `make verify` passes locally and in CI.
- File-size limits hold (see `.agents/stack.md`).
- Architectural boundaries are not violated.

## Governance

This document **supersedes** any conflicting guidance in `AGENTS.md`,
`CONTRIBUTING.md`, or per-spec documents. When they disagree, this document wins.

**Amendments.** A change to any Core Principle, to the Technology &
Architectural Constraints, or to a Quality Gate requires:

1. A proposal PR describing motivation, current behavior, proposed behavior,
   downstream impact, alternatives.
2. Explicit decision recorded in the PR description.
3. The amending PR updates this file and bumps the
