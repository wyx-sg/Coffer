# Testing — 4 Tiers + Acceptance Markers

Coffer uses four test tiers running in parallel CI jobs. Acceptance scenarios from `spec.md` are tagged across tiers, not as a separate tier. The doc reflects what's actually wired up today; future-state notes are explicitly marked.

## Tiers at a Glance

| Tier            | Tests what                                                                                                                                          | Speed budget (per file) | Tools                                                                                                                                                                                                    | Runs in `make verify`?          |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| **Unit**        | Pure functions, single class, domain logic, value objects. No I/O. Fake ports / no real infrastructure. Enforced by `scripts/check_unit_purity.py`. | < 100 ms                | `pytest`                                                                                                                                                                                                 | yes                             |
| **Integration** | Multiple modules + real local infrastructure: real SQLite, real subprocess, real filesystem, `keyring` test backend. No network.                    | < 2 s                   | `pytest` + `httpx.AsyncClient` / `fastapi.TestClient`                                                                                                                                                    | yes                             |
| **Contract**    | Wire-format conformance: hand-written `*.openapi.yaml` ↔ Pydantic models. Blocks PR on drift.                                                       | < 1 s                   | Currently: `pytest` + `TestClient` manual assertions on `/openapi.json`. **Future** (add when contract surface grows): `schemathesis` for backend fuzzing.                                                | yes                             |
| **E2E**         | Full stack via real surfaces: a real MCP client → `coffer-mcp-shim` (stdio) → daemon (`/mcp` HTTP) → upstream MCP servers → SQLite.                  | < 30 s                  | `Playwright` (`@playwright/test`) + TypeScript 5.x. Specs spawn the real shim + daemon as OS subprocesses and drive JSON-RPC across them end-to-end.                                                       | NO (separate `make verify-e2e`) |

**Suite shape**: integration ≫ unit > contract > e2e (in counts of tests). This is deliberately NOT the classic unit-heavy pyramid: the integration tier runs against real SQLite files and real subprocesses but stays fast (the full backend suite is ~100 s), so most behavior is pinned where the real wiring lives. The unit tier is reserved for pure logic (mechanically enforced by `scripts/check_unit_purity.py`).

Per-test budgets are guidance, not gates — a single slow test isn't a CI failure. They exist so a test that drifts an order of magnitude past its tier prompts a "wrong tier?" question. No total-suite budget is enforced; the suite grows with the project.

## Coverage Bar

The suite is the safety net: **a green `make verify` (+ `verify-e2e`) must mean the product works, with no manual re-testing required.** That sets a completeness bar across the surfaces:

1. **Every function is unit-tested.** Each function/method carries at least one test that exercises it and asserts its real result or effect — including its meaningful branches (error paths, empty/None, boundary values), not just the happy path.
2. **Every HTTP endpoint is tested.** Each route (every method+path in `coffer/surfaces/http/**`) has a test asserting status, response body/shape, and side effects — plus its auth and validation-failure responses.
3. **Every CLI command is tested.** Each Typer command/subcommand (`coffer/surfaces/cli/**`) has a test asserting exit code AND output/resulting state, plus its documented non-zero exit paths.
4. **Every core user flow is covered e2e.** Each end-to-end flow a user relies on (and every `## Acceptance Scenarios` entry in `spec.md`) has an e2e or acceptance-tagged test driving it through real surfaces.

**Tests must be genuine — never written just to move the coverage number.** A test earns its place only if it would FAIL on a real regression. Reject (and in review, call out) these anti-patterns:

- **Tautological** — asserts something always true, or echoes back a literal the code never transformed (`assert x == x`; asserting an input you just passed through a logic-free constructor).
- **No meaningful assertion** — calls the code but only checks "didn't raise" / "is not None" / `status_code == 200` / `exit_code == 0` when the real contract (a specific value, body, or side effect) is cheaply checkable and left unchecked. (Asserting *only* a status/exit code IS legitimate when that code is the contract under test — e.g. `401` for missing auth, `exit 3` for daemon-unreachable.)
- **Vacuous loop / conditional** — `for x in results: assert ...` with no guard that `results` is non-empty; `if captured: assert ...` that passes when the branch never ran. Add the `len(...) >= 1` / unconditional guard so emptiness fails.
- **Over-mocking** — mocking the unit under test, or mocking so much the test only verifies the mock. Real fakes at a *boundary* (in-memory SQLite, the `keyring` test backend, a fake upstream session) are fine; mocking the thing you claim to test is not.
- **Too loose** — an assertion (or a perf budget) so wide it can't fail (`assert len(x) >= 0`, a latency ceiling 100× the real value).

