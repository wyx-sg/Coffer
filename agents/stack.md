# Stack — Python Backend / TypeScript Frontend

Coffer is Python 3.12+ on the backend, TypeScript 5.x on the frontend.

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

**Rules:**

- `domain/` may NOT import `infrastructure/`, `surfaces/`, or any external SDK (FastAPI, SQLAlchemy, httpx, etc.). Pure Python + Pydantic only.
- `application/` may NOT import `surfaces/` or `infrastructure/` directly. It defines ports; infrastructure adapts to them.
- Only the credential module may import `keyring`. Everywhere else uses credential refs.
- Cross-cutting modules under `application/` or `infrastructure/` are extracted only after the second feature needs them. Don't pre-allocate.

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
make dev                           # backend (:8000) + frontend (:5173) in parallel
.venv/bin/uvicorn coffer.main:app --reload --port 8000   # backend only
make lint / make test / make format / make verify
```

## Frontend — TypeScript / React / Vite / Tailwind / shadcn

### Languages & Versions

- **TypeScript 5.x** (strict mode)
- **React 18**
- **Vite 5+** for dev server + build
- **Tailwind CSS 3** for styling
- **shadcn/ui** for components (copy-paste, not a runtime dependency)
- **TanStack Query** for server state
- **react-hook-form** + **zod** for forms
- **TanStack Router** or **React Router** for routing
- **Vitest** + **@testing-library/react** for tests
- **Playwright** for E2E (lands when first e2e test ships)

### Architecture

```
frontend/src/
├── main.tsx              — entry point
├── App.tsx               — root component / router setup
├── pages/                — route-level components (one per route)
├── components/           — reusable components
│   └── ui/               — shadcn/ui copies (style: default, slate base)
├── hooks/                — custom React hooks (use*)
├── lib/                  — utilities (cn, fetch wrappers, zod schemas)
├── api/                  — TanStack Query hooks + fetch functions, one file per feature
├── types/                — TS types (hand-written or generated later from OpenAPI)
└── index.css             — Tailwind directives + CSS variables
```

### Code Style

- **ESLint 9** flat config for lint, **Prettier** for format.
- **tsc** for typecheck (`tsc --noEmit`).
- File sizes:
  - Frontend page: **≤ 200 lines**
  - Frontend component: **≤ 250 lines**
  - Frontend hook: **≤ 300 lines**
- Naming: components PascalCase, hooks `useXxx`, utils camelCase.

### Component Patterns

- **shadcn/ui** components are copied into `src/components/ui/` and customized. They are NOT a runtime dependency.
- Forms: `react-hook-form` + `zod` resolver. Schema lives next to the form.
- Server state: `TanStack Query`. Local UI state: `useState`. Cross-component state: lift up or use a small `useContext` provider — no Zustand/Redux unless a spec needs it.
- API calls: thin wrapper around `fetch` that throws on non-2xx. TanStack Query handles retries + caching.

### Wire Contracts

Backend exposes Pydantic models that match `specs/<NNN>-<short-name>/contracts/*.openapi.yaml`. Frontend consumes those routes; until type codegen lands, hand-write TS types in `src/types/` that match the backend Pydantic models and keep them in sync via PR review.

### Local Dev

```bash
make install                       # also installs frontend deps
make dev                           # backend + frontend in parallel
cd frontend && npm run dev         # frontend only (Vite on :5173)
cd frontend && npm run lint / npm run typecheck / npm run test / npm run format
```

## Desktop Shell — Tauri 2 / Rust

Coffer's desktop distribution is a thin Tauri shell wrapping the same React app the browser dev server runs.

### Languages & Versions

- **Tauri 2.x** (Rust shell)
- **Rust** stable (managed via `rustup`)
- Frontend bindings via `@tauri-apps/api` (JS) and `@tauri-apps/cli` (build CLI)

### Architecture

```
src-tauri/
├── Cargo.toml                — Rust crate manifest
├── build.rs                  — invokes tauri-build during cargo build
├── tauri.conf.json           — app metadata, window config, dev/build wiring
├── src/
│   ├── main.rs               — binary entry; calls into lib.rs
│   └── lib.rs                — Tauri builder; one place to register commands
└── capabilities/
    └── default.json          — permission manifest per window
```

**Tauri commands** (Rust functions invokable from JS via `@tauri-apps/api/core` `invoke()`) live in `src-tauri/src/lib.rs` for now; split into modules when more than ~3 commands accumulate. Each command is `read` / `write` / `destructive` and goes through the same approval coordinator as HTTP / MCP / CLI surfaces (when those land).

### Local Dev

```bash
make desktop-dev                   # frontend + Tauri window (Vite is started by tauri.conf.json beforeDevCommand)
make desktop-build                 # release bundle (skipped in CI; manual on-demand)
```

`bundle.active` is `false` in `tauri.conf.json` until a release pipeline is added — `make desktop-build` will compile the binary but not produce installers (`.dmg` / `.msi` / `.AppImage`).
