## Why

The 2026-11-06 review of command-line tool management found that Coffer's login
check duplicated what an agent already does: an agent that runs `gh` sees "not
logged in" itself and can run `gh auth status`. The check also had two defects
(a timeout or a failed run read as logged out, and after a daemon restart the
unknown login state read as ready). The same holds for the version check: an
agent that needs a newer `gh` sees the error and runs `gh --version` itself,
while Coffer's own `--version` probe could not read every tool's output and
needed a "can't compare" flag for those. The owner's principle is that Coffer
stays as lean as possible and leaves to the agent what the agent can do, so
both checks go and Coffer runs none of the commands it checks. The options are
argued in ADR `agents-check-cli-logins-themselves`.

## What Changes

- Coffer runs no command it checks: it only looks each one up on the agent's
  `PATH`. A command is `missing` or `ready`.
- Login checks go: `login_check`, `login` and the `logged_out` status.
- Version checks go: `min_version` (and `version`, `gh>=2.40`), the `outdated`
  status, the `cli_outdated` attention reason, the version on CLI rows, the MCP
  launcher's version and the Minimum version field in Add/Edit CLI. A skill that
  still declares any of them is accepted without a warning and the fields are
  never read (`gh>=2.40` reads as `gh`); a stored hand-added `min_version` or
  `login_check` is dropped the next time the entry is written, and one sent to
  the REST route is ignored.
- The hand-off prompt (only for a missing command) ends with "confirm it works,
  then run `coffer cli check <cmd>`".
- Claude Code and Codex sessions Coffer starts get the same `PATH` the CLIs page
  checks commands on.
- `coffer-guide` points agents at `coffer cli list` for which tools the developer
  uses, and leaves checking install, version and login to the agent.
- Writing the `cli-tools` document now drops an emptied `notes` or `edits` key
  (it was kept by the vault's ordered merge).

## Impact

- `domain/skill` (requirements, requirements_union, cli_status, cli_declared),
  `command_probe`, `cli_requirements`, `cli_handoff`, `cli_attention`,
  `cli_tools`, `cli_tool_repo`, MCP `server_requires`, chat providers, HTTP and
  CLI surfaces, the CLIs page, Requires tab, skill banners, Overview and the MCP
  server's Requires; skill-manager, web-ui, resource-framework and mcp-gateway
  specs; CLIs, skills and MCP docs (English and Chinese); the Capabilities
  canvas.
