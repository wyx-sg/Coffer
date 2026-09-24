_VENV_PY := .venv/bin/python3
PY := $(or $(and $(wildcard $(_VENV_PY)),$(_VENV_PY)),python3)
BACKEND := backend
FRONTEND := frontend

.PHONY: help install install-e2e-browsers hooks \
	verify verify-all \
	verify-unit verify-integration verify-contract verify-e2e verify-acceptance openspec-validate verify-benchmark \
	coverage lock \
	eval eval-routing eval-curate \
	bundle-binaries \
	desktop desktop-stage-binaries desktop-lint desktop-test \
	frontend-codegen docs-reference \
	lint format dev clean

help:
	@echo "Coffer Makefile targets:"
	@echo "  make install               create venv + install backend + frontend deps"
	@echo "  make install-e2e-browsers  download the Playwright chromium build (heavy)"
	@echo "  make hooks                 install pre-commit + commit-msg git hooks"
	@echo ""
	@echo "  Verification (4 test tiers + lint, see .agents/testing.md):"
	@echo "  make verify                fast path: lint + unit + integration + contract + acceptance audit"
	@echo "  make verify-all            verify + e2e (full suite)"
	@echo "  make verify-unit           unit tier only (includes purity guardrail)"
	@echo "  make verify-integration    integration tier only"
	@echo "  make verify-contract       contract tier only"
	@echo "  make verify-e2e            e2e tier only (Playwright: web + mcp projects)"
	@echo "  make verify-acceptance     openspec validate + audit scenarios vs test markers"
	@echo "  make verify-benchmark      gateway-overhead budget benchmark (COFFER_RUN_BENCHMARKS=1)"
	@echo "  make lint                  ruff + mypy + eslint + tsc + knip + import-linter + file/response_model checks"
	@echo "  make format                ruff format + prettier"
	@echo "  make coverage              pytest --cov + vitest --coverage (no threshold gates yet)"
	@echo "  make eval                  AI eval harness: tool-search suite (local) + baseline gate"
	@echo "  make eval-routing          + tool-routing suite (needs a local LLM, e.g. ollama)"
	@echo "  make eval-curate           curate captured traces into golden cases (ARGS=--dry-run)"
	@echo "  make lock                  refresh backend/uv.lock from pyproject.toml (the install lockfile)"
	@echo ""
	@echo "  Desktop shell (optional; needs a Rust toolchain — not in 'make verify'):"
	@echo "  make desktop               build the Coffer.app + .dmg (SLOW: runs PyInstaller, ~50 min)"
	@echo "  make desktop-lint          cargo check + cargo clippy for the desktop crate"
	@echo "  make desktop-test          cargo test for the desktop crate"
	@echo "  make desktop-stage-binaries  stage externalBin placeholders so cargo can compile"
	@echo ""
	@echo "  Dev:"
	@echo "  make dev                   run backend (:8000) + frontend (:5173) in parallel"
	@echo "  make frontend-codegen      regenerate the frontend's OpenAPI types from the daemon"
	@echo "  make docs-reference        regenerate the docs site's CLI and REST API reference pages"
	@echo "  make bundle-binaries       freeze the three CLI binaries with PyInstaller (into dist/)"
	@echo "  make clean                 remove venv + node_modules + caches"

# Use `./.venv/bin/python3` directly in the install recipe instead of $(PY).
# $(PY) is evaluated at parse time: when .venv doesn't yet exist, it expands
# to the system `python3`, which on Homebrew macOS is PEP-668-protected and
# rejects `pip install --upgrade pip` with "externally-managed-environment".
# By creating the venv inside the recipe and then calling its python directly,
# the install path works on a fresh checkout regardless of the host OS's pip
# policy.
install:
	@if [ ! -d .venv ]; then python3 -m venv .venv; fi
	./.venv/bin/python3 -m pip install --upgrade pip
	./.venv/bin/python3 -m pip install -e '$(BACKEND)[dev]'
	@if [ -d $(FRONTEND) ] && command -v npm >/dev/null 2>&1; then \
		cd $(FRONTEND) && npm install; \
	else \
		echo "install: skipping frontend npm install (npm or frontend/ missing)"; \
	fi
	@if command -v npm >/dev/null 2>&1; then \
		npm install; \
	else \
		echo "install: skipping the OpenSpec CLI (npm missing)"; \
	fi
	@if [ -d e2e ] && command -v npm >/dev/null 2>&1; then \
		cd e2e && npm install; \
	else \
		echo "install: skipping e2e npm install (npm or e2e/ missing)"; \
	fi
	@echo ""
	@echo "install: complete. For Playwright browsers (heavy), run 'make install-e2e-browsers'."

