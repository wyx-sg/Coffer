# Design Principles

::: tip This page is normative
This page is the single source of Coffer's project principles. It holds **scaffolding-level** invariants only: tech stack, workflow, licensing posture, and architectural style. Product behavior — the resource model, the gate on who may drive an agent, the surface roster, what gets persisted where — is defined per capability in `openspec/specs/`. The clauses under [The three principles](#the-three-principles), [Technology & architectural constraints](#technology-architectural-constraints), [Quality gates](#quality-gates) and [Governance](#governance) are binding; the surrounding sections explain them.
:::

> Coffer is a local-first AI agent vault: a developer's accumulated AI assets
> live on-device, and any AI agent (Claude Code, Codex, future ones) reads
> and contributes through one safe interface.

Coffer exists to solve a specific, concrete problem. Understanding that problem is the fastest path to understanding every architectural choice that follows.

## The problem

Modern AI development involves many MCP servers — file systems, databases, web browsers, code executors, APIs — and multiple MCP clients: Claude Code, Codex, and whatever ships next month. The naive setup requires configuring each client separately for each server: N clients × M servers configurations, each maintained by hand, each holding its own copy of API keys and credentials. When a server's URL changes or a credential rotates, every client config must be updated individually. Worse, the tool names exposed by the same upstream server may differ between clients because each client applies its own filtering or aliasing.

The result is credential sprawl, config drift between clients, and an identity problem: the `read_file` tool in Claude Code may or may not be the same as `read_file` in Codex. There is no single point of control.

Coffer's answer to this slice is a long-lived local daemon that registers upstream MCP servers once, exposes all of them through a single namespaced surface (every tool appears as `<server-name>__<tool-name>`), and handles all client connections through that one point. Configure once; every client sees the same tools, the same names, the same policies.

The MCP gateway, though, is only one capability of a broader vault. The same daemon and the same kind-agnostic Resource framework also manage registered coding agents, master skill bundles, the shared knowledge store, aggregated agent memory, model providers, and messaging channels — **seven** resource kinds in all (`mcp_server`, `agent`, `skill`, `knowledge`, `memory`, `provider`, `channel`) — plus the cross-cutting turn platform that drives those agents behind the channels, and bidirectional vault sync against a git remote you own. The principles below govern the whole vault, with the gateway as the founding kind rather than the entire system.

## The three principles

Everything else — technology choices, layering, process model, persistence strategy — is a consequence of these three.

### I. Local-First (NON-NEGOTIABLE)

::: warning Invariant
All user data lives on the user's machines — one vault, every machine holding the full state. Cloud services are LLM and tool providers only — they never become the system of record for any vault state. The HTTP API binds to `127.0.0.1`. Replicating user-state to a vendor-controlled cloud requires an amendment.
:::

Every vault asset — registered server configs, credential references, audit logs, capability preferences — stays on your devices. No backup to a vendor cloud and no telemetry leave the machine without the user's explicit action.

"Local-first" does not mean "no network": calling a remote LLM API or invoking a cloud-hosted MCP tool is entirely expected. The constraint is about **where state lives**, not about whether the network is used. The daemon can make outbound HTTP calls to LLM providers; it simply cannot make your vault state visible to a third party without an amendment to the principles.

**Exception — user-owned sync remote.** Coffer may converge the vault with a git remote the user owns, so that the user's own machines hold one vault rather than several. The exception is bounded by three conditions, **all of which must hold**:

1. The remote is a **rendezvous, never a system of record** — each machine's local vault stays authoritative and complete, so the remote can be deleted and rebuilt from any single machine without losing anything.
2. Secrets travel **as ciphertext only**, and the master key never leaves the machine except through the out-of-band key transfer.
3. The feature is **off by default**, enabled by the user against a repository they own.

A hosted endpoint Coffer itself operates remains outside this exception.

Convergence is **bidirectional**: Coffer applies what the remote brought in as well as pushing what this machine changed. It is authorised only under the safety rules the sync spec carries — git's own three-way merge is the arbiter, what gets applied is a **diff against the last state this vault provably held** rather than a wholesale overwrite, and a round that would delete more than its configured share stops and asks. A mechanism that writes the vault outside those rules is not covered by this exception. How the converge round meets these rules is described in [Vault sync](/architecture/sync).

### II. Spec-as-Truth (OpenSpec)

