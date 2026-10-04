# Stack — Python Backend

Coffer's backend is Python 3.12+.

## Backend — Python / FastAPI / SQLite

### Languages & Versions

- **Python 3.12+**
- **FastAPI** for HTTP surface
- **Pydantic v2** for models + validation
- **SQLite** via **SQLAlchemy 2 (async)** + **`aiosqlite`** (the only access path to `runs.db`, the history database; the vault's files are the system of record for configuration and are written only through `VaultWriter`, `infrastructure/vault/`)
- **`cryptography`** (Fernet) for the envelope-encrypted secret store
- **`keyring`** for OS keychain (secret module only — master key opt-in + legacy migration)
- **`asyncio`** for async + subprocess management. Coffer's own code imports
  `asyncio`, never `anyio` (which `domain/` is forbidden to import at all) — but
  `anyio` is underneath Starlette and the `mcp` SDK, and its task-group cancel
  scopes are why an `mcp` `ClientSession` must be opened and closed in the same
  task (see `infrastructure/mcp/http_client.py`).

Coffer is past the point where every feature library arrives with its own spec:
the substantive ones are declared as **core** dependencies in
[`backend/pyproject.toml`](../backend/pyproject.toml), which is the list to read
before assuming something is absent.

- **`langgraph` + `langchain` + `langchain-anthropic` / `-openai` / `-ollama`** —
  Coffer runs an **in-process LangGraph multi-LLM agent** for its own agent
  turns. This is not an optional extra; it is how a turn executes.
- **`claude-agent-sdk`** and **`openai`** — the external agent/model providers a
  turn can run against instead.
- **`mcp`** (≥ 2.2, plus **`httpx2`** its 2.x line builds on) — the MCP SDK
  behind the gateway, both as server and as client of upstream servers.
- **`alembic`** — every schema change is a migration, never an implicit create.
- **`typer`** + **`rich`** (CLI), **`structlog`** (logging), **`psutil`**,
  **`tomlkit`**, **`pyyaml`** (agent-native config files), **`sse-starlette`** +
  **`watchfiles`** (streamed turns, file watching).
- **`markitdown[docx,pdf,pptx,xls,xlsx]`** — inbound **channel attachment → text**
  (`infrastructure/chat/document_extract.py`) and **uploaded document → Markdown
  file** (`infrastructure/knowledge/converters/markitdown_converter.py`). Those
  two modules are its only permitted importers; an importlinter contract over
  the whole `coffer` package refuses any other. The extras are what stop each
  rich format raising at extraction time.

Coffer embeds nothing: there is no vector index and no embedding model in the
dependency set, and knowledge search and memory recall are literal. A genuinely
feature-local library still arrives with the spec that first needs it — but
check the file before adding one.

### Architecture

Layered DDD (under `backend/coffer/`):

```
surfaces/      — entry points; one subdir per surface, defined per spec
application/   — commands, queries, ports (interfaces), shared services
domain/        — entities, value objects, domain services (PURE)
infrastructure/— adapters for SQLite, keyring, and outbound I/O
```

**Import direction is one-way**: `surfaces → application → domain`; `infrastructure` adapts to ports defined in `application`. `domain/` is pure.

The layering import rules, the secret-access rule, and the "extract cross-cutting modules only after the second feature needs them" rule are invariants owned by [`docs-site/architecture/principles.md`](../docs-site/architecture/principles.md). The Python-specific way they land in this codebase:

- `domain/` stays pure Python + Pydantic only — no FastAPI, SQLAlchemy, httpx, or other external SDKs.
- `application/` defines ports; `infrastructure/` adapts to them.
- `keyring` is imported only by the secret module; everywhere else passes secret refs.
- Each registered resource kind has a factory in `application/<kind>/kind.py` (`make_agent_kind`, `make_mcp_kind`, …; chat and sync register none) that takes the services it needs and returns a frozen `Kind`; the composition root (`surfaces/http/app.py` via per-kind `*_wiring.py`, `surfaces/cli/main.py`) registers it and mounts its routes. FastAPI dependency providers are split per kind: `surfaces/http/dependencies.py` holds only the kind-agnostic core, and each kind publishes its own concretely-typed `set_*`/`get_*` pairs from its own module — nothing is typed `Any`.
- The import-linter cross-kind fence covers every kind symmetrically (mcp, agent, skill, knowledge, channel, chat, provider, memory, sync). The only exceptions are domain vocabulary, not services: `provider`/`memory` may import `domain.agent`, `channel` may import `domain.chat`; `TYPE_CHECKING`-only imports don't count. Code two kinds need moves to a kind-agnostic package at the layer root (`infrastructure/net/`, `infrastructure/agent_files/`, `domain/hook_trust.py`).
- Only `infrastructure/platform/` asks which OS Coffer runs on. The application reaches it through `PlatformPort` (`application/platform_port.py`), whose adapter `HostPlatform` is built once in the composition root and passed in; other infrastructure imports the platform modules directly. `scripts/check_platform_calls.py` (in `make lint`) fails on a `sys.platform` / `platform.system()` / `os.name` check anywhere else. See [Platform port](../docs-site/architecture/platform.md).
- Per-agent behaviour lives on the agent descriptor (`domain/agent/descriptor.py`, `AGENT_DESCRIPTORS`): values as fields (`config_subpath`, `mcp`, `skill_subpath`, `hook_source_keys`, `program`, …) and mechanisms as four optional facets — `projection` (`AgentProjection`, the asset × landing registry in `domain/agent/facets.py`), `driver` (`application/chat/ports.AgentDriver`; `infrastructure/chat/drivers.py`), `memory_reader` (`domain/memory/reader.MemoryReader`; `infrastructure/memory/readers/`), `dependency_probe` (`DependencyProbe`; `infrastructure/agent/program_probe.py`). The provider entry of the projection is `domain/provider/agent_projection.py`; the delivery hook is `infrastructure/memory/delivery/`. Each implementation declares its agent; `surfaces/http/agent_facet_wiring.build_agent_catalog()` binds them into one `AgentCatalog`, built once in the lifespan and passed to every service that needs a mechanism (tests: `tests/support/facets.agent_catalog()`, with a fixed-answer probe). `scripts/check_agent_type_branches.py` (in `make lint`) fails on an `AgentType.<MEMBER>` or a comparison with an agent type literal anywhere else. See [Agent facets](../docs-site/architecture/agent-facets.md).
- Everything Coffer writes outside its database is converged by one level-triggered reconciler (ADR `one-level-triggered-reconciler-compares-parameters`; [The reconciler](../docs-site/architecture/reconciler.md)). The vocabulary is pure in `domain/reconcile.py` (`Item` with full `params`, `Difference`, `Decision`/`Disposition`, `Trigger`, `diff()`); the loop is `application/reconcile/reconciler.Reconciler` (`register`, `run(targets=, trigger=)`, `plan()` = dry-run, `apply(ids, actor=)`, `hint(Changed)`, `hold()`, `serve()`), its per-target steps `pass_ops.py`, the target protocol `ports.ReconcileTarget` (`desired`/`observe`/`decide`/`apply` → `Applied(AuditEvent, undo)` — the reconciler records the audit and runs the undo if that fails). One target per asset in the projection registry, in its kind's package: `application/agent/mcp_reconcile.McpEntryTarget` (`mcp_entry`), `application/skill/link_reconcile` (`skill_link`), `application/provider/projection_reconcile.ProviderProjectionTarget` (`provider_projection`), `application/memory/delivery_reconcile.DeliveryHookTarget` (`delivery_hook`). Hints come from `application/reconcile/hints.HintingResourceRepo`, which wraps the resource repo so every write emits `Changed(kind, uid, op)` (no revision number is kept). Composition is `surfaces/http/reconcile_wiring.py` (built before the kinds; boot pass before ready; one sync post-import hook with `Trigger.IMPORT`; `SyncService` holds the reconciler across a round and its import pass). Read models: `surfaces/http/reconcile_routes.py` (`GET /reconcile/plan`, `POST /reconcile/apply`, `GET /attention`). The attention list is `application/attention.AttentionService` over one `AttentionSource` per kind (`application/<kind>/attention.py`, composed in `surfaces/http/attention_wiring.py`) plus `application/reconcile/attention_source.DriftAttentionSource`. A new target never audits its own write, never adds what the user did not ask for, and comes with the four tests the page lists.

### Code Style

- **Ruff** for lint + format. Config in `backend/pyproject.toml`.
- **mypy --strict** for the whole package.
- File size: **≤ 400 lines** per Python file.
- Type hints on every function signature.
- Pydantic v2 `BaseModel` for any data crossing a boundary (HTTP, MCP, SQLite I/O).

### HTTP Contracts (Wire Format)

The wire contract runs **Pydantic models → generated OpenAPI → generated frontend client** (Principles, "II. Spec-as-Truth" → Contract direction; ADR `docs/decisions/wire-contract-generated-from-the-pydantic-models.md`). The backend Pydantic `BaseModel`s in `surfaces/http/` are the only hand-written description of the wire. Each spec's `openspec/specs/<short-name>/contracts/api.openapi.yaml` (one file per spec, and spec folders are named, never numbered) is generated from them and checked in, so a wire change is reviewed as a diff; never edit it by hand to describe a shape the models do not produce. Every HTTP route declares `response_model=<Foo>Response` against a Pydantic `BaseModel` — never `dict[str, Any]`, and `scripts/check_response_models.py` (in `make lint`) enforces it.

**Regenerate, never edit.** `make contracts` runs `scripts/gen_contracts.py` (the app's `openapi()` split by the route-ownership table `OWNERS` in that script, deterministic output) and then the frontend codegen. `make lint` runs `scripts/gen_contracts.py --check`, which fails when a checked-in contract differs from what the models produce or when a served route has no owning capability — a new route family needs an `OWNERS` entry naming its spec. `surfaces/http/openapi_document.py` makes the served document state Coffer's error envelope (`ErrorResponse`) instead of FastAPI's `HTTPValidationError`, and marks every field of a response-only schema required, since no route excludes unset fields. Give a model a stable, meaningful class name: it is the schema name the frontend imports.

**Event stream and pagination.** UI freshness comes from `GET /api/v1/events` (spec resource-framework "Announce every change on one daemon-wide event stream"): invalidation hints `{seq, kind, id, rev, op}`, never state. A list that grows while it is read pages by an opaque cursor (`limit` + `cursor` → `next_cursor`, spec resource-framework "Page growing lists by an opaque cursor"), never by `offset`.

### Local Dev

```bash
make install                       # one-time setup
make dev                           # backend on :38470 + Vite on :5173
# backend only — go through the daemon entry point, never bare uvicorn:
cd backend && COFFER_DEV_CORS=1 PYTHONPATH=. ../.venv/bin/python3 -m coffer.infrastructure.daemon.entry
make lint / make verify-unit / make format / make verify
```

`entry` is what allocates the port, mints the auth token and writes
`~/.coffer/daemon.json`; a bare `uvicorn coffer.main:app` leaves the active
token unset, so every token-gated endpoint answers `503` and the UI is
unusable. The comment above the `dev:` target in the `Makefile` has the detail.

## Desktop Shell — Rust / Tauri 2

The desktop shell lives in `desktop/`. It is a **native host over the same
`frontend/dist`** the daemon serves, not a second UI: it hosts the built SPA as
a local asset, supplies the API token over IPC (because the daemon spec's "Hand the browser its token in the served page" injection
cannot reach a document nobody served), runs detect-or-spawn for the daemon, and
sits in the menu bar. Beyond that it owns three things only a native host can
do: the **secret boundary** (the presence check and the presence grant, signed
with the master key, that release a plaintext value or an approval, plus the
notice that a secret is waiting for approval), the **updater** (a signed
release manifest, and replacing the old daemon after the relaunch), and **sync
alerts** (a notification when the vault's last sync round needs a human). File
actions go through the daemon's HTTP routes in both hosts, and binary
deployment belongs to the daemon's frozen-start path ([The Desktop Shell
Returns](../docs/decisions/desktop-shell-over-a-shared-frontend.md);
[Distribution](../docs-site/architecture/distribution.md)).

- **Rust 2021**, **Tauri 2** (`tray-icon`, `image-png`).
- File size: **≤ 400 lines** per `.rs` file, same cap as backend Python and
  gated by `scripts/check_file_sizes.py`. The shell is deliberately split into
  small modules to stay under it, grouped by responsibility:
  - **daemon:** `resolve` (the five-step chain deciding where a daemon comes
    from), `discovery` (reading `daemon.json`, probing a port), `spawn`,
    `ready`, `restart` (the restart policy as pure functions), `daemon` (the
    IPC commands the webview calls and the detect-or-spawn policy behind them —
    rate limiting, stop-then-start, the token handshake), `daemon_http`,
    `env_path`, `sidecar`, `coffer_home` (every `~/.coffer` path the shell
    touches);
  - **menu bar:** `tray`, `tray_state`, `tray_watch`, `tray_nav`, `tray_locale`;
  - **secret boundary:** `secrets` (its IPC commands), `presence`,
    `presence_macos`, `presence_grant`, `master_key`, `approval_watch`;
  - **updates:** `updater`, `update_state`, `update_relaunch`;
  - **sync alerts:** `sync_watch`, `sync_alert`, `sync_presentation`;
  - `logging` (the shell's own records, appended to `~/.coffer/logs/daemon.log`,
    so a failed tray restart does not fail in silence).
- Pure decision functions — the resolution chain, the rate limit, `daemon.json`
  parsing, the `$PATH` merge — are split from their I/O so `cargo test` covers
  them without a Tauri runtime or a socket.
- `cargo test` is **not** part of `make verify`: the desktop crate has its own
  CI job (`.github/workflows/desktop.yml`, on pushes to `main` and pull requests into
  `main` that touch `desktop/`, the `Makefile` or the workflow), which
  runs `make desktop-lint` and `make desktop-test`. Run the same locally; build
  the app with `make desktop` (which runs PyInstaller for the three bundled
  binaries — `coffer`, `coffer-daemon` and `coffer-mcp-shim` — first, so it is
  slow).

## E2E — TypeScript / Playwright

The end-to-end tier lives in `e2e/`. The far larger TypeScript surface is the
frontend (`frontend/src`): a page module per route under `pages/` — with
`activity/`, `settings/` and `sync/` subtrees where an area has
several pages — feature components under `components/<feature>/` over the shared
`components/ui/` primitives, and hooks + the API layer + pure helpers under
`lib/`. [`frontend.md`](./frontend.md) owns that scheme. `e2e/` is a second,
much smaller TypeScript tier on top of it. (Deliberately no line count: the one
that used to sit in this sentence went stale by 3.5×, and no gate guards it.)

- **TypeScript 5.x**, ESM modules (`tsconfig.json` with `@playwright/test` + `node` types).
- **Playwright** (`@playwright/test`) as the e2e runner, with **two projects** in
  `e2e/playwright.config.ts` — `make verify-e2e` runs both.
- The web suite (`e2e/web/specs/*.spec.ts`) drives Chromium against the UI, with
  the config's two `webServer` entries bringing up an isolated-`HOME` daemon on
  `:18000` and a Vite server pointed at it.
- The MCP suite (`e2e/mcp/specs/*.spec.ts`) exercises the full chain: a real MCP
  client → `coffer-mcp-shim` (stdio) → daemon (`/mcp` HTTP) → upstream MCP
  server → SQLite. Tests spawn the shim and daemon as OS subprocesses and drive
  JSON-RPC across them; no browser is involved.
- Run with `cd e2e && npm test` (`playwright test`), or `make verify-e2e`;
  `--project=web` / `--project=mcp` runs one leg. Conventions live in
  [`testing.md`](./testing.md).
