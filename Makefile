_VENV_PY := .venv/bin/python3
PY := $(or $(and $(wildcard $(_VENV_PY)),$(_VENV_PY)),python3)
BACKEND := backend
FRONTEND := frontend

.PHONY: help install install-e2e-browsers hooks \
	verify verify-all \
	verify-unit verify-integration verify-contract verify-e2e verify-acceptance verify-desktop verify-benchmark \
	coverage lock \
	eval eval-routing eval-curate \
	desktop-dev desktop-build \
	bundle-binaries \
	frontend-codegen \
	lint format dev clean

help:
	@echo "Coffer Makefile targets:"
	@echo "  make install               create venv + install backend + frontend deps"
	@echo "  make hooks                 install pre-commit + commit-msg git hooks"
	@echo ""
	@echo "  Verification (4 test tiers + lint, see agents/testing.md):"
	@echo "  make verify                fast path: lint + unit + integration + contract + acceptance audit"
	@echo "  make verify-all            verify + e2e (full suite)"
	@echo "  make verify-unit           unit tier only (includes purity guardrail)"
	@echo "  make verify-integration    integration tier only"
	@echo "  make verify-contract       contract tier only"
	@echo "  make verify-e2e            e2e tier only (currently: Playwright web only)"
	@echo "  make verify-acceptance     audit spec.md scenarios vs test markers"
	@echo "  make verify-benchmark      SC-003 gateway-overhead benchmark (COFFER_RUN_BENCHMARKS=1)"
	@echo "  make verify-desktop        cargo test --lib for the Tauri crate (skipped if rust missing)"
	@echo "  make lint                  ruff + mypy + eslint + tsc + import-linter + file/response_model checks"
	@echo "  make format                ruff format + prettier"
	@echo "  make coverage              pytest --cov + vitest --coverage (no threshold gates yet)"
	@echo "  make eval                  AI eval harness: retrieval suite (local) + baseline gate"
	@echo "  make eval-routing          + tool-routing suite (needs a local LLM, e.g. ollama)"
	@echo "  make eval-curate           curate captured traces into golden cases (ARGS=--dry-run)"
	@echo "  make lock                  refresh backend/uv.lock from pyproject.toml (the install lockfile)"
	@echo ""
	@echo "  Desktop (Tauri; needs Rust toolchain, see CONTRIBUTING.md):"
	@echo "  make desktop-dev           run frontend + backend + Tauri window in dev mode"
	@echo "  make desktop-build         build the desktop bundle (release)"
	@echo ""
	@echo "  Dev:"
	@echo "  make dev                   run backend (:8000) + frontend (:5173) in parallel"
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

verify-acceptance:
	$(PY) scripts/audit_acceptance.py

# Run the Rust unit tests in the Tauri crate (desktop/src/lib.rs). We don't
# require cargo locally — contributors without the Rust toolchain still need
# `make verify` to succeed for backend/frontend changes — so this step
# skips gracefully when cargo is absent. CI installs rust unconditionally
# (see .github/workflows/verify.yml :: desktop-build) and runs `cargo test
# --lib` directly there, so coverage is enforced at the PR layer.
verify-desktop:
	@if ! command -v cargo >/dev/null 2>&1; then \
		echo "verify-desktop: cargo not found — skipping (install via https://rustup.rs to enable)"; \
		exit 0; \
	fi; \
	if [ "$$(uname -s)" = "Linux" ] && command -v pkg-config >/dev/null 2>&1 && ! pkg-config --exists gdk-3.0 2>/dev/null; then \
		echo "verify-desktop: gdk-3.0 not installed — skipping (apt install libgtk-3-dev to enable)"; \
		exit 0; \
	fi; \
	echo "verify-desktop: cargo test --lib (desktop crate)"; \
	cd desktop && cargo test --lib

lint:
	$(PY) scripts/check_file_sizes.py
	$(PY) scripts/check_response_models.py
	$(PY) -m ruff check $(BACKEND) evals
	$(PY) -m ruff format --check $(BACKEND) evals
	$(PY) -m mypy --config-file $(BACKEND)/pyproject.toml $(BACKEND)/coffer
	.venv/bin/lint-imports --config $(BACKEND)/pyproject.toml
	@if [ -d $(FRONTEND)/node_modules ]; then \
		cd $(FRONTEND) && npm run lint && npm run typecheck; \
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

