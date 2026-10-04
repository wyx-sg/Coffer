## Why

The CLIs page lists the commands skills declare, the launchers MCP servers
start with and the tools a person adds by hand. Coffer itself also runs a
command: `git`, which keeps the vault's history and syncs it. That dependency
only surfaced as the Sync page's `sync_git_missing` item, so the CLIs page —
the one place that answers "what does this machine need" — never showed it.

## What Changes

- Coffer declares the commands it runs itself (`git`, titled Git, for the
  vault's history and sync). Each is a required command like any other: listed,
  checked on the agent's `PATH`, joined with any skill, server or hand-added
  declaration of the same command.
- `GET /api/v1/clis` and `GET /api/v1/clis/{command}` carry
  `needed_by_coffer` — what Coffer runs the command for (`vault_history`,
  `sync`); `coffer cli list` names "Coffer (the vault's history and sync)".
- The hand-off prompt for a missing or outdated `git` says Coffer itself uses
  it to keep the vault's history and to sync the vault.
- A command only Coffer needs raises no `cli_*` attention item: sync's own
  `sync_git_missing` item already reports it.
- The CLIs page counts Coffer among who needs a command ("Coffer and 1 skill"),
  its Needed by section shows a Coffer row naming the uses, and the banner says
  what Coffer can't do without it.

## Capabilities

### Modified Capabilities

- `skill-manager`: adds "List the commands Coffer itself runs".
- `web-ui`: adds "Show the commands Coffer itself runs on the CLIs page".

## Impact

- Backend: `domain/skill/cli_status` (`CofferNeed`, `CofferUse`,
  `COFFER_NEEDS`), `CliRequirementService`, `cli_wiring`, `cli_handoff`,
  `cli_tools`, `cli_schemas`, `coffer cli list`.
- Frontend: `components/clis/*`, `lib/clis/format`, en/zh strings.
- Contract: `CliOut.needed_by_coffer` (skill-manager OpenAPI).
- Docs: guides/clis (en/zh).
