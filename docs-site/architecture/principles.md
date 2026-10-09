---
title: Principles
description: The binding project principles, technology constraints, quality gates and governance of Coffer.
---

# Principles

::: tip This page is normative
This page is the single source of Coffer's project principles. It holds **scaffolding-level** invariants only: tech stack, workflow, licensing posture, architectural style, and how the product hands work to an agent. Product behavior — the resource model, the gate on who may drive an agent, the surface roster, what gets persisted where — is defined per capability in `openspec/specs/`. The clauses under [The four principles](#the-four-principles), [Technology & architectural constraints](#technology-architectural-constraints), [Quality gates](#quality-gates) and [Governance](#governance) are binding; the surrounding sections explain them. The reasoning behind each design choice is laid out in [Design philosophy](/architecture/design-principles).
:::

> Coffer is a local-first AI agent vault: a developer's accumulated AI assets
> live on-device, and any AI agent (Claude Code, Codex, future ones) reads
> and contributes through one safe interface.

Coffer exists to solve a specific, concrete problem. Understanding that problem is the fastest path to understanding every architectural choice that follows.

## The problem

Modern AI development involves many MCP servers — file systems, databases, web browsers, code executors, APIs — and multiple MCP clients: Claude Code, Codex, and whatever ships next month. The naive setup requires configuring each client separately for each server: N clients × M servers configurations, each maintained by hand, each holding its own copy of API keys and secrets. When a server's URL changes or a secret rotates, every client config must be updated individually. Worse, the tool names exposed by the same upstream server may differ between clients because each client applies its own filtering or aliasing.

The result is secret sprawl, config drift between clients, and an identity problem: the `read_file` tool in Claude Code may or may not be the same as `read_file` in Codex. There is no single point of control.

Coffer's answer to this slice is a long-lived local daemon that registers upstream MCP servers once, exposes all of them through a single namespaced surface (every tool appears as `<server-name>__<tool-name>`), and handles all client connections through that one point. Configure once; every client sees the same tools, the same names, the same policies.

The MCP gateway, though, is only one capability of a broader vault. The same daemon and the same kind-agnostic Resource framework also manage registered coding agents, master skill bundles, the shared knowledge store, aggregated agent memory, model providers, and messaging channels — **seven** resource kinds in all (`mcp_server`, `agent`, `skill`, `knowledge`, `memory`, `provider`, `channel`) — plus the cross-cutting turn platform that drives those agents behind the channels, and bidirectional vault sync against a git remote you own. The principles below govern the whole vault, with the gateway as the founding kind rather than the entire system.

## The four principles

Everything else — technology choices, layering, process model, persistence strategy, how the product asks a person for help — is a consequence of these four.

### I. Local-First (NON-NEGOTIABLE)

::: warning Invariant
All user data lives on the user's machines — one vault, every machine holding the full state. Cloud services are LLM and tool providers only — they never become the system of record for any vault state. The HTTP API binds to `127.0.0.1`. Replicating user-state to a vendor-controlled cloud requires an amendment.
:::

Every vault asset — registered server configs, secret references, audit logs, capability preferences — stays on your devices. No backup to a vendor cloud and no telemetry leave the machine without the user's explicit action.

"Local-first" does not mean "no network": calling a remote LLM API or invoking a cloud-hosted MCP tool is entirely expected. The constraint is about **where state lives**, not about whether the network is used. The daemon can make outbound HTTP calls to LLM providers; it simply cannot make your vault state visible to a third party without an amendment to the principles.

**Exception — user-owned sync remote.** Coffer may converge the vault with a git remote the user owns, so that the user's own machines hold one vault rather than several. The exception is bounded by three conditions, **all of which must hold**:

1. The remote is a **rendezvous, never a system of record** — each machine's local vault stays authoritative and complete, so the remote can be deleted and rebuilt from any single machine without losing anything.
2. Secrets travel **as ciphertext only**, and the master key never leaves the machine except through the out-of-band key transfer.
3. The feature is **off by default**, enabled by the user against a repository they own.

