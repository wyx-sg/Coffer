# Coffer Architecture

> Architectural snapshot of what is currently being built. The _why_ of each
> choice lives in `docs/decisions/*.md`. This file describes the system
> as scoped by the active specs in `roadmap.md`. `scripts/check_architecture_doc.py`
> keeps the code-layout tree and the builtin-tool list below level with the tree.

## Layering

```
surfaces  →  application  →  domain
                   ↓
            infrastructure
```

The import rules and the "extract cross-cutting modules only after the second
feature needs them" rule are invariants owned by
[`constitution.md`](./constitution.md); the rationale for the layer-first code
layout is in [Layer-First Code Layout](../../docs/decisions/code-layout-layer-first.md).
Enforced by `scripts/check_*.py` and importlinter contracts.

## Resource framework (kind-agnostic core)

The framework is [spec resource-framework](../../specs/resource-framework/spec.md):
the kind registry, the lifecycle surface, per-agent reach, the audit log,
per-table retention and the cross-kind read of the passes in flight. What a kind
*is* belongs to that kind's own spec. Every user-managed entity in coffer is a
**Resource** identified by `<kind>:<name>`. The framework unifies:

- Identity (`kind`, `name`, stable `<kind>:<name>` string reference)
- Lifecycle (register / update / enable / disable / delete)
- Audit (every lifecycle change recorded with actor)
- Schema validation (per-kind Pydantic schema, kind-agnostic dispatch)
- Scope (an optional activation list of agent names, `null` meaning every
  agent — framework-owned; each kind declares whether it supports scope and
  owns its enforcement point; registered-but-inactive semantics. Scope and
  `enabled` together are the resource's **reach**, and reach is machine-local:
  it is set on the machine it applies to and never converges —
  [Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md))

It does **not** unify invocation semantics. Each kind defines how its
capabilities are used; the framework only describes how a kind is registered,
described, and curated. Nor does it *enforce* reach: each kind gates at its own
choke point, where the asking identity is known.

Currently registered kinds:

| Kind             | Spec                                                         | Description                                                                                                                                                                                                                                                                                                                                                                                                            |
| ---------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mcp_server`     | [mcp-gateway](../../specs/mcp-gateway/spec.md)       | A registered upstream MCP server. Carries transport configuration, credential references, and the per-server policies the gateway needs.                                                                                                                                                                                                                                                                                  |
| `agent`          | [agent-registry](../../specs/agent-registry/spec.md) | A registered coding agent (e.g. Claude Code). Carries its config directory and the Coffer-MCP install state. The workspace amendment also surfaces the agent's own files as **read-only** facets — MCP entries (listed, with adopt-into-Coffer the one write), plugins (listed only), and directory config entries with per-child edit — all derived at read time, never stored. Coffer no longer writes into another tool's private config to remove, toggle or uninstall an entry: the plugin toggle/uninstall surface and the MCP entry remove/toggle surface are gone, and with them the `agent_plugin_toggled`, `agent_plugin_uninstalled` and `agent_mcp_entry_removed` audit events.                                                       |
| `skill`          | [skill-manager](../../specs/skill-manager/spec.md)   | A master skill bundle Coffer can deliver into one or more agents' skill directories. The workspace amendment adds an unmanaged-skill scan (adopt hand-placed skills into the master store). Delivery is decided by the skill's own `enabled` flag intersected with its agent scope and reconciled on every change to either — the agent-side follow-master-library policy this row once described is gone.                                                                                                     |
| `knowledge`      | [knowledge](../../specs/knowledge/spec.md)                 | One **collection** — a top-level folder under `~/.coffer/knowledge/` holding two lanes, `sources/` (what people contribute) and `topics/` (what curation derives and agents read). The collection is the only boundary the system knows, and it is a Resource for its lifecycle and its one switch: `enabled`, which decides whether it is served at all. It carries **no per-agent reach** — every enabled collection is catalogued into every agent's delivered skill, since the per-agent form only trimmed a skill that hands the agent the whole knowledge root anyway (spec knowledge FR-010). Nothing is derived from a cwd and nothing auto-provisions. See [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md). |
| `channel`        | [channels](../../specs/channels/spec.md)             | A messaging-channel binding (Telegram, SeaTalk). Carries transport config + credential refs and a default agent; a paired owner chats with managed agents from the IM app and receives notifications. Its per-agent scope is read INVERTED — it names the agents this channel may drive, since a channel is an inbound surface no agent consumes — narrowing `/agent` and the channel's own default agent; a channel that may drive nothing does not run. A channel DOES sync, and carries `runs_on` — the `machine_id` of the one machine whose daemon starts its adapter, so the document travels and the adapter does not (spec channels FR-026). Thin adapters over the turn-platform seams (spec chat FR-001…FR-026), which the web Chat page sits on as the second surface (spec chat FR-029…FR-041) — once a message reaches the turn orchestrator nothing downstream knows which surface it came from ([Channel Adapter Framework](../../docs/decisions/channel-adapter-framework.md), [Chat Is a Single-Owner Live Mirror](../../docs/decisions/chat-single-owner-live-mirror.md)).                                                                                              |
| `memory`         | [memory](../../specs/memory/spec.md)                 | One **partition** of aggregated agent memory — a project, or `global`. Its facts are read out of the registered agents' own native memories, never written back; everything on disk is derived and rebuildable, with no non-derived state left beside it — the per-fact hide/pin/mark-superseded/settle-a-conflict overrides went with the surface that recorded them, and the table that stored them was dropped. It carries **no per-agent reach**: an enabled partition is delivered to, and recalled by, every agent — the reach it used to default to, the agents it had been aggregated from, withheld a repository's notes from the other agent working in that same repository, which is the opposite of what aggregating is for (spec memory FR-013) ([Aggregate Agent Memory](../../docs/decisions/aggregate-agent-memory-never-write-it.md)).                                                                                              |
| `provider`       | [provider-switching](../../specs/provider-switching/spec.md) | One **model-provider profile** — a wire protocol, a base URL and one `credential_ref`. Pure config with no on-disk artifact, so it takes the framework's generic create/update path. Its per-agent scope names the agents it projects into, which is the reach this kind used to carry itself as `compatible_agents` inside its own config; `application/provider/targets.py` is the enforcement point the switch, the per-agent key lookup, the import reconcile and the boot self-heal all read. A new profile starts scoped to the agents its protocol can actually serve rather than to every agent ([Provider Switching](../../docs/decisions/provider-switching.md)). |

The knowledge layer is **a directory, not a database**, and it has two lanes.
Under `~/.coffer/knowledge/<collection>/`, `sources/` holds what a person, an
upload and `coffer__write` put there; `topics/` holds the documents an
internal-model **curation pass** derives from those sources, and is what an
agent reads. There is no `documents` table and no chunk table, so nothing has
to be reconciled and a file edited in the user's own editor is live on the very
next pass ([Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md),
which supersedes Files as Truth and Retrieval Mode Is Internal).

**Sources are the truth; topics are derived.** Deleting `topics/` and
re-running curation must reproduce a corpus carrying the same facts. That
inversion is what makes an unattended rewriter acceptable: the thing being
rewritten is no longer the only copy. It is also why the two lanes are
directories rather than a frontmatter property — "who may write here" is the
one thing a key inside a file cannot say. `.history/` and `.raw/` are gone with
the reasons they existed; an uploaded original is now an ordinary visible file
in `sources/` beside the text extracted from it.

A file's **path is its identity** — names are readable slugs, not ULIDs.
Frontmatter carries `title`, `description`, `actor` and timestamps, plus
`coffer_ingested_at` on a source: Coffer's watermark, compared against the
file's own mtime, which is how a sweep knows what curation still owes without
any state file or table. A collection describes itself in its own `README.md`
rather than in a database row, so the person browsing the folder sees the same
sentence the delivered skill does.

**Retrieval has no tool.** `coffer__list`, `grep`, `read`, `search` and
`delete` are deleted. An audit of 448 Claude Code sessions after the corpus was
built found the delivered skill had never once been loaded and no knowledge
tool had ever been called: a tool an agent does not remember to call is not
retrieval, and every agent Coffer supports already has `Read` and `Grep`, which
need no remembering. So the layer's job narrows to putting the right absolute
paths in front of the model. Ripgrep survives inside the process as the
candidate selector a curation pass uses (`infrastructure/knowledge/grep.py`,
with an identical Python walk in `grep_fallback.py` where `rg` is absent), not
as anything a caller can reach.

**Coffer embeds nothing.** Ranked semantic retrieval over a disposable vector
sidecar was built, shipped and then deliberately removed (2026-09-14); the
`~/.coffer/index` directory, the `/embeddings` client and every trace of an
embedding setting are gone. What replaces conceptual recall is the model
reading a catalogue, which works while the catalogue fits in context — into the
hundreds of files. Literal matching is a **placeholder**, not a verdict, and
semantic retrieval is expected back
([Product Scope Is Settled](../../docs/decisions/product-scope-is-settled.md)).

The layer contributes **one** builtin tool, `coffer__write` (see
[Builtin tools](#builtin-tools)), because writing is where an agent genuinely
needs Coffer: the collection, the lane, the frontmatter and the audit entry are
Coffer's to decide. Everything else rides a **generated skill**, written per
agent into `<config_dir>/skills/coffer-knowledge/SKILL.md` as real bytes rather
than a link into one shared master. Its frontmatter description names the
subjects the agent's collections cover — the only part of this layer always in
a model's context — and its body carries the absolute knowledge root and every
topic document's path, title and description. Per-agent authorization is
enforced **there**: a collection an agent is not activated for is never named,
so it is non-disclosure rather than a refusal after the fact. Nothing is
injected into a session and no agent's own memory is written to
([Aggregate Agent Memory](../../docs/decisions/aggregate-agent-memory-never-write-it.md)).

The **curation** pass is a bounded agentic rewrite of one collection's
`topics/`, driven by the internal-engine connection. One pass sees one source
in full, at most five candidate documents, and the collection's whole catalogue
of titles; it may write at most eight files, may not reach `sources/` at all,
and may not record a reference to another knowledge file — that last is
enforced at the write, because 343 of the corpus's 398 internal references were
already dead when the rule was introduced. It is triggerable by hand (the UI,
and `coffer knowledge curate`); the interval worker is governed by one
installation-wide setting on `internal_engine_config` that names an owner
machine and, unlike the tidy pass it replaces, defaults **on** — it is the only
path from a source to something an agent can read.

Putting a Markdown file in `sources/` stays a complete way to add knowledge —
no import, no registration, and the next sweep folds it in. Ingestion is a
second entrance, for where the filesystem is out of reach: a document uploaded
from the Knowledge page or forwarded to a channel is converted by `markitdown`
and lands in `sources/` beside its own original. Upload is a human surface, not
an agent tool.

## Builtin tools

The daemon registers **three** builtin tools in one in-process
`BuiltinToolRegistry` (`application/builtin_tools.py`). Each is declared as a
`BuiltinTool(name=…)` by the slice that owns it, stored unprefixed, and listed
by the gateway under the `coffer__` prefix. One more, `coffer__search_tools`,
is the gateway's own: it is answered in `application/mcp/gateway_builtin.py`
without passing through the registry.

| Slice       | Tools                                                                                                     | Declared in                                                                |
| ----------- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| knowledge   | `coffer__write`                                                                                           | `application/knowledge/builtin_tools.py`                                   |
| memory      | `coffer__recall`                                                                                          | `application/memory/builtin_recall_tool.py`                                |
| skill       | `coffer__list_skills`, `coffer__load_skill`                                                               | `application/skill/builtin_tools.py`                                       |
| diagnostics | `coffer__diagnose`                                                                                        | `application/diagnostics.py`                                               |
| gateway     | `coffer__search_tools` ([Tool Retrieval](../../docs/decisions/tool-retrieval-for-overload.md))            | `application/mcp/gateway_builtin.py`                                       |

The gateway threads the session's handshake identity into every builtin call
as the `agent` argument the knowledge and memory tools authorize by; no tool
advertises that argument, and a value a client supplies is overwritten (spec mcp-gateway FR-013).

## Code layout

Layer-first, with kind-specific subdirectories inside each layer. See
[Layer-First Code Layout](../../docs/decisions/code-layout-layer-first.md).

```
backend/coffer/
├── domain/                       # kind-agnostic entities + kind protocol; imports nothing
│   ├── resource.py               # Resource, Kind, ResourceRef
│   ├── scope.py                  # is_active(scope, agent) — the one reach predicate
│   ├── audit.py                  # audit event names + entry
│   ├── errors.py                 # app-wide error base + codes
│   ├── mcp/                      # MCP-specific value objects, tool search + tiering
│   ├── agent/                    # agent-specific value objects (config, facets, model catalogue)
│   ├── skill/                    # skill-specific value objects
│   ├── knowledge/                # catalogue + file value objects, errors
│   ├── channel/                  # channel config, envelopes, seatalk signing
│   ├── chat/                     # conversation, message, attachment, turn events
│   ├── memory/                   # fact, partition, budget, delivery, reader protocol
│   ├── provider/                 # provider config, modality, projection rules
│   └── sync/                     # manifest, models, diff, convergence + machine rules
├── application/
│   ├── resource_service.py       # kind-agnostic CRUD; reads app.state.kinds
│   ├── audit_service.py
│   ├── retention_service.py      # + retention_registry.py, retention_worker.py
│   ├── builtin_tools.py          # BuiltinTool + BuiltinToolRegistry
│   ├── diagnostics.py            # coffer__diagnose
│   ├── credentials/              # shared CredentialResolver (refs → secrets)
│   ├── mcp/                      # gateway, supervisor, discovery, search_tools + make_mcp_kind
│   ├── agent/                    # agent services + make_agent_kind
│   ├── skill/                    # skill services, list_skills/load_skill + make_skill_kind
│   ├── knowledge/                # one service, one tool, curation, skill rendering + make_knowledge_kind
│   ├── channel/                  # adapter protocol, pairing, inbound, runtime + make_channel_kind
│   ├── chat/                     # turn orchestrator, runner, state, conversation service
│   ├── memory/                   # aggregate, digest, delivery, recall + make_memory_kind
│   ├── provider/                 # provider service, projection, reconcile + make_provider_kind
│   ├── engine/                   # which connection Coffer's own unattended passes run on; must not import the provider kind
│   ├── sync/                     # converge round, exporter, appliers, worker, ports
│   └── fs/                       # filesystem browse / pick / open / editor services
├── infrastructure/
│   ├── persistence/              # SQLAlchemy + Alembic (central metadata)
│   ├── credentials/              # encrypted credential store + master key — only place importing `keyring`
│   ├── daemon/                   # pid_lock, port allocation, child processes, version skew
│   ├── mcp/                      # subprocess, http upstream client
│   ├── net/                      # SSRF guard for outbound HTTP
│   ├── logging/                  # structlog setup, log files, eval capture
│   ├── llm/                      # LangChain models, completion, transcription
│   ├── agent/                    # agent config-file store
│   ├── agent_files/              # kind-agnostic readers of an agent's own on-disk files (transcripts) shared by agent + memory
│   ├── skill/                    # master store, sync engine
│   ├── knowledge/                # paths, file tree, frontmatter, ripgrep + Python fallback
│   ├── channel/                  # telegram/seatalk transports (incl. the SeaTalk websocket connector and its operator-supplied SDK loader), cloudflared supervision, peer repo, render
│   ├── chat/                     # Claude SDK / Codex adapters, persistence, document extraction
│   ├── memory/                   # native-memory readers, store, delivery state
│   ├── provider/                 # provider introspector
│   └── sync/                     # git mirror, tree mirror, bundle, machine id
└── surfaces/
    ├── http/                     # FastAPI app, composition root, per-kind routers + `*_wiring.py`
    │   ├── chat/                 # conversation + turn routes
    │   ├── knowledge/            # knowledge routes
    │   ├── mcp/                  # MCP protocol endpoint, capability + invocation routes
    │   └── memory/               # memory routes
    ├── cli/                      # Typer app + per-kind subcommand groups
    ├── shim/                     # coffer-mcp-shim entry
    └── callback/                 # channel callback listener (separate process)
