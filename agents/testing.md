# Testing — 4 Tiers + Acceptance Markers

Coffer uses four test tiers running in parallel CI jobs. Acceptance scenarios from `spec.md` are tagged across tiers, not as a separate tier. The doc reflects what's actually wired up today; future-state notes are explicitly marked.

## Tiers at a Glance

| Tier | Tests what | Speed budget (per file) | Tools | Runs in `make verify`? |
|---|---|---|---|---|
| **Unit** | Pure functions, single class, domain logic, value objects. No I/O. Fake ports / no real infrastructure. Enforced by `scripts/check_unit_purity.py`. | < 100 ms | `pytest` (backend), `vitest` (frontend) | yes |
| **Integration** | Multiple modules + real local infrastructure: real SQLite, real subprocess, real filesystem, `keyring` test backend. No network. | < 2 s | `pytest` + `httpx.AsyncClient` / `fastapi.TestClient` (backend), `vitest` + jsdom + React Testing Library across multiple components (frontend) | yes |
| **Contract** | Wire-format conformance: hand-written `*.openapi.yaml` ↔ Pydantic models ↔ TS types. Blocks PR on drift. | < 1 s | Currently: `pytest` + `TestClient` manual assertions on `/openapi.json`. **Future** (add when contract surface grows): `schemathesis` for backend fuzzing, `openapi-typescript` round-trip for TS types. | yes |
| **E2E** | Full stack via real surfaces: browser → frontend → backend → SQLite. | < 30 s | `Playwright` (web). | NO (separate `make verify-e2e`) |

**Pyramid shape**: unit ≫ integration > contract > e2e (in counts of tests).

Per-test budgets are guidance, not gates — a single slow test isn't a CI failure. They exist so a test that drifts an order of magnitude past its tier prompts a "wrong tier?" question. No total-suite budget is enforced; the suite grows with the project.

## Test File Locations

**Backend** — tier by directory:

```
backend/tests/
├── unit/                      # pure logic, no I/O (purity-checked)
│   └── <module>/test_*.py
├── integration/               # real local I/O
│   └── <module>/test_*.py
└── contract/                  # OpenAPI / wire-format conformance
    └── test_*.py
```

**Frontend** — unit co-located, higher tiers in `tests/<tier>/`:

```
frontend/src/
├── App.tsx
├── App.test.tsx               # unit (co-located, *.test.tsx pattern)
├── components/Button.tsx
└── components/Button.test.tsx # unit (co-located)

frontend/tests/
└── integration/               # multi-component + provider + hook scenarios
    └── *.test.tsx
```

(`frontend/tests/contract/` lands when the first frontend ↔ backend type-conformance test is written.)

**E2E** — top-level, crosses backend + frontend boundaries:

```
e2e/
├── playwright.config.ts
├── package.json               # own npm package — separate node_modules
└── web.spec.ts                # Playwright browser tests
```

## Layout Rationale

- **Why `e2e/` is top-level (not under `frontend/` or `backend/`)**: e2e is the seam *between* stacks — a Playwright test exercises browser → frontend → backend → SQLite. Putting it under either stack would misrepresent ownership. It's also a separate npm package (own `playwright.config.ts`, own `node_modules`, separate Playwright browser install) so it can't share frontend's Vite/Vitest workspace.
- **Why frontend co-locates unit tests, backend uses `tests/<tier>/`**: each follows its ecosystem's idiom. Vitest discovers `*.test.tsx` next to source; pytest expects a `tests/` tree. We don't fight either.
- **When to split inside a directory**: when a tier accumulates two clearly-different test families (e.g. once `e2e/` has both browser tests and a Python MCP-shim suite), split into subdirs (`e2e/web/`, `e2e/mcp/`) and split the corresponding CI job. Don't pre-split for tests that don't exist yet.

## Naming

- Backend pytest files: `test_<thing>.py`. Test functions: `test_<scenario>` (snake_case).
- Frontend vitest files: `<Source>.test.tsx` for component tests; `<Source>.test.ts` for util tests.
- Test names describe behavior, not implementation: `test_health_returns_ok_with_version` ✓, `test_handler_calls_method` ✗.

## Acceptance Scenarios — Cross-Tier Markers