A hosted endpoint Coffer itself operates remains outside this exception.

Convergence is **bidirectional**: Coffer applies what the remote brought in as well as pushing what this machine changed. It is authorised only under the safety rules the sync spec carries — git's own three-way merge is the arbiter, what gets applied is a **diff against the last state this vault provably held** rather than a wholesale overwrite, and a round that would delete more than its configured share stops and asks. A mechanism that writes the vault outside those rules is not covered by this exception. How the converge round meets these rules is described in [Vault sync](/architecture/vault-sync).

### II. Spec-as-Truth (OpenSpec)

Specifications under `openspec/specs/`, written with [OpenSpec](https://github.com/Fission-AI/OpenSpec), are the canonical product contract. A change to externally visible behavior starts as an OpenSpec change under `openspec/changes/<id>/` whose spec deltas say what will be true afterwards, lands with the code that makes it true, and is archived into `openspec/specs/`. A spec is not "documentation" — it is the implementation's contract; if the code disagrees with the spec, the code is wrong.

This principle exists because distributed teams (and AI agents generating code) tend to drift from design intent over time. By making the spec the source of truth and requiring it to be updated before code changes, Coffer ensures that architectural intent is always recorded and verifiable.

**Contract direction.** The two halves of a spec folder are written in opposite directions:

1. The **behavioural spec** — requirements and their scenarios in `spec.md` — is written first, by hand, and the code is built to satisfy it.
2. The **wire schema** — `contracts/api.openapi.yaml` in the same folder — is generated from the backend's Pydantic models and checked in, so every change to it is reviewed as a diff in the PR that causes it.
3. The **frontend's typed client** and its wire types are generated from that schema.

No wire type is hand-written on either side. The Pydantic models are the only hand-written description of the HTTP wire, because they are what the daemon actually serves. A hand-written schema beside them is a second copy that has to be kept in agreement by a gate, and a gate that compares two documents by field name cannot see a type, a nullability or a constraint that differs; generating the schema from the models removes the second copy, and generating the client from the schema lets the TypeScript compiler check every consumer's types, which no name-only gate can. The reasoning is recorded in [The wire contract is generated from the Pydantic models](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/wire-contract-generated-from-the-pydantic-models.md).

### III. Open-Source-Readiness from Day One

License (AGPL-3.0-or-later), governance, contribution flow, and Conventional Commits are present in the repository from v0.0.1, not retrofitted later. A change that would shorten this list — adding a closed-source dependency without an exception, omitting attribution for AI-authored content — violates this principle and requires an amendment with an explicit migration plan.

This prevents the hidden cost of "we'll open-source it later" — retrofitting licenses, attribution, and governance onto a codebase after the fact is expensive and error-prone.

### IV. AI-Native

Everyone who uses Coffer already works with a coding agent, so Coffer treats an agent as the way environment-dependent work gets done. When a task depends on the person's machine and has no single right procedure — installing a program, setting up a tool or an outside account, diagnosing and fixing the environment — the product hands it to an agent. It builds a prompt that states the facts (what is missing, why it is needed, the constraints) and offers it two ways: started as a new session of the person's default agent in their preferred terminal, with the prompt sent as its first message — pressing the hand-off button is the consent — or copied, for any agent the person chooses. The product does not hard-code one package manager's install commands, run installers, or walk the person through long manual step lists. Work the person could do in the UI but may not want to — resolving a sync conflict, merging a skill's upstream update with local edits — also offers the hand-off beside the manual controls, so the person chooses whether to look at it themselves. The prompt is built by the daemon, so the CLI and the UI offer the same words.

Two cases stay outside the hand-off:

1. **Work Coffer owns and can do deterministically and safely** — repairing its own entry in an agent's config, a reconcile pass, rotating its own token — is a plain button.
2. **Work only the person can do** — a login in a browser, an approval, a setting in a platform's portal — stays with the person; a prompt may still help with the steps around it.

A prompt never asks an agent to handle a credential; where a login is needed, it tells the agent to leave the login to the person.

This holds because a hard-coded procedure is right for one kind of machine and wrong for the rest, and it goes stale as tools change, while an agent reads the machine it is on.

The hand-off starts the agent in the person's terminal rather than in a conversation Coffer runs, for three reasons. Neither agent's command line can open a session with a prompt typed in but not sent — `claude [prompt]` and `codex [PROMPT]` both send it as they start — so pressing the button is where the person says yes. In their own terminal the agent runs under its own permission mode, the one the person set up and watches, which is safer than an agent Coffer drives with full permissions. And the person stays in control there: the prompt is the session's first message, in plain view, and Esc or Ctrl-C stops the agent at any moment.

## Technology & architectural constraints

- **Languages.** Python 3.12+ for backend, CLI, and any MCP shim; TypeScript 5.x for frontend. No other primary languages without an amendment.
- **Architecture.** Layered: `surfaces → application → domain`; `infrastructure` adapts to ports defined in `application` and is wired only at the composition root. `domain/` may not import `infrastructure/`, `surfaces/`, or external SDKs. `application/` may not import `surfaces/`. Cross-cutting modules are extracted only after the second feature needs them. The layers, their enforcement and the code layout are described in [Layering and code layout](/architecture/layering).
- **Persistence.** The vault's files are the system of record for configuration: `~/.coffer/vault` is a git repository, and every accepted write to it is one validated commit naming its writer. History (audit, invocations, conversations, sync rounds) lives in `runs.db`. Bulk user content — knowledge collections, memory partitions — is stored as files on the local file system, and those files are the only copy: nothing keeps a persistent index, chunks or embeds them (memory retrieval ranks lexically over an in-memory index rebuilt from the files). See [Persistence](/architecture/persistence).
- **Secrets.** Secrets live **only** as Fernet ciphertext, one file per secret (`vault/secret/<ref>.enc`, or `local/secret/` for machine-local refs); plaintext exists in memory solely between decrypt and the spawn/header-injection that consumes it. The one long-lived holder is the local model proxy, the daemon's only sibling process: a header-injection consumer that keeps the decrypted keys of the connections it serves in memory for its lifetime, receives them from the daemon over its authenticated loopback control route, and never holds the master key or writes a key anywhere. The Fernet master key is managed exclusively by `coffer.infrastructure.secret` — a data-protection Keychain item in an access group limited to Coffer's Team ID. `keyring` import stays confined to that module. All other code uses secret refs. No secret plaintext reaches the vault, `runs.db`, logs, audit, or any structured event. Secret material leaves the machine only as Fernet ciphertext and only when the user asks for it explicitly; the master key is never written into anything the vault publishes, and reaches another machine only through the explicit out-of-band transfer (a key backup the desktop app writes behind a presence check, and `/secrets/key/import`, which move key material and nothing else). See [Security](/architecture/security).
- **Secret plaintext reaches only a present human; agents get capabilities, never keys.** A secret's plaintext, and the master key, leave Coffer only to a person at the machine: in the desktop app, released by the operating system's presence check (Touch ID or the login password) on each reveal, copy or key backup, with no reuse window — never through REST, the CLI, MCP or the browser UI. (The one other plaintext path is `coffer run`, which resolves a standalone secret into one child's environment, and only after a person granted that secret to local programs in the desktop app; it is labelled as readable by local processes.) Coffer sends a secret to a destination it has not sent it to before — an MCP server's environment or header, a channel's credential, a provider's base URL, a tool's authentication, the sync remote — only after that person approves the binding in the desktop app, and only that person can turn the protection off. Agents may use and configure Coffer through every surface; they use a secret through a capability Coffer injects on their behalf (the MCP gateway, the local model proxy), never by holding it. Where a secret must sit in a process an agent can inspect — a third-party stdio server's environment, a `coffer run` child — the product says so rather than claiming protection. A request that carries a secret never follows a redirect to another origin, and where the secret rides in a request is part of what was approved. Approvals default on (a person's own setting wins). See [Security](/architecture/security).
- **Network defaults.** Loopback-only. Outbound HTTP to a URL Coffer probes or fetches on the user's behalf from something typed into a form goes through the SSRF guard first (`coffer.infrastructure.net.ssrf_guard`, which rejects loopback, private and link-local destinations). Traffic to the endpoints the user explicitly configures as their own — HTTP MCP upstreams, model and transcription endpoints, the IM platforms, the git sync remote — is exempt once Coffer is using them, because a loopback or LAN endpoint is a legitimate target there (Ollama, a localhost MCP server). Which calls the guard covers is listed in [Security → Outbound requests](/architecture/security#outbound-requests).

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

**Secret plaintext never reaches storage.** The vault's files, `local/` and `runs.db` hold secret references — opaque identifiers — and, in `vault/secret/` and `local/secret/`, ciphertext; never plaintext. No code outside `infrastructure/secret/` may import `keyring`.

**Secret plaintext never reaches an agent through Coffer.** No route, command or tool returns a secret's value or the master key; the only reveal is the desktop app's, behind a presence check on each use.

**Every upstream tool is namespaced.** Tools exposed through the Coffer MCP surface appear as `<server-name>__<tool-name>` (e.g., `filesystem__read_file`). This namespace is stable and deterministic: the same upstream registered under the same name always produces the same tool namespace regardless of which client connects.

**Single SQLite writer.** Only the daemon process writes to `~/.coffer/runs.db`. The CLI and shim read state through the daemon's HTTP API; they never open the database directly. The local model proxy opens no database either: it spools its usage records to files the daemon ingests. This invariant makes WAL-mode isolation trivially correct.

## What Coffer is not

Understanding scope is as important as understanding capabilities.

**Not a cloud service.** There is no hosted Coffer, no SaaS plan, no account required. The daemon is a process on your machine.

**Not a hosted sync service.** Coffer converges your machines only through a git remote you own and configure; it ships no remote of its own and no hosted sync endpoint. Offering one would require an amendment to the principles.

**Not a model provider.** Coffer is not itself an LLM and does not host one. The MCP gateway routes protocol messages without reasoning about tool outputs, and the turn platform behind the channels drives your registered coding agents, which do invoke LLMs to converse — but those models are external providers Coffer calls, never models Coffer ships or trains. Coffer orchestrates models and tools; it is not the model.

**Not a firewall or a sandbox.** Coffer applies capability-level enable/disable policies, but it is a developer tool running as the user's own process — it does not sandbox upstream server code, confine what an agent does with its own shell, or enforce OS-level access control. It holds exactly one boundary against the agents it serves: a secret's plaintext, and where a secret is sent, are decided by a present human.

**Not a second agent.** What a coding agent already does for itself — orchestrating a multi-step task (a skill and its subagents), running on a schedule (the agent's own automations), asking before a tool runs (the agent's own permission prompts) — Coffer does not rebuild. Coffer builds what spans agents or what no agent can do alone: one skill, MCP server, knowledge collection or memory serving every agent, the vault converged across machines, the agents' configuration managed in one place, and a channel that reaches an agent on this machine from elsewhere. A proposed capability an agent already has is declined, or reshaped into carrying that native capability across agents.

## Rejected alternatives

These rejections are recorded in the ADRs; the summaries here anchor the principles:

**Why not a cloud-hosted gateway?** A hosted gateway would be the natural answer for teams, but it violates Local-First unconditionally. Secrets would have to leave the machine; vault state would have a network dependency. The single-user local-first model is the design's foundation.

**Why not per-client configuration?** Per-client config is the status quo — it is the problem Coffer solves. The pain it creates (N × M maintenance burden, secret sprawl, identity inconsistency) is precisely the motivation for a central daemon.

**Why not extract cross-cutting abstractions eagerly?** Cross-cutting modules are extracted only when a second feature needs them, to avoid over-engineering.
