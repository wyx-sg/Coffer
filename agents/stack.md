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
- **`anyio`** + `asyncio` for async + subprocess management

Feature-specific libraries (e.g. an MCP SDK) are added by the spec that first
needs them, not pre-installed here.

### Architecture

Layered DDD (under `backend/coffer/`):

```
surfaces/      — entry points; one subdir per surface, defined per spec
application/   — commands, queries, ports (interfaces), shared services
domain/        — entities, value objects, domain services (PURE)
infrastructure/— adapters for SQLite, keyring, and outbound I/O
```

**Import direction is one-way**: `surfaces → application → domain`; `infrastructure` adapts to ports defined in `application`. `domain/` is pure.

The layering import rules, the credential-access rule, and the "extract cross-cutting modules only after the second feature needs them" rule are invariants owned by [`.specify/memory/constitution.md`](../.specify/memory/constitution.md). The Python-specific way they land in this codebase:

- `domain/` stays pure Python + Pydantic only — no FastAPI, SQLAlchemy, httpx, or other external SDKs.
- `application/` defines ports; `infrastructure/` adapts to them.
- `keyring` is imported only by the credential module; everywhere else passes credential refs.

### Code Style

- **Ruff** for lint + format. Config in `backend/pyproject.toml`.
- **mypy --strict** for the whole package.
- File size: **≤ 400 lines** per Python file.
- Type hints on every function signature.
- Pydantic v2 `BaseModel` for any data crossing a boundary (HTTP, MCP, SQLite I/O).

### HTTP Contracts (Wire Format)

The authoritative wire contract for any feature is `specs/<NNN>-<short-name>/contracts/*.openapi.yaml` (hand-written, PR-reviewed). Backend Pydantic `BaseModel`s are HAND-WRITTEN to match the yaml. Every HTTP route declares `response_model=<Foo>Response` against a Pydantic `BaseModel` — never `dict[str, Any]`.

CI gate (lands when first feature spec lands): `make verify-contract` rejects PRs where the runtime OpenAPI dump structurally differs from any spec yaml.

### Local Dev

```bash
make install                       # one-time setup
make dev                           # backend on :8000
.venv/bin/uvicorn coffer.main:app --reload --port 8000   # backend only
make lint / make verify-unit / make format / make verify
```

## Desktop Shell — Rust / Tauri 2

The desktop shell lives in `desktop/`. It is a **native host over the same
`frontend/dist`** the daemon serves, not a second UI: it hosts the built SPA as
a local asset, supplies the API token over IPC (because FR-025's injection
cannot reach a document nobody served), runs detect-or-spawn for the daemon, and
sits in the tray. It owns nothing else — file actions go through the daemon's
HTTP routes in both hosts, and binary deployment belongs to the daemon's
frozen-start path ([The Desktop Shell
Returns](../docs/decisions/desktop-shell-over-a-shared-frontend.md)).

- **Rust 2021**, **Tauri 2** (`tray-icon`, `image-png`).
- File size: **≤ 400 lines** per `.rs` file, same cap as backend Python and
  gated by `scripts/check_file_sizes.py`. The shell is deliberately split into
  small modules (`resolve`, `discovery`, `spawn`, `env_path`, `sidecar`, `tray`)
  to stay under it.
- Pure decision functions — the resolution chain, the rate limit, `daemon.json`
  parsing, the `$PATH` merge — are split from their I/O so `cargo test` covers
  them without a Tauri runtime or a socket.
- `cargo test` is **not** part of `make verify` and no CI leg carries a Rust
  toolchain. Run it with `make desktop-test`; build the app with `make desktop`
  (which runs PyInstaller for the four bundled binaries first, so it is slow).

## E2E — TypeScript / Playwright

The end-to-end tier lives in `e2e/`. The primary TypeScript surface is the
frontend (`frontend/src`, ~18k lines of TS/TSX); `e2e/` is an additional
TypeScript tier on top of it.

- **TypeScript 5.x**, ESM modules (`tsconfig.json` with `@playwright/test` + `node` types).
- **Playwright** (`@playwright/test`) as the e2e runner.
- The MCP suite (`e2e/mcp/specs/*.spec.ts`, config `e2e/playwright.config.ts`)
  exercises the full chain: a real MCP client → `coffer-mcp-shim` (stdio) →
  daemon (`/mcp` HTTP) → upstream MCP server → SQLite. Tests spawn the shim and
  daemon as OS subprocesses and drive JSON-RPC across them.
- Run with `cd e2e && npm test` (`playwright test`), or `make verify-e2e`.
