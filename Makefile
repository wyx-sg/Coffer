_VENV_PY := .venv/bin/python3
PY := $(or $(and $(wildcard $(_VENV_PY)),$(_VENV_PY)),python3)
BACKEND := backend
FRONTEND := frontend

.PHONY: help install install-e2e-browsers hooks \
	verify verify-all \
	verify-unit verify-integration verify-contract verify-e2e verify-acceptance \
	coverage lock \
	desktop-dev desktop-build \
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
	@echo "  make lint                  ruff + mypy + eslint + tsc + import-linter + file/response_model checks"
	@echo "  make format                ruff format + prettier"
	@echo "  make coverage              pytest --cov + vitest --coverage (no threshold gates yet)"
	@echo "  make lock                  regenerate backend/requirements-dev.lock from pyproject.toml"
	@echo ""
	@echo "  Desktop (Tauri; needs Rust toolchain, see CONTRIBUTING.md):"
	@echo "  make desktop-dev           run frontend + backend + Tauri window in dev mode"
	@echo "  make desktop-build         build the desktop bundle (release)"
	@echo ""
	@echo "  Dev:"
	@echo "  make dev                   run backend (:8000) + frontend (:5173) in parallel"
	@echo "  make clean                 remove venv + node_modules + caches"

install:
	@if [ ! -d .venv ]; then python3 -m venv .venv; fi
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e $(BACKEND)[dev]
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
verify-all: verify verify-e2e

verify-acceptance:
	$(PY) scripts/audit_acceptance.py

lint:
	$(PY) scripts/check_file_sizes.py
	$(PY) scripts/check_response_models.py
	$(PY) -m ruff check $(BACKEND)
	$(PY) -m ruff format --check $(BACKEND)
	$(PY) -m mypy $(BACKEND)/coffer
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
	$(PY) -m ruff format $(BACKEND)
	$(PY) -m ruff check --fix $(BACKEND)
	@if [ -d $(FRONTEND)/node_modules ]; then cd $(FRONTEND) && npm run format; fi

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

# Regenerate the snapshot lockfile from pyproject.toml's dev extras.
# The lockfile is not enforced at install time (see CONTRIBUTING.md);
# it's a snapshot of "what versions worked when these tests last passed."
# --no-emit-index-url / --no-emit-trusted-host keep developer-local pip
# configs (corporate mirrors, etc.) out of the committed lockfile.
lock:
	$(PY) -m piptools compile --extra dev --quiet --strip-extras \
		--no-emit-index-url --no-emit-trusted-host \
		--output-file $(BACKEND)/requirements-dev.lock \
		$(BACKEND)/pyproject.toml

dev:
	@echo "Starting backend (:8000) and frontend (:5173). Ctrl-C to stop both."
	@trap 'kill 0' EXIT; \
	(cd $(BACKEND) && ../.venv/bin/uvicorn coffer.main:app --reload --port 8000) & \
	(cd $(FRONTEND) && npm run dev) & \
	wait

# Tauri desktop shell. Requires Rust toolchain (rustup) and the frontend
# npm deps installed via `make install`. Tauri itself spawns the Vite dev
# server via `beforeDevCommand` in src-tauri/tauri.conf.json.
desktop-dev:
	@command -v cargo >/dev/null 2>&1 || { \
		echo "desktop-dev: Rust toolchain missing. Install via https://rustup.rs."; \
		exit 1; \
	}
	cd $(FRONTEND) && npm run tauri:dev

desktop-build:
	@command -v cargo >/dev/null 2>&1 || { \
		echo "desktop-build: Rust toolchain missing. Install via https://rustup.rs."; \
		exit 1; \
	}
	cd $(FRONTEND) && npm run tauri:build

clean:
	rm -rf .venv \
		$(FRONTEND)/node_modules $(FRONTEND)/dist \
		$(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache \
		.mypy_cache .ruff_cache .pytest_cache \
		src-tauri/target src-tauri/gen
