# Testing — 4 Tiers + Acceptance Markers

Coffer uses four test tiers running in parallel CI jobs. Acceptance scenarios from `spec.md` are tagged across tiers, not as a separate tier. The doc reflects what's actually wired up today; future-state notes are explicitly marked.

## Tiers at a Glance

| Tier            | Tests what                                                                                                                                          | Speed budget (per file) | Tools                                                                                                                                                                                                    | Runs in `make verify`?          |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| **Unit**        | Pure functions, single class, domain logic, value objects. No I/O. Fake ports / no real infrastructure. Enforced by `scripts/check_unit_purity.py`. | < 100 ms                | `pytest`                                                                                                                                                                                                 | yes                             |
| **Integration** | Multiple modules + real local infrastructure: real SQLite, real subprocess, real filesystem, `keyring` test backend. No network.                    | < 2 s                   | `pytest` + `httpx.AsyncClient` / `fastapi.TestClient`                                                                                                                                                    | yes                             |
| **Contract**    | Wire-format conformance: hand-written `*.openapi.yaml` ↔ Pydantic models. Blocks PR on drift.                                                       | < 1 s                   | Currently: `pytest` + `TestClient` manual assertions on `/openapi.json`. **Future** (add when contract surface grows): `schemathesis` for backend fuzzing.                                                | yes                             |
| **E2E**         | Full stack via real surfaces, in **two legs**: a browser (Chromium) against the UI the daemon serves, and a real MCP client → `coffer-mcp-shim` (stdio) → daemon (`/mcp` HTTP) → upstream MCP servers → SQLite. | < 30 s                  | `Playwright` (`@playwright/test`) + TypeScript 5.x. The `web` project drives pages against a Vite server pointed at an isolated daemon; the `mcp` project spawns the real shim + daemon as OS subprocesses and drives JSON-RPC across them. | NO (separate `make verify-e2e`) |

**Suite shape**: integration ≫ unit > contract > e2e (in counts of tests). This is deliberately NOT the classic unit-heavy pyramid: the integration tier runs against real SQLite files and real subprocesses but stays fast (the full backend suite is ~100 s), so most behavior is pinned where the real wiring lives. The unit tier is reserved for pure logic (mechanically enforced by `scripts/check_unit_purity.py`).

Per-test budgets are guidance, not gates — a single slow test isn't a CI failure. They exist so a test that drifts an order of magnitude past its tier prompts a "wrong tier?" question. No total-suite budget is enforced; the suite grows with the project.

## Coverage Bar

The suite is the safety net: **a green `make verify` (+ `verify-e2e`) must mean the product works, with no manual re-testing required.** That sets a completeness bar across the surfaces:

1. **Every function is unit-tested.** Each function/method carries at least one test that exercises it and asserts its real result or effect — including its meaningful branches (error paths, empty/None, boundary values), not just the happy path.
2. **Every HTTP endpoint is tested.** Each route (every method+path in `coffer/surfaces/http/**`) has a test asserting status, response body/shape, and side effects — plus its auth and validation-failure responses.
3. **Every CLI command is tested.** Each Typer command/subcommand (`coffer/surfaces/cli/**`) has a test asserting exit code AND output/resulting state, plus its documented non-zero exit paths.
4. **Every core user flow is covered e2e.** Each end-to-end flow a user relies on (and every `#### Scenario:` in an `openspec/specs/**/spec.md`) has an e2e or acceptance-tagged test driving it through real surfaces.

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

**E2E** — top-level, two Playwright projects: a browser suite over the served UI
and a cross-process suite over the daemon ↔ shim ↔ MCP-client boundary:

```
e2e/
├── playwright.config.ts       # runner config: `web` + `mcp` projects, and the
│                              # two webServers (isolated daemon on :18000,
│                              # Vite on :5173 pointed at it)
├── package.json               # @playwright/test + TypeScript
├── scripts/start_daemon.sh    # the isolated-HOME daemon both projects share
├── web/
│   └── specs/                 # browser against the daemon-served UI
│       ├── *.spec.ts          # agent_workspace, shell_activity, shell_agents,
│       │                      # shell_cold_start, shell_knowledge,
│       │                      # shell_mcp_flows, shell_settings, shell_skills
│       └── _acceptance.ts, _helpers.ts   # support modules, not specs
└── mcp/
    └── specs/                 # real MCP client → shim → daemon
        ├── *.spec.ts
        └── _acceptance.ts, _helpers.ts
```

Run both with `cd e2e && npm test` (`playwright test`), or one leg with
`npx playwright test --project=web` / `--project=mcp`.

