## Why

Coffer tracks the command-line tools skills require, the launchers MCP servers
start with and the tools a person adds by hand — what each is for, who needs it,
whether it is ready on this machine. Only the CLIs page showed it, and an agent
has no page: it learned nothing from a tool the developer added, and could not
tell a tool Coffer knows to be missing from one it never heard of.

## What Changes

- `coffer cli list [--json]` prints every command Coffer manages, problems
  first: status, version, what it is for, and who needs it. `--json` carries the
  rows of `GET /api/v1/clis`, hand-off prompts included. It reads Coffer's last
  check and runs none.
- The `coffer-guide` manual names it, so every agent learns where to look.
- The command is recorded as a hand-off command; the removed-commands gate lists
  the old group's other verbs.

## Capabilities

### Modified Capabilities
- `skill-manager`: an agent reads the managed commands with `coffer cli list`.
- `resource-framework`: `cli list` joins the kept command tree.
- `knowledge`: the guide's manual names `coffer cli list`.

## Impact

`surfaces/cli/cli_cmd.py`, `command_reasons.py`, the `coffer-guide` asset, the
CLI reference pages, `docs-site/guides/clis.md` and `skills.md` (en + zh),
`scripts/check_removed_commands.py`.
