# Contributing to Coffer

Thanks for your interest in Coffer. This page is the **human contributor** entry point. AI agents (Claude Code, Codex, Cursor) should read `AGENTS.md` in the repository root instead.

## Quick Start

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
make install    # venv + backend deps
make hooks      # wire pre-commit + commit-msg hooks
make dev        # backend daemon (:8000)
```

## Project Anchors

- **`.specify/memory/constitution.md`** — what Coffer is and what it must never become.
- **`AGENTS.md`** — operating manual; humans can read it too, the rules apply equally.

## Workflow

Every contribution follows the same six steps:

1. Branch off `main` (see [Conventional Commits & git workflow](/reference/conventions/workflow) for naming conventions).
2. **Write or update the spec first** if the change is user-visible — see [Spec-driven development](/reference/conventions/sdd). Every feature starts with a spec; code follows the spec, not the other way around.
3. Implement, with tests in the right tier.
4. Run `make verify-all` locally.
5. Open a PR; the title must follow **Conventional Commits** format.
6. Wait for review. Branches are squash-merged into `main`.

### Conventional Commits

PR titles and commit subjects must follow the [Conventional Commits](https://www.conventionalcommits.org/) specification: `type(scope): description`. The pre-commit hook enforces this. See [Conventional Commits & git workflow](/reference/conventions/workflow) for the full rules, branch naming, and merge policy.

### Spec-driven development (SDD)

All user-visible changes require a spec — a `specs/<NNN>-<short-name>/spec.md` — to be written or updated **before** implementation begins. The spec is the contract; the implementation must satisfy it. See [Spec-driven development](/reference/conventions/sdd) for the full SDD discipline.

## Testing

Four tiers, run before opening a PR:

```bash
make verify-unit          # < 5s
make verify-integration   # < 30s
make verify-contract      # < 5s
make verify-e2e           # MCP shim + daemon round-trip

make verify               # unit + integration + contract (skip e2e)
make verify-all           # everything
```

## Security

Do not open public GitHub issues for security findings. See [Security](/contributing/security).

## License

By contributing, you agree your contributions are licensed under the [MIT License](https://github.com/wyx-sg/Coffer/blob/main/LICENSE).