Both legs run the checkout they are launched from, and say so rather than
assume it: `coffer` is installed into the venv editable, so `-m coffer...`
resolves to whichever tree the venv was built in — which in a git worktree is
the main checkout, because `.venv` there is a symlink to it. `start_daemon.sh`
and `spawnShim` both put `<repo>/backend` on `PYTHONPATH` for that reason, and
the daemon launcher refuses to start if `coffer` still resolves somewhere else.
A suite that tests the wrong tree passes, which is why this is a hard failure
rather than a warning.

## Layout Rationale

- **Why `e2e/` is top-level (not under `backend/`)**: e2e is the seam exercised through real surfaces — a browser clicks through the UI the daemon serves, and an MCP client talks to `coffer-mcp-shim` over stdio, which talks to the daemon over `/mcp`, which fans out to upstream MCP servers and SQLite. Neither leg belongs to one package: putting them under `backend/` (or `frontend/`) would misrepresent ownership; they drive the assembled product.
- **When to split inside a directory**: when a tier accumulates two clearly-different test families, split into subdirs and split the corresponding CI job. Don't pre-split for tests that don't exist yet.

## Naming

- Backend pytest files: `test_<thing>.py`. Test functions: `test_<scenario>` (snake_case).
- Test names describe behavior, not implementation: `test_health_returns_ok_with_version` ✓, `test_handler_calls_method` ✗.

## Acceptance Scenarios — Cross-Tier Markers

Every scenario in a capability spec must be covered by at least one test in any tier (typically integration or e2e). Tag tests with markers so coverage can be audited.

**Spec convention** — each scenario is an OpenSpec `#### Scenario: <name>` inside the `### Requirement:` it verifies, under `## Requirements` (see [openspec.md](./openspec.md) "Writing `spec.md`"):

```markdown
## Requirements

### Requirement: Register an upstream MCP server
The system MUST ...

#### Scenario: register and list
- **GIVEN** ...
- **WHEN** ...
- **THEN** ...
```

The marker quotes the scenario's name, so a name is unique within its spec. The spec ID is the spec's path under `openspec/specs/` (`openspec/specs/foo/spec.md` → `foo`; a child at `openspec/specs/foo/bar/spec.md` → `foo/bar`).

**Python (pytest):**

```python
import pytest

@pytest.mark.acceptance(spec="mcp-gateway", scenario="register and list")
def test_register_then_appears_in_list(...):
    ...
```

Marker is registered in `backend/pyproject.toml` under `[tool.pytest.ini_options]` with `--strict-markers` enabled — typos fail collection.

**TypeScript (Vitest / Playwright):**

```ts
import { acceptance } from "@/test/acceptance";

acceptance("chat", "chat runs on the built-in model when no connection", () => {
  ...
});
```

`acceptance()` is a thin wrapper over `test()` exported from
`frontend/src/test/acceptance.ts`; the audit strips comments before matching, so
a commented-out call does not count as coverage.

**Rust (the desktop crate):**

```rust
// acceptance(spec = "desktop-app", scenario = "a spawned daemon outlives the app")
#[test]
fn a_spawned_daemon_leaves_the_apps_process_group() { ... }
```

Rust has no user-defined test attribute without a proc-macro crate, so the marker
is a line comment the compiler ignores. It counts **only** when a `#[test]` or
`#[tokio::test]` follows before the next `fn` — a marker that drifts away from
its test stops counting and its scenario resurfaces as uncovered, rather than
reporting green on nothing. `#[ignore]` makes it a dead marker, the Rust
analogue of `@pytest.mark.skip`. Stack several markers to cover several
scenarios with one test. Doc comments (`//!`, `///`) are never matched.

These tests are gated by `.github/workflows/desktop.yml` (`make desktop-lint`,
`make desktop-test`), **not** by `make verify`, which excludes the crate — so a
local `make verify` proves nothing about the desktop shell.

**Coverage audit** — `make verify-acceptance` runs two halves of one rule. First `openspec validate --all --strict` (the pinned CLI from the root `package.json`; `make install` fetches it) fails any requirement that owns no scenario. Then `scripts/audit_acceptance.py` scans every `openspec/specs/**/spec.md` and every test file, and fails on:

- a scenario without a covering marker (missing coverage)
- a marker referring to a scenario / spec ID that doesn't exist (orphan marker — usually means a spec or scenario was renamed)
- a marker on a test that can never run (`@pytest.mark.skip`, Rust `#[ignore]`)
- a scenario name used twice in one spec

The audit itself is stdlib-only and runs in milliseconds.

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
make verify-benchmark    # the benchmark-marked tests (excluded from verify)
make verify-e2e          # e2e tier only (Playwright: web + mcp projects)
make verify-acceptance   # audit spec.md scenarios vs test markers