verify-integration:
	@if [ -d $(BACKEND)/tests/integration ]; then \
		$(PY) -m pytest $(BACKEND)/tests/integration; \
	else \
		echo "verify-integration: $(BACKEND)/tests/integration/ does not exist yet — skipping backend"; \
	fi
	@if [ -d $(FRONTEND)/tests/integration ] && [ -d $(FRONTEND)/node_modules ]; then \
		cd $(FRONTEND) && npx vitest run tests/integration; \
	else \
		echo "verify-integration: no $(FRONTEND)/tests/integration/ — skipping frontend"; \
	fi

verify-benchmark:
	COFFER_RUN_BENCHMARKS=1 $(PY) -m pytest $(BACKEND)/tests -m benchmark

verify-contract:
	@if [ -d $(BACKEND)/tests/contract ]; then \
		$(PY) -m pytest $(BACKEND)/tests/contract; \
	else \
		echo "verify-contract: $(BACKEND)/tests/contract/ does not exist yet — skipping backend"; \
	fi
	@if [ -d $(FRONTEND)/tests/contract ] && [ -d $(FRONTEND)/node_modules ]; then \
		cd $(FRONTEND) && npx vitest run tests/contract; \
	else \
		echo "verify-contract: no $(FRONTEND)/tests/contract/ — skipping frontend"; \
	fi

verify-e2e:
	@if [ ! -f e2e/playwright.config.ts ]; then \
		echo "verify-e2e: no e2e/playwright.config.ts — skipping"; \
	elif [ ! -d e2e/node_modules ]; then \
		echo "verify-e2e: e2e/node_modules missing — run 'make install' first"; exit 1; \
	else \
		cd e2e && npx playwright test; \
	fi
	@if [ -d e2e ] && ls e2e/*.py >/dev/null 2>&1; then \
		$(PY) -m pytest e2e; \
	else \
		echo "verify-e2e: no e2e/*.py — skipping MCP shim tests"; \
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
# here (and `--coverage.thresholds.lines=N` on the vitest side) via a
# constitutional amendment.
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

# Tauri desktop shell. Requires Rust toolchain (rustup) and the frontend
# npm deps installed via `make install`. Tauri itself spawns the Vite dev
# server via `beforeDevCommand` in desktop/tauri.conf.json.
#
# We run @tauri-apps/cli from inside desktop/ rather than via an npm script
# in frontend/: Tauri CLI 2.x discovers the project by walking subdirs for
# tauri.conf.json, so cwd must be the crate dir. The CLI binary itself is
# installed under frontend/node_modules/ as a frontend dev-dep, and we
# invoke it through the relative path `../frontend/node_modules/.bin/tauri`
# from desktop/.

desktop-dev:
	@command -v cargo >/dev/null 2>&1 || { \
		echo "desktop-dev: Rust toolchain missing. Install via https://rustup.rs."; \
		exit 1; \
	}
	cd desktop && ../$(FRONTEND)/node_modules/.bin/tauri dev

# Clean any leftover bundle/ from a prior aborted build before running
# `tauri build`. Tauri's bundle_dmg.sh leaves rw.<pid>.*.dmg intermediates
# on failure, which then break the next DMG creation. The bundle dir is
# fully regenerated each run, so deleting it is safe.
desktop-build:
	@command -v cargo >/dev/null 2>&1 || { \
		echo "desktop-build: Rust toolchain missing. Install via https://rustup.rs."; \
		exit 1; \
	}
	rm -rf desktop/target/release/bundle
	cd desktop && ../$(FRONTEND)/node_modules/.bin/tauri build

frontend-codegen:
	@if [ -d $(FRONTEND) ]; then \
		cd $(FRONTEND) && npm run codegen; \
	fi

.PHONY: bundle-binaries
bundle-binaries:
	bash ./scripts/build_binaries.sh

clean:
	rm -rf .venv \
		$(FRONTEND)/node_modules $(FRONTEND)/dist \
		$(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache \
		.mypy_cache .ruff_cache .pytest_cache \
		desktop/target desktop/gen