**Measuring it.** `pytest --cov=coffer --cov-report=term-missing` reports line/branch coverage; use it to find untested functions and branches. Coverage is a *floor-finding tool, not the goal* — a line counted as covered by a tautological test is still untested in spirit. Genuinely-unreachable defensive lines may be excluded with `# pragma: no cover` and a one-line reason rather than padded with a fake test. New code should not lower coverage of the file it touches.

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

**E2E** — top-level, crosses the daemon ↔ shim ↔ MCP-client boundary:

```
e2e/
├── playwright.config.ts       # Playwright runner config (mcp project)
├── package.json               # @playwright/test + TypeScript
└── mcp/
    └── specs/                 # real MCP client → shim → daemon
        └── *.spec.ts
```

Run with `cd e2e && npm test` (`playwright test`).

## Layout Rationale

- **Why `e2e/` is top-level (not under `backend/`)**: e2e is the seam exercised through real surfaces — an MCP client talks to `coffer-mcp-shim` over stdio, which talks to the daemon over `/mcp`, which fans out to upstream MCP servers and SQLite. Putting it under `backend/` would misrepresent ownership; it drives the assembled product, not one package's internals.
- **When to split inside a directory**: when a tier accumulates two clearly-different test families, split into subdirs and split the corresponding CI job. Don't pre-split for tests that don't exist yet.

## Naming

- Backend pytest files: `test_<thing>.py`. Test functions: `test_<scenario>` (snake_case).
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
make verify-e2e          # e2e tier only (Playwright MCP e2e: shim + daemon)
make verify-acceptance   # audit spec.md scenarios vs test markers

make lint                # ruff + mypy
make format              # ruff format
```

### Verification targets — what each one runs

| Target                    | What it runs                                                                                                                                                                                | When to use                                                                 |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `make verify`             | `lint` → `verify-unit` → `verify-integration` → `verify-contract` → `verify-acceptance`. The "pre-PR" gate.                                                                                 | Before every push and PR. CI runs the same tiers in parallel.               |
| `make verify-all`         | `verify` plus `verify-e2e`.                                                                                                                                                                  | Before merging anything that touches a surface (HTTP, CLI, shim).           |
| `make verify-unit`        | `scripts/check_unit_purity.py` (AST-scans for forbidden I/O imports) then `pytest backend/tests/unit`.                                                                                       | Tight TDD loop on pure domain code.                                         |
| `make verify-integration` | `pytest backend/tests/integration`.                                                                                                                                                          | After touching application services, SQLAlchemy repos, HTTP routes, or CLI plumbing. |
| `make verify-contract`    | `pytest backend/tests/contract`.                                                                                                                                                             | After editing `specs/*/contracts/api.openapi.yaml` or Pydantic API schemas. |
| `make verify-e2e`         | `cd e2e && playwright test` — the Playwright/TypeScript MCP e2e suite (`e2e/mcp/specs/*.spec.ts`) drives a real MCP client through the shim to the daemon and upstream servers.               | After touching the daemon ↔ shim ↔ MCP-client boundary.                   |
| `make verify-acceptance`  | `scripts/audit_acceptance.py`: parses every `specs/*/spec.md` `## Acceptance Scenarios` block and every `@acceptance(spec=…, scenario=…)` marker; fails on uncovered or orphan scenarios.   | Every spec.md edit. Cheap; runs without dependencies.                       |

## CI Jobs

`.github/workflows/verify.yml` runs these jobs in parallel; all must pass to merge:

| Job           | What                                                      |
| ------------- | --------------------------------------------------------- |
| `lint`        | ruff + mypy                                               |
| `unit`        | `make verify-unit` (purity check + backend)               |
| `integration` | `make verify-integration`                                 |
| `contract`    | `make verify-contract`                                    |
| `acceptance`  | `python3 scripts/audit_acceptance.py` (no install needed) |
| `e2e`         | `make verify-e2e` (Playwright MCP e2e: shim + daemon)     |

## When a Tier is Empty

A tier with no tests yet runs trivially green (pytest collects 0 tests). The Makefile checks for tier directories and skips silently if absent — don't gate `make verify` on tiers that don't exist.
