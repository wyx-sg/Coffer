# Contributing to Coffer

Thanks for the interest in Coffer. This file is the **human contributor** entry point. AI agents (Claude Code, Codex, Cursor) should read [`AGENTS.md`](./AGENTS.md) instead.

## Quick Start

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
make install                       # venv + backend deps
make hooks                         # wire pre-commit + commit-msg hooks
make dev                           # backend daemon (:8000)
```

## Project Anchors

- **[`.specify/memory/constitution.md`](./.specify/memory/constitution.md)** — what Coffer is and what it must never become.
- **[`AGENTS.md`](./AGENTS.md)** — operating manual; humans can read it too, the rules apply equally.

## Workflow

1. Branch off `main` (see [`agents/workflow.md`](./agents/workflow.md) for naming).
2. Write or update `specs/<NNN>-<short-name>/spec.md` **first** if the change is user-visible (see [`agents/sdd.md`](./agents/sdd.md)).
3. Implement, with tests in the right tier (see [`agents/testing.md`](./agents/testing.md)).
4. `make verify-all` locally.
5. Open a PR; title must be Conventional Commits.
6. Wait for review + merge. Branch is squash-merged.

## Testing

Four tiers, see [`agents/testing.md`](./agents/testing.md):

```bash
make verify-unit          # < 5s
make verify-integration   # < 30s
make verify-contract      # < 5s
make verify-e2e           # MCP shim + daemon round-trip

make verify               # unit + integration + contract (skip e2e)
make verify-all           # everything
```

## Security

Don't open public issues for security findings. See [`SECURITY.md`](./SECURITY.md).

## License

By contributing, you agree your contributions are licensed under the [MIT License](./LICENSE).