Specifications under `openspec/specs/`, written with [OpenSpec](https://github.com/Fission-AI/OpenSpec), are the canonical product contract. A change to externally visible behavior starts as an OpenSpec change under `openspec/changes/<id>/` whose spec deltas say what will be true afterwards, lands with the code that makes it true, and is archived into `openspec/specs/`. A spec is not "documentation" — it is the implementation's contract; if the code disagrees with the spec, the code is wrong.

This principle exists because distributed teams (and AI agents generating code) tend to drift from design intent over time. By making the spec the source of truth and requiring it to be updated before code changes, Coffer ensures that architectural intent is always recorded and verifiable.

### III. Open-Source-Readiness from Day One

License (MIT), governance, contribution flow, and Conventional Commits are present in the repository from v0.0.1, not retrofitted later. A change that would shorten this list — adding a closed-source dependency without an exception, omitting attribution for AI-authored content — violates this principle and requires an amendment with an explicit migration plan.

This prevents the hidden cost of "we'll open-source it later" — retrofitting licenses, attribution, and governance onto a codebase after the fact is expensive and error-prone.

## Technology & architectural constraints

- **Languages.** Python 3.12+ for backend, CLI, and any MCP shim; TypeScript 5.x for frontend. No other primary languages without an amendment.
- **Architecture.** Layered: `surfaces → application → domain`; `infrastructure` adapts to ports defined in `application` and is wired only at the composition root. `domain/` may not import `infrastructure/`, `surfaces/`, or external SDKs. `application/` may not import `surfaces/`. Cross-cutting modules are extracted only after the second feature needs them. (Exception: the Resource framework — see [Resource framework](/architecture/resource-framework#why-kind-agnostic-upfront-adr-resource-framework-upfront).) The layers, their enforcement and the code layout are described in [Layering & boundaries](/architecture/layering).
- **Persistence.** SQLite is the system of record for control-plane state. Bulk user content — knowledge collections, memory partitions — is stored as files on the local file system, and those files are the only copy: nothing indexes, chunks or embeds them. See [Persistence](/architecture/persistence).
- **Credentials.** Secrets live **only** as Fernet ciphertext in the `credentials` table; plaintext exists in memory solely between decrypt and the spawn/header-injection that consumes it. The Fernet master key is managed exclusively by `coffer.infrastructure.credentials` — a `0600` file beside the DB by default, the OS keychain via `keyring` when opted in. `keyring` import stays confined to that module. All other code uses credential refs. No secret plaintext reaches the database, logs, audit, or any structured event. Credential material leaves the machine only as Fernet ciphertext and only when the user asks for it explicitly; the master key is never written into anything the vault publishes, and reaches another machine only through the explicit out-of-band transfer (`/sync/key/export` and `/sync/key/import`, which move key material and nothing else). See [Security](/architecture/security).
- **Network defaults.** Loopback-only. Outbound HTTP goes through a SSRF-guarded client (`coffer.infrastructure.net.ssrf_guard`, which rejects loopback, private and link-local destinations). Where the code does not yet meet this — the guard currently has one caller — is recorded in [Security → Outbound HTTP](/architecture/security#outbound-http-one-guarded-path-and-the-rest).

## Quality gates

A change is "done" only when **all** of the following hold:

- The relevant spec is updated to match the code, through an archived OpenSpec change.
- Every requirement owns a scenario, and every scenario is covered by a passing test.
- `make verify` passes locally and in CI.
- File-size limits hold (see `.agents/stack.md`).
- Architectural boundaries are not violated.

## Governance

This page **supersedes** any conflicting guidance in `AGENTS.md`, `CONTRIBUTING.md`, or per-spec documents. When they disagree, this page wins.

**Amendments.** A change to any Core Principle, to the Technology & Architectural Constraints, or to a Quality Gate requires:

1. A proposal PR describing motivation, current behavior, proposed behavior, downstream impact, alternatives.
2. Explicit decision recorded in the PR description.
3. The amending PR updates this page (`docs-site/architecture/principles.md`). Its history is the file's git log.

**Removing a shipped capability.** Removing a capability that has shipped requires the project owner's explicit confirmation. The PR proposing it MUST state in its description what a reversal would cost: the code it deletes, the migrations it runs against user data and whether they can be undone, and the documents it rewrites (specs, ADRs, this page, OpenSpec changes). It MUST remove the dead code and every documentation reference in the same PR, so the tree never carries a half-removed capability that the next reader has to reconstruct.

**PR review.** Every PR description must, where applicable, name the principles or constraints it affects, and explain why the change respects (or formally amends) them.

## Guarantees and invariants

These follow from the constraints above and hold unconditionally; they are not configuration options:

**Loopback-only.** The daemon's HTTP server binds to `127.0.0.1` and will not accept connections from any other interface.

**Secret plaintext never reaches the database.** The SQLite database holds credential references — opaque identifiers — and ciphertext, never plaintext. No code outside `infrastructure/credentials/` may import `keyring`.

**Every upstream tool is namespaced.** Tools exposed through the Coffer MCP surface appear as `<server-name>__<tool-name>` (e.g., `filesystem__read_file`). This namespace is stable and deterministic: the same upstream registered under the same name always produces the same tool namespace regardless of which client connects.

**Single SQLite writer.** Only the daemon process writes to `~/.coffer/coffer.db`. The CLI and shim read state through the daemon's HTTP API; they never open the database directly. This invariant makes WAL-mode isolation trivially correct.

## What Coffer is not

Understanding scope is as important as understanding capabilities.

**Not a cloud service.** There is no hosted Coffer, no SaaS plan, no account required. The daemon is a process on your machine.

**Not a hosted sync service.** Coffer converges your machines only through a git remote you own and configure; it ships no remote of its own and no hosted sync endpoint. Offering one would require an amendment to the principles.

**Not a model provider.** Coffer is not itself an LLM and does not host one. The MCP gateway routes protocol messages without reasoning about tool outputs, and the turn platform behind the channels drives your registered coding agents, which do invoke LLMs to converse — but those models are external providers Coffer calls, never models Coffer ships or trains. Coffer orchestrates models and tools; it is not the model.

**Not a firewall or security boundary.** Coffer applies capability-level enable/disable policies, but it is a developer tool running as the user's own process — it does not sandbox upstream server code or enforce OS-level access control.

## Rejected alternatives

These rejections are recorded in the ADRs; the summaries here anchor the principles:

**Why not a cloud-hosted gateway?** A hosted gateway would be the natural answer for teams, but it violates Local-First unconditionally. Credentials would have to leave the machine; vault state would have a network dependency. The single-user local-first model is the design's foundation.

**Why not per-client configuration?** Per-client config is the status quo — it is the problem Coffer solves. The pain it creates (N × M maintenance burden, credential sprawl, identity inconsistency) is precisely the motivation for a central daemon.

**Why not extract cross-cutting abstractions eagerly?** Cross-cutting modules are extracted only when a second feature needs them, to avoid over-engineering. The sole exception is the Resource framework, which was designed upfront because it spans every layer (domain, persistence, audit, surface routing) — retrofitting it after a second resource kind arrived would require a non-trivial migration, not a modest extraction.
