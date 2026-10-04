## Why

After a Codex agent was switched onto a Coffer provider, Codex's first turn hung
("Task creation is not yet confirmed"). Codex's own log showed its provider `auth`
command, `coffer proxy token`, timed out after 5000 ms. The command takes about a
second warm but exceeded Codex's 5 second default on a cold start: the daemon had
just restarted and Codex was launching many MCP servers at once.

## What Changes

- The `auth` table Coffer projects into Codex's `config.toml` carries
  `timeout_ms = 30000`.
- An existing projection without it is a parameter difference, so the reconcile
  pass rewrites it; nothing is migrated by hand.

## Impact

- Backend: `domain/provider/codex_projection.py`.
- Specs: provider-switching.
- Docs: architecture/model-proxy, guides/providers (en and zh), the model-proxy ADR.