install-e2e-browsers:
	@if [ -d e2e/node_modules ]; then \
		cd e2e && npx playwright install chromium; \
	else \
		echo "install-e2e-browsers: run 'make install' first"; exit 1; \
	fi

# Wire pre-commit + commit-msg hooks into .git/hooks/. Requires `make install`
# (pre-commit is a dev dep). Per-developer; not run by CI.
hooks:
	@if [ -x .venv/bin/pre-commit ]; then \
		.venv/bin/pre-commit install --hook-type pre-commit --hook-type commit-msg; \
	else \
		echo "hooks: .venv/bin/pre-commit missing — run 'make install' first"; exit 1; \
	fi

verify: lint verify-unit verify-integration verify-contract verify-acceptance
	@$(PY) scripts/verify_stamp.py write && echo "verify: OK — recorded .coffer-verify.stamp"
verify-all: verify verify-e2e

# Two halves of one rule: `openspec validate --strict` fails a requirement
# that owns no scenario, and audit_acceptance fails a scenario no test covers.
# The CLI is pinned in the root package.json; `make install` fetches it.
verify-acceptance: openspec-validate
	$(PY) scripts/audit_acceptance.py

openspec-validate:
	@if [ -x node_modules/.bin/openspec ]; then \
		node_modules/.bin/openspec validate --all --strict --no-interactive; \
	else \
		echo "openspec-validate: node_modules/.bin/openspec missing — run 'make install'"; exit 1; \
	fi

lint:
	$(PY) scripts/check_file_sizes.py
	$(PY) scripts/check_response_models.py
	$(PY) scripts/check_doc_numbering.py
	$(PY) scripts/check_spec_citations.py
	$(PY) scripts/check_architecture_doc.py
	$(PY) scripts/check_pyinstaller_specs.py
	$(PY) scripts/check_cli_reference.py
# Both trees are checked under the project's rules. `backend/**` gets them
# from backend/pyproject.toml; `evals/**` used to get ruff's built-in defaults
# (line-length 88, the starter rule set) because nothing above it carried a
# config — the root ruff.toml now inherits the real one. See the comment in
# that file for why it is a file and not a `--config` flag here.
	$(PY) -m ruff check $(BACKEND) evals
	$(PY) -m ruff format --check $(BACKEND) evals
	$(PY) -m mypy --config-file $(BACKEND)/pyproject.toml $(BACKEND)/coffer
# PYTHONPATH is load-bearing, not decorative: lint-imports resolves `coffer`
# by import, so in a git worktree (whose .venv symlinks to the main
# checkout's, whose editable install points at the MAIN checkout's backend)
# a bare invocation silently analyses the other checkout's code and reports
# contract violations for modules this tree does not have. In the main
# checkout it resolves to the same code either way, so setting it always is
# free and makes the two environments agree.
	PYTHONPATH=$(BACKEND) .venv/bin/lint-imports --config $(BACKEND)/pyproject.toml
# `npm run knip` is the frontend's dead-code gate — eslint.config.js carries
# only the react-hooks rules and one no-restricted-syntax, which is why dead
# modules, dead hooks and dead query keys once accumulated unnoticed. Its
# config is frontend/package.json's "knip" key, and the script is
# `npx --yes knip@<pinned>`: the same on-demand pattern `make desktop` uses for
# the Tauri CLI, so it needs no entry in the lockfile.
	@if [ -d $(FRONTEND)/node_modules ]; then \
		PYTHONPATH=$(BACKEND) $(PY) scripts/dump_i18n_backend_keys.py --check && \
		cd $(FRONTEND) && npm run lint && npm run typecheck && npm run knip; \
	else \
		echo "lint: $(FRONTEND)/node_modules missing — skipping frontend"; \
	fi

verify-unit:
	$(PY) scripts/check_unit_purity.py
	@if [ -d $(BACKEND)/tests/unit ]; then \
		$(PY) -m pytest $(BACKEND)/tests/unit; \
	else \
		echo "verify-unit: $(BACKEND)/tests/unit/ does not exist yet — skipping backend"; \
	fi
	@if [ -d $(FRONTEND)/node_modules ]; then \
		cd $(FRONTEND) && npx vitest run src; \
	else \
		echo "verify-unit: $(FRONTEND)/node_modules missing — skipping frontend"; \
	fi