make lint                # every static gate (see below) — NOT just ruff + mypy
make format              # ruff format + ruff --fix + prettier (frontend)
```

**`make lint` is the whole static gate, not a formatter pass.** In order
(`Makefile`): `scripts/check_file_sizes.py`, `scripts/check_response_models.py`,
`scripts/check_doc_numbering.py`, `scripts/check_spec_citations.py`,
`scripts/check_architecture_doc.py`,
`scripts/check_pyinstaller_specs.py`, `ruff check`, `ruff format --check`,
`mypy --strict`, `lint-imports` (the layering + cross-kind fence), and — when
`frontend/node_modules` is present — `scripts/dump_i18n_backend_keys.py --check`
plus `npm run lint`, `npm run typecheck` and `npm run knip` in `frontend/`.

Two consequences worth internalising:

- **A docs-only edit can fail `make lint`.** `check_doc_numbering.py` rejects a
  numbered ADR/spec token and a dead link under `docs/decisions/`;
  `check_spec_citations.py` rejects a requirement citation —
  `spec <capability> "<Title>"` or a link to a capability's `spec.md` followed
  by a quoted title — whose capability or title does not exist, and a retired
  id form (an amendment letter after a capability, a numbered `CODE-` error id,
  an uppercase `SPEC-` id), so renaming a requirement fails until every
  citation of the old title follows;
  `check_architecture_doc.py` holds `docs/architecture.md` to the
  code. Run `make lint` after touching markdown, not just after touching code.
- **`lint-imports` is invoked with `PYTHONPATH=$(BACKEND)`, and that is
  load-bearing in a worktree** — a bare invocation resolves `coffer` through
  the editable install (which points at the main checkout) and reports contract
  violations for modules this tree does not have.

### Verification targets — what each one runs

| Target                    | What it runs                                                                                                                                                                                | When to use                                                                 |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `make verify`             | `lint` → `verify-unit` → `verify-integration` → `verify-contract` → `verify-acceptance`. The "pre-PR" gate.                                                                                 | Before every push and PR. CI runs the same tiers in parallel.               |
| `make verify-all`         | `verify` plus `verify-e2e`.                                                                                                                                                                  | Before merging anything that touches a surface (web UI, HTTP, CLI, shim).   |
| `make verify-unit`        | `scripts/check_unit_purity.py` (AST-scans for forbidden I/O imports), then `pytest backend/tests/unit`, then `vitest run src` in `frontend/` when its `node_modules` is present.             | Tight TDD loop on pure domain code.                                         |
| `make verify-integration` | `pytest backend/tests/integration`.                                                                                                                                                           | After touching application services, SQLAlchemy repos, HTTP routes, or CLI plumbing. |
| `make verify-contract`    | `pytest backend/tests/contract`.                                                                                                                                                              | After editing `openspec/specs/*/contracts/api.openapi.yaml` or Pydantic API schemas. |
| `make verify-benchmark`   | `COFFER_RUN_BENCHMARKS=1 pytest backend/tests -m benchmark` — the perf-budget tests, which `make verify` deliberately excludes.                                                               | After touching the gateway hot path or any code a perf budget covers.       |
| `make verify-e2e`         | `cd e2e && playwright test` — **both** projects: `web` (Chromium over the served UI, `e2e/web/specs/*.spec.ts`) and `mcp` (`e2e/mcp/specs/*.spec.ts`, a real MCP client through the shim to the daemon and upstream servers). | After touching a page, or the daemon ↔ shim ↔ MCP-client boundary.      |
| `make verify-acceptance`  | `openspec validate --all --strict` (every requirement owns a scenario), then `scripts/audit_acceptance.py` (every scenario has a marker, every marker a scenario).                | Every spec.md edit. Cheap; needs the root `npm install` for the OpenSpec CLI. |

## CI Jobs

`.github/workflows/verify.yml` runs **eight** jobs in parallel; all must pass to merge:

| Job           | What                                                                                                                       |
| ------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `lint`        | `make lint` — every static gate above, frontend included (it installs Node + `npm ci`)                                     |
| `unit`        | `make verify-unit` (purity check + backend pytest + frontend vitest)                                                       |
| `integration` | `make verify-integration` (installs `ripgrep`, which curation's candidate selection uses)                                  |
| `benchmark`   | `make verify-benchmark` — the **only** place the benchmark-marked perf-budget tests execute, so a budget can't go unchecked while its acceptance marker reports green |
| `acceptance`  | `openspec validate --all --strict` (needs the root `npm ci`), then `python3 scripts/audit_acceptance.py`                    |
| `secrets`     | `gitleaks` over the full history (`fetch-depth: 0`) — a committed secret fails the PR even if the final tree is clean       |
| `contract`    | `make verify-contract`                                                                                                     |
| `e2e`         | `make verify-e2e` (installs Chromium; runs the `web` and `mcp` projects)                                                    |

## When a Tier is Empty

A tier with no tests yet runs trivially green (pytest collects 0 tests). The Makefile checks for tier directories and skips silently if absent — don't gate `make verify` on tiers that don't exist.
