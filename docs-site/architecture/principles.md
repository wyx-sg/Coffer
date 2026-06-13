# Design Principles

Coffer exists to solve a specific, concrete problem. Understanding that problem is the fastest path to understanding every architectural choice that follows.

## The problem

Modern AI development involves many MCP servers — file systems, databases, web browsers, code executors, APIs — and multiple MCP clients: Claude Code, Codex, Cursor, and whatever ships next month. The naive setup requires configuring each client separately for each server: N clients × M servers configurations, each maintained by hand, each holding its own copy of API keys and credentials. When a server's URL changes or a credential rotates, every client config must be updated individually. Worse, the tool names exposed by the same upstream server may differ between clients because each client applies its own filtering or aliasing.

The result is credential sprawl, config drift between clients, and an identity problem: the `read_file` tool in Claude Code may or may not be the same as `read_file` in Cursor. There is no single point of control.

Coffer's answer to this slice is a long-lived local daemon that registers upstream MCP servers once, exposes all of them through a single namespaced surface (every tool appears as `<server-name>__<tool-name>`), and handles all client connections through that one point. Configure once; every client sees the same tools, the same names, the same policies.

The MCP gateway, though, is only one capability of a broader vault. Coffer is a local-first AI agent vault: the same daemon and the same kind-agnostic Resource framework also manage registered coding agents, master skill bundles, a knowledge-base and memory substrate, and messaging channels — six resource kinds in all — plus cross-cutting chat, channels, and multi-machine sync. The principles below govern the whole vault, with the gateway as the founding kind rather than the entire system.

## The three principles

The Coffer constitution establishes three non-negotiable principles. Everything else — technology choices, layering, process model, persistence strategy — is a consequence of these three.

### I. Local-First (NON-NEGOTIABLE)

::: warning Invariant
All user data lives on the user's machine. Cloud services are LLM and tool providers only — they never become the system of record for any vault state.
:::

Every vault asset — registered server configs, credential references, audit logs, capability preferences — stays on your device. The HTTP API binds exclusively to `127.0.0.1`. No backup to a vendor cloud and no telemetry leave the machine without the user's explicit action.

"Local-first" does not mean "no network": calling a remote LLM API or invoking a cloud-hosted MCP tool is entirely expected. The constraint is about **where state lives**, not about whether the network is used. The daemon can make outbound HTTP calls to LLM providers; it simply cannot make your vault state visible to a third party without a constitutional amendment.

Replicating user state to a **vendor-controlled** cloud as a system of record requires a formal constitutional amendment — an explicit, recorded decision, not a silent configuration change.

**Sync exception (constitution v0.3.0).** Multi-machine sync is permitted under a bounded exception to this principle, added in constitution v0.3.0 alongside spec 010. Sync runs only over a **user-owned, user-controlled** medium (the user's own git repository); every participating machine keeps the full vault, so the medium is transport and history, never a new system of record. Secrets travel as Fernet **ciphertext only** — the master key never crosses the sync medium and is bootstrapped onto each machine out-of-band. Sync is **opt-in** and points at a remote the user supplies. See [ADR-016](/reference/adr/ADR-016-multi-machine-sync).

### II. Spec-as-Truth (Spec-Driven Development)

Specifications under `specs/` are the canonical product contract. Every pull request that changes externally visible behavior updates the relevant spec **first**, then the code. The spec is not documentation written after the fact — it is the contract the implementation must conform to. If the code disagrees with the spec, the code is wrong.

This principle exists because distributed teams (and AI agents generating code) tend to drift from design intent over time. By making the spec the source of truth and requiring it to be updated before code changes, Coffer ensures that architectural intent is always recorded and verifiable.

### III. Open-Source-Readiness from Day One

MIT license, governance rules, contribution flow, and Conventional Commits are present in the repository from v0.0.1, not retrofitted later. This principle prevents the hidden cost of "we'll open-source it later" — retrofitting licenses, attribution, and governance onto a codebase after the fact is expensive and error-prone.

Any change that shortens the open-source readiness checklist — introducing a closed-source dependency without a documented exception, omitting attribution for AI-authored content — violates this principle and requires a constitutional amendment.

## Guarantees and invariants

These hold unconditionally; they are not configuration options:

**Loopback-only.** The daemon's HTTP server binds to `127.0.0.1` and will not accept connections from any other interface. Public-reachable surfaces, if ever introduced, run as a separate process and are limited to signed callback paths.

**Secret plaintext never reaches the database.** Secrets are stored only as Fernet ciphertext in the `credentials` table (envelope encryption); the SQLite database holds credential references — opaque identifiers — and ciphertext, never plaintext. Plaintext exists in memory only between decrypt and the spawn/header injection that consumes it. The Fernet master key is managed exclusively by `infrastructure/credentials/` (a `0600` file beside the DB by default, the OS keychain opt-in), the only place permitted to import `keyring`. No other code module may import `keyring` directly.

**Every upstream tool is namespaced.** Tools exposed through the Coffer MCP surface appear as `<server-name>__<tool-name>` (e.g., `filesystem__read_file`). This namespace is stable and deterministic: the same upstream registered under the same name always produces the same tool namespace regardless of which client connects.

**Single SQLite writer.** Only the daemon process writes to `~/.coffer/coffer.db`. The CLI and shim read state through the daemon's HTTP API; they never open the database directly. This invariant makes WAL-mode isolation trivially correct.

## What Coffer is not

Understanding scope is as important as understanding capabilities.

**Not a cloud service.** There is no hosted Coffer, no SaaS plan, no account required. The daemon is a process on your machine.

**Not a hosted sync service.** Coffer does sync vault state across machines (spec 010), but only over a medium the user owns and controls — their own git repository — under the v0.3.0 sync exception above. Coffer ships no hosted or vendor sync endpoint; offering one would still require a further constitutional amendment.

**Not a model provider.** Coffer is not itself an LLM and does not host one. The MCP gateway routes protocol messages without reasoning about tool outputs, and the in-process LangGraph chat agent (spec 008) does invoke LLMs to converse — but those models are external providers Coffer calls, never models Coffer ships or trains. Coffer orchestrates models and tools; it is not the model.

**Not a firewall or security boundary.** Coffer applies capability-level enable/disable policies (per ADR-004), but it is a developer tool running as the user's own process — it does not sandbox upstream server code or enforce OS-level access control.

## Rejected alternatives

These rejections are recorded in the ADRs; the summaries here anchor the principles:

**Why not a cloud-hosted gateway?** A hosted gateway would be the natural answer for teams, but it violates Local-First unconditionally. Credentials would have to leave the machine; vault state would have a network dependency. The single-user local-first model is the design's foundation.

**Why not per-client configuration?** Per-client config is the status quo — it is the problem Coffer solves. The pain it creates (N × M maintenance burden, credential sprawl, identity inconsistency) is precisely the motivation for a central daemon.

**Why not extract cross-cutting abstractions eagerly?** The constitution states that cross-cutting modules should be extracted only when a second feature needs them, to avoid over-engineering. The sole exception is the Resource framework, which was designed upfront because it spans every layer (domain, persistence, audit, surface routing) — retrofitting it after a second resource kind arrived would require a non-trivial migration, not a modest extraction. See [ADR-001](/reference/adr/ADR-001-resource-framework-upfront).

---

**See also:** [Constitution reference](/reference/project/constitution)
