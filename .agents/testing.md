# Testing — 4 Tiers + Acceptance Markers

Coffer uses four test tiers running in parallel CI jobs. Acceptance scenarios from `spec.md` are tagged across tiers, not as a separate tier. The doc reflects what's actually wired up today; future-state notes are explicitly marked.

## Tiers at a Glance

| Tier            | Tests what                                                                                                                                          | Speed budget (per file) | Tools                                                                                                                                                                                                    | Runs in `make verify`?          |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| **Unit**        | Pure functions, single class, domain logic, value objects. No network, process or database I/O; a `tmp_path` directory is allowed. Fake ports / no real infrastructure. Enforced by `scripts/check_unit_purity.py`. | < 100 ms                | `pytest`                                                                                                                                                                                                 | yes                             |
| **Integration** | Multiple modules + real local infrastructure: real SQLite, real subprocess, real filesystem, `keyring` test backend. No network.                    | < 2 s                   | `pytest` + `httpx.AsyncClient` / `fastapi.TestClient`                                                                                                                                                    | yes                             |
| **Contract**    | What contract freshness cannot see: every served route has an owning capability (`test_contract_coverage.py` over `scripts/gen_contracts.py`'s ownership table), MCP protocol behaviour against the SDK oracle, built-in tool names. The contracts themselves are generated from the Pydantic models and their freshness is a `make lint` step (`scripts/gen_contracts.py --check`), not a test. | < 1 s                   | `pytest` over the app's generated OpenAPI and the MCP SDK. **Future** (add when contract surface grows): `schemathesis` for backend fuzzing.                                                | yes                             |
| **E2E**         | Full stack via real surfaces, in **two legs**: a browser (Chromium) against the UI the daemon serves, and a real MCP client → `coffer-mcp-shim` (stdio) → daemon (`/mcp` HTTP) → upstream MCP servers → SQLite. | < 30 s                  | `Playwright` (`@playwright/test`) + TypeScript 5.x. The `web` project drives pages against a Vite server pointed at an isolated daemon; the `mcp` project spawns the real shim + daemon as OS subprocesses and drives JSON-RPC across them. | NO (separate `make verify-e2e`) |

**Suite shape**: integration ≫ unit > contract > e2e (in counts of tests). This is deliberately NOT the classic unit-heavy pyramid: the integration tier runs against real SQLite files and real subprocesses but runs in parallel on xdist workers (and in four shards on CI), so most behavior is pinned where the real wiring lives. The unit tier is reserved for pure logic (mechanically enforced by `scripts/check_unit_purity.py`).

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
- **Pinning a bug** — asserting what the code happens to do instead of what the contract says (an unknown method "returns -32603", an unknown tool "is a disabled tool"), or a test helper that only works because the implementation is lax (an `initialize` with half its required fields). When the helper and the code agree on something the external protocol forbids, both are wrong.
- **Ordinary inputs only** — every name typical (`test`, `live`). A rule with a limit or a normalisation (a 40-character name, case-insensitive uniqueness, a field that may be absent, null, empty or the wrong type) is tested at the limit and across the normalisation, or as a property (see "Property-Based Tests").

**Measuring it.** `pytest --cov=coffer --cov-report=term-missing` reports line/branch coverage; use it to find untested functions and branches. Coverage is a *floor-finding tool, not the goal* — a line counted as covered by a tautological test is still untested in spirit. Genuinely-unreachable defensive lines may be excluded with `# pragma: no cover` and a one-line reason rather than padded with a fake test. New code should not lower coverage of the file it touches.

## Test File Locations

**Backend** — tier by directory:

```
backend/tests/
├── conftest.py                # installs the real-home guard first (see below)
├── support/                   # shared, not tests: real_home_guard, homes, channel, fixtures
├── unit/                      # pure logic, no I/O (purity-checked)
│   └── <module>/test_*.py
├── integration/               # real local I/O
│   └── <module>/test_*.py
└── contract/                  # route ownership, MCP protocol conformance
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
│       ├── *.spec.ts          # one spec per page or flow
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

The audit sees only what a spec states. When a capability speaks an external protocol (MCP and JSON-RPC for `mcp-gateway`), the protocol's own rules that Coffer relies on — error codes, the session lifecycle, version negotiation, cancellation, server-initiated requests, optional fields it relays — are written as requirements and scenarios in Coffer's spec too, so a rule nobody wrote down cannot pass unnoticed with no test at all.

**Spec convention** — each scenario is an OpenSpec `#### Scenario: <name>` inside the `### Requirement:` it verifies, under `## Requirements` (see [openspec.md](./openspec.md) "Writing `spec.md`"):

```markdown
## Requirements

### Requirement: Manage MCP servers as resources
The system MUST ...

#### Scenario: register a stdio MCP server
- **GIVEN** ...
- **WHEN** ...
- **THEN** ...
```

The marker quotes the scenario's name, so a name is unique within its spec. The spec ID is the spec's path under `openspec/specs/` (`openspec/specs/foo/spec.md` → `foo`; a child at `openspec/specs/foo/bar/spec.md` → `foo/bar`).

**Python (pytest):**

```python
import pytest

@pytest.mark.acceptance(spec="mcp-gateway", scenario="register a stdio MCP server")
def test_register_stdio_server(...):
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
  — a marker naming a scenario that an in-flight change adds (under `ADDED` / `MODIFIED` in `openspec/changes/<name>/specs/`) is accepted and listed until that change is archived
- a marker on a test that can never run (`@pytest.mark.skip`, Rust `#[ignore]`)
- a scenario name used twice in one spec

The audit itself is stdlib-only and runs in milliseconds.

## Unit-Tier Purity Guardrail

`scripts/check_unit_purity.py` AST-scans `backend/tests/unit/**/*.py` and fails if any test imports a known I/O module (`subprocess`, `sqlite3`, `httpx`, `fastapi.testclient`, `socket`, `requests`, `urllib.request`, `aiohttp`, `keyring`). Runs as the first step of `make verify-unit`.

The unit tier's "no network, process or database I/O" rule (line 1 of the table above) was previously a culture-only constraint. Reading and writing files under pytest's `tmp_path` is allowed in the unit tier (a file-format parser or a config editor is still a single unit); the script does not police that, and anything that touches a socket, a subprocess or a database belongs in integration. The script makes it mechanical: a test that sneaks in a `from fastapi.testclient import TestClient` gets flagged with the file:line and a message pointing to integration. To add a new banned module, edit the `BANNED` dict in the script.

## Mocking Philosophy

Prefer **real over mock** when speed allows:

- Real SQLite (in-memory or temp file) for integration tests.
- Real subprocess for subprocess lifecycle tests (use short-running child processes).
- Real filesystem (under `tmp_path`).
- `keyring` test backend (in-memory) — NOT a mock; it's an alternate real implementation.

**A fake never replaces the seam under test.** A test of a callback that a library wires in (the MCP SDK's sampling and roots handlers, which it fixes when its client session is built) goes through the real library and a real peer, not a direct call of the callback. A test of what reaches a log, a process or a socket uses a peer that actually produces it (an upstream that really prints its injected secret on stderr), and asserts on the raw bytes, the exact process ids, or how many times the peer was really called — never only on a status or a mock's call list. The 2026-10-06 full MCP test found eleven defects behind a green suite; two of them lived exactly in a seam the tests had faked.

Only mock when:

- The dependency is **non-local** (external HTTP service, LLM API).
- The dependency is **non-deterministic** in a way the test cares about (system clock, randomness).
- The dependency is **slow** (only as last resort — usually means the test is the wrong tier).

## The Real-Home Guard

No test may touch the real user's home. `backend/tests/conftest.py` installs `tests/support/real_home_guard.py` before any `coffer` import; it enforces the rules below mechanically.

- **What it does.** At import: `HOME` → a throwaway dir; every inherited `COFFER_*` stripped (kept: `COFFER_RUN_*`, `COFFER_SMOKE_*`, `COFFER_TEST_*`); `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GIT_CONFIG_GLOBAL`, `XDG_*` removed; `FORCE_COLOR`, `PY_COLORS`, `TTY_COMPATIBLE`, `COLUMNS`, `LINES` removed and `NO_COLOR=1`, `_TYPER_FORCE_DISABLE_TERMINAL=1` set, so CLI output reads the same on a CI runner (which forces colour and a width) as on a laptop. Per test (autouse `_real_home_guard`): a fresh `HOME` from `tmp_path_factory` with a `.gitconfig` identity. Always: an audit hook (`sys.addaudithook`) refuses `open` / dir / rename / remove / `shutil` / `sqlite3.connect` / spawn events under the real home's `.coffer`, `.claude`, `.claude.json`, `.codex`, `.agents` — raising `RealHomeAccessError` before the syscall — and refuses a spawn whose env has no `HOME` or the real one (except `ldconfig`, which library code runs with its own env on Linux and which never reads `HOME`). Every refusal is recorded; the test fails at teardown even if the code swallowed the error. A violation outside any test fails the session.
- **Rules.**
  1. Build every path from `tmp_path` or a builder in `tests/support/homes.py`; never from the real home.
  2. A subprocess inherits `os.environ` (already isolated). If you hand-build `env=`, start from `os.environ` or `IsolatedHome.env()` — never omit `HOME`.
  3. Do not re-add a `COFFER_*` path from the developer's shell; set it with `monkeypatch.setenv` to a tmp path.
  4. Do not weaken the guard to make a test pass. `GUARD.expect_violation()` is for the guard's own tests only (`integration/isolation/test_real_home_guard.py`).
  5. A new Coffer path root (a new `COFFER_*_ROOT` or a new top-level dir under the home) must derive from `$HOME` or be pinned in the root conftest; a new agent config dir goes into `PROTECTED_NAMES`.
- **Builders** (`tests/support/homes.py`, fixtures in `tests/support/fixtures.py`) — extend these, do not write another `_setup_home`:
  - `isolated_home` / `make_home(path)` — one machine; `.activate(monkeypatch)`, `.env()` for subprocesses.
  - `two_homes` / `two_machine_homes(base)` — machines `a`, `b` + one bare remote (`bare_remote()`, also used by `integration/sync_surfaces/harness.py` and `integration/sync_thin/`).
  - `claude_code_dir`, `codex_dir` / `fake_agent_dir(home, AgentType.X, config_dir=None, files=None)` — agent config tree laid out from the descriptor; `.write(key, text)`, `.add_skill(name)`, `.home_env()`.
  - `fake_channel_adapter` / `tests.support.channel.FakeChannelAdapter` — recording IM transport (re-exported by `integration/channel/conftest.py`).
  - `tests.support.facets.agent_catalog(programs=None)` — the composition root's bound agent catalogue with every dependency probe answering "not installed" unless `programs` says otherwise (`installed(version)`); `put_programs_on_path(monkeypatch, bin_dir, {"codex": "codex-cli 1.0"})` for tests that go through the real probe (assert the state, not the version — the login shell's `PATH` may find the real program first). The shared facet contract, `integration/agent/test_facet_contract.py`, runs against `fake_agent_dir` for every shipped agent.

## Running in Parallel

The backend unit and integration tiers run on **pytest-xdist**: `make verify-unit` and `make verify-integration` pass `-n $(PYTEST_WORKERS) --dist loadgroup`, and `PYTEST_WORKERS` defaults to `auto` (one worker per core). The contract and benchmark tiers stay serial — they are small, and a benchmark measured under contention measures the contention.

- **One integration run per machine.** `make verify-integration` runs pytest through `scripts/verify_lock.py`, an `fcntl` lock on `~/.cache/coffer/verify-integration.lock`: a second run, from another worktree or session, waits for the first instead of competing with it (two runs at once slow each other until time-based tests fail). The lock dies with its holder; `COFFER_VERIFY_LOCK=off` skips it.
- **Per-test cap.** The integration tier passes `--timeout=$(PYTEST_TIMEOUT)` (default 300 s), so a hung test fails by name within minutes. A test that needs longer marks itself `@pytest.mark.timeout(seconds)`.
- **Fanning out work.** Parallel agents or worktrees run the tests for what they changed (their unit and integration folders) plus `make lint`; the full `make verify` runs once, after their work is merged, on the integration branch.
- **Serial escape hatch.** `PYTEST_WORKERS=0 make verify-integration` runs the tier in one process — for `pdb`, `-s` output that interleaves sanely, or bisecting an order-dependent failure. `PYTEST_WORKERS=4` pins the count. `PYTEST_ARGS="..."` is appended to the pytest command line (`PYTEST_ARGS="-k sync -x"`). Running pytest by hand without `-n` is serial too.
- **What each worker gets.** Every worker is its own pytest process, so it imports the root conftest and installs its own real-home guard: its own throwaway `HOME`, its own scratch root (`coffer-test-run-*`, holding the run-wide `COFFER_LOG_DIR` and the per-root defaults), its own `tmp_path_factory` base (`popen-gwN`). The controller's `COFFER_TEST_REAL_HOME` tells each worker what the real home is, so its tripwire still guards it even though the worker starts with the controller's fake `HOME`. Subprocesses a worker spawns inherit that worker's isolated `HOME`, exactly as in a serial run.
- **Writing a parallel-safe test.** Nothing a test writes may have a name another process could pick: build paths from `tmp_path`, get ports from `tests.fixtures.net.free_port()` (never a literal), and never write into the repo tree (copy the file into `tmp_path`, as `test_stamp_channel.py` does). Module-level state is per worker, so a singleton cannot leak across workers — but it still leaks across the tests one worker runs, so reset it in a fixture as before.
- **When isolation is impossible.** Mark the tests that share the resource with the same group, and xdist runs the whole group on one worker, in order:

  ```python
  pytestmark = pytest.mark.xdist_group(name="<the shared resource>")
  ```

  Use it for a resource the code under test fixes and the test cannot redirect. No test needs it today — every port, directory and log already moves per worker. Reach for it last: a group is a serial island, and the tier is only as fast as its largest one. `--dist loadgroup` is what makes the marker count; a plain `-n auto` ignores it.
- **Timeouts.** Under `-n auto` a test shares the machine with a worker per core, so a tight `@pytest.mark.timeout` or a wall-clock assertion can fail from load alone. Make the test cheaper (a smaller tree, a fake clock, a condition to wait on instead of a sleep) before widening a budget.

CI shards the integration tier as well — see [CI Jobs](#ci-jobs).

## Property-Based Tests

A rule that must hold for every input — not for three hand-picked ones — is tested as a property with `hypothesis` (a dev dependency in `backend/uv.lock`). Today: the sync deletion breaker (`tests/unit/domain/sync/test_breaker_properties.py`, checked against the threshold in integers), a stop and its answers (`test_stop_properties.py`), and a round's merge decision (`tests/unit/application/sync/test_round_merge_properties.py`, the real `RoundEngine` over the in-memory `fake_git.py`: any conflict stops, a lossy clean merge is held, and neither snapshots, checks out or pushes).

- **Profiles** (`tests/support/hypothesis_profiles.py`, loaded by the root `conftest.py`): `ci` is the default — 100 examples, derandomized (every run draws the same cases), `deadline=None`, no example database. `HYPOTHESIS_PROFILE=thorough` draws 2000 random examples for a local hunt.
- **No per-example deadline.** A deadline is a wall-clock assertion and fails on a loaded machine; keep it off.
- **A pinned dependency.** `hypothesis` is a locked dev dependency (`uv sync --frozen`); property modules import it plainly, so a venv without it fails collection instead of silently skipping.
- **A shrunk failure becomes an example test** beside the property, so the case stays pinned whatever the profile draws.
- **Check the generator reaches every branch.** `event(...)` plus `--hypothesis-show-statistics` shows each outcome's share; a property whose generator never reaches the branch it claims to cover is a vacuous test.

## Performance Budgets

Each budget is a test with a ceiling a few times above the measured cost, so it catches work that should not be there, not a busy machine. Measured 2026-10-01 on an Apple-silicon laptop under a shared load average of 6–27.

| Budget | Measured | Ceiling | Test (`backend/tests/integration/perf/`) | Runs in |
| --- | --- | --- | --- | --- |
| Daemon spawn → first `ready` `/api/v1/daemon/status`, fake `HOME`, empty vault — **CPU time** (daemon + reaped children, via `psutil`), because wall time swung 2.4–22 s with load | 2.4–2.7 s CPU | 8 s CPU (`CPU_CEILING_S`); 60 s wall only as a hang guard (`WALL_CEILING_S`) | `test_startup_time.py` | `make verify` + `verify-benchmark` |
| Gateway median overhead per tool call vs a direct upstream connection | 2–5 ms | 50 ms | `test_gateway_overhead.py` (spec mcp-gateway) | `make verify` + `verify-benchmark` |
| Steady-state reconcile pass (2 agents, 20 skills, a provider) | 27–40 ms | 2 s (`PASS_BUDGET_SECONDS`) | `test_reconcile_pass_cost.py` | `verify-benchmark` only (~1 min setup), `skipif` without `COFFER_RUN_BENCHMARKS=1` |

All three carry `pytestmark = pytest.mark.benchmark`, so `-m benchmark` selects every budget; a budget cheap enough for verify simply has no `skipif`. When a budget moves, re-measure (serially and on xdist), update the numbers here, in the test's docstring and in docs-site `contributing/testing.md` (en + zh), and keep the ceiling at 2–3× the loaded measurement.

**Flaky means a wall-clock assumption.** No test retries itself (no `pytest-rerunfailures`, no loop-until-green). A test that fails only under load is fixed at the root: replace a sleep-then-assert with a wait on the condition, bound only the thing that can hang, and never let a per-test `pytest.mark.timeout` sit within a small factor of the test's loaded runtime. A hang that shows up only under load is often a patch that reached too far: `monkeypatch.setattr(module.time, "sleep", …)` replaces `time.sleep` for every thread in the process (`subprocess.Popen.wait` polls with it), so patch the module's own name instead (`monkeypatch.setattr(module, "time", fake)`) — `test_secret_boundary.py`'s `--wait` tests once deadlocked a daemon thread inside the vault writer's lock this way.

**Why the sync tests are slow under load.** A sync integration test makes hundreds of `git` calls (one round-heavy test: ~625), so its wall time is the per-call spawn cost times that count. The thin-sync suite carries no per-test `pytest.mark.timeout` (the old `tests/integration/sync/` suite capped files at 60–180 s, which load routinely exceeded); the only wall-clock bound is `git.run`'s per-call hang guard (`LOCAL_TIMEOUT_S` 60 s, `NETWORK_TIMEOUT_S` 120 s). `git.run` resolves the real binary once (`git --exec-path`), because macOS's `/usr/bin/git` launcher measured 0.5 s median / 1.7 s max per call under load against 0.05 s for the binary. Don't pass a blanket `--timeout` to the integration tier: under load it fails sync tests that are merely slow.

## Make Targets

```bash
make verify              # fast path: lint + unit + integration + contract + acceptance audit (timed per stage)
make verify-all          # verify + e2e (full suite)

make verify-unit         # unit-purity guardrail + unit tier (xdist, PYTEST_WORKERS=auto)
make verify-integration  # integration tier only (xdist, PYTEST_WORKERS=auto)
make test-durations      # re-measure backend/.test_durations (CI shard balance)
make verify-contract     # contract tier only
make verify-benchmark    # every benchmark-marked test, including those too slow for verify
make verify-e2e          # e2e tier only (Playwright: web + mcp projects)
# ports busy? COFFER_E2E_WEB_PORT=5183 COFFER_E2E_PORT=18200 make verify-e2e
make verify-acceptance   # audit spec.md scenarios vs test markers
make verify-visual       # screenshot baseline: every route, light + dark (not in verify / verify-e2e)
make verify-secrets      # gitleaks over the full history (skips without a gitleaks binary)
make verify-installed-mcp OUT=<dir>  # opt-in: MCP acceptance against an INSTALLED Coffer (see "Installed-build Acceptance")
make visual-update       # re-record this platform's screenshot baseline

make lint                # every static gate (see below) — NOT just ruff + mypy
make format              # ruff format + ruff --fix (backend, evals, e2e/installed); prettier is run per file
```

**`make lint` is the whole static gate, not a formatter pass.** In order
(`Makefile`): `scripts/check_file_sizes.py`, `scripts/gen_contracts.py --check`
(contract freshness), `scripts/check_response_models.py`,
`scripts/check_adr_index.py`, `scripts/check_spec_citations.py`,
`scripts/check_architecture_doc.py`,
`scripts/check_pyinstaller_specs.py`, `scripts/check_cli_reference.py`,
`scripts/check_docs_locales.py`,
`scripts/check_removed_commands.py`, `scripts/check_platform_calls.py`,
`scripts/check_coffer_paths.py`, `scripts/check_agent_type_branches.py`, `scripts/check_frontend_colors.py`,
`scripts/check_ignored_sources.py`, `scripts/check_error_codes_reference.py`,
`scripts/check_bare_tasks.py`,
`ruff check` and `ruff format --check` (over `backend/`, `evals/` and `e2e/installed/`), `mypy`
(configured in `backend/pyproject.toml` with `strict = true`), `lint-imports`
(the layering + cross-kind fence), and `scripts/dump_i18n_backend_keys.py --check`
plus `npm run lint`, `npm run typecheck` and `npm run knip` in `frontend/`.
A missing `frontend/node_modules` fails `make lint` and `make verify-unit` (run
`make install`); the frontend leg is never skipped silently.
Each script gate has a one-line description in
[`harness.md` "Gates"](./harness.md#gates).

Two consequences worth internalising:

- **A docs-only edit can fail `make lint`.** `check_adr_index.py` rejects a
  dead link under `docs/decisions/` and an ADR the index does not list;
  `check_spec_citations.py` rejects a requirement citation —
  `spec <capability> "<Title>"` or a link to a capability's `spec.md` followed
  by a quoted title — whose capability or title does not exist, so renaming a
  requirement fails until every citation of the old title follows;
  `check_architecture_doc.py` holds the code-layout tree in
  `docs-site/architecture/layering.md` and the builtin-tool roster in
  `docs-site/architecture/` to the code; `check_removed_commands.py` rejects any
  `coffer` command or `coffer__` tool the CLI/MCP reshape removed wherever it is
  quoted under `docs-site/`, `README.md`, `README.zh-CN.md`, `AGENTS.md`, `CONTRIBUTING.md`,
  `.agents/`, `docs/` (except the ADRs), `openspec/specs/`, `desktop/`, the shipped skill bodies
  (`backend/coffer/**/skill_assets/`), `frontend/src/` or `e2e/` (a line that
  names one on purpose is listed in the script's `ALLOWED`). Run `make lint`
  after touching markdown, not just after touching code.
- **`lint-imports` is invoked with `PYTHONPATH=$(BACKEND)`, and that is
  load-bearing in a worktree** — a bare invocation resolves `coffer` through
  the editable install (which points at the main checkout) and reports contract
  violations for modules this tree does not have.

### Verification targets — what each one runs

| Target                    | What it runs                                                                                                                                                                                | When to use                                                                 |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `make verify`             | `lint` → `docs-build` → `verify-unit` → `verify-integration` → `verify-contract` → `verify-acceptance`, printing each stage's wall time at the end (kept in `.coffer-verify.timings`). The "pre-PR" gate. | Before every push and PR. CI runs the same tiers in parallel.               |
| `make verify-all`         | `verify` plus `verify-e2e`.                                                                                                                                                                  | Before merging anything that touches a surface (web UI, HTTP, CLI, shim).   |
| `make verify-unit`        | `scripts/check_unit_purity.py` (AST-scans for forbidden I/O imports), then `pytest -n $(PYTEST_WORKERS) --dist loadgroup backend/tests/unit` (`PYTEST_WORKERS` defaults to `auto`), then `vitest run src` in `frontend/` when its `node_modules` is present.             | Tight TDD loop on pure domain code.                                         |
| `make verify-integration` | `pytest -n $(PYTEST_WORKERS) --dist loadgroup --timeout=$(PYTEST_TIMEOUT) backend/tests/integration`, under the machine-wide lock (`scripts/verify_lock.py`).                                                                                                                                                         | After touching application services, SQLAlchemy repos, HTTP routes, or CLI plumbing. |
| `make verify-contract`    | `pytest backend/tests/contract`.                                                                                                                                                              | After adding a route or touching the MCP surface. After editing Pydantic API schemas run `make contracts` (models → contracts → frontend types); `make lint` fails on a stale contract. |
| `make verify-benchmark`   | `COFFER_RUN_BENCHMARKS=1 pytest backend/tests -m benchmark` — every perf-budget test (see "Performance Budgets"); the env var releases the ones `make verify` skips as too slow.                     | After touching the gateway hot path or any code a perf budget covers.       |
| `make verify-e2e`         | `cd e2e && playwright test` — **both** projects: `web` (Chromium over the served UI, `e2e/web/specs/*.spec.ts`) and `mcp` (`e2e/mcp/specs/*.spec.ts`, a real MCP client through the shim to the daemon and upstream servers). | After touching a page, or the daemon ↔ shim ↔ MCP-client boundary.      |
| `make verify-acceptance`  | `openspec validate --all --strict` (every requirement owns a scenario), then `scripts/audit_acceptance.py` (every scenario has a marker, every marker a scenario).                | Every spec.md edit. Cheap; needs the root `npm install` for the OpenSpec CLI. |

## Visual Baseline

`e2e/playwright.visual.config.ts` (project `visual`, `e2e/visual/specs/`) shoots
every top-level sidebar route in light and dark — the theme comes from
`emulateMedia({ colorScheme })` and is checked on `<html data-theme>` — at
1280×800, DPR 1, locale `en`, timezone UTC. It runs on its own fresh daemon
(`:18100`, HOME `/tmp/coffer-e2e-visual`, wiped each run) and its own Vite
(`:5174`), so nothing the functional suite creates shows up in the pixels. It
is the reference for UI work: a restyle that was not meant to move a page shows
up here as an image diff.

- `make verify-visual` compares; `make visual-update` re-records.
- Baselines are per platform — `e2e/visual/specs/__screenshots__/{darwin,linux}/`
  — because font rasterising differs between them. Locally a missing baseline
  fails. In CI (`test-visual`) a missing one is written instead and uploaded as the
  `visual-baseline-linux` artifact; commit its `linux/` folder to start
  comparing there.
- Update only for a deliberate visual change, and commit the new images in the
  same PR so the reviewer sees the image diff. A diff you did not intend is a
  regression, not a baseline to refresh.
- Time-dependent text (`<time>`, relative and absolute timestamps, uptime) is
  masked; animations, transitions and the caret are frozen, and the Vite-only
  TanStack Query devtools button is hidden. A page that differs between two runs
  of the same tree needs a mask or a better wait — never a looser threshold
  (`maxDiffPixelRatio` 0.001: reruns are pixel-identical, the budget only
  absorbs glyph anti-aliasing jitter).

## Installed-build Acceptance

The four tiers test **this checkout's source**, in-process or against a daemon
started from it. The installed-build suites under `e2e/installed/` test an
**installed Coffer** from the outside instead: the frozen daemon binary over
real HTTP `/mcp` and its notification stream, the installed `coffer-mcp-shim`,
and the official MCP SDK as the client. Run them before a release, and after
installing a fix, to see that what ships behaves as the source does. They are
opt-in: neither `make verify` nor `make verify-all` runs them, and CI does not.

```bash
make verify-installed-mcp OUT=/tmp/coffer-acceptance/mcp-$(date +%H%M%S)
# another target or shim:
make verify-installed-mcp OUT=<dir> DAEMON_JSON=<home>/.coffer/daemon.json SHIM=<path>/coffer-mcp-shim
```

- **Target.** `DAEMON_JSON` (default `~/.coffer/daemon.json`) names the daemon;
  it must already be running and answer `ready`. `SHIM` defaults to the
  `coffer-mcp-shim` next to the daemon binary, then
  `/Applications/Coffer.app/Contents/MacOS/`. The shim reads
  `$HOME/.coffer/daemon.json`, so the suite runs it with `HOME` set to the home
  that `DAEMON_JSON` lives in. A shim that finds no daemon starts one, so the
  suite checks the target answers right before it starts the shim.
- **Results.** `OUT` is required, must be outside the repository, and must be
  new or empty, so no run overwrites another's evidence. It receives
  `cases.json` and `summary.md` (one row per case: id, title, status, expected,
  actual, upstream request counts, evidence), `target.json` (port, pid, version,
  and the sha256 and mtime of the daemon binary and the shim), `guard.json`,
  `journal.json`, `transcript.jsonl` (every request and stream event) and the
  fixtures' ledgers. The daemon token and every canary are redacted from all of
  it.
- **Status.** A case is PASS, FAIL, BLOCKED or N/A. BLOCKED is a case that
  cannot run here, with the reason: a daemon restart, the idle reaper's window,
  or a secret binding that waits for a person's approval (a signed build,
  whose approvals need Touch ID). N/A is an observation outside the contract.
  Neither counts as a pass. The run exits 1 when any case FAILs and 2 when a
  guard refuses it. Case ids are the OpenSpec scenario title when the case
  verifies that scenario, otherwise a short stable local id.

**Safety rules**, which hold because the default target is the person's own
running app:

- Only `qa-` names are created. Every name a suite will use is reserved before
  it writes anything; if one already exists the run refuses to start, so it
  never changes or deletes what it did not create. Everything it created is
  deleted in `finally`, and the run records a case for "no `qa-` object left".
- **Sync guard.** Before any write the suite reads the target's sync state
  (`GET /api/v1/daemon/status` for the feature, `GET /api/v1/sync/remote` for
  the remote) and refuses when a remote is configured and enabled: every `qa-`
  object would be committed and pushed to the person's remote. `ALLOW_SYNC_REMOTE=1`
  overrides it. Anything the guard cannot read is a refusal.
- No restart, stop or upgrade of the daemon; the run records a case that the
  daemon is still the same process at the end. No approval is granted, and no
  shared setting (protection, features) is changed.
- Upstreams are synthetic only: `e2e/installed/mcp/upstream.py` (stdio,
  stateless and stateful Streamable HTTP, with a call ledger of
  start/done/cancelled) and its own echo receiver. No business tool is called.
  A `tools/list` through the gateway still makes Coffer list every server the
  session can see; that is the gateway's fan-out, not a tool call.
- Secrets are a random fake canary minted per run. A fixture child the target
  spawned must be gone once its server is deleted: the run checks by pid and by
  a marker path only its own fixtures carry, and records "no fixture process
  left".
- Sessions cannot be ended explicitly (`DELETE /mcp` is 405); the ones a run
  opened hold no child once its servers are deleted, and the idle reaper drops
  them.

`e2e/installed/_common/` is the shared part (arguments and target, journal,
sync guard, case recorder, process check, the run lifecycle) and stays
surface-neutral; `e2e/installed/mcp/` is the MCP suite. A `cli/` suite for the
installed `coffer` command (`--coffer`, default `~/.coffer/bin/coffer`) joins under the same `_common`.

To validate the suite itself against this checkout, start a daemon from source
under a throwaway `HOME` (with `COFFER_PORT_RANGE_START`/`_END` on free ports)
and point `DAEMON_JSON` at its `daemon.json`.

## CI Jobs

`.github/workflows/verify.yml` runs on every push to `main` and every pull request into `main`, with its jobs in parallel; the required checks on `main` are `lint`, `test-unit`, `test-integration`, `test-contract`, `audit-acceptance`, `secrets-scan` (plus the PR-title check `conventional-title`). Every job but `changes` runs exactly one Makefile target, so a red check names the command that reproduces it locally:

| Job                               | What                                                                                                                       |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `changes`                         | Classifies the pull request with `scripts/ci_change_scope.py`: `code=false` when every changed file is prose no test reads (Markdown outside `openspec/`, `.agents/`, `.claude/`, `backend/`, `frontend/`, `e2e/`, `evals/`; anything under `docs/` or `docs-site/` except `docs-site/public/`; never the root `README.md`). Pushes are always `code=true`. |
| `lint`                            | `make lint` — every static gate above, frontend included (it installs Node + `npm ci`). Always runs.                       |
| `test-unit`                       | `make verify-unit` (purity check + backend pytest on xdist + frontend vitest)                                              |
| `test-integration (N/4)`          | Four shards of `make verify-integration`, each picking its quarter with pytest-split (`--splits 4 --group N --splitting-algorithm least_duration`) balanced by the committed `backend/.test_durations`, and each running that quarter on xdist across the runner's cores. Installs `ripgrep`. |
| `test-integration`                | The required check: succeeds only when all four shards succeeded, or when they were skipped because the change is `code=false`. |
| `test-benchmark`                  | `make verify-benchmark` — every benchmark-marked perf-budget test, and the **only** place the slow ones (gated on `COFFER_RUN_BENCHMARKS=1`) execute, so a budget can't go unchecked while its acceptance marker reports green |
| `audit-acceptance`                | `make verify-acceptance`: `openspec validate --all --strict` (needs the root `npm ci`), then `scripts/audit_acceptance.py`. Always runs. |
| `secrets-scan`                    | `gitleaks` over the full history (`fetch-depth: 0`) through gitleaks-action — the scan `make verify-secrets` runs locally. A committed secret fails the PR even if the final tree is clean. Always runs. |
| `test-contract`                   | `make verify-contract`                                                                                                     |
| `test-e2e`                        | `make verify-e2e` (installs Chromium; runs the `web` and `mcp` projects)                                                   |
| `test-visual`                     | `make verify-visual`, uploading the linux baselines and diffs as the `visual-baseline-linux` artifact. Report-only (`continue-on-error`): a failure is reported, not blocking, until the baselines are committed |

The test jobs are skipped only on an explicit `code=false`: if `changes` itself fails they run anyway. A job skipped by its condition reports success, which is how a docs-only PR still shows every required check green.

**Shard balance.** A test missing from `backend/.test_durations` is weighed at the average, so a stale file only unbalances the shards — it never drops a test. When one shard runs clearly longer than the others, run `make test-durations` (serial, ~15 min) and commit the file. Changing the shard count means editing both the `shard` matrix and `--splits`.

`.github/workflows/ci.yml` runs one full `make verify` on every push to `main` and `feature/**` and on manual dispatch; it inherits the xdist default from the Makefile. The same workflow runs a weekly latest-dependencies canary (Mondays 06:00 UTC) that re-resolves the `>=` floors instead of the frozen lock, so an upstream release that breaks Coffer shows up on a schedule.
