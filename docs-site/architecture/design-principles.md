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
| [Pull, not push](#pull-not-push) | Coffer puts paths and a catalogue in front of the agent and puts nothing into a session; memory reaches an agent only as files in its own memory, which you can see and undo. |
| [Reach is machine-local](#reach-is-machine-local) | Whether a resource is enabled, and for which agents, is decided on the machine it applies to. |
| [Each kind enforces reach at its own choke point](#each-kind-enforces-reach-at-its-own-choke-point) | One predicate, many enforcement points, no central gate. |
| [Secrets are never plaintext at rest](#secrets-are-never-plaintext-at-rest) | Fernet ciphertext files in the vault, refs everywhere else. |
| [Detect, never refuse](#detect-never-refuse) | On version skew, say so and carry on. |
| [Off keeps data](#off-keeps-data) | Switching a feature off hides it; it never deletes anything. |
| [Extract on second use](#extract-on-second-use) | A shared module is created when the second feature needs it, not before. |

## Local-first

**Statement.** Everything Coffer holds lives on your machines, and each machine holds the full vault. Cloud services are model and tool providers only; none of them is ever the system of record for vault state. The HTTP API binds to `127.0.0.1`.

**Rationale.** The assets Coffer holds — API keys, private notes, everything your agents have learned about your environment — are exactly the assets you would not hand to a third party. A local store also has no availability dependency: an agent's first tool call of the day does not wait on anyone's service.

**The bounded exception.** Coffer can sync the vault with a git remote *you* own, so your own machines hold one vault rather than several. The exception holds only while three conditions all hold:

1. **The remote is a rendezvous, never a system of record.** Every machine's local vault stays authoritative and complete, so the remote can be deleted and rebuilt from any one machine.
2. **Secrets travel as ciphertext only.** The master key leaves a machine only through an explicit out-of-band transfer: a key backup the desktop app writes behind a presence check, installed on the other machine from **Settings › Security › Import a master key**.
3. **It is off by default** and pointed only at a repository you configure.

Sync is bidirectional but only under the sync spec's safety rules: git computes the merge outside the vault, only a clean merge is applied, any conflict stops the round for you with nothing changed, a round that would lose too much stops and asks, and every round can be rolled back from its snapshot.

**In the code.** The daemon binds `127.0.0.1` when it allocates its port. Channels reach Telegram and SeaTalk only over connections the daemon opens, so the loopback socket is the only one Coffer listens on. The sync remote defaults to absent, and secret ciphertext is carried only when you set `--with-secrets`.

**Rules out.** A hosted Coffer endpoint; a "Coffer cloud" account; any design where losing the remote loses data; a sync that overwrites a vault wholesale; replicating vault state to a vendor-controlled service.

## Spec as truth

**Statement.** The specs under `openspec/specs/<capability>/spec.md` are the product contract. A change to externally visible behaviour starts as an OpenSpec change under `openspec/changes/<id>/`, lands together with the code that makes it true, and is archived into the specs. If the code disagrees with the spec, the code is wrong.

**Rationale.** Coffer is developed by people and AI coding agents together. An agent is only as good as the contract it can read, and a contract that lives in a PR description or a chat log is gone the moment the session ends. A spec that is enforced by the build is a contract every future contributor — human or agent — can rely on.

**In the code.** Every requirement must own at least one scenario (`openspec validate --strict`), and every scenario must be covered by a test that carries an `acceptance` marker (an acceptance-audit gate checks this). The wire contract runs in one direction: the backend's Pydantic models are the only hand-written description of the wire, the generator writes each spec's `contracts/api.openapi.yaml` from them so a wire change shows up as a reviewed diff, and the frontend's typed client and wire types are generated from that file. No wire type is written by hand on either side, so the compiler compares types where a gate over two hand-written documents could only compare names. A citation of a requirement by title is checked by a spec-citation gate.

**Rules out.** Behaviour that exists only in code; "documentation" specs that describe intent rather than obligation; a wire shape the contract does not declare. See [Spec-driven workflow](/contributing/spec-workflow).

## Everything user-managed is a Resource

**Statement.** Every entity you manage — an MCP server, an agent, a skill, a knowledge collection, a channel, a model provider — is a **Resource** of some **kind**. The framework unifies identity, lifecycle, audit, schema validation and reach. It does not unify behaviour: how an MCP server is invoked and how a skill is delivered stay entirely inside their kinds.

**Rationale.** Every kind needs the same things: to be named, listed, edited, enabled, disabled, deleted, audited and scoped. Building those six times is more code and six chances to drift. But a framework that tried to own behaviour too — one invoke operation for everything — would be a leaky abstraction over things that have nothing in common.

**In the code.** One immutable kind descriptor per kind, one kind-agnostic resource service, one JSON file per resource in the vault (`resources/<kind>/<name>.json`), one `/api/v1/resources` router, one `audit_log`. The kind-agnostic core is tested against a fake kind and an import contract forbids it from importing any real one. See [Resource framework](/architecture/resource-framework).

**Rules out.** A generic invoke operation; a third-party plugin system (a plugin contract needs several concrete implementations to design against, and Coffer serves one user); per-kind CRUD, audit or scope implementations.

## Identity is an immutable uid

**Statement.** A resource's identity is its `uid`: an opaque random (version 4) UUID written as 32 hex characters, minted once at creation, never reused, and the same value on every machine that holds the resource. The `name` is a label, unique within its kind, and mutable unless agents quote it: an MCP server's name (the prefix of every tool name) and a skill's name (the folder an agent loads it from) are fixed once registered, and an agent's name is its type (one agent per type). The kinds whose name is a label a person chose — providers and channels — also carry an optional `title` for display. The uid is written inside the resource's own file, so the file's path and name are only its location and label; there is no integer surrogate key.

**Rationale.** Once a vault syncs across machines, the question an identifier must answer is "is the thing on that machine the same thing as the thing on this one?" A name cannot answer it, because a name is exactly what you are allowed to change: a rename would cross the sync remote as a deletion plus a creation, cascading away everything attached to the old row. An autoincrement row number cannot answer it either, because two machines allocate the same number to different resources.

**In the code.** `/api/v1/resources/{uid}` addresses every resource; a resource `scope` and a channel's `default_agent` hold agent uids; the vault files each resource as `resources/<kind>/<name>.json` with its uid inside, so a moved or renamed file is still the same resource; rename is an ordinary field on `PATCH`, refused with `409 NAME_IMMUTABLE` for a kind that declares its names fixed, and `title` is editable on the kinds that carry one. The CLI still takes names and resolves them to uids itself, so nobody types a UUID.

**Rules out.** `<kind>:<name>` identifiers; cross-resource references by name; per-kind rename endpoints; keying anything on a file's path.

## Agent files are the source of truth

**Statement.** An agent's own files are the source of truth for that agent. Coffer reads config files, MCP entries, plugins, native memory and transcripts where the agent keeps them, at read time, and never copies them into SQLite. It writes only an agent's documented surfaces, addressed by an allowlist, atomically and with a backup copy in Coffer's own folder.

**Rationale.** A copy of someone else's state drifts the moment they change it, and the agent changes its own state constantly. Deriving at read time means Coffer is never wrong about what the agent has, and uninstalling Coffer leaves every agent exactly as functional as before.

**In the code.** The `agent` kind stores only a config directory and install state; everything else is read from the agent's own files by the agent adapters in the infrastructure layer (the `infrastructure/agent/` and `infrastructure/agent_files/` packages). Codex TOML is edited with `tomlkit` so comments and ordering survive. An agent's internal state (for example Claude Code's `installed_plugins.json`) is only read; a change that must reach it is delegated to the agent's own CLI. The memory layer reads each agent's native memory and never changes what the agent wrote; it adds only files of its own beside it, which it records and can remove. See [Memory](/architecture/memory).

**Rules out.** Mirroring an agent's config into Coffer's own store; editing or deleting a memory an agent wrote; editing undocumented internal files; any change an agent could not survive Coffer being removed.

## Files are the truth for bulk content

**Statement.** The vault's files are the system of record for configuration, and `runs.db` for history. Bulk user content — knowledge collections and the memory hub — is plain Markdown on disk, and those files are the only copy: nothing indexes, chunks or embeds them.

**Rationale.** A derived index has to be reconciled with its source, and every reconciliation is a place to be wrong. Plain files are live the moment you save them in your own editor, readable by every agent's own `Read` and `Grep`, diffable in git, and survive Coffer entirely. Measured usage showed agents never reached for a retrieval tool they had to remember to call, while they read files constantly.

**In the code.** The knowledge layer owns no table: a collection is a resource file plus a directory. Retrieval is the agent's own file tools against absolute paths; An import contract bans vector-store and embedding libraries from the codebase. See [Knowledge](/architecture/knowledge) and [Knowledge Is Plain Files](https://github.com/wyx-sg/Coffer/blob/main/docs/decisions/knowledge-is-plain-files.md).

**Rules out.** A documents table; FTS or vector indexes; an embedding sidecar; a second copy of a document in any other store. Literal matching is a placeholder rather than a verdict: semantic retrieval may return, but not as a copy of the files.

## Pull, not push

**Statement.** Coffer puts nothing into an agent's session. It puts the right paths and a catalogue in front of the model and lets the model read what it needs. The catalogue is a skill: Coffer's own `coffer-guide`, whose resident description names Coffer, its builtin tools and the subjects your knowledge covers, and whose body carries the manual and every knowledge document's path, title and description.

**Rationale.** Anything in the MCP handshake or a session-start hook is charged to every session whether or not it is needed. A skill has the opposite cost structure: its short description is always in context, its body costs nothing until a model opens it. So the resident budget is spent once, on one description a model can match against.

**In the code.** The gateway's handshake `instructions` are capped at 800 characters: what Coffer is, the builtin tool names, the per-session count of hidden upstream tools, and a pointer to the skill. `coffer-guide` is an ordinary `skill` resource rendered by the knowledge layer and delivered by the skill kind. Coffer installs no hook and appends nothing to a turn. Memory reaches an agent as files in the agent's own memory, which the agent loads the way it loads its own: Coffer's memory sync writes only its own copies and one marked block, backs up what it changes, shows a first or large sync as a preview, audits every sync and offers a one-click undo.

**Rules out.** Hooks or context injected into a session; changing a memory an agent wrote; writing into an agent's memory without a record, a preview and an undo; a catalogue spread across several always-resident skills.

## Reach is machine-local

**Statement.** A resource's **reach** is its `enabled` flag together with its agent `scope`. Reach is set on the machine it applies to and never syncs: the vault carries what a resource *is* and how it is configured, never what it reaches.

**Rationale.** A synced reach would be set from wherever you happen to sit, about machines you cannot see, and two machines editing it would put a permission through a text merge where whichever round ran last silently decides what the other machine exposes. A machine-local reach has nothing to merge and can always be verified where it takes effect. The cost is honest: a resource arriving on a machine for the first time starts at that kind's default reach there.

**In the code.** Reach is stored in `~/.coffer/local/reach.json`, outside the vault repository, so it cannot be committed or pushed at all; the resource file holds no `enabled` or `scope`. The experimental-feature switches live in `~/.coffer/daemon-config.json` for the same reason. Surfaces say so where reach is set: each kind's scope control states that the scope applies to this machine only.

**Rules out.** Machine ids inside a scope; a "newest write wins" reach; any permission that changes because another machine's round ran.

## Each kind enforces reach at its own choke point

**Statement.** The framework stores reach; each kind enforces it where the asking identity is known. Every enforcement point asks the same question of the same predicate in the domain layer: given a resource's scope and the asking agent's uid, is the resource active for that agent?

**Rationale.** A central gate would have to sit on every kind's read path and know every kind's notion of "use". The gateway already knows which agent is asking for tools; skill delivery already iterates agents; the provider projection already knows which config file it is writing. Putting the check there costs one function call and no new machinery.

**In the code.** `mcp_server` filters in the gateway, `skill` in delivery reconciliation, `provider` where the provider projection chooses which agent config files to write, and `channel` — whose scope is inverted to name the agents it may *drive* — in its agent routing and its runtime. An unidentified session matches only an unrestricted scope, so it sees strictly less, never more. See the [kinds table](/architecture/resource-framework#the-six-kinds).

**Rules out.** A reach evaluator object; a deny-list (a new agent would silently gain access); a kind inventing its own "which agents" field.

## Secrets are never plaintext at rest

**Statement.** Secrets live only as Fernet ciphertext, one file per secret under `~/.coffer/vault/secret/`. Plaintext exists in memory solely between decrypt and the spawn or header injection that consumes it, and never reaches a file, logs, audit or any structured event. All other code holds secret **refs**. The master key is managed only by the secret module in the infrastructure layer — one item in the macOS Keychain, in an access group only Coffer's signed binaries can read — and that module is the only importer of `keyring`.

**Rationale.** Envelope encryption puts one key in the Keychain for any number of secrets, so vault sync can still carry ciphertext, while a copy of `~/.coffer/` holds only ciphertext without its key. Refs make every config document safe to audit, sync and display.

**In the code.** An import contract confines `keyring`; another stops the CLI from importing the secret store at all, so the daemon is the single reader of the key. The MCP server schema rejects static `env` and header values that look like tokens. Kinds supply an audit redactor so config written to the audit log carries no secret-bearing maps. See [Security model](/architecture/security).

**Rules out.** Secrets in resource config; the CLI decrypting in-process; the master key inside anything the vault publishes; a setting that moves the master key out of the Keychain.

## Detect, never refuse

**Statement.** When a client finds a daemon from a different build, it says so and carries on. It never refuses to work and never kills or upgrades the running daemon on its own.

**Rationale.** The daemon outlives the CLI and shim processes that attach to it, so version skew is a normal state right after an upgrade. Refusing would break every agent's tools until the user noticed; killing the daemon could interrupt work in progress. A one-line warning that names both versions and the daemon's executable lets the user restart at a moment of their choosing.

**In the code.** `GET /api/v1/daemon/status` reports `version` and `executable`; every CLI command and the shim compare it with their own build through one shared version-skew check and print a warning on stderr; the desktop shell shows a restart affordance. `coffer daemon restart` is the fix.

The same stance governs other mismatches Coffer can detect but not safely resolve: a database migrated by a newer build fails fast with `DB_SCHEMA_TOO_NEW` rather than guessing, and a sync remote laid out by a newer build is refused with an upgrade message.

**Rules out.** Auto-update; auto-kill; silently running an old daemon.

## Off keeps data

**Statement.** `main` carries every capability. A feature that is not ready is declared experimental and ships in the same build as everything else, switched off until you switch it on. Switching a feature off hides it on every surface; it never deletes, migrates or rewrites its data, and switching it back on resumes where it stopped.

**Rationale.** A second release branch drifts and collides on every rebase. A runtime switch lets the owner keep testing everything while releasing only what is ready — and a switch that destroyed data would make trying a feature a one-way door.

**In the code.** A registry in the domain layer records each experimental feature with the route prefixes and resource kinds it owns; it holds two entries today, `knowledge` and `memory`. Vault sync and model providers began there as `sync` and `models` and have graduated: they are always on, with no switch. A feature never hard-depends on another: a surface that would show two features simply leaves out the part of the one that is off. A switched-off feature looks absent in the UI, with no notice in its place. Gates run at request time: gated routes answer `404 FEATURE_DISABLED`, the generic resource routes refuse and hide the feature's kinds, builtin tools leave `tools/list`, and workers skip their round. Kinds stay registered and migrations always run. Every feature is off by default in every build, and the switch is per machine, in `~/.coffer/daemon-config.json`. See [Experimental features](/guides/experimental-features).

**Rules out.** Wiring-time gates that need a restart; a switch stored in the synced vault; deleting a feature's data when it is switched off.

## Extract on second use

**Statement.** A cross-cutting module is extracted only when a second feature needs it. Code two kinds need moves to a kind-agnostic package at the layer root; code one kind needs stays inside that kind.

**Rationale.** An abstraction designed against one use case either over-fits it or is too generic to enforce anything. Waiting for the second caller means the shared shape is discovered, not guessed.

**In the code.** Shared packages exist exactly where two kinds met: `infrastructure/net/` (the SSRF guard) and `infrastructure/agent_files/` (transcript readers shared by agent and memory). The cross-kind import contracts make any other sharing fail the build.

**Rules out.** Speculative "common" packages; a utilities module that grows ahead of its callers; one kind importing another's services.

## How the principles fit together

The principles group into three families, and the places where they pull against each other are resolved explicitly rather than left to judgement.

| Family | Principles | What it protects |
| --- | --- | --- |
| Custody | Local-first, agent files are the source of truth, files are the truth for bulk content, off keeps data, detect never refuse | Your data and your agents keep working whatever happens to Coffer: an uninstall, a switched-off feature, a lost remote, a version skew. |
| One mechanism | Everything is a Resource, identity is a uid, reach is machine-local, reach is enforced at each kind's choke point, extract on second use | Behaviour that every kind shares is built once and cannot drift between kinds; behaviour that differs stays where it belongs. |
| Contract first | Spec as truth, secrets never plaintext at rest, pull not push | What Coffer promises, and what it will never do behind your back, is written down and checked by the build. |

Two tensions are resolved by a declared, bounded exception rather than by quietly bending a rule:

- **Local-first versus several machines.** Vault sync is allowed only as a rendezvous you own, off by default, with secrets as ciphertext. See [Local-first](#local-first).
- **Pull, not push, versus memory sync.** Memory is the one thing Coffer writes into an agent's own files unasked: only its own copies and one marked block, recorded per sync in the audit log, previewed when first or large, and removed by one undo. See [Pull, not push](#pull-not-push).

When a proposal needs a third exception, that is the signal to amend [Principles](/architecture/principles) in its own pull request, not to add a special case in code.

## Related

- [Resource framework](/architecture/resource-framework)
- [Layering and code layout](/architecture/layering)
- [Security model](/architecture/security)
- [Decision records](/architecture/decisions)
- [Principles](/architecture/principles)
