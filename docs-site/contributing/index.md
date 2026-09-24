# Contributing to Coffer

Thanks for your interest in Coffer. This page is the **human contributor** entry point. AI agents (Claude Code, Codex) should read `AGENTS.md` in the repository root instead.

## Quick Start

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
uv sync --frozen --extra dev --project backend   # the locked deps, as CI installs them
make hooks      # wire pre-commit + commit-msg hooks
make dev        # backend daemon (:8000) + Vite (:5173)
```

`make install` exists and uses `pip install -e ./backend[dev]`, which **re-resolves**
dependencies — so it can give you versions CI has never seen. Prefer `uv sync --frozen`
against `backend/uv.lock`, and rebuild that way first when a local result disagrees with CI.

## Project Anchors

- **[Principles](/architecture/principles)** (`docs-site/architecture/principles.md`) — what Coffer is and what it must never become.
- **`AGENTS.md`** — operating manual; humans can read it too, the rules apply equally.

## Workflow

Every contribution follows the same six steps:

1. Branch off `main`, following the repository's branch-naming convention.
2. **Propose an OpenSpec change first** if the change is user-visible. Every feature starts with a spec change; code follows the spec, not the other way around.
3. Implement, with tests in the right tier.
4. Run `make verify-all` locally.
5. Open a PR; the title must follow **Conventional Commits** format.
6. Wait for review. Branches are squash-merged into `main`.

### Conventional Commits

PR titles and commit subjects must follow the [Conventional Commits](https://www.conventionalcommits.org/) specification: `type(scope): description`. The pre-commit hook enforces this. `AGENTS.md` carries the full rules, branch naming, and merge policy.

### Work that is not ready yet

Everything lands on `main`, and a release is a tagged `main` — there is no second branch. Work that is not ready for users still lands on `main`, behind an entry in the experimental-feature registry (`coffer.domain.features`): off on a `stable` release, on in every `dev` build. Every surface the work adds is gated through that entry. Once it is ready, it leaves the registry and its gates are deleted in the same PR. See [Experimental features](/guide/experimental-features).

### OpenSpec

Coffer writes its specs with [OpenSpec](https://github.com/Fission-AI/OpenSpec). Every user-visible change starts as an OpenSpec change (`/opsx:propose`) — a proposal, an optional design, a task list and the spec deltas — written **before** implementation begins, and archived into the specs (`/opsx:archive`) in the same PR. Capabilities are named, never numbered; a CI gate rejects a numbered reference. The spec is the contract; the implementation must satisfy it. `.agents/openspec.md` carries the full workflow.

## Testing

Four tiers, run before opening a PR:

```bash
make verify-unit          # < 5s
make verify-integration   # < 30s
make verify-contract      # < 5s
make verify-e2e           # MCP shim + daemon round-trip

make verify               # lint + unit + integration + contract + acceptance (skips e2e)
make verify-all           # verify + e2e
```

`make verify` includes `make lint`, which is more than ruff, mypy and the frontend's
eslint/tsc — it also runs the repository's own gates: file-size limits
(`check_file_sizes.py`), response-model coverage (`check_response_models.py`), named-not-
numbered specs and ADRs (`check_doc_numbering.py`), requirement citations that name a real
title (`check_spec_citations.py`), the architecture-doc check
(`check_architecture_doc.py`), the import-linter layering contracts, and the i18n key
dump. Running the test tiers alone is **not** the same as running `make verify`.

## Security

Do not open public GitHub issues for security findings. See [Security](/contributing/security).

## License

By contributing, you agree your contributions are licensed under the [MIT License](https://github.com/wyx-sg/Coffer/blob/main/LICENSE).
