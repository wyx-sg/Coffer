## Why

The 2026-11-06 review of command-line tool management found that Coffer's login
check duplicated what an agent already does: an agent that runs `gh` sees "not
logged in" itself and can run `gh auth status`. The check also had two defects
(a timeout or a failed run read as logged out, and after a daemon restart the
unknown login state read as ready). The owner's principle is that Coffer stays as
lean as possible and leaves to the agent what the agent can do, so login checks
go. The options are argued in ADR `agents-check-cli-logins-themselves`.

## What Changes

- Coffer checks no login: `login_check`, `login` and the `logged_out` status are
  gone. A skill that still declares `login_check` / `login` is accepted without a
  warning and the fields are never read; a stored hand-added `login_check` is
  dropped the next time the entry is written.
- A found command whose version can't be read carries `version_unverifiable`
  when a minimum is asked for, and the CLIs page says the minimum can't be
  compared.
- The hand-off prompt ends with "confirm it works, then run
  `coffer cli check <cmd>`", with no hard-coded `--version`.
- Claude Code and Codex sessions Coffer starts get the same `PATH` the CLIs page
  checks commands on.
- `coffer-guide` points agents at `coffer cli list` for which tools the developer
  uses, and leaves checking install and login to the agent.
- Writing the `cli-tools` document now drops an emptied `notes` or `edits` key
  (it was kept by the vault's ordered merge).
- `docs/TODO.md` records the deferred CLI items.

## Impact

- `domain/skill` (requirements, cli_status, cli_declared), `command_probe`,
  `cli_requirements`, `cli_handoff`, `cli_tool_repo`, chat providers, HTTP and
  CLI surfaces, the CLIs page and Requires tab; skill-manager, web-ui and
  resource-framework specs; CLIs and skills docs (English and Chinese); the
  Capabilities canvas.