# Backend-only, as .agents/testing.md documents. The frontend has no
# tier-by-directory layout: its tests are co-located `*.test.tsx` beside the
# module they cover and all of them run in `verify-unit`'s `vitest run src`.
# A `frontend/tests/integration` leg used to sit here; that directory was the
# first scaffold's shape, deleted when the real web shell landed, and the guard
# it left behind could only ever print its own skip message.
verify-integration:
	@if [ -d $(BACKEND)/tests/integration ]; then \
		$(PY) -m pytest $(BACKEND)/tests/integration; \
	else \
		echo "verify-integration: $(BACKEND)/tests/integration/ does not exist yet — skipping backend"; \
	fi

verify-benchmark:
	COFFER_RUN_BENCHMARKS=1 $(PY) -m pytest $(BACKEND)/tests -m benchmark

# Backend-only, as .agents/testing.md documents. The one frontend contract test
# (`frontend/src/bootstrap.contract.test.ts`) is co-located and runs in
# `verify-unit`; `frontend/tests/contract/` has never existed, so the leg that
# used to guard on it only ever printed a skip.
verify-contract:
	@if [ -d $(BACKEND)/tests/contract ]; then \
		$(PY) -m pytest $(BACKEND)/tests/contract; \
	else \
		echo "verify-contract: $(BACKEND)/tests/contract/ does not exist yet — skipping backend"; \
	fi

# `npx playwright test` runs BOTH projects in e2e/playwright.config.ts: `web`
# (browser specs under e2e/web/specs/) and `mcp` (cross-process shim+daemon
# specs under e2e/mcp/specs/, no browser). A pytest leg used to follow, guarded
# on `e2e/*.py`; no such file has ever existed in this repo — the MCP shim
# tests it claimed to skip are the Playwright `mcp` project above.
verify-e2e:
	@if [ ! -f e2e/playwright.config.ts ]; then \
		echo "verify-e2e: no e2e/playwright.config.ts — skipping"; \
	elif [ ! -d e2e/node_modules ]; then \
		echo "verify-e2e: e2e/node_modules missing — run 'make install' first"; exit 1; \
	else \
		cd e2e && npx playwright test; \
	fi

format:
	$(PY) -m ruff format $(BACKEND) evals
	$(PY) -m ruff check --fix $(BACKEND) evals
	@if [ -d $(FRONTEND)/node_modules ]; then cd $(FRONTEND) && npm run format; fi

eval:
	$(PY) -m pytest evals/tests -q
	$(PY) -m evals.run

eval-routing:
	$(PY) -m evals.run --routing

eval-curate:
	$(PY) -m evals.curate $(ARGS)

# Coverage on demand. No threshold gates are wired yet — thresholds need
# empirical data from real feature code. When ready, add `--cov-fail-under=N`
# here (and `--coverage.thresholds.lines=N` on the vitest side) via an
# amendment to docs-site/architecture/principles.md.
coverage:
	@if [ -d $(BACKEND)/tests ]; then \
		$(PY) -m pytest $(BACKEND)/tests --cov=coffer --cov-report=term-missing --cov-report=xml; \
	fi
	@if [ -d $(FRONTEND)/node_modules ]; then \
		cd $(FRONTEND) && npx vitest run --coverage; \
	fi

# Refresh the install lockfile (backend/uv.lock) from backend/pyproject.toml.
# uv.lock is the single source of truth for dependency versions: CI and the
# release workflow install from it FROZEN (`uv sync --frozen`) so tagged
# artifacts are reproducible. See the "Lockfile" section in CONTRIBUTING.md.
# Run this whenever you add/bump/remove a dependency in pyproject.toml, then
# commit the updated uv.lock alongside the pyproject change.
lock:
	@command -v uv >/dev/null 2>&1 || { \
		echo "lock: uv not found — install it (https://docs.astral.sh/uv/) to refresh uv.lock"; \
		exit 1; \
	}
	uv lock --project $(BACKEND)

