## MODIFIED Requirements

### Requirement: Name a missing stdio launcher
A stdio server whose launcher command does not resolve on this machine (an imported server referencing e.g.
`uvx` where `uv` is not installed) MUST be surfaced as such — `missing <runner>` in the server status —
instead of a bare "failing" with no cause. Coffer MUST NOT install it, and MUST NOT name a package-manager
command for it either: which installer fits depends on the machine, so installing the launcher is handed to
the person's agent (Principle IV, AI-Native). The server's status read
(`GET /api/v1/resources/mcp_server/{uid}/status`), a failed test of it
(`POST /api/v1/resources/mcp_server/{uid}/test`) and its `mcp_missing_launcher` attention item MUST each carry
`handoff`, one prompt that names the server, the launcher, the command line the server is started with, the
`PATH` Coffer looks it up on and this machine's OS and architecture, asks for an install a process started
from the GUI can find, and names `coffer mcp test <name>` to confirm. The command line MUST NOT carry a secret:
an argument that follows a secret-named flag or looks like a token reads `<secret>`, and environment values
are never quoted. The attention item's reason MUST name no command. `coffer mcp prompt <name>` MUST print the
status read's prompt as served.

#### Scenario: a missing stdio launcher is named in the server status
- **GIVEN** a stdio server (e.g. imported from another machine) whose launcher command does not resolve on this machine,
- **WHEN** the server's status is read,
- **THEN** it reports `missing <runner>` instead of a bare failing state, with a `handoff` for installing it rather than Coffer installing it ("Name a missing stdio launcher").

#### Scenario: the launcher hand-off names the launcher, the server and its command
- **GIVEN** a stdio server started as `uvx mcp-atlassian --api-token <value>` with an environment variable holding a value, on a machine where `uvx` is not found
- **WHEN** its status is read
- **THEN** the `handoff` prompt names `uvx`, the server, the command line with the token's value replaced by `<secret>`, the `PATH` and this machine, and names `coffer mcp test <name>`
- **AND** it names no package manager (`brew install`) and neither the token's nor the environment variable's value appears in it

#### Scenario: the missing launcher attention item carries the same hand-off
- **GIVEN** an enabled stdio server whose launcher is not found on this machine
- **WHEN** the attention list is read
- **THEN** its `mcp_missing_launcher` item carries the launcher hand-off and its reason names no command

#### Scenario: coffer mcp prompt prints the server's hand-off
- **GIVEN** a server whose status read carries a `handoff`, and one whose status carries none
- **WHEN** `coffer mcp prompt <name>` is run for each
- **THEN** the first prints the prompt exactly as the route serves it, and the second says there is nothing to hand off and exits 5

## ADDED Requirements

### Requirement: Hand a failing MCP server's diagnosis to an agent
Finding why a server will not start or answer depends on the machine, so a failing server MUST offer its
diagnosis as a hand-off prompt for the person's agent (Principle IV, AI-Native). The status read of a
server that reads `failing` (and is not missing its launcher or a secret), a failed test of a registered
server whose launcher resolves, and the `mcp_failing` attention item MUST carry `handoff`: one prompt naming
the server, its transport and a config summary — the command line and working directory, or the URL — with
the NAMES of its environment variables, headers and stored secrets and never their values, a URL's
`user:pass@` and secret-named query values and any secret-looking argument reading `<secret>`; the error of
the test or of the last failed call; at most the newest 20 lines the server printed on stderr (the test's
own capture, else the server's log file, whose path it names), each passed through the same secret scrub;
and this machine. Its steps MUST ask to find the cause (a missing environment variable, a wrong path, a
package that won't start) and propose the fix before changing anything, MUST forbid reading or changing the
secrets Coffer stores, and MUST name `coffer mcp test <name>` to verify. A resolved secret is never read for
it. A test that failed because a stored secret was not released carries no `handoff`: that fix is the
person's own. `coffer mcp test <name> --prompt` MUST print a failed test's prompt as served.

#### Scenario: the diagnosis prompt never carries a secret value
- **GIVEN** a failing stdio server whose arguments hold a token, whose environment sets a value, whose stored secret is cited by a key, and whose stderr printed a bearer token
- **WHEN** its diagnosis prompt is built
- **THEN** it names the environment variable and the secret's key, quotes the command line and the stderr lines with every one of those values replaced by `<secret>`
- **AND** none of the values appears anywhere in the prompt

#### Scenario: a failed test hands over its error and its stderr
- **GIVEN** a registered stdio server whose launcher resolves but whose test fails with an error after printing 25 stderr lines
- **WHEN** it is tested
- **THEN** the result carries a `handoff` naming the server, its transport, the error and the newest 20 stderr lines, and naming `coffer mcp test <name>`

#### Scenario: a failing server's status and attention item carry the diagnosis
- **GIVEN** an enabled server whose last test failed
- **WHEN** its status and the attention list are read
- **THEN** the status's `handoff` and the `mcp_failing` item's `handoff` both ask to find the cause without changing stored secrets, and the item's reason names no command

#### Scenario: coffer mcp test prints the diagnosis with --prompt
- **GIVEN** a server whose test fails with a `handoff`
- **WHEN** `coffer mcp test <name>` is run, and run again with `--prompt`
- **THEN** both exit 7; the first points at `--prompt`, and the second prints the prompt exactly as the route serves it
