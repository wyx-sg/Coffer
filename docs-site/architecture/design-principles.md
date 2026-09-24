---
title: Design philosophy
description: The rules Coffer's codebase keeps — local-first, spec as truth, one resource model, derived state, pull-based delivery, machine-local reach, encrypted secrets — each with its rationale, its consequences in the code and what it rules out.
---

# Design philosophy

This page states the design philosophy behind Coffer as a set of principles. The binding rules themselves — the principles, constraints, quality gates and governance — are on [Principles](/architecture/principles); this page explains the reasoning they rest on. Each one gives the rule, why it exists, where it shows up in the code, and what it deliberately rules out. Read it before proposing a change that crosses a boundary: most of what looks like an arbitrary restriction in the code is one of these principles doing its job.

The invariants themselves are owned by [Principles](/architecture/principles) and the capability specs under [`openspec/specs/`](https://github.com/wyx-sg/Coffer/tree/main/openspec/specs); the reasoning behind individual decisions is in the [decision records](/architecture/decisions).

## The philosophy in one paragraph

Coffer is a **custodian, not an owner**. It holds your assets on your machine, hands them to agents through channels the agents already speak, and makes sure that removing Coffer, switching a feature off or losing a remote never costs you anything. It prefers **one mechanism enforced at many points** over many mechanisms: one resource model, one reach predicate, one lock, one log reader. And it treats **the contract as the product**: what the specs say, the code must do, and gates in the build check it. Every principle below is one of those three ideas applied to a specific part of the system.

## At a glance

| Principle | In one line |
| --- | --- |
| [Local-first](#local-first) | Your machine is the system of record; the only remote is one you own, and it is a rendezvous. |
| [Spec as truth](#spec-as-truth) | The OpenSpec specs are the contract; code that disagrees is wrong. |
| [Everything user-managed is a Resource](#everything-user-managed-is-a-resource) | One identity, lifecycle, audit and reach for every kind; behaviour stays per kind. |
| [Identity is an immutable uid](#identity-is-an-immutable-uid) | Names are labels; references hold uids. |
| [Agent files are the source of truth](#agent-files-are-the-source-of-truth) | Coffer reads an agent's state where it lives and never keeps a copy that could drift. |
| [Files are the truth for bulk content](#files-are-the-truth-for-bulk-content) | Knowledge and memory are plain Markdown; nothing indexes, chunks or embeds them. |
| [Pull, not push](#pull-not-push) | Coffer puts paths and a catalogue in front of the agent; it does not inject context behind your back. |
| [Reach is machine-local](#reach-is-machine-local) | Whether a resource is enabled, and for which agents, is decided on the machine it applies to. |
| [Each kind enforces reach at its own choke point](#each-kind-enforces-reach-at-its-own-choke-point) | One predicate, many enforcement points, no central gate. |
| [Secrets are never plaintext at rest](#secrets-are-never-plaintext-at-rest) | Fernet ciphertext in SQLite, refs everywhere else. |
| [Detect, never refuse](#detect-never-refuse) | On version skew, say so and carry on. |
| [Off keeps data](#off-keeps-data) | Switching a feature off hides it; it never deletes anything. |
| [Extract on second use](#extract-on-second-use) | A shared module is created when the second feature needs it, not before. |

## Local-first

**Statement.** Everything Coffer holds lives on your machines, and each machine holds the full vault. Cloud services are model and tool providers only; none of them is ever the system of record for vault state. The HTTP API binds to `127.0.0.1`.

**Rationale.** The assets Coffer holds — API keys, private notes, everything your agents have learned about your environment — are exactly the assets you would not hand to a third party. A local store also has no availability dependency: an agent's first tool call of the day does not wait on anyone's service.

**The bounded exception.** Coffer can converge the vault with a git remote *you* own, so your own machines hold one vault rather than several. The exception holds only while three conditions all hold:

1. **The remote is a rendezvous, never a system of record.** Every machine's local vault stays authoritative and complete, so the remote can be deleted and rebuilt from any one machine.
2. **Secrets travel as ciphertext only.** The master key leaves a machine only through an explicit out-of-band transfer (`coffer sync key export` / `import`).
3. **It is off by default** and pointed only at a repository you configure.

Convergence is bidirectional but only under the sync spec's safety rules: git's three-way merge arbitrates, what is applied is a diff against the last state this vault provably held, and a round that would delete more than its configured share stops and asks.

**In the code.** The daemon binds `127.0.0.1` in [`infrastructure/daemon/port_alloc.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/daemon/port_alloc.py). Channels reach Telegram and SeaTalk only over connections the daemon opens, so the loopback socket is the only one Coffer listens on. The sync remote defaults to absent, and credential ciphertext is carried only when you set `--with-credentials`.

**Rules out.** A hosted Coffer endpoint; a "Coffer cloud" account; any design where losing the remote loses data; a sync that overwrites a vault wholesale; replicating vault state to a vendor-controlled service.

## Spec as truth

**Statement.** The specs under `openspec/specs/<capability>/spec.md` are the product contract. A change to externally visible behaviour starts as an OpenSpec change under `openspec/changes/<id>/`, lands together with the code that makes it true, and is archived into the specs. If the code disagrees with the spec, the code is wrong.

**Rationale.** Coffer is developed by people and AI coding agents together. An agent is only as good as the contract it can read, and a contract that lives in a PR description or a chat log is gone the moment the session ends. A spec that is enforced by the build is a contract every future contributor — human or agent — can rely on.

**In the code.** Every requirement must own at least one scenario (`openspec validate --strict`), and every scenario must be covered by a test that carries an `acceptance` marker ([`scripts/audit_acceptance.py`](https://github.com/wyx-sg/Coffer/blob/main/scripts/audit_acceptance.py)). Each spec's OpenAPI contract is the wire truth: backend models are hand-written to match it, `make verify-contract` fails on structural drift, and the frontend's typed client is generated from it. A citation of a requirement by title is checked by [`scripts/check_spec_citations.py`](https://github.com/wyx-sg/Coffer/blob/main/scripts/check_spec_citations.py).

**Rules out.** Behaviour that exists only in code; "documentation" specs that describe intent rather than obligation; a wire shape the contract does not declare. See [Spec-driven workflow](/contributing/spec-workflow).

## Everything user-managed is a Resource

**Statement.** Every entity you manage — an MCP server, an agent, a skill, a knowledge collection, a memory partition, a channel, a model provider — is a **Resource** of some **kind**. The framework unifies identity, lifecycle, audit, schema validation and reach. It does not unify behaviour: how an MCP server is invoked and how a skill is delivered stay entirely inside their kinds.

**Rationale.** Every kind needs the same things: to be named, listed, enabled, disabled, renamed, deleted, audited and scoped. Building those seven times is more code and seven chances to drift. But a framework that tried to own behaviour too — one `invoke()` for everything — would be a leaky abstraction over things that have nothing in common.

**In the code.** One frozen [`Kind`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/domain/resource.py) descriptor per kind, one kind-agnostic `ResourceService`, one `resources` table, one `/api/v1/resources` router, one `audit_log`. The kind-agnostic core is tested against a fake kind and an import contract forbids it from importing any real one. See [Resource framework](/architecture/resource-framework).

**Rules out.** A generic `invoke` method; a third-party plugin system (a plugin contract needs several concrete implementations to design against, and Coffer serves one user); per-kind CRUD, audit or scope implementations.

::: info Why this principle was built up front
Coffer's general rule is to extract shared code only on second use. The Resource framework is the deliberate exception: it is core domain, not a cross-cutting helper, and extracting it later from MCP-specific code would have meant re-modelling the audit table, the routes and retention at once. See [Resource Framework Designed Upfront](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/resource-framework-upfront.md).
:::

## Identity is an immutable uid

**Statement.** A resource's identity is its `uid`: an opaque `uuid4().hex` minted once at creation, never reused, and the same value on every machine that holds the resource. The `name` is a mutable label, unique within its kind. The integer `id` is an internal surrogate key that never leaves the process.

**Rationale.** Once a vault converges across machines, the question an identifier must answer is "is the thing on that machine the same thing as the thing on this one?" A name cannot answer it, because a name is exactly what you are allowed to change: a rename would cross the sync remote as a deletion plus a creation, cascading away everything attached to the old row. An autoincrement row number cannot answer it either, because two machines allocate the same number to different resources.

**In the code.** `/api/v1/resources/{uid}` addresses every resource; a resource `scope` and a channel's `default_agent` hold agent uids; the sync bundle is laid out as `resources/<kind>/<uid>.yaml`; rename is an ordinary field on `PATCH`, available to every kind. The CLI still takes names and resolves them to uids itself, so nobody types a UUID.

**Rules out.** `<kind>:<name>` identifiers; cross-resource references by name; per-kind rename endpoints; exposing `resources.id` on any surface.

## Agent files are the source of truth

**Statement.** An agent's own files are the source of truth for that agent. Coffer reads config files, MCP entries, plugins, native memory and transcripts where the agent keeps them, at read time, and never copies them into SQLite. It writes only an agent's documented surfaces, addressed by an allowlist, atomically and with a `.bak`.

**Rationale.** A copy of someone else's state drifts the moment they change it, and the agent changes its own state constantly. Deriving at read time means Coffer is never wrong about what the agent has, and uninstalling Coffer leaves every agent exactly as functional as before.

**In the code.** The `agent` kind stores only a config directory and install state; everything else is read through [`infrastructure/agent/`](https://github.com/wyx-sg/Coffer/tree/main/backend/coffer/infrastructure/agent) and [`infrastructure/agent_files/`](https://github.com/wyx-sg/Coffer/tree/main/backend/coffer/infrastructure/agent_files). Codex TOML is edited with `tomlkit` so comments and ordering survive. An agent's internal state (for example Claude Code's `installed_plugins.json`) is only read; a change that must reach it is delegated to the agent's own CLI. The memory layer reads each agent's native memory and never writes it; everything under `~/.coffer/memory/` is derived and rebuildable. See [Memory](/architecture/memory).

**Rules out.** Mirroring an agent's config into the database; writing into an agent's memory files; editing undocumented internal files; any change an agent could not survive Coffer being removed.

## Files are the truth for bulk content

**Statement.** SQLite is the system of record for control-plane state. Bulk user content — knowledge collections and memory partitions — is plain Markdown on disk, and those files are the only copy: nothing indexes, chunks or embeds them.

**Rationale.** A derived index has to be reconciled with its source, and every reconciliation is a place to be wrong. Plain files are live the moment you save them in your own editor, readable by every agent's own `Read` and `Grep`, diffable in git, and survive Coffer entirely. Measured usage showed agents never reached for a retrieval tool they had to remember to call, while they read files constantly.

**In the code.** The knowledge layer owns no table: a collection is a `resources` row plus a directory. Retrieval is the agent's own file tools against absolute paths; ripgrep survives only as the in-process candidate selector the curation pass uses. An import contract bans vector-store and embedding libraries from the codebase. See [Knowledge](/architecture/knowledge) and [Knowledge Is Plain Files](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md).

**Rules out.** A documents table; FTS or vector indexes; an embedding sidecar; a second copy of a document in any other store. Literal matching is a placeholder rather than a verdict: semantic retrieval may return, but not as a copy of the files.

## Pull, not push

**Statement.** Coffer does not inject context into an agent's session automatically. It puts the right paths and a catalogue in front of the model and lets the model read what it needs. The catalogue is a skill: Coffer's own `coffer-guide`, whose resident description names Coffer, its builtin tools and the subjects your knowledge covers, and whose body carries the manual and every knowledge document's path, title and description.

**Rationale.** Anything in the MCP handshake or a session-start hook is charged to every session whether or not it is needed. A skill has the opposite cost structure: its short description is always in context, its body costs nothing until a model opens it. So the resident budget is spent once, on one description a model can match against.

**In the code.** The gateway's handshake `instructions` are capped at 800 characters ([`application/mcp/gateway_instructions.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/mcp/gateway_instructions.py)): what Coffer is, the builtin tool names, the per-session count of hidden upstream tools, and a pointer to the skill. `coffer-guide` is an ordinary `skill` resource rendered by [`application/knowledge/guide_render.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/knowledge/guide_render.py) and delivered by the skill kind. The one session-start delivery Coffer offers — the memory index — is a hook you install explicitly per agent, remove the same way, and whose every fire is an audit event.

**Rules out.** Silently installed hooks; context injected into a session without an audit trail; writing Coffer's output into an agent's own memory; a catalogue spread across several always-resident skills.

## Reach is machine-local

**Statement.** A resource's **reach** is its `enabled` flag together with its agent `scope`. Reach is set on the machine it applies to and never converges: the sync bundle carries what a resource *is* and how it is configured, never what it reaches.

**Rationale.** A synced reach would be set from wherever you happen to sit, about machines you cannot see, and two machines editing it would put a permission through a text merge where whichever round ran last silently decides what the other machine exposes. A machine-local reach has nothing to merge and can always be verified where it takes effect. The cost is honest: a resource arriving on a machine for the first time starts at that kind's default reach there.

**In the code.** `domain/sync/serialization.py` leaves `enabled` and `scope` out of the resource document, and the applier leaves local reach untouched. The experimental-feature switches live in `~/.coffer/daemon-config.json` rather than the database for the same reason. Surfaces say so where reach is set: `coffer scope set --help` states that the scope applies to this machine only.

**Rules out.** Machine ids inside a scope; a "newest write wins" reach; any permission that changes because another machine's round ran.

## Each kind enforces reach at its own choke point

**Statement.** The framework stores reach; each kind enforces it where the asking identity is known. Every enforcement point asks the same question of the same function, `is_active(scope, agent_uid)` in [`domain/scope.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/domain/scope.py).

**Rationale.** A central gate would have to sit on every kind's read path and know every kind's notion of "use". The gateway already knows which agent is asking for tools; skill delivery already iterates agents; the provider projection already knows which config file it is writing. Putting the check there costs one function call and no new machinery.

**In the code.** `mcp_server` filters in the gateway, `skill` in delivery reconciliation, `provider` in `application/provider/targets.py`, and `channel` — whose scope is inverted to name the agents it may *drive* — in its agent routing and its runtime. An unidentified session matches only an unrestricted scope, so it sees strictly less, never more. See the [kinds table](/architecture/resource-framework#the-seven-kinds).

**Rules out.** A reach evaluator object; a deny-list (a new agent would silently gain access); a kind inventing its own "which agents" field.

## Secrets are never plaintext at rest

**Statement.** Secrets live only as Fernet ciphertext in the `credentials` table. Plaintext exists in memory solely between decrypt and the spawn or header injection that consumes it, and never reaches the database, logs, audit or any structured event. All other code holds credential **refs**. The master key is managed only by `coffer.infrastructure.credentials` — a `0600` file beside the database by default, the OS keychain when you opt in — and that module is the only importer of `keyring`.

**Rationale.** Envelope encryption gives zero keychain prompts under an unsigned, frequently rebuilt binary, while the keychain opt-in still defends against offline copying of `~/.coffer/`. Refs make every config document safe to audit, sync and display.

**In the code.** An import contract confines `keyring`; another stops the CLI from importing the credential store at all, so the daemon is the single reader of the key. The MCP server schema rejects static `env` and header values that look like tokens. Kinds supply an `audit_redactor` so config written to the audit log carries no secret-bearing maps. See [Security model](/architecture/security).

**Rules out.** Secrets in resource config; the CLI decrypting in-process; the master key inside anything the vault publishes; re-encrypting data to switch key storage (the key moves, the ciphertext does not).

## Detect, never refuse

**Statement.** When a client finds a daemon from a different build, it says so and carries on. It never refuses to work and never kills or upgrades the running daemon on its own.

**Rationale.** The daemon outlives the CLI and shim processes that attach to it, so version skew is a normal state right after an upgrade. Refusing would break every agent's tools until the user noticed; killing the daemon could interrupt work in progress. A one-line warning that names both versions and the daemon's executable lets the user restart at a moment of their choosing.

**In the code.** `GET /api/v1/daemon/status` reports `version` and `executable`; every CLI command and the shim compare it with their own build through [`infrastructure/daemon/version_skew.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/daemon/version_skew.py) and print a warning on stderr; the desktop shell shows a restart affordance. `coffer daemon restart` is the fix.

The same stance governs other mismatches Coffer can detect but not safely resolve: a database migrated by a newer build fails fast with `DB_SCHEMA_TOO_NEW` rather than guessing, and a sync bundle laid out by a newer build is refused with an upgrade message.

**Rules out.** Auto-update; auto-kill; silently running an old daemon.

## Off keeps data

**Statement.** `main` carries every capability. A feature that is not ready is declared experimental and ships switched off in a `stable` build. Switching a feature off hides it on every surface; it never deletes, migrates or rewrites its data, and switching it back on resumes where it stopped.

**Rationale.** A second release branch drifts and collides on every rebase. A runtime switch lets the owner keep testing everything while releasing only what is ready — and a switch that destroyed data would make trying a feature a one-way door.

**In the code.** [`domain/features.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/domain/features.py) registers `vault_sync`, `knowledge` and `memory` with the route prefixes and resource kinds each owns. Gates run at request time: gated routes answer `404 FEATURE_DISABLED`, the generic resource routes refuse and hide the feature's kinds, builtin tools leave `tools/list`, and workers skip their round. Kinds stay registered and migrations always run. The switch is per machine, in `~/.coffer/daemon-config.json`. See [Experimental features](/guides/experimental-features).

**Rules out.** Wiring-time gates that need a restart; a switch stored in the synced database; deleting a feature's data when it is switched off.

## Extract on second use

**Statement.** A cross-cutting module is extracted only when a second feature needs it. Code two kinds need moves to a kind-agnostic package at the layer root; code one kind needs stays inside that kind.

**Rationale.** An abstraction designed against one use case either over-fits it or is too generic to enforce anything. Waiting for the second caller means the shared shape is discovered, not guessed.

**In the code.** Shared packages exist exactly where two kinds met: [`infrastructure/net/`](https://github.com/wyx-sg/Coffer/tree/main/backend/coffer/infrastructure/net) (the SSRF guard), [`infrastructure/agent_files/`](https://github.com/wyx-sg/Coffer/tree/main/backend/coffer/infrastructure/agent_files) (transcript readers shared by agent and memory), and [`domain/connection.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/domain/connection.py). The cross-kind import contracts make any other sharing fail the build. The Resource framework is the one declared exception, described above.

**Rules out.** Speculative "common" packages; a utilities module that grows ahead of its callers; one kind importing another's services.

## How the principles fit together

The principles group into three families, and the places where they pull against each other are resolved explicitly rather than left to judgement.

| Family | Principles | What it protects |
| --- | --- | --- |
| Custody | Local-first, agent files are the source of truth, files are the truth for bulk content, off keeps data, detect never refuse | Your data and your agents keep working whatever happens to Coffer: an uninstall, a switched-off feature, a lost remote, a version skew. |
| One mechanism | Everything is a Resource, identity is a uid, reach is machine-local, reach is enforced at each kind's choke point, extract on second use | Behaviour that every kind shares is built once and cannot drift between kinds; behaviour that differs stays where it belongs. |
| Contract first | Spec as truth, secrets never plaintext at rest, pull not push | What Coffer promises, and what it will never do behind your back, is written down and checked by the build. |

Three tensions are resolved by a declared, bounded exception rather than by quietly bending a rule:

- **Local-first versus several machines.** Vault sync is allowed only as a rendezvous you own, off by default, with secrets as ciphertext. See [Local-first](#local-first).
- **Pull, not push, versus memory at session start.** The memory index is the one thing a session is handed, through a hook you install per agent, remove the same way, and see fire in the audit log. See [Pull, not push](#pull-not-push).
- **Extract on second use versus a shared resource model.** The Resource framework was designed before the second kind existed, because extracting it later would have meant re-modelling audit, routes and retention at once. See [Everything user-managed is a Resource](#everything-user-managed-is-a-resource).

When a proposal needs a fourth exception, that is the signal to amend [Principles](/architecture/principles) in its own pull request, not to add a special case in code.

## Related

- [Resource framework](/architecture/resource-framework)
- [Layering and code layout](/architecture/layering)
- [Security model](/architecture/security)
- [Decision records](/architecture/decisions)
- [Principles](/architecture/principles)