# Run backend (:8000) + frontend (:5173) in parallel for browser dev.
#
# The backend MUST go through `coffer.infrastructure.daemon.entry` rather
# than `uvicorn coffer.main:app` directly: entry.py is what allocates the
# port, generates the auth token, and writes ~/.coffer/daemon.json. The
# Vite dev plugin (frontend/vite.config.ts) then reads that file to inject
# window.__COFFER_TOKEN__ so the FE is authenticated without manual setup.
# A bare `uvicorn coffer.main:app` leaves the active token unset and every
# token-gated endpoint 503s — the FE is unusable.
#
# Foreground (no --reload) so Ctrl-C cleanly tears down both children via
# the trap. Backend code changes need a manual restart; that's the
# tradeoff for an end-to-end working dev mode.
#
# Vite only starts AFTER the daemon is genuinely reachable: we spawn the
# backend in the background, then poll until ~/.coffer/daemon.json exists
# AND GET /api/v1/daemon/status returns HTTP 200 (up to 30 s). This
# eliminates the race where Vite starts first, the browser fetches /,
# cofferDevTokenInjection finds no daemon.json, and injects no token — so
# the page bakes in the wrong base URL and shows "Failed to fetch" forever.
dev:
	@echo "Starting backend (:8000) and frontend (:5173). Ctrl-C to stop both."
	@trap 'kill 0' EXIT; \
	DAEMON_JSON="$$HOME/.coffer/daemon.json"; \
	(cd $(BACKEND) && COFFER_DEV_CORS=1 PYTHONPATH=. ../.venv/bin/python3 -m coffer.infrastructure.daemon.entry) & \
	echo "Waiting for daemon to become ready (up to 30 s)…"; \
	_elapsed=0; \
	until [ -f "$$DAEMON_JSON" ]; do \
		if [ $$_elapsed -ge 30 ]; then \
			echo "dev: daemon did not write $$DAEMON_JSON within 30 s — aborting."; \
			exit 1; \
		fi; \
		sleep 1; \
		_elapsed=$$(($$_elapsed + 1)); \
	done; \
	_port=$$($(PY) -c "import json,sys; d=json.load(open('$$DAEMON_JSON')); print(d.get('port',8000))" 2>/dev/null || echo 8000); \
	until curl -sf "http://127.0.0.1:$$_port/api/v1/daemon/status" >/dev/null 2>&1; do \
		if [ $$_elapsed -ge 30 ]; then \
			echo "dev: daemon HTTP not ready on port $$_port within 30 s — aborting."; \
			exit 1; \
		fi; \
		sleep 1; \
		_elapsed=$$(($$_elapsed + 1)); \
	done; \
	echo "Daemon ready on port $$_port. Starting Vite…"; \
	(cd $(FRONTEND) && npm run dev) & \
	wait

frontend-codegen:
	@if [ -d $(FRONTEND) ]; then \
		cd $(FRONTEND) && npm run codegen; \
	fi

# The CLI and REST reference pages are generated from the code;
# scripts/check_cli_reference.py (in `lint`) fails when they drift.
docs-reference:
	$(PY) docs-site/scripts/gen_cli_reference.py
	$(PY) docs-site/scripts/gen_rest_reference.py

bundle-binaries:
	bash ./scripts/build_binaries.sh

# --- Desktop shell (docs/decisions/desktop-shell-over-a-shared-frontend.md) ---
#
# Deliberately NOT a prerequisite of `verify`: the Rust toolchain is a
# prerequisite of `make desktop` only, and no CI workflow installs one for
# the test gates. `make desktop-test` is how anyone with a toolchain runs
# the crate's unit tests.
#
# `desktop` produces an UNSIGNED, un-notarised Coffer.app + .dmg. macOS will
# refuse a browser-downloaded copy on double-click until a Developer ID
# exists; a locally-built one runs fine.
#
# The .app bundles the three frozen binaries via tauri.conf.json's
# `externalBin`, which is why this target has to run PyInstaller first. Tauri
# resolves each `binaries/<name>` entry to `binaries/<name>-<target-triple>`,
# so the freshly-built binaries are staged under that suffixed name.
desktop:
	@echo "make desktop: this runs PyInstaller for three binaries before the"
	@echo "  Tauri build — expect roughly 50 minutes on a laptop. The result is"
	@echo "  UNSIGNED: macOS Gatekeeper will block a downloaded copy of it."
	@echo ""
	@command -v rustc >/dev/null 2>&1 || { \
		echo "desktop: no Rust toolchain — install one from https://rustup.rs"; exit 1; \
	}
	@command -v npx >/dev/null 2>&1 || { \
		echo "desktop: npx not found. The Tauri CLI is invoked as"; \
		echo "  'npx @tauri-apps/cli' — install Node.js, or install the Rust CLI"; \
		echo "  with 'cargo install tauri-cli --version ^2' and run 'cargo tauri build'"; \
		echo "  from desktop/ yourself."; exit 1; \
	}
	@if [ ! -d $(FRONTEND)/node_modules ]; then \
		echo "desktop: $(FRONTEND)/node_modules missing — run 'make install' first"; exit 1; \
	fi
