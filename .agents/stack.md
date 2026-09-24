# Stack — Python Backend

Coffer's backend is Python 3.12+.

## Backend — Python / FastAPI / SQLite

### Languages & Versions

- **Python 3.12+**
- **FastAPI** for HTTP surface
- **Pydantic v2** for models + validation
- **SQLite** via **SQLAlchemy 2 (async)** + **`aiosqlite`** (the exclusive data-access path)
- **`cryptography`** (Fernet) for the envelope-encrypted credential store
- **`keyring`** for OS keychain (credential module only — master key opt-in + legacy migration)
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

The layering import rules, the credential-access rule, and the "extract cross-cutting modules only after the second feature needs them" rule are invariants owned by [`docs-site/architecture/principles.md`](../docs-site/architecture/principles.md). The Python-specific way they land in this codebase:

- `domain/` stays pure Python + Pydantic only — no FastAPI, SQLAlchemy, httpx, or other external SDKs.
- `application/` defines ports; `infrastructure/` adapts to them.
- `keyring` is imported only by the credential module; everywhere else passes credential refs.
- Each resource kind's `make_<kind>_kind()` factory returns a frozen `Kind`; the composition root (`surfaces/http/app.py` via per-kind `*_wiring.py`, `surfaces/cli/main.py`) registers it and mounts its routes. FastAPI dependency providers are split per kind: `surfaces/http/dependencies.py` holds only the kind-agnostic core, and each kind publishes its own concretely-typed `set_*`/`get_*` pairs from its own module — nothing is typed `Any`.
- The import-linter cross-kind fence covers every kind symmetrically (mcp, agent, skill, knowledge, channel, chat, provider, memory, sync). The only exceptions are domain vocabulary, not services: `provider`/`memory` may import `domain.agent`, `channel` may import `domain.chat`; `TYPE_CHECKING`-only imports don't count. Code two kinds need moves to a kind-agnostic package at the layer root (`infrastructure/net/`, `infrastructure/agent_files/`, `domain/connection.py`).

### Code Style

- **Ruff** for lint + format. Config in `backend/pyproject.toml`.
- **mypy --strict** for the whole package.
- File size: **≤ 400 lines** per Python file.
- Type hints on every function signature.
- Pydantic v2 `BaseModel` for any data crossing a boundary (HTTP, MCP, SQLite I/O).

### HTTP Contracts (Wire Format)

The authoritative wire contract for any feature is `openspec/specs/<short-name>/contracts/api.openapi.yaml` (hand-written, PR-reviewed — one file per spec, and spec folders are named, never numbered). Backend Pydantic `BaseModel`s are HAND-WRITTEN to match the yaml. Every HTTP route declares `response_model=<Foo>Response` against a Pydantic `BaseModel` — never `dict[str, Any]`, and `scripts/check_response_models.py` (in `make lint`) enforces it.

CI gate: `make verify-contract` rejects PRs where the runtime OpenAPI dump structurally differs from any spec yaml.

### Local Dev

```bash
make install                       # one-time setup
make dev                           # backend on :8000 + Vite on :5173
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
sits in the tray. It owns nothing else — file actions go through the daemon's
HTTP routes in both hosts, and binary deployment belongs to the daemon's
frozen-start path ([The Desktop Shell
Returns](../docs/decisions/desktop-shell-over-a-shared-frontend.md)).

- **Rust 2021**, **Tauri 2** (`tray-icon`, `image-png`).
- File size: **≤ 400 lines** per `.rs` file, same cap as backend Python and
  gated by `scripts/check_file_sizes.py`. The shell is deliberately split into
  small modules to stay under it: `resolve` (the five-step chain deciding where
  a daemon comes from), `discovery` (reading `daemon.json`, probing a port),
  `spawn` (starting one), `daemon` (the three IPC commands the webview calls
  and the detect-or-spawn policy behind them — rate limiting, stop-then-start,
  the credential handshake), `env_path`, `sidecar`, `tray`, and `logging` (the
  shell's own records, appended to `~/.coffer/logs/daemon.log`, so a failed
  tray restart does not fail in silence).
- Pure decision functions — the resolution chain, the rate limit, `daemon.json`
  parsing, the `$PATH` merge — are split from their I/O so `cargo test` covers
  them without a Tauri runtime or a socket.
- `cargo test` is **not** part of `make verify` and no CI leg carries a Rust
  toolchain. Run it with `make desktop-test`; build the app with `make desktop`
  (which runs PyInstaller for the four bundled binaries first, so it is slow).

## E2E — TypeScript / Playwright

The end-to-end tier lives in `e2e/`. The far larger TypeScript surface is the
frontend (`frontend/src`): a page module per route under `pages/` — with
`activity/`, `resources/`, `settings/` and `sync/` subtrees where an area has
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
