# Harness — Agent Control Layer

Coffer ships a checked-in control layer so the agent-facing harness is enforced, not just documented: the right thing is the default path, destructive commands are blocked, and feedback is fast, deterministic and legible to humans, CI and agents alike.

## The layers

The harness around this repo is a stack, and each layer has one home:

| Layer         | What it gives                                                                                  | Where it lives                                                                                                                                  |
| ------------- | ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Control       | Hooks and permission rules that act on the agent's tool calls, not just advise it             | `.claude/` — this page                                                                                                                          |
| Knowledge     | What an agent reads before working                                                             | `AGENTS.md`, `.agents/*.md`, the principles, the architecture pages, `docs/decisions/`, `openspec/specs/`                                      |
| Hermeticity   | The same dependency set on every machine and in CI                                             | `.python-version` (3.12) and `backend/uv.lock`, installed with `uv sync --frozen` by CI and the release workflow; `make lock` refreshes the lock |
| Feedback      | One command that says whether the tree is good                                                 | `make verify` and the test tiers ([`testing.md`](./testing.md)), pre-commit, the CI workflows                                                   |
| Eval          | A regression net for non-deterministic behaviour that exact-match tests cannot pin             | `evals/`, `make eval`, `.github/workflows/evals.yml` — see [Eval harness](#eval-harness) below                                                  |

A hook or gate must stay fast: a slow one trains people to bypass it. That is why the backend test tiers run on xdist workers locally and the integration tier runs as four duration-balanced shards in CI ([`testing.md` "Running in Parallel"](./testing.md#running-in-parallel), [CI Jobs](./testing.md#ci-jobs)), and why a docs-only pull request skips the test jobs while the static gates still run.

## What is wired (`.claude/`)

| File                                    | Role                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `.claude/settings.json`                 | Permissions (allow safe commands, deny destructive ones) + hook wiring. Committed, team-shared.                                                                                                                                                                                                                                                                                                                                      |
| `.claude/hooks/auto_format.py`          | PostToolUse on Edit/Write — formats the edited file. Python: `ruff check --fix` then `ruff format` (lint-fix first, formatter has the final say), repo-wide. Prettier (`.ts/.tsx/.js/.jsx/.css/.json/.md`): only under `frontend/`; the rest of the repo's prettier types are owned by the pinned pre-commit pass (different prettier version), so the hook leaves them alone to avoid CI-fighting churn. Best-effort, never blocks. |
| `.claude/hooks/block_dangerous_bash.py` | PreToolUse on Bash — denies a narrow set of destructive commands (recursive root/home delete incl. reversed flags & quoted targets, force/direct push to protected branches, pipe-to-shell, `dd of=/dev/<disk>` and raw redirects to block devices incl. macOS `disk`/`rdisk` and `nvme`).                                                                                                                                           |

## Commands and Skills

- OpenSpec's six commands — `/opsx:explore`, `/opsx:propose`, `/opsx:apply`,
  `/opsx:update`, `/opsx:sync` and `/opsx:archive` — live in
  `.claude/commands/opsx/*.md`, and the six matching skills in
  `.claude/skills/openspec-*/SKILL.md`. Both are generated by
  `openspec init --tools claude` and refreshed by `npx openspec update`; do not
  hand-edit them. `backend/tests/integration/harness/test_skills.py` pins that
  exactly those six skills are checked in and carry the required frontmatter.
  Read [`openspec.md`](./openspec.md) for the change workflow they drive.
- Whatever a change adds, a capability is **named, never numbered**, and a
  requirement is cited by its title — `scripts/check_spec_citations.py` fails
  a citation whose capability or title does not exist in `openspec/specs/`.

## Gates

`make verify` is the single entry point. It runs `lint`, `docs-build` (the
docs site's VitePress build), `verify-unit`, `verify-integration`, `verify-contract` and `verify-acceptance` in that order,
prints how long each stage took, and keeps the times in
`.coffer-verify.timings`. Each target is one job in
`.github/workflows/verify.yml` (the header comment there holds the mapping);
`ci.yml` runs `make verify` whole. The repository gates under `scripts/`, one
line each:

| Gate                                         | Runs in               | Fails when                                                                                                                  |
| -------------------------------------------- | --------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `scripts/check_file_sizes.py`                | `make lint`           | A backend, desktop or frontend file is over its tier's line limit                                                           |
| `scripts/gen_contracts.py --check`           | `make lint`           | A checked-in `api.openapi.yaml` is not what the Pydantic models produce, or a served route has no owning capability        |
| `scripts/check_response_models.py`           | `make lint`           | A FastAPI route declares neither `response_model=` nor `response_class=`                                                    |
| `scripts/check_adr_index.py`                 | `make lint`           | A link inside `docs/decisions/` is dead, or the ADR index does not list exactly the ADRs that exist                         |
| `scripts/check_spec_citations.py`            | `make lint`           | A `spec <capability> "<Title>"` citation — or, inside `openspec/`, a relative `spec.md` link or a `see "<Title>"` of the file's own capability — names a capability or requirement title that does not exist; a title wrapped across lines is read joined |
| `scripts/check_architecture_doc.py`          | `make lint`           | The code-layout tree or the built-in tool roster in `docs-site/architecture/` has drifted from the code                    |
| `scripts/check_pyinstaller_specs.py`         | `make lint`           | A PyInstaller spec names a missing file or has lost the `-X utf8` runtime option                                            |
| `scripts/check_cli_reference.py`             | `make lint`           | A generated CLI reference page (en or zh: the index or a command group's page) differs from the code, or is left over from a removed group (`make docs-reference` fixes it) |
| `scripts/check_docs_locales.py`              | `make lint`           | A docs-site page, sidebar entry, heading anchor or link exists in English and not in `docs-site/zh/`, or the other way round  |
| `scripts/check_error_codes_reference.py`     | `make lint`           | `docs-site/reference/error-codes.md` or its zh twin lacks a code `surfaces/http/errors.py` maps, lists it at another HTTP status, or lists a code the daemon does not map |
| `scripts/check_removed_commands.py`          | `make lint`           | A doc (`docs-site/`, `docs/` except the ADRs, both READMEs), spec, shipped skill, web UI or desktop shell source file, or e2e spec quotes a removed `coffer` command, option or tool |
| `scripts/check_platform_calls.py`            | `make lint`           | Code outside `infrastructure/platform/` asks which operating system it runs on                                              |
| `scripts/check_coffer_paths.py`              | `make lint`           | A `~/.coffer` path is built outside `infrastructure/vault/home.py` (allowed: migrations, the tests' isolated homes and real-home guard) |
| `scripts/check_agent_type_branches.py`       | `make lint`           | Code outside the agent descriptor and its facets branches on an agent type (tests: `test_agent_type_gate.py`)              |
| `scripts/check_frontend_colors.py`           | `make lint`           | A colour literal appears in `frontend/src/` outside `index.css` (tests: `test_frontend_colors_gate.py`)                     |
| `scripts/check_ignored_sources.py`           | `make lint`           | A `.gitignore` rule hides a path in a source tree, or an unanchored pattern names a source-folder word such as `lib/`      |
| `scripts/check_bare_tasks.py`                | `make lint`           | A module under `backend/coffer/` makes more `create_task` / `ensure_future` calls than its allowance in the script (background work goes through `application/runtime/supervisor`; tests: `test_bare_tasks_gate.py`) |
| `scripts/dump_i18n_backend_keys.py --check`  | `make lint`           | A backend error code or audit event type is missing from the frontend's locale-coverage fixture                             |
| `scripts/check_unit_purity.py`               | `make verify-unit`    | A test under `backend/tests/unit/` imports an I/O module                                                                    |
| `openspec validate --all --strict`          | `make verify-acceptance` | A spec or change is malformed, or a requirement owns no scenario (runs first, before `audit_acceptance.py`)             |
| `scripts/audit_acceptance.py`                | `make verify-acceptance` | A spec scenario has no test marker, or a marker names no scenario                                                        |
| `scripts/ci_change_scope.py`                 | CI `changes` job      | (Not a gate.) Decides whether a pull request is prose-only, so the test jobs can be skipped                                |

The rest of `scripts/` is build and release tooling, run by a Makefile target
or `release.yml` and never by `make verify`: `build_binaries.sh`
(`make bundle-binaries`), `smoke_test_bundle.sh`, `bump_version.py`,
`stamp_channel.py`, `stamp_build_identity.py`, `release_plan.py`,
`release_signing.sh`, `make_update_manifest.py`, `refresh_model_prices.py`
(`make refresh-prices`), `sync_gitleaks_rules.py`
(`make refresh-secret-rules`) and `render_tray_icons.sh` (redraws the desktop tray
icons from `desktop/icons/tray/tray.svg`).

Where a gate has tests of its own they live in `backend/tests/integration/harness/`. `scripts/verify_lock.py` is run-time tooling, not a gate: `make verify-integration` runs the integration suite through it so a second run on one machine queues instead of competing.

## How it is tested

The hooks and settings are pinned by `backend/tests/integration/harness/`, which subprocess the real scripts with synthetic stdin. They run under `make verify-integration`, so the harness tests itself.

The test suite carries one guard of its own: `backend/tests/conftest.py` + `backend/tests/support/real_home_guard.py` — the real-home guard. It redirects `HOME`, strips inherited `COFFER_*` variables, and an audit hook fails any test that touches the real `~/.coffer` / `~/.claude` / `~/.codex`; proven by `backend/tests/integration/isolation/test_real_home_guard.py`. Rules in [`testing.md`](./testing.md) "The Real-Home Guard".

## Eval harness

Non-deterministic AI behaviour — tool-search ranking and tool routing — is measured under [`evals/`](../evals/README.md): `make eval` (local, deterministic) and `make eval-routing` (needs a local LLM). It is the regression net for prompt / model / catalogue changes; the design is recorded in [Eval Capture and Regression Gate](../docs/decisions/eval-capture-and-regression-gate.md).

## The eval flywheel (loop engineering)

[Eval Capture and Regression Gate](../docs/decisions/eval-capture-and-regression-gate.md) closes the loop so the eval suite is not just a static instrument but a self-feeding cycle — the development-time loop that keeps Coffer's non-deterministic behaviour from drifting:

1. **Capture** — set `COFFER_EVAL_CAPTURE` and real `coffer__search_tools` calls record their `(query → ranked tools)` shape to a local, gitignored JSONL sink (opt-in; off by default; never tool args/results). The invocation log was made honest first (in-band `isError` → `status=error`) so failures are legible.
2. **Curate** — `make eval-curate` turns captured queries into labelled `datasets/*.jsonl` golden cases (dedup vs the existing dataset; you mark which returned tools were relevant), tagged `"source": "captured"`.
3. **Gate** — the `evals.yml` workflow runs the deterministic, model-free suites on PRs touching prompts / mcp / retrieval / catalogue and fails on **relative regression vs the committed baseline** (`evals/run.py`). The model-bearing routing suite stays on-demand (`make eval-routing`), out of CI.
4. **Feedback** — a real-usage failure becomes a captured case → a curated golden case → a baseline regression the gate catches → a fix → `python -m evals.run --update-baseline`. The dataset ratchets up from real usage; the human + Claude Code inner loop still owns the fix (the flywheel measures and guards, it does not auto-optimise — see [Eval Capture and Regression Gate](../docs/decisions/eval-capture-and-regression-gate.md)).

## Conventions

- Hooks are Python (no `jq` dependency; the project guarantees Python 3.12). A hook must never break the agent — on any error it exits 0 with no decision.
- `.claude/settings.json`, the four `.claude/hooks/` scripts, the six `.claude/commands/opsx/*.md` commands and the six `.claude/skills/openspec-*/SKILL.md` skills are the tracked files under `.claude/` — that is the whole harness. The repo's `.gitignore` ignores `.claude/settings.local.json` (personal overrides), every other `.claude/commands/*` entry (it un-ignores only `opsx/`), `.claude/worktrees/` and the loop/scheduler state files.