Every `spec.md` scenario in `## Acceptance Scenarios` must be covered by at least one test in any tier (typically integration or e2e). Tag tests with markers so coverage can be audited.

**Spec convention** — under `## Acceptance Scenarios`, list scenarios as `### <title>` (an optional `Scenario:` prefix is stripped):

```markdown
## Acceptance Scenarios

### register and list
**Given** ..., **When** ..., **Then** ...

### Scenario: re-register existing
...
```

The spec ID is the spec folder name (e.g. `specs/001-foo/spec.md` → `001-foo`).

**Python (pytest):**

```python
import pytest

@pytest.mark.acceptance(spec="001-foo", scenario="register and list")
def test_register_then_appears_in_list(...):
    ...
```

Marker is registered in `backend/pyproject.toml` under `[tool.pytest.ini_options]` with `--strict-markers` enabled — typos fail collection.

**TypeScript (vitest / Playwright):**

```ts
test.acceptance("001-foo", "register and list", async () => {
  // ...
});
```

(Implement `test.acceptance` as a thin wrapper around `test` that records spec + scenario in metadata. The wrapper lands when the first acceptance test is written; the audit script already detects calls of this shape regardless.)

**Coverage audit** — `scripts/audit_acceptance.py` (run via `make verify-acceptance`) scans every `specs/*/spec.md` and every test file, then fails on:

- scenarios listed in spec.md without a covering marker (missing coverage)
- markers referring to a scenario / spec ID that doesn't exist (orphan marker — usually means a spec was renamed)

Stdlib-only, runs in milliseconds. With zero specs it's a no-op pass — the rail is in place before the first spec lands.

## Unit-Tier Purity Guardrail

`scripts/check_unit_purity.py` AST-scans `backend/tests/unit/**/*.py` and fails if any test imports a known I/O module (`subprocess`, `sqlite3`, `httpx`, `fastapi.testclient`, `socket`, `requests`, `urllib.request`, `aiohttp`, `keyring`). Runs as the first step of `make verify-unit`.

The unit tier's "no I/O" rule (line 1 of the table above) was previously a culture-only constraint. The script makes it mechanical: a test that sneaks in a `from fastapi.testclient import TestClient` gets flagged with the file:line and a message pointing to integration. To add a new banned module, edit the `BANNED` dict in the script.

## Mocking Philosophy

Prefer **real over mock** when speed allows:

- Real SQLite (in-memory or temp file) for integration tests.
- Real subprocess for subprocess lifecycle tests (use short-running child processes).
- Real filesystem (under `tmp_path`).
- `keyring` test backend (in-memory) — NOT a mock; it's an alternate real implementation.

Only mock when:

- The dependency is **non-local** (external HTTP service, LLM API).
- The dependency is **non-deterministic** in a way the test cares about (system clock, randomness).
- The dependency is **slow** (only as last resort — usually means the test is the wrong tier).

## Make Targets

```bash
make verify              # fast path: lint + unit + integration + contract + acceptance audit
make verify-all          # verify + e2e (full suite)

make verify-unit         # unit-purity guardrail + unit tier
make verify-integration  # integration tier only
make verify-contract     # contract tier only
make verify-e2e          # e2e tier only (Playwright)
make verify-acceptance   # audit spec.md scenarios vs test markers

make lint                # ruff + mypy + eslint + tsc
make format              # ruff format + prettier
```

## CI Jobs

`.github/workflows/verify.yml` runs these jobs in parallel; all must pass to merge:

| Job | What |
|---|---|
| `lint` | ruff + mypy + eslint + tsc |
| `unit` | `make verify-unit` (purity check + backend + frontend) |
| `integration` | `make verify-integration` |
| `contract` | `make verify-contract` |
| `acceptance` | `python3 scripts/audit_acceptance.py` (no install needed) |
| `e2e` | `make verify-e2e` (Playwright) |

Each tier job runs both backend and frontend portions inside it (so the bottleneck is the slowest stack inside a tier, not cross-tier).

## When a Tier is Empty

A tier with no tests yet runs trivially green (pytest collects 0 tests; vitest collects 0 tests). The Makefile checks for tier directories and skips silently if absent — don't gate `make verify` on tiers that don't exist.
