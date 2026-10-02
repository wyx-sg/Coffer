---
title: Development setup
description: Install Coffer from source, run the daemon and web UI against a throwaway vault, find your way around the repository, and build the frozen binaries and desktop app.
---

# Development setup

This page takes you from a fresh clone to a running daemon and web UI built from your checkout. It also covers every `make` target, contract and frontend codegen, release builds, and working in git worktrees. It is written for contributors on macOS or Linux. The desktop app is built on macOS only.

## Prerequisites

| Tool | Version | Needed for |
| --- | --- | --- |
| Python | 3.12 (`.python-version`; `requires-python = ">=3.12"`) | Backend, CLI, MCP shim, every repository gate |
| [uv](https://docs.astral.sh/uv/) | any recent | Installing the locked dependency set, `make lock` |
| Node.js + npm | 20, the version every CI job uses | Web UI, the OpenSpec CLI, Playwright |
| ripgrep (`rg`) | any | Knowledge curation, used by integration tests (CI installs it) |
| git | 2.40 or later (`merge-tree --write-tree --merge-base`) | The vault is a git repository: the daemon refuses to start without git, and the vault and sync tests run it |
| Rust toolchain ([rustup](https://rustup.rs)) + Xcode command line tools | stable | Only the desktop shell (`make desktop*`) |

::: warning Use Node 20
CI runs Node 20. Other major versions can behave differently in the test runner. For example, Node 22 ships a built-in Web Storage that breaks `localStorage` under jsdom, which `frontend/src/test/setup.ts` has to work around. If the frontend suite fails locally but not in CI, check `node --version` first.
:::

## Install

```sh
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
make install      # .venv from uv.lock + frontend, OpenSpec CLI and e2e npm deps
make hooks        # pre-commit and commit-msg git hooks
```

`make install` needs [uv](https://docs.astral.sh/uv/). It syncs the backend and its dev extras from `backend/uv.lock` into `.venv` exactly as CI does, with the backend itself editable:

```sh
UV_PROJECT_ENVIRONMENT=.venv uv sync --frozen --extra dev --project backend --python 3.12
```

It then runs `npm install` in `frontend/`, at the repository root (for the pinned OpenSpec CLI) and in `e2e/`. Browsers for the end-to-end suite are a separate, heavy download: `make install-e2e-browsers`.

::: tip When a local result disagrees with CI
Re-run `make install` before you debug anything else. A venv that drifted from the lock, for example after a `pip install` of the `>=` floors, is the most common reason a test fails locally but passes in CI.
:::

## Run Coffer from source

### The quick way: `make dev`

```sh
make dev
```

`make dev` starts the daemon from `backend/` through its real entry point, `python -m coffer.infrastructure.daemon.entry`, with `COFFER_DEV_CORS=1`. It waits until `~/.coffer/daemon.json` exists and `GET /api/v1/daemon/status` answers, and then starts Vite on `http://localhost:5173`. A Vite plugin reads `daemon.json` and injects the daemon's port and API token into the page, so the UI is signed in without any setup. Press Ctrl-C to stop both processes. Backend changes need a restart, because the daemon runs without auto-reload.

::: danger `make dev` uses your real vault
Run as-is, `make dev` reads and writes `~/.coffer`, which holds your real vault (configuration, knowledge, skills and secrets), history and memory. It also writes to your agents' configuration under your home directory, such as `~/.claude`. It also binds port 8000. If an installed Coffer is already running there, the dev daemon refuses to start and does not fall back to another port. Use a sandbox, as described next.
:::

Always start the daemon through `coffer.infrastructure.daemon.entry`, never with a bare `uvicorn coffer.main:app`. The entry point allocates the port, mints the API token and writes `daemon.json`. Without it every token-gated endpoint answers `503`.

### Run against a throwaway vault

Every path Coffer uses is derived from `HOME`: `~/.coffer/` and the agent configuration directories it manages. Point `HOME` at a temporary directory and give the daemon its own port range. The result is a fully isolated instance that can run next to your installed Coffer:

```sh
export HOME="$(mktemp -d -t coffer-dev)"
export COFFER_PORT_RANGE_START=18150 COFFER_PORT_RANGE_END=18159
make dev
```

With a port range set, the daemon binds the first free port in the range instead of insisting on 8000. `make dev` and the Vite plugin both read the chosen port from the sandbox's `daemon.json`. In a second terminal, export the same three variables and use the CLI against the sandbox:

```sh
.venv/bin/coffer daemon status
```

```text
status:  ready
version: 0.2.0
port:    18150
```

::: warning Export the variables in every shell
A `coffer` command that needs a daemon starts one when it finds none. If you run the CLI with your real `HOME`, it talks to your real vault. If you run it with the sandbox `HOME` but without the port range, it tries to start a second daemon on port 8000.
:::

Vite always serves on port 5173 (`strictPort`). If another checkout's `make dev` already holds that port, the frontend half fails with `Port 5173 is already in use`, and the daemon half keeps running.

The source daemon also serves the built UI at its own origin when `frontend/dist/index.html` exists. After `npm run build --prefix frontend`, open `http://127.0.0.1:<port>/` to see exactly what a release serves.

### Environment variables for development

| Variable | Effect |
| --- | --- |
| `COFFER_PORT_RANGE_START`, `COFFER_PORT_RANGE_END` | Bind the first free port in this range instead of the configured fixed port (default 8000) |
| `COFFER_DEV_CORS=1` | Allow the Vite origins `http://localhost:5173` and `http://127.0.0.1:5173`, plus the desktop shell's origins. Without it the daemon refuses requests from those origins with `403 ORIGIN_NOT_ALLOWED` |
| `COFFER_CORS_ORIGINS` | Comma-separated list that replaces the CORS allowlist entirely, shell origins included. Use it when your UI runs on any other origin |
| `HOME` | Every Coffer tree — the vault, `local/`, `content/`, `derived/`, `runs.db` — resolves from it; there is no per-tree override. A sandbox `HOME` is a separate Coffer |
| `COFFER_DB_URL` | SQLAlchemy URL of the history database (default `sqlite+aiosqlite:///~/.coffer/runs.db`) |
| `COFFER_LOG_DIR` | Where the daemon writes its log files |
| `COFFER_FEATURES` | Pin experimental features for this daemon, as `<key>=on,<other-key>=off`. For example `models=on,sync=off`; the keys are `knowledge`, `memory`, `sync` and `models`, and each is off unless pinned or switched on in Settings |
| `COFFER_WEBUI_DIR` | Serve a built UI from another directory |

The [configuration reference](/reference/configuration) lists every variable the daemon reads.

::: danger Tests must never see your real vault
`backend/tests/conftest.py` points `HOME` at a throwaway directory and strips every inherited `COFFER_*` variable before any test module is imported, gives every test its own `HOME`, and pins `COFFER_LOG_DIR`. A tripwire (`tests/support/real_home_guard.py`) also refuses, and fails the test for, any file, SQLite or spawn event under the real `~/.coffer`. Because every tree resolves from `HOME`, a fresh `HOME` isolates all of them. If you write a script or fixture outside pytest that starts the app, give it its own `HOME`.
:::

## A tour of the repository

| Path | What it holds |
| --- | --- |
| [`backend/coffer/`](https://github.com/wyx-sg/Coffer/tree/main/backend/coffer) | The Python package, in four layers: `domain/`, `application/`, `infrastructure/`, `surfaces/`. See [Layering and code layout](/architecture/layering) |
| `backend/tests/` | `unit/`, `integration/` and `contract/` test tiers |
| `backend/*.spec` | PyInstaller specs for `coffer`, `coffer-daemon` and `coffer-mcp-shim` |
| `backend/pyproject.toml`, `backend/uv.lock` | Dependencies, ruff, mypy, pytest and import-linter configuration |
| [`frontend/`](https://github.com/wyx-sg/Coffer/tree/main/frontend) | The React web UI. See [Frontend](/contributing/frontend) |
| [`desktop/`](https://github.com/wyx-sg/Coffer/tree/main/desktop) | The Tauri 2 desktop shell (Rust) that hosts the same `frontend/dist` |
| [`e2e/`](https://github.com/wyx-sg/Coffer/tree/main/e2e) | Playwright suites: `web/` (browser), `mcp/` (MCP client to shim to daemon) and `visual/` (screenshot baselines, `make verify-visual`) |
| [`evals/`](https://github.com/wyx-sg/Coffer/tree/main/evals) | Eval harness for tool search and tool routing, with datasets and baselines |
| [`openspec/`](https://github.com/wyx-sg/Coffer/tree/main/openspec) | The product contract: `specs/` (current), `changes/` (in flight and archived) |
| [`docs/`](https://github.com/wyx-sg/Coffer/tree/main/docs) | `decisions/` (ADRs), `research/` and `skill-library/`. Principles and architecture live in this site, under [Architecture](/architecture/) |
| `docs-site/` | This VitePress site |
| [`scripts/`](https://github.com/wyx-sg/Coffer/tree/main/scripts) | Repository gates (`check_*.py`, `audit_acceptance.py`) and build scripts |
| `.agents/` | Convention files for contributors and agents |
| `.claude/` | The agent harness: settings, hooks, OpenSpec commands and skills |
| `.github/workflows/` | CI, release, docs-site and desktop workflows. See [Testing](/contributing/testing#ci-workflows) |

## Make targets

Run `make help` for the same list.

| Target | What it does |
| --- | --- |
| `make install` | Sync `.venv` from `backend/uv.lock` (backend editable, dev extras), and run `npm install` for frontend, OpenSpec CLI and e2e |
| `make install-e2e-browsers` | Download Playwright's Chromium build |
| `make hooks` | Install the pre-commit and commit-msg git hooks (trailing whitespace, YAML/TOML/JSON checks, ruff, prettier, commitlint) |
| `make dev` | Run the daemon and Vite together (see above) |
| `make verify` | `lint`, `verify-unit`, `verify-integration`, `verify-contract` and `verify-acceptance` in order, printing each stage's time, then record a freshness stamp. The pre-PR gate |
| `make verify-all` | `verify` plus `verify-e2e` |
| `make verify-unit` | The unit-purity check, backend unit tests, then the frontend Vitest suite |
| `make verify-integration` | Backend integration tests |
| `make verify-contract` | Backend contract tests: every served route has an owning capability, and the MCP endpoint behaves as the protocol says |
| `make verify-e2e` | Both Playwright projects, `web` and `mcp` |
| `make verify-acceptance` | `openspec validate --all --strict`, then `scripts/audit_acceptance.py` |
| `make openspec-validate` | Only the OpenSpec strict validation |
| `make verify-benchmark` | Every perf-budget test marked `benchmark`, including the ones too slow for `verify` |
| `make verify-secrets` | gitleaks over the full git history, as CI's `secrets-scan` job runs it. Skips when gitleaks is not installed |
| `make lint` | Every static gate: see [Testing](/contributing/testing#what-make-verify-runs) |
| `make format` | `ruff format` and `ruff check --fix` over `backend` and `evals`. The frontend is formatted by its own prettier setup, not by this target |
| `make verify-visual` | Screenshot baseline: every route, light and dark. Not part of `verify` or `verify-all` |
| `make visual-update` | Re-record this platform's screenshot baseline |
| `make test-durations` | Re-measure test durations for the integration shard balance (serial, about 15 minutes) |
| `make coverage` | pytest and Vitest coverage reports, with no thresholds |
| `make eval` | The deterministic eval suites and the baseline gate |
| `make eval-routing` | Adds the tool-routing suite (needs a local LLM) |
| `make eval-curate` | Turn captured tool-search queries into labelled golden cases (`ARGS=--dry-run`) |
| `make lock` | Refresh `backend/uv.lock` from `pyproject.toml` |
| `make contracts` | Regenerate every capability's wire contract from the backend's models, then the frontend's types from those contracts |
| `make frontend-codegen` | Regenerate only the frontend's TypeScript API types from the checked-in contracts |
| `make docs-reference` | Regenerate the CLI reference pages of this site (English and Chinese) |
| `make docs-build` | Build this site the way the Pages workflow does; fails on a dead internal link |
| `make refresh-prices` | Refresh the bundled model price list (needs the network; not in `verify`) |
| `make bundle-binaries` | Freeze `coffer`, `coffer-daemon` and `coffer-mcp-shim` with PyInstaller into `dist/` |
| `make desktop` | Build the unsigned `Coffer.app` and `.dmg` (slow: see below) |
| `make desktop-lint` | `cargo check` and `cargo clippy -D warnings` on the desktop crate |
| `make desktop-test` | `cargo test` on the desktop crate |
| `make desktop-stage-binaries` | Stage placeholder sidecar binaries so cargo can compile without a real build |
| `make clean` | Remove `.venv`, `node_modules`, `frontend/dist`, caches and desktop build output |

## Wire contracts and frontend codegen

The wire runs in one direction: the backend's Pydantic models are the only hand-written description of the HTTP API. Each capability's OpenAPI file, `openspec/specs/<capability>/contracts/api.openapi.yaml`, is generated from them and checked in, so a change to the wire shows up as a diff in the pull request that causes it. The frontend's types are generated from those files in turn. Change a model, then regenerate both:

```sh
make contracts                 # models → contracts → frontend types
make frontend-codegen          # only the last step (= cd frontend && npm run codegen)
```

The contracts are cut from the daemon's own OpenAPI document, built without starting the daemon, and split by which capability owns each route. The output is deterministic, so two people regenerating the same models get the same bytes. `make lint` regenerates the contracts in memory and fails when a checked-in file differs, and when the daemon serves a route that no capability owns. `npm run lint` starts with `codegen:check`, which does the same for the frontend's generated types, and then refuses a wire type written by hand in the frontend's API modules. Never edit a contract or `generated/` by hand. Rerun `make contracts` after rebasing onto a `main` that changed a model.

## Build the frozen binaries

```sh
npm run build --prefix frontend   # first: the daemon binary embeds frontend/dist
make bundle-binaries              # dist/coffer, dist/coffer-daemon, dist/coffer-mcp-shim
bash scripts/smoke_test_bundle.sh dist
```

`coffer-daemon.spec` bundles `frontend/dist` only if `frontend/dist/index.html` exists. If you skip the frontend build, you get a daemon that runs but serves no UI. The smoke test starts the bundled daemon under an isolated `HOME`, checks that it serves the web UI, and completes one MCP `initialize` round trip through the bundled shim.

`scripts/check_pyinstaller_specs.py` (part of `make lint`) keeps the three `.spec` files level with the tree, because no CI job on a pull request runs PyInstaller.

## Build the desktop app

```sh
make desktop
```

This builds `frontend/dist`, runs `make bundle-binaries`, stages the three binaries under `desktop/binaries/` with the Rust host triple as a suffix, and runs the Tauri 2 CLI. The unsigned `.app` and `.dmg` land in `desktop/target/release/bundle/`. Expect it to take around 50 minutes on a laptop, most of it PyInstaller. A locally built app runs. A downloaded copy of an unsigned build is blocked by Gatekeeper.

For day-to-day work on `desktop/src/*.rs`, you do not need a full build:

```sh
make desktop-lint    # cargo check + clippy, placeholders staged automatically
make desktop-test    # cargo test
```

The desktop crate is not part of `make verify`. The `desktop` workflow runs these two targets on pull requests that touch `desktop/`. The shell's architecture is covered in [Desktop app](/guides/desktop-app) and [Distribution and releases](/architecture/distribution).

## Work in git worktrees

The maintainer, and often several AI agents at once, work in parallel [git worktrees](https://git-scm.com/docs/git-worktree), one branch per worktree:

```sh
git worktree add ../coffer-my-fix -b fix/my-fix main
cd ../coffer-my-fix && make install
```

Keep these caveats in mind:

- **`.git` is shared.** `origin/main` moves under you whenever any worktree fetches. Rebase deliberately rather than assuming `main` is where you left it.
- **The stash is shared too.** `git stash` in one worktree pushes to the same stack every other worktree sees, and a bare `git stash pop` can apply someone else's work. Prefer a temporary WIP commit. If you must stash, name the entry (`git stash push -m "<tag>"`) and apply it by its SHA.
- **Give each worktree its own `.venv`.** The backend is installed editable, so a `.venv` symlinked from another checkout imports that checkout's code. Your tests would then pass against the wrong tree. Two gates guard against this: `make lint` runs `lint-imports` with `PYTHONPATH=backend`, and `e2e/scripts/start_daemon.sh` refuses to start if `coffer` resolves outside this checkout. Everything else simply tests whatever the venv points at.
- **One session per worktree.** Two editors or agents writing to the same worktree overwrite each other's uncommitted changes.
- **Sandbox the daemon.** Worktrees share your `HOME`, so two `make dev` runs fight over `~/.coffer` and port 8000. Use the throwaway-vault recipe above.

## Related

- [Testing](/contributing/testing)
- [Frontend](/contributing/frontend)
- [Running the daemon](/guides/daemon)
- [Files and directories](/reference/filesystem)
- [`.agents/stack.md`](https://github.com/wyx-sg/Coffer/blob/main/.agents/stack.md): backend conventions, file-size limits, layering rules
