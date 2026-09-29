---
title: Testing
description: Coffer's four test tiers, where each lives and how to run it, the real-home guard and isolated homes, acceptance markers, the mocking philosophy, every gate make verify runs, and the CI workflows.
---

# Testing

This page covers how Coffer is tested: the four tiers and where each lives, how to run them, how the suite keeps tests away from your real home, how tests link to spec scenarios, what counts as a good test here, and every gate that `make verify` and CI apply. The full convention is in [`.agents/testing.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/testing.md).

The standard is simple to state: **a green `make verify` plus `make verify-e2e` must mean the product works**, with no manual re-testing.

## The four tiers

| Tier | Tests what | Lives in | Budget per test | Run with |
| --- | --- | --- | --- | --- |
| **Unit** | Pure logic: domain functions, value objects, one class. No I/O | `backend/tests/unit/`, plus colocated `frontend/src/**/*.test.ts(x)` | < 100 ms | `make verify-unit` |
| **Integration** | Several modules with real local infrastructure: real SQLite, real subprocesses, real filesystem, the `keyring` test backend. No network | `backend/tests/integration/` | < 2 s | `make verify-integration` |
| **Contract** | Wire conformance that freshness cannot see: every route the daemon serves has an owning capability, and the MCP endpoint and built-in tools behave as the protocol and the specs say | `backend/tests/contract/` | < 1 s | `make verify-contract` |
| **E2E** | The assembled product through real surfaces: a browser against the UI, and a real MCP client through the shim and daemon to upstream servers | `e2e/web/specs/`, `e2e/mcp/specs/` | < 30 s | `make verify-e2e` |

The budgets are guidance, not gates. A test that drifts an order of magnitude past its budget is a hint that it belongs in another tier.

The suite is deliberately **integration-heavy**: integration ≫ unit > contract > e2e by count. The integration tier runs against real SQLite files and real subprocesses and is still fast, so most behaviour is pinned where the real wiring lives. The unit tier is kept for pure logic, and a script enforces that (see [unit purity](#unit-purity)).

### Running tests

```sh
make verify-unit                     # purity check, backend unit, frontend Vitest
make verify-integration
make verify-contract
make verify-e2e                      # both Playwright projects

# one file or one test
.venv/bin/python3 -m pytest backend/tests/integration/surfaces/http/test_feature_routes.py -q
.venv/bin/python3 -m pytest backend/tests -k "dev_channel" -q
cd frontend && npx vitest run src/components/PageHeader.test.tsx
cd e2e && npx playwright test --project=web shell_skills
```

`make verify-benchmark` runs the perf-budget tests marked `benchmark` with `COFFER_RUN_BENCHMARKS=1`. `make verify` excludes them, and a separate CI job runs them. `make coverage` produces pytest and Vitest coverage reports. Use it to find untested branches, not as a target.

## What a good test looks like

Every function, HTTP route and CLI command has a test that asserts its real result: status and body, exit code and output, or the resulting state. It also covers the error and edge branches. Every scenario in a spec is driven through a real surface by at least one test. A test earns its place only if it would fail on a real regression. Reviewers reject:

- **Tautologies.** Asserting a literal you just passed through untransformed.
- **Missing assertions.** Checking only "did not raise", `status_code == 200` or `exit_code == 0` when the real contract is cheap to check. Asserting only a code is fine when the code *is* the contract, such as `401` for missing auth.
- **Vacuous loops and conditionals.** `for x in results: assert …` with no guard that `results` is non-empty.
- **Over-mocking.** Mocking the unit under test, so the test only verifies the mock.
- **Assertions too loose to fail.** `len(x) >= 0`, or a latency ceiling 100 times the real value.

### Mocking philosophy

Prefer the real thing whenever it is fast enough:

- real SQLite, in memory or in a temporary file
- real subprocesses, using short-running children
- the real filesystem, under `tmp_path`
- the `keyring` test backend, an alternate real implementation rather than a mock

Mock only what is **non-local** (an external HTTP service, an LLM API), **non-deterministic** in a way the test cares about (the clock, randomness), or, as a last resort, **slow**. A test that needs to mock something slow is often in the wrong tier.

### Tests run in parallel

The backend unit and integration tiers spread their tests across one worker process per core, which turns the integration tier from the slowest step of a local verify into one of the quicker ones. Each worker is a complete, separate test run: it gets its own throwaway home, its own scratch directory and its own temporary folders, so the protections described below hold in every worker exactly as they do in a single process.

When you need one process — to step through a test in a debugger, to read output that is not interleaved, or to chase a failure that depends on test order — set the worker count to zero and the tier runs serially.

For a test to be safe alongside others, nothing it creates may have a name another process could choose too. Build files inside the test's own temporary directory, ask the operating system for a free port instead of writing one down, and never write into the checkout itself. When a test depends on something the code under test fixes and the test cannot move, mark it as belonging to a named group: every test in a group runs on the same worker, one after another. Use this last, because each group is a small serial island inside the parallel run.

### Tests never touch your real home

Nearly everything Coffer keeps on disk lives under your home directory: the vault with its database, notes and logs, and the configuration of the coding agents that Coffer connects to. A test that forgets to point one of those somewhere else does not fail. It quietly runs against your real data.

This has happened. When the setting that locates the knowledge tree was left unset, Coffer fell back to the default location in the home directory. A test that started the app without setting it ran the knowledge migration over a developer's real vault and moved their files. Setting one more variable would only have closed that one path, so the suite now enforces the rule for every path at once, in two layers.

**Redirect the home.** Before any Coffer code loads, the test run points the home directory at a throwaway location. It also drops every Coffer setting inherited from your shell, along with the variables that could send an agent or git to a different directory. Each test then gets a fresh home of its own, already set up so git can commit in it. Programs that a test starts, such as the daemon, the MCP shim or the command line, inherit the same throwaway home, so they cannot reach the real one either.

**A tripwire on the real home.** Redirection can still be undone, most easily by a test that changes or removes the home variable. Without one, the system falls back to your real home. So the suite also watches the interpreter's own file, database and process-start events. Any attempt to read or write inside Coffer's directory or an agent's configuration directory under your real home is refused *before* it happens, so nothing is ever written. Starting a program with no home set, or with the real one, is refused the same way. Each refusal is also recorded, because code that tolerates an unreadable file might quietly swallow the error. The test then fails with a list of what it tried to touch, even when nothing else went wrong. A dedicated set of tests proves this: they aim at the real home on purpose, and they check both that every attempt is refused and that nothing appeared.

If the tripwire fails your test, the message names each path. The fix is almost always to build that path inside the test's own temporary directory, or to use one of the isolated setups below. Do not point anything at your real home.

### Isolated homes

In a test, a "machine" is simply a home directory. The suite provides ready-made isolated setups, so a test never has to assemble its own:

- **A single machine.** A fresh home that the test process is already using. Coffer derives every one of its directories from it, exactly as an installed copy would. The same home can be handed to a program the test starts, so the program runs as that machine.
- **Two machines sharing a remote.** Two independent homes that share nothing except one real git repository they can both reach. Vault sync scenarios are played out between them through the real sync code and real git, with nothing faked.
- **Fake agent configuration.** An agent's configuration directory, such as Claude Code's or Codex's, laid out inside an isolated home from the same description of that agent that Coffer itself uses. A file the test writes therefore lands exactly where Coffer will look for it. Both the default location and a custom one are supported.
- **A fake chat channel.** A stand-in for an instant-messaging platform. It records everything Coffer sends (messages, cards, edits, typing indicators, reactions, files) and lets a test deliver incoming messages and button taps. Its capabilities can be switched on and off, so the same fake can act like a platform that edits messages in place or like one that streams its replies.

When a test needs a new kind of isolated setup, add it next to these rather than building a one-off inside a single test file.

## Acceptance markers

Every `#### Scenario:` in `openspec/specs/**/spec.md` needs at least one covering test in any tier. The test carries a marker that quotes the capability id and the scenario name:

::: code-group

```python [pytest]
@pytest.mark.acceptance(
    spec="experimental-features", scenario="a source build reports the dev channel"
)
async def test_status_reports_the_dev_channel_and_every_feature_unauthenticated(client): ...
```

```ts [Vitest]
import { acceptance } from "@/test/acceptance";

acceptance("chat", "chat runs on the built-in model when no connection", () => {
  // ...
});
```

```ts [Playwright]
import { acceptance } from "./_acceptance";

acceptance("web-ui", "legacy /audit redirects to activity", async ({ page }) => {
  // ...
});
```

```rust [Rust]
// acceptance(spec = "desktop-app", scenario = "a spawned daemon outlives the app")
#[test]
fn a_spawned_daemon_leaves_the_apps_process_group() { /* ... */ }
```

:::

`make verify-acceptance` runs two checks. First, `openspec validate --all --strict` fails any requirement without a scenario. Then `scripts/audit_acceptance.py` fails on:

- a scenario with no covering marker
- a marker naming a capability or scenario that does not exist
- a marker on a test that can never run (`@pytest.mark.skip`, Rust `#[ignore]`)
- a scenario name used twice in one spec

The pytest marker is registered in `backend/pyproject.toml` and runs under `--strict-markers`. The TypeScript audit strips comments first, so commented-out calls do not count. A Rust marker counts only when a `#[test]` or `#[tokio::test]` follows it before the next `fn`. Rust tests run under `make desktop-test` and the `desktop` workflow, not under `make verify`. See [Spec-driven workflow](/contributing/spec-workflow#acceptance-scenarios-and-markers) for how scenarios are written.

## Unit purity

`scripts/check_unit_purity.py` runs first in `make verify-unit`. It parses every file under `backend/tests/unit/` and fails on an import of an I/O module: `subprocess`, `sqlite3`, `httpx`, `fastapi.testclient`, `socket`, `requests`, `urllib.request`, `aiohttp` or `keyring`. The failure message names the file and line and points you to the integration tier. To ban another module, add it to the `BANNED` dict in the script.

## End-to-end tests with Playwright

`e2e/playwright.config.ts` defines two projects, and `make verify-e2e` runs both:

| Project | Specs | What it drives |
| --- | --- | --- |
| `web` | `e2e/web/specs/*.spec.ts`: `agent_workspace` and the `shell_*` specs for activity, agents, cold start, knowledge, MCP flows, settings and skills | Chromium against the web UI |
| `mcp` | `e2e/mcp/specs/*.spec.ts`: round trips over stdio and HTTP, concurrent clients, capability disable, a mutating upstream, upstream crash recovery | A real MCP client → `coffer-mcp-shim` (stdio) → daemon (`/mcp`) → upstream MCP servers. No browser |

Before the first run:

```sh
make install-e2e-browsers            # Playwright's Chromium
make verify-e2e                      # or: cd e2e && npx playwright test [--project=web|mcp]
```

Playwright starts two web servers:

- **The daemon.** `e2e/scripts/start_daemon.sh` runs it under a fresh temporary `HOME`, with `COFFER_DB_URL` inside it, a port range starting at `18000`, and `COFFER_DEV_CORS=1`. It waits up to 45 seconds for port 18000 to be free, and records the chosen home in `/tmp/coffer-e2e-home.path`. It puts this checkout's `backend/` on `PYTHONPATH` and refuses to start if `coffer` still resolves to another checkout, so the suite cannot silently test the wrong tree.
- **Vite** on port 5173, with `VITE_COFFER_BASE_URL=http://127.0.0.1:18000/api/v1`. The Vite server is never reused, because a leftover `make dev` Vite would point at the wrong daemon.

::: warning Changing the ports
The daemon's development CORS allowlist is fixed to `http://localhost:5173` and `http://127.0.0.1:5173`. If you serve the UI from any other port, also set `COFFER_CORS_ORIGINS` to that origin. It replaces the allowlist entirely. Without it, the daemon refuses every browser request with `403 ORIGIN_NOT_ALLOWED`, the page reports "Failed to fetch", and the `web` specs fail even though nothing is broken.
:::

On a CI failure, the `e2e` job uploads the Playwright report and traces, plus the isolated daemon's log directory and `daemon.json`, as workflow artifacts.

## Frontend tests

Frontend tests use Vitest and Testing Library in a jsdom environment. Each test sits next to the module it covers (`*.test.ts`, `*.test.tsx`), and `make verify-unit` runs them all with `npx vitest run src`. `src/test/setup.ts` loads the real i18n catalogues, so components render real copy. Render with a real `QueryClientProvider` and mock only the network boundary: the `src/lib/api/*` module, or `streamClient` for chat. See [Frontend](/contributing/frontend#testing) for conventions.

Use **Node 20**, the version CI uses, when you run the frontend suite locally.

## What `make verify` runs

`make verify` runs `lint`, then `verify-unit`, `verify-integration`, `verify-contract` and `verify-acceptance`. When everything passes, it writes `.coffer-verify.stamp`, a content fingerprint of the source files. The Claude Code harness hook reads that stamp and warns when a commit happens while it is stale. `make verify-all` adds `verify-e2e`.

`make lint` is the whole static gate, not only a formatter pass. It runs these steps in order:

| Gate | What it protects |
| --- | --- |
| `scripts/check_file_sizes.py` | File-size limits: backend Python and desktop Rust ≤ 400 lines, frontend page ≤ 200, component ≤ 250, hook and utility ≤ 300. Generated files are excluded |
| Contract freshness | Each capability's `api.openapi.yaml` is regenerated from the Pydantic models and must equal the checked-in file, and every served route must belong to a capability. Fix with `make contracts` |
| `scripts/check_response_models.py` | Every FastAPI route declares `response_model=` (or `response_class=` for streaming and file responses), so no route returns an untyped `dict` |
| `scripts/check_doc_numbering.py` | Specs, ADRs and requirements stay named, not numbered. Links inside `docs/decisions/` resolve, and the ADR index lists exactly the ADRs that exist |
| `scripts/check_spec_citations.py` | Every `spec <capability> "<Title>"` citation in any tracked file names a real requirement, and retired id forms stay out |
| `scripts/check_architecture_doc.py` | The code-layout tree in `docs-site/architecture/layering.md` names every package, names nothing that is gone, and the architecture pages name every built-in `coffer__*` tool |
| `scripts/check_pyinstaller_specs.py` | The three PyInstaller specs point at files that exist and keep the `-X utf8` runtime option. No pull request job runs PyInstaller, so this is the only early warning |
| `scripts/check_cli_reference.py` | This site's generated CLI and REST API reference pages match the code. Fix drift with `make docs-reference` |
| `scripts/check_removed_commands.py` | No page under `docs-site/`, shipped skill body or e2e spec quotes a `coffer` command or `coffer__` tool that the CLI and MCP reshape removed. Each hit names the command to use instead |
| Platform-check gate | No code outside the platform part of the infrastructure layer asks which operating system it runs on. Tests are exempt. See [Platform port](/architecture/platform) |
| `ruff check`, `ruff format --check` | Lint and formatting over `backend/` and `evals/`, under the rules in `backend/pyproject.toml` |
| `mypy --strict` | Type-checks the whole `coffer` package |
| `lint-imports` | Import-linter contracts: the layer direction (`surfaces` → `application` → `domain`), a pure `domain`, `keyring` confined to the credentials code, no cross-kind imports between kinds, and specific libraries confined to their adapters |
| `scripts/dump_i18n_backend_keys.py --check` | Every backend error code and audit event type has an entry in the fixture that the frontend's locale-coverage test reads, so none ships untranslated |
| `npm run lint` | `codegen:check` (generated API types match the contracts, and no wire type in the API modules is written by hand), then ESLint |
| `npm run typecheck` | `tsc` over the frontend |
| `npm run knip` | Dead frontend code: unused files, exports and dependencies |

The four frontend steps are skipped when `frontend/node_modules` is missing. CI always installs it. `lint-imports` runs with `PYTHONPATH=backend` so that in a git worktree it analyses this checkout rather than the one the editable install points at.

::: tip Docs-only changes can fail `make lint`
The citation, numbering, architecture-doc and reference gates all read Markdown. Run `make lint` after editing docs too.
:::

The pre-commit hooks from `make hooks` add fast checks at commit time: trailing whitespace, end-of-file, YAML, TOML and JSON syntax, merge-conflict markers, large files, ruff, prettier and commitlint on the message.

## CI workflows

| Workflow | Trigger | What it runs |
| --- | --- | --- |
| `verify.yml` | Pull requests to `main`, pushes to `main` | Parallel jobs: `lint`, `test-unit`, `test-integration`, `test-benchmark`, `audit-acceptance`, `secrets-scan` (gitleaks over the full history), `test-contract`, `test-e2e`. The integration tier is split into four shards that run side by side, balanced by how long each test took last time it was measured, with one final check that passes only when every shard passed. A pull request that changes only documentation no test reads skips the test jobs; the gates that check documentation still run, and the skipped checks count as passed |
| `ci.yml` | Pushes to `main` and `feature/**`, weekly schedule | One `make verify` job. The scheduled run is the **latest-deps canary**: it installs with `uv sync --upgrade` instead of the lockfile, so an upstream release that breaks Coffer shows up on a schedule |
| `pr-title.yml` | Pull request opened or edited | The title against `.commitlintrc.yaml` |
| `desktop.yml` | Changes to `desktop/**` or the `Makefile` | `make desktop-lint` and `make desktop-test` |
| `evals.yml` | Changes to `evals/` or to the MCP, knowledge or memory code | `make eval`: the deterministic eval suites, gated on regression against the committed baseline |
| `pages.yml` | Changes to `docs-site/**` | Builds this site, and deploys it from `main` |
| `release.yml` | A `v*` tag | Frozen binaries, the CLI archive and the desktop `.dmg` for macOS on Apple Silicon, then a GitHub Release |

Every backend install in CI is frozen from `backend/uv.lock`, except the canary. A red canary means an upstream release broke something, not that your lockfile drifted.

## Evals

Some behaviour is non-deterministic or ranking-based, such as tool search and tool routing. It is measured by the eval harness in [`evals/`](https://github.com/wyx-sg/Coffer/tree/main/evals) rather than by pass/fail tests. `make eval` runs the deterministic suites and fails on regression against the committed baseline. `make eval-routing` adds a suite that needs a local LLM. `make eval-curate` turns captured real queries into labelled golden cases. [`.agents/harness.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/harness.md) describes the capture, curate and gate loop.

## Related

- [Development setup](/contributing/development)
- [Spec-driven workflow](/contributing/spec-workflow)
- [Frontend](/contributing/frontend)
- [Layering and code layout](/architecture/layering)
