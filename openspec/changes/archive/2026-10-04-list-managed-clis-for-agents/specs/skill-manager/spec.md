## MODIFIED Requirements

### Requirement: Serve required commands on REST and the web
The required commands MUST be readable and checkable through
`GET /api/v1/clis`, `GET /api/v1/clis/{command}`, `POST /api/v1/clis/check`
and `POST /api/v1/clis/{command}/check`, each command carrying its hand-off
prompt and the MCP servers started with it (`needed_by_servers`: each server's
uid, name and launcher) beside the skills that need it (`needed_by`). An
agent reads the same list with `coffer cli list` (`--json` for the full rows,
hand-off prompts included), the one required-command command: it reads what
Coffer last found and MUST NOT run a check or a login check. Lists MUST put problems first: missing, then outdated, then not
logged in, then ready. The web UI's CLIs page shows them (spec web-ui "Show
every CLI a skill requires on the CLIs page") and a skill's detail page
carries a **Requires** tab listing what the skill declares, each linked to its
command's page and offering the hand-off for a command that needs the user.

#### Scenario: required commands list problems first
- **GIVEN** skills requiring a missing `jq`, an outdated `gh` and a ready `uv`
- **WHEN** the user reads `GET /api/v1/clis`
- **THEN** the commands come back in the order `jq`, `gh`, `uv`, each with its status and the skills that need it

#### Scenario: the route and the page carry the same prompt
- **GIVEN** a missing required command `jq` and a ready `uv`
- **WHEN** the user reads `GET /api/v1/clis/jq` and the CLIs page's Copy prompt for `jq`
- **THEN** both carry exactly the same `handoff.prompt`
- **AND** `GET /api/v1/clis/uv` carries a `null` `handoff` and the page offers no prompt for it

#### Scenario: a CLI page lists the MCP servers started with the command
- **GIVEN** an enabled stdio MCP server `duckdb` started with `uvx`, a skill `data-profiling` requiring `uv`, and no `uv` on the agent's `PATH`
- **WHEN** the user reads `GET /api/v1/clis/uv`
- **THEN** it is `missing`, `needed_by` names `data-profiling`, `needed_by_servers` names `duckdb` with launcher `uvx`, and its hand-off prompt names both

#### Scenario: an agent lists the command-line tools Coffer manages
- **GIVEN** a skill requiring a missing `gh`, an MCP server started with `uvx` and a ready `uv`, and `jq` added by hand with the title `JSON` and a description
- **WHEN** an agent runs `coffer cli list`, and then `coffer cli list --json`
- **THEN** the table lists `gh`, `uv` and `jq` problems first, each with its status, what it is for and who needs it — the skill, the MCP server, or added by hand
- **AND** the JSON carries the same rows as `GET /api/v1/clis`, and the command made that one read and started no check
