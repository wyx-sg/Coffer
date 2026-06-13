---
name: coffer-verify
description: Run Coffer's full verification pipeline (lint + unit + integration + contract + acceptance) before opening a PR.
disable-model-invocation: true
allowed-tools: Bash
---

Run Coffer's verification gate and report the outcome honestly.

1. From the repo root, run: `make verify`
   - This runs, in order: `lint` (ruff check + ruff format --check + mypy + import-linter + frontend lint/typecheck), `verify-unit`, `verify-integration`, `verify-contract`, `verify-acceptance`. See `agents/testing.md` for the tier definitions.
2. If anything fails, surface the exact failing command and output. Do NOT claim success.
3. End-to-end (e2e) is intentionally separate: run `make verify-e2e` only when asked.

A green `make verify` is the bar for "the product works, no manual re-testing required."