```

Composition root (`surfaces/http/app.py`, `surfaces/cli/main.py`) explicitly
wires each of the seven kinds — no global registry, no import side effects.
Each kind's `make_*_kind()` factory (`make_mcp_kind`, `make_agent_kind`,
`make_skill_kind`, `make_knowledge_kind`, `make_channel_kind`,
`make_provider_kind`, `make_memory_kind`) returns a frozen `Kind`
(`domain/resource.py`), and the composition root populates the per-app
`app.state.kinds` dict (`kind_name → Kind`) directly: `app_mcp_composition.py`
sets `"mcp_server"`, `agent_skill_wiring.py` sets `"agent"` and `"skill"`,
`knowledge_wiring.py` sets `"knowledge"`, `channel_wiring.py` sets
`"channel"`, `provider_wiring.py` sets `"provider"` and `memory_wiring.py`
sets `"memory"`. `ResourceService` reads that dict for kind-agnostic dispatch.
The surface-layer artefacts a kind contributes (HTTP routers, Typer groups)
are registered by those same wiring modules; there is no carrier object for
them, and nothing in `domain/` knows they exist.

FastAPI dependency providers (`surfaces/http/dependencies.py`) are plain
module-level `set_*` / `get_*` pairs over module-global singletons — the
composition root calls each `set_*` once at startup; the matching `get_*` is
the `Depends()` target and raises if accessed before initialisation. Kind-
specific services are typed `Any` there to keep the kind-agnostic core from
importing kind modules (Contract 6).

## Surfaces

| Surface                        | Process                | Role                                                                                                         |
| ------------------------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------ |
| REST API                       | daemon                 | Management plane: `/api/v1/*`. Token authenticated; same-origin by default (`COFFER_DEV_CORS` opts the Vite dev origins in). |
| Web UI                         | daemon                 | The built frontend, served by the daemon as static files at its own loopback origin — same-origin with the API. The daemon injects its live API token into the `index.html` it serves (`window.__COFFER_TOKEN__`, every SPA route, `no-store`), so any page it serves is authenticated with nothing persisted; `coffer open` only resolves the daemon's current port and opens the browser there. The served token is what makes the loopback-`Host` check mandatory (spec daemon FR-016 / FR-017 / FR-015, [The Daemon Serves Its Token in the Page](../../docs/decisions/daemon-serves-the-token-in-the-page.md)). |
| Desktop shell                  | `desktop/` (Tauri 2, Rust) | The same `frontend/dist`, hosted as a **local asset** in a native window with a Dock icon and a resident tray — so the UI renders before the daemon answers and the port never reaches an address bar. Because nobody served that document, spec daemon FR-017's injection cannot reach it: the shell hands the page the same two globals over an IPC command before first render, making it a second credential *supplier* and not a second code path. It also owns detect-or-spawn at launch (live `daemon.json` → bundle → `~/.coffer/bin/` → `PATH`, liveness first so it attaches rather than races), a rate-limited restart reachable from the tray and the offline banner, and a version-skew check. It deliberately owns nothing else — file actions stay on the daemon's HTTP routes, and binary deployment stays in spec daemon FR-027 (spec desktop-app FR-001 – FR-011, [The Desktop Shell Returns](../../docs/decisions/desktop-shell-over-a-shared-frontend.md)). |
| MCP protocol                   | daemon                 | `/mcp` HTTP/SSE endpoint speaking MCP JSON-RPC.                                                              |
| CLI (`coffer …`)               | short-lived child      | Calls daemon over loopback HTTP. Every command compares the daemon's reported `version` with its own build and prints a one-line warning on stderr on skew, naming the daemon's `executable` — detection, never refusal (spec daemon FR-027, [Detect-or-Spawn](../../docs/decisions/daemon-detect-or-spawn.md)). |
| Stdio shim (`coffer-mcp-shim`) | per MCP-client session | `stdin/stdout ↔ daemon HTTP/SSE` forwarder; detect-or-spawn daemon, with the same version-skew warning on its status probe. |
| Callback listener              | daemon-spawned child   | Signed channel webhooks only (`POST /seatalk/{channel}`); loopback port behind a tunnel. Runs only for SeaTalk channels on **webhook** delivery (spec channels/seatalk FR-004). |
| Managed tunnel (`cloudflared`) | daemon-spawned child   | One per webhook SeaTalk channel that records a Cloudflare connector token; terminates that channel's public callback URL so the owner need not run a tunnel by hand. |
| SeaTalk websocket connection   | thread inside daemon   | One outbound connection per SeaTalk channel on **websocket** delivery — no listening socket, no tunnel, nothing exposed; events land on the same ingest seam the listener forwards to (spec channels/seatalk FR-002/FR-004). |

## Processes

- **`coffer-daemon`** — long-lived FastAPI service on `127.0.0.1:<port>` — the
  port the user fixed in `~/.coffer/daemon-config.json`, else the first free one
  in 8000–8009. Owns all state; single SQLite writer. `GET /api/v1/daemon/status`
  reports its `version` and `executable`, and a frozen build deploys its sibling
  binaries into `~/.coffer/bin/<version>/` at start, flipping the public
  `~/.coffer/bin/<name>` symlinks onto that directory atomically and keeping the
  previous version's directory for a rollback (spec daemon FR-027,
  [PyInstaller Distribution](../../docs/decisions/distribution-pyinstaller.md)).
- **Stdio shim** — short-lived; lifecycle bound to one MCP client process.
- **Callback listener** — daemon-spawned child serving only signed channel
  callback paths on `127.0.0.1:<callback-port>`; runs while any SeaTalk
  channel on **webhook** delivery is enabled (spec channels, [Channel Adapter Framework](../../docs/decisions/channel-adapter-framework.md)).
- **`cloudflared`** — daemon-spawned child, one per webhook SeaTalk channel that
  records a connector token; the token reaches it through a `0600` temp file, never
  argv, and the spawn is recorded in the upstream-pids directory so the startup
  orphan sweep reaps it after a crash.
- **No process for websocket delivery.** A SeaTalk channel on websocket delivery
  is supervised *inside* the daemon — a worker thread holding one outbound
  connection, reconciled like a tunnel is, backing off on failure and on being
  kicked by another registration of the same app. It needs no separate process
  because it exposes nothing: the constitution's separate-process rule guards
  publicly reachable surfaces, and this one is a socket only this machine opened
  ([SeaTalk Inbound Over WebSocket](../../docs/decisions/seatalk-websocket-inbound.md)).

The shim and the listener discover the daemon through `~/.coffer/daemon.json`
(PID + port + token, mode `0600`) — runtime state, written at start and unlinked at exit.
Its counterpart `~/.coffer/daemon-config.json` holds the settings the daemon
must read *before* it binds, and therefore before any database exists: today,
the optional fixed port and the cached machine id. See [Detect-or-Spawn](../../docs/decisions/daemon-detect-or-spawn.md).

## Persistence

- **SQLite** at `~/.coffer/coffer.db`, WAL mode, single writer.
- **SQLAlchemy 2.0 async** ORM; **Alembic** central migrations (all kinds
  register their ORM models against one metadata). Migrations run on daemon
  startup (`upgrade head`); if the DB's current revision is unknown to the
  running build (created by a newer/divergent version), startup fails fast
  with `DB_SCHEMA_TOO_NEW` instead of an opaque Alembic error. Before
  `upgrade head` changes an on-disk database, the daemon copies it (with its
  `-wal`/`-shm` companions) to `coffer.db.pre-<revision>`, keeping the three
  newest copies (`surfaces/http/migrations_runner.py`, spec daemon FR-027).
- JSON fields stored as `TEXT` validated by Pydantic at the application
  boundary.
- **The knowledge layer owns no table at all.** A collection is a row in the
  kind-agnostic `resources` table like every other Resource, and its contents
  are files. The eleven tables the indexed layer used — `documents`, `chunks`,
  the six `documents_fts*` tables, `embedding_config` and the two scope side
  tables — were dropped by migration 0066, and nothing has replaced them
  ([Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)).
- The database file plus daemon discovery file, logs, the knowledge file tree,
  and per-upstream PID files all live under `~/.coffer/` for a single backup
  target.

## Cross-cutting concerns

| Concern           | Location                                                                                         | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Credentials       | `infrastructure/credentials/` (`encrypted_store.py`, `master_key.py`, `keyring_adapter.py`)      | Spec credentials. Secrets stored only as Fernet ciphertext in the `credentials` table; the master key (`0600` file by default, OS keychain opt-in) and legacy migration are the sole `keyring` users. The **daemon is the sole credential-store owner**: every surface (web UI, CLI, shim) reaches secrets through the daemon's `/api/v1/credentials` routes and toggles master-key storage via `/api/v1/settings/credentials` — the CLI never touches the store in-process ([Envelope-Encrypted Credentials](../../docs/decisions/envelope-encrypted-credential-store.md)). Refs in config; materialized (decrypted) at upstream-spawn time; plaintext never persisted. |
| Audit             | `domain/audit.py` + `application/audit_service.py` + `audit_log` table                           | Every resource lifecycle change. Actor (cli / api / ui / system) required. Owned by spec resource-framework; every kind contributes its own event types to one shared vocabulary.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Retention         | `application/retention_service.py` + `retention_policies` table + asyncio worker                 | Each log-style table registers as a `PrunableTable`; central registry enforces SQL allowlist. Owned by spec resource-framework.                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Errors            | `domain/errors.py` + FastAPI global handlers                                                     | Uniform `{error: {code, message, details}}` envelope; `X-Coffer-Trace` header for correlation.                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Logging           | `structlog` JSON-per-line to `~/.coffer/logs/`                                                   | Per-request trace IDs via contextvar.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Document extraction | `DocumentExtractor` port + `infrastructure/chat/document_extract.py`                           | The only place importing a converter library (MarkItDown, imported lazily and optional). It serves **inbound channel attachments** (spec channels FR-030): a PDF or docx reaches the agent as extracted text rather than an opaque path, degrading to a file attachment when the library or the extraction fails. The knowledge layer converts through the same library on its own upload path, landing both the extracted Markdown and the original in `sources/` ([Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)).                                                                                                                                                                                                                                                                                                                                                                                                  |
| Sync              | `application/sync/` + `infrastructure/sync/` + CLI and HTTP surfaces | Convergence with **one user-owned git remote** (spec vault-sync, [Vault Sync](../../docs/decisions/vault-sync.md), constitution 0.6.0). A worker shaped like `RetentionWorker` runs a **converge round**: serialize the vault differentially into the git working tree and commit it as `L`, merge `origin/<branch>` into `L` giving `M`, apply the diff `L..M` back into the vault path by path — deletions included — then push and advance the **pointer**, the local-only record of the commit this vault provably absorbed and the base of every diff. Paths that fail to apply join a **retry set** the exporter must not delete, so a pending document is never published as a deletion; a machine with no pointer is joining, and the registry tells a new one (pointer := git's empty tree, so the diff can only add) from a returning one (pointer := the commit its descriptor names). Applying a diff writes knowledge and skill files, upserts resource documents through the resource service with `${HOME}` expanded and the kind's import gate run, hands `state/<area>/**` to its owning module, and re-runs each kind's post-import hook. Git's three-way merge arbitrates — credential blobs are ordered by encryption time instead, an unresolved conflict aborts the round untouched — under a pre-apply snapshot tag and a circuit breaker that holds an oversized deletion for confirmation in both directions. Each machine writes one `machines/<machine_id>.yaml` it alone owns, so the registry is a derived view of the tree rather than a synced table; `machine_id` is derived from the host and hashed before it travels, so a reinstall leaves no ghost. The one-shot export-to-a-directory and import-of-one-back surfaces are **deleted** — a wholesale overwrite with no base has no place beside the diff-based apply. Cross-cutting, not a kind. A resource document carries identity, description and config alone: a resource's **reach** — its `enabled` flag and its agent `scope` — is machine-local and never converges, so an import leaves the local reach exactly as this machine set it, and a newly arrived resource lands at this machine's own default ([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)). Every kind is serialized, `channel` included: a channel carries the one machine whose daemon runs its adapter inside its own config, so the document converges while the adapter stays put (spec channels FR-026). Channel peer pairings are a synced state area again for the same reason — a channel that travelled without them would make the owner re-pair on every rebind — carrying platform identity only, never this machine's conversation pointer. |