# (1) The window loads frontend/dist as a local asset, so it must exist.
# tauri.conf.json's beforeBuildCommand builds it too; doing it up front
# fails fast on a broken frontend instead of after the PyInstaller hour.
	npm run build --prefix $(FRONTEND)
# (2) Freeze coffer / coffer-daemon / coffer-mcp-shim.
	$(MAKE) bundle-binaries
# (3) Stage them where externalBin expects, under the rustc host triple
# (the same value Tauri exposes as TAURI_ENV_TARGET_TRIPLE).
	@set -e; \
	TRIPLE=$$(rustc -vV | awk '/^host:/ {print $$2}'); \
	case "$$TRIPLE" in *windows*) EXT=.exe ;; *) EXT= ;; esac; \
	mkdir -p desktop/binaries; \
	for b in coffer coffer-daemon coffer-mcp-shim; do \
		cp "dist/$$b$$EXT" "desktop/binaries/$$b-$$TRIPLE$$EXT"; \
		chmod +x "desktop/binaries/$$b-$$TRIPLE$$EXT"; \
	done; \
	echo "desktop: staged binaries for $$TRIPLE"
# (4) Build the .app + .dmg.
	cd desktop && npx --yes @tauri-apps/cli@^2 build
	@echo ""
	@echo "desktop: built (unsigned) — see desktop/target/release/bundle/"

# ANY cargo command on the crate (check, clippy, test, build) needs the
# externalBin entries to resolve at build time, so a checkout with no frozen
# binaries staged cannot compile it. Stand in a placeholder for any that is
# missing: it is gitignored like the real ones, and it announces itself loudly
# if it ever escapes into a bundle. A real `make desktop` overwrites all three.
# Split out of `desktop-test` so the CI desktop job (.github/workflows/
# desktop.yml) stages the same placeholders before `cargo check`/`clippy`
# instead of keeping a second copy of this loop.
desktop-stage-binaries:
# The staging loop asks rustc for the host triple, so the no-toolchain case has
# to be caught here rather than in each caller — otherwise `make desktop-lint`
# on a machine without Rust dies on a bare "rustc: command not found".
	@command -v rustc >/dev/null 2>&1 || { \
		echo "desktop: no Rust toolchain — install one from https://rustup.rs"; exit 1; \
	}
	@set -e; \
	TRIPLE=$$(rustc -vV | awk '/^host:/ {print $$2}'); \
	case "$$TRIPLE" in *windows*) EXT=.exe ;; *) EXT= ;; esac; \
	mkdir -p desktop/binaries; \
	for b in coffer coffer-daemon coffer-mcp-shim; do \
		f="desktop/binaries/$$b-$$TRIPLE$$EXT"; \
		if [ ! -e "$$f" ]; then \
			printf '#!/bin/sh\necho "%s: placeholder staged by make desktop-stage-binaries; run make desktop to build the real binary" >&2\nexit 1\n' "$$b" > "$$f"; \
			chmod +x "$$f"; \
		fi; \
	done

# Compile + lint the crate without bundling anything. This is what CI runs
# (.github/workflows/desktop.yml): `make desktop` is PyInstaller + Tauri and
# takes about fifty minutes, so it is not a gate anywhere; these two are.
# `-D warnings` makes clippy's findings failures, matching how ruff/eslint
# behave for the other two languages in the tree.
desktop-lint: desktop-stage-binaries
	cd desktop && cargo check --all-targets
	@cd desktop && if cargo clippy --version >/dev/null 2>&1; then \
		cargo clippy --all-targets -- -D warnings; \
	else \
		echo "desktop-lint: clippy component missing — run 'rustup component add clippy'"; \
		exit 1; \
	fi

desktop-test: desktop-stage-binaries
	cd desktop && cargo test

clean:
	rm -rf .venv \
		$(FRONTEND)/node_modules $(FRONTEND)/dist \
		$(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache \
		.mypy_cache .ruff_cache .pytest_cache \
		desktop/target desktop/gen/schemas
	@find desktop/binaries -type f ! -name .gitkeep -delete 2>/dev/null || true
