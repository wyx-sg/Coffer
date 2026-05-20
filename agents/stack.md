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
desktop/                      ← Tauri 2 crate; deviates from the `src-tauri/`
├── Cargo.toml                  default to match Coffer's role-named layout
├── Cargo.lock                  (backend / frontend / e2e / desktop). The
├── build.rs                    Makefile (desktop-dev / desktop-build) runs
├── tauri.conf.json             the CLI from desktop/ via the relative path
├── src/                        ../frontend/node_modules/.bin/tauri, because
│   ├── main.rs                 Tauri 2 CLI discovers the project via cwd
│   └── lib.rs                  rather than the --config flag.
├── icons/                    — generated by `tauri icon`; bundle artifacts
└── capabilities/
    └── default.json          — permission manifest per window
```

**Tauri commands** (Rust functions invokable from JS via `@tauri-apps/api/core` `invoke()`) live in `desktop/src/lib.rs` for now; split into modules when more than ~3 commands accumulate.

### Path resolution rules in `tauri.conf.json`

Two different bases — gotcha:

| Field | Base | Reason |
|---|---|---|
| `build.beforeBuildCommand` / `beforeDevCommand` | parent of the crate dir (`<repo>/`) | Tauri runs these from the project root, which it defines as the parent of `desktop/` |
| `build.frontendDist` / `build.devUrl` (URL: n/a) | the config file itself (`desktop/`) | standard Tauri config path resolution |

That's why `beforeBuildCommand: "npm run build --prefix frontend"` has no `../` while `frontendDist: "../frontend/dist"` does.

### Local Dev

```bash
make desktop-dev                   # frontend + Tauri window (Vite is started by tauri.conf.json beforeDevCommand)
make desktop-build                 # release bundle (.dmg / .msi / .AppImage / .deb depending on host)
```

### Testing

| Tier | Today | When |
|---|---|---|
| `tauri build` (frontend + bundle) | CI `desktop-build` job (Linux `.deb` only) | always |
| `cargo test` (Rust unit) | none yet | added with first Tauri command |
| Tauri E2E (webdriver / app smoke) | none | added with first desktop-only product spec |

### Security note (CSP)

`tauri.conf.json` currently sets `"app.security.csp": null` (Tauri's dev default). Before the first public release, a strict CSP must be defined; see Tauri 2 docs on [Content Security Policy](https://v2.tauri.app/security/csp/).
