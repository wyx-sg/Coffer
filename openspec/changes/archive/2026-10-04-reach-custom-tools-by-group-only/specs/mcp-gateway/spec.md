## ADDED Requirements

### Requirement: Switch off one custom tool
A custom tool that is switched off MUST be left out of `tools/list` and of
`coffer__search_tools` results, and a call on it MUST be recorded as `denied`
and answered with TOOL_DISABLED. A tool that is on reaches exactly the agents its
group reaches: a tool has no reach of its own.

#### Scenario: a switched-off custom tool is hidden and refused
- **GIVEN** a group with two tools, one switched off
- **WHEN** an agent lists the tools and then calls the switched-off one by its name
- **THEN** only the other tool is listed, and the call is refused with TOOL_DISABLED and recorded as `denied`

#### Scenario: every tool that is on follows its group's reach
- **GIVEN** a group reaching Claude Code only, with two tools that are on
- **WHEN** Claude Code and Codex each list the gateway's tools
- **THEN** Claude Code is offered both tools and Codex neither

## MODIFIED Requirements

### Requirement: Import custom tools from an OpenAPI document
The system MUST read an OpenAPI 3.0 or 3.1 document, JSON or YAML, given as a
file or fetched from a URL, into draft tools — one per operation, named from
its `operationId`, with its path and query parameters as holes, its JSON
request body as a `body` argument, and local `$ref`s resolved — and suggest
the base URL from its `servers` and the header a credential goes in from its
security schemes (`Authorization` for bearer, basic and OAuth; the key's name for
an API key), which the form pre-fills as one header row with no value. Each
draft operation MUST carry its text in the document with its first and last
line, and its text is kept on the tool it becomes. A document that cannot be
parsed MUST be refused with the line and column where it broke. A URL that does
not answer — its host name does not resolve, the connection is refused, or it
times out — MUST be refused with the distinct code `OPENAPI_UNREACHABLE`, the
reason, and a hand-off prompt about checking the URL, the network, VPN or proxy
(Principle IV, AI-Native). A URL typed into the import MUST pass the SSRF guard before it is fetched, and
the document MUST be at most 5 MiB. The chosen operations become the tools of
a new group, which records where the document came from and the operations
left out. **Re-import** MUST read the source again and first preview the
operations it would add, the tools it would remove and the ones it keeps,
changing nothing; applying it MUST remove the removed tools, add the chosen
added ones switched on, refresh each kept tool's request from the document and
keep its switch and changes-data flag. A tool added by hand is
never removed by a re-import.

#### Scenario: an OpenAPI document becomes draft tools
- **GIVEN** an OpenAPI 3.1 document with five operations, a server URL and a bearer security scheme
- **WHEN** it is read for import
- **THEN** five draft tools are returned with their methods, paths and argument schemas, the server URL as the base URL and `Authorization` as the suggested header
- **AND** creating a group from three of them yields exactly those three tools, each switched on, and records the other two as left out

#### Scenario: the import preview shows each operation's source
- **GIVEN** an OpenAPI document written over several lines
- **WHEN** it is read for import
- **THEN** each operation carries its first and last line and its text in the document, and the tool drafted from it keeps that text

#### Scenario: an unreadable spec says where it broke
- **GIVEN** a JSON document with a missing comma on line 5, and a YAML document with an unclosed bracket
- **WHEN** each is read for import
- **THEN** each is refused as `OPENAPI_UNREADABLE` with the line and column where it broke

#### Scenario: an unreachable spec URL says why
- **GIVEN** an import URL whose host name does not resolve, one that refuses the connection, and one that times out
- **WHEN** each is read for import
- **THEN** each is refused as `OPENAPI_UNREACHABLE` with the reason `dns`, `refused` or `timeout` and a hand-off prompt naming the URL

#### Scenario: an OpenAPI URL on a private address is refused
- **GIVEN** an import URL whose host resolves to a loopback or private address
- **WHEN** it is read for import
- **THEN** the read is refused before any request is sent, and the refusal says to import the document as a file

#### Scenario: re-import applies additions and removals keeping switches
- **GIVEN** a group imported with three operations, one of them switched off, and a document that now drops one of them and adds a new one
- **WHEN** re-import is previewed and then applied with the new operation chosen
- **THEN** the preview names one operation to add and one tool to remove and nothing changed before applying
- **AND** after applying, the dropped tool is gone, the new tool is on, and the kept tools keep their switch

### Requirement: Manage custom tools through REST and the Custom tools page
Custom-tool groups MUST be managed through `/api/v1/custom-tools` — list
(failing groups first, each with its health, its secret's state, its calls and
failures in the last 24 hours and its tools), create (with tools), read,
change, delete, add / change / remove one tool, test a draft tool once without saving it, read an OpenAPI document,
and preview and apply a re-import — and on the Custom tools page, which calls
those routes; the command line carries no custom-tool command. A change that
waits for a secret approval MUST report it as a pending approval on the Secrets
page ([secret](../secret/spec.md) "Hold a secret for a new destination until a
person approves it").
A group's health MUST be `off` while disabled, `failing` when its last call
in 24 hours failed, `attention` while its secret is missing or waits for
approval, `healthy` after a successful last call, and `idle` with no call in
24 hours.

#### Scenario: create a custom-tool group and add a tool
- **GIVEN** the daemon is running and a stored secret `deploy-token` whose binding is approved
- **WHEN** the user creates a group `deploy` with `POST /api/v1/custom-tools` (base URL `https://deploy.example/v1`, an `Authorization` header with the prefix `Bearer ` and the secret `deploy-token`), then adds a `rollback` tool with `POST /api/v1/custom-tools/deploy/tools` (method `POST`, path `/services/{service}/rollback`, a required string argument `service`)
- **THEN** reading the group lists the `rollback` tool with the changes-data flag on
- **AND** `POST /api/v1/custom-tools/deploy/test` for that tool with the argument `service=web` returns the upstream's status line

#### Scenario: a test runs a draft tool once without saving it
- **GIVEN** a group with an approved secret
- **WHEN** a draft tool that is not saved is tested with sample arguments
- **THEN** the response's status, duration and body are returned, the group's tools are unchanged, and nothing is added to the invocation log

#### Scenario: the group list puts a failing group first
- **GIVEN** one group whose last call failed, one whose last call succeeded and one disabled
- **WHEN** the groups are listed
- **THEN** the failing group comes first with health `failing`, then the healthy one, and the disabled one last with health `off`

## REMOVED Requirements

### Requirement: Switch off or narrow one custom tool
**Reason**: A per-tool reach override duplicated the group's reach for a case the on/off switch and a second group already cover, and put a reach control in every row of the tools table.
**Migration**: `~/.coffer/local/tool-reach.json` is no longer read or written; a tool that was narrowed now follows its group. The route that set or cleared one tool's reach is removed. Switching a tool off is "Switch off one custom tool".
