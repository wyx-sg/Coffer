# Stack — Python Backend

Coffer's backend is Python 3.12+.

## Backend — Python / FastAPI / SQLite

### Languages & Versions

- **Python 3.12+**
- **FastAPI** for HTTP surface
- **Pydantic v2** for models + validation
- **SQLite** via standard library `sqlite3` or SQLAlchemy
- **`keyring`** for OS keychain (credentials only)
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
make lint / make test / make format / make verify
```

## E2E — TypeScript / Playwright

The end-to-end tier lives in `e2e/` and is the only TypeScript in the repo.

- **TypeScript 5.x**, ESM modules (`tsconfig.json` with `@playwright/test` + `node` types).
- **Playwright** (`@playwright/test`) as the e2e runner.
- The MCP suite (`e2e/mcp/specs/*.spec.ts`, config `e2e/playwright.config.ts`)
  exercises the full chain: a real MCP client → `coffer-mcp-shim` (stdio) →
  daemon (`/mcp` HTTP) → upstream MCP server → SQLite. Tests spawn the shim and
  daemon as OS subprocesses and drive JSON-RPC across them.
- Run with `cd e2e && npm test` (`playwright test`), or `make verify-e2e`.
