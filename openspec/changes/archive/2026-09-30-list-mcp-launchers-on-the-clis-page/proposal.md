## Why

The CLIs page on the capabilities canvas (boards 4.4.01–4.4.05, 4.4.13 and
4.4.14) lists the command-line tools skills declare **and** the launchers MCP
servers start with (`uv` for `uvx`, `node` for `npx`), and its Needed by
section names the MCP servers beside the skills. The backend only read skills,
so a server whose `uvx` was missing showed on the MCP page but never on the
CLIs page. The page also still showed a "Log in with `gh auth login`" row with
a Copy button and a "Run … in a terminal" sentence, which Principle IV
(AI-Native) rules out: Coffer never installs, updates or logs in for the
person, and hands the fix to an agent instead.

## What Changes

- The required-command check also reads every enabled stdio MCP server's
  launcher and lists it under the command that provides it — `uv` for `uvx`,
  `node` for `npx`, `bun` for `bunx`, the launcher itself otherwise; a launcher
  given as a path is not a command on `PATH` and is not listed. Such a command
  has no minimum and no login check.
- Every command carries `needed_by_servers` (server uid, name and launcher) on
  `GET /api/v1/clis` and `GET /api/v1/clis/{command}`; `coffer cli list|show`
  name the servers too.
- The hand-off prompt names the MCP servers started with the command beside
  the skills that need it; it still names no install command.
- A command only MCP servers need raises no `cli_*` attention item — the
  server's `mcp_missing_launcher` item already reports it — but it counts
  toward the CLIs sidebar badge like any other command that needs the person.
- The CLIs page shows the servers under Needed by, each opening the server's
  page, with a kind badge when both servers and skills need the command; the
  header reads "needed by 1 MCP server and 1 skill"; the banner is a plain
  sentence ("duckdb can't start, and data-profiling fails at the step that
  calls uv."). The login command row and every "run it in a terminal" line are
  gone; `coffer cli show` no longer prints a login command.
- The MCP servers list row for a missing launcher reads "uvx isn't found on
  this machine", as the server's callout does, and so does the attention
  item's reason.

## Capabilities

### Modified Capabilities

- `skill-manager`: "Check every required command where the agent runs",
  "Serve required commands on REST, the command line and the web" and "Hand a
  required command to an agent with a prompt".
- `web-ui`: "Show every CLI a skill requires on the CLIs page" is revised in
  the in-flight change `revise-web-ui-ia`, which owns it.

## Impact

- Backend: `domain/skill/cli_status` (`ServerLauncher`, `launcher_cli`),
  `CliRequirementService` (`McpLaunchersPort`), a new
  `application/mcp/stdio_launchers` reader wired at the composition root,
  `cli_handoff`, `cli_attention`, `cli_schemas`, `coffer cli`.
- Frontend: `components/clis/*`, `lib/clis/format`, en/zh strings, the MCP
  list row's launcher reason.
- Contract: `CliOut.needed_by_servers`, `CliServerOut` (skill-manager OpenAPI).
- Docs: guides/clis, guides/mcp-servers, the coffer-guide skill's CLI section.
