## ADDED Requirements

### Requirement: Serve an HTTP API as a group of custom tools
The gateway MUST support a third upstream transport, `http_api`, whose server
is a **custom-tool group**: an `mcp_server` whose tools are HTTP requests the
gateway makes itself, with no process to run and no MCP server at the other
end. A group MUST carry a base URL (`http` or `https`), optional static
headers, an optional auth header whose value is one stored secret (with an
optional prefix such as `Bearer `), a per-request timeout between 1 and 300
seconds (30 by default) and its tools. Each tool MUST carry a name unique in
the group, a description, a method (GET, POST, PUT, PATCH or DELETE), a path
template relative to the base URL whose `{argument}` holes may sit in the path
or the query, optional headers, an optional JSON body template, the JSON
Schema of its arguments, an on/off switch and a changes-data flag. Like every
server, the group's name is fixed and prefixes each tool an agent sees as
`<group>__<tool>` ("Namespace every upstream capability"). A tool whose
template names an argument its schema does not declare, or whose path is not
a path (`//host`, a URL with a scheme), MUST be refused when it is saved, with
nothing persisted.

#### Scenario: a custom tool reaches the agent under its group's prefix
- **GIVEN** a group `billing` with a `list_invoices` tool, reaching every agent
- **WHEN** an agent lists the gateway's tools
- **THEN** it is offered `billing__list_invoices` with the tool's description and argument schema

#### Scenario: a tool naming an undeclared argument is refused
- **GIVEN** a group `billing`
- **WHEN** a tool with path `/invoices/{id}` and an argument schema that declares no `id` is added
- **THEN** the addition is refused as a validation error naming `id`, and the group is unchanged

### Requirement: Make a custom tool's request in the gateway
On `tools/call` for a custom tool the gateway MUST render the request from the
arguments — each path hole percent-encoded so a value cannot change the path,
the query or the host; a query pair whose hole's argument is absent dropped;
the body template filled with JSON values, or, with no template, the unused
arguments sent as a JSON object for POST, PUT and PATCH — add the auth header
with the secret's value last, send it with the group's timeout without
following redirects, read at most 1 MiB of the response, and return one text
result that starts with the HTTP status line. A status of 400 or more MUST be
returned as an in-band tool error; a redirect MUST be returned, not followed;
a timeout MUST be recorded as `timeout`. The secret's value MUST NOT appear in
the result, the tool's description or schema, or any log, invocation or audit
record: an occurrence in the response is masked as `***`. Every call MUST be
recorded like any other tool call ("Record invocations without content").

#### Scenario: a custom tool call sends the rendered request with the secret
- **GIVEN** a group with base URL `https://api.example/v2`, auth header `Authorization` with prefix `Bearer ` bound to an approved secret, and a tool `GET /invoices/{id}?status={status}`
- **WHEN** an agent calls it with `id` = `a/b` and no `status`
- **THEN** the gateway sends `GET https://api.example/v2/invoices/a%2Fb` with `Authorization: Bearer <secret>`
- **AND** the agent receives `HTTP 200 OK` and the body, and the invocation log records one `ok` call with no arguments or content

#### Scenario: a custom tool's response is capped and masked
- **GIVEN** an upstream that answers with a 2 MiB body containing the secret's value
- **WHEN** an agent calls the tool
- **THEN** the result holds at most 1 MiB of the body, says it was truncated, and shows `***` where the secret's value was

#### Scenario: an error status is an error result and a redirect is not followed
- **GIVEN** one tool whose upstream answers 404 and one whose upstream answers 302 to another host
- **WHEN** an agent calls each
- **THEN** the first result is an in-band error starting `HTTP 404`, recorded as `error`
- **AND** the second result reports the 302 and its location, and no request reaches the other host

### Requirement: Annotate every tool with whether it changes data
Each entry the gateway lists MUST carry the MCP annotations its upstream
declared. A custom tool MUST be listed with `readOnlyHint: false` and
`destructiveHint: true` when its changes-data flag is on, and with
`readOnlyHint: true` otherwise. The flag MUST default to on for every method
but GET, and a person MAY turn it off or on for any tool.

#### Scenario: a custom tool that changes data is annotated destructive
- **GIVEN** a group with `GET /invoices`, `POST /refunds`, and `POST /search` with its changes-data flag turned off
- **WHEN** an agent lists the tools
- **THEN** the refunds tool carries `readOnlyHint: false` and `destructiveHint: true`, and the invoices and search tools carry `readOnlyHint: true`

#### Scenario: an upstream tool's own annotations reach the agent
- **GIVEN** a stdio server whose tool declares `readOnlyHint: true`
- **WHEN** an agent lists the gateway's tools
- **THEN** the namespaced entry carries `readOnlyHint: true`

### Requirement: Switch off or narrow one custom tool
A custom tool switched off, or whose **reach override** does not admit the
session's agent, MUST be left out of `tools/list` and of
`coffer__search_tools` results, and a call on it MUST be recorded as `denied`
and answered with TOOL_DISABLED. A reach override is a list of agent uids that
narrows the group's reach for that one tool — an agent the group does not
reach is not reached by any of its tools — and, like every reach, it is kept on
this machine only and never travels with sync. Removing a tool or its group
MUST remove its override.

#### Scenario: a switched-off custom tool is hidden and refused
- **GIVEN** a group with two tools, one switched off
- **WHEN** an agent lists the tools and then calls the switched-off one by its name
- **THEN** only the other tool is listed, and the call is refused with TOOL_DISABLED and recorded as `denied`

#### Scenario: a reach override hides one tool from one agent
- **GIVEN** a group reaching Claude Code and Codex, and one tool overridden to Claude Code only
- **WHEN** each agent lists the tools
- **THEN** Codex is offered every tool but that one, and Claude Code is offered all of them
- **AND** the override is absent from what the vault syncs

### Requirement: Import custom tools from an OpenAPI document
The system MUST read an OpenAPI 3.0 or 3.1 document, JSON or YAML, given as a
file or fetched from a URL, into draft tools — one per operation, named from
its `operationId`, with its path and query parameters as holes, its JSON
request body as a `body` argument, and local `$ref`s resolved — and suggest
the base URL from its `servers` and the auth header from its security schemes.
A URL typed into the import MUST pass the SSRF guard before it is fetched, and
the document MUST be at most 5 MiB. The chosen operations become the tools of
a new group, which records where the document came from and the operations
left out. **Re-import** MUST read the source again and first preview the
operations it would add, the tools it would remove and the ones it keeps,
changing nothing; applying it MUST remove the removed tools, add the chosen
added ones switched on, refresh each kept tool's request from the document and
keep its switch, changes-data flag and reach override. A tool added by hand is
never removed by a re-import.

#### Scenario: an OpenAPI document becomes draft tools
- **GIVEN** an OpenAPI 3.1 document with five operations, a server URL and a bearer security scheme
- **WHEN** it is read for import
- **THEN** five draft tools are returned with their methods, paths and argument schemas, the server URL as the base URL and `Authorization` with `Bearer ` as the auth header
- **AND** creating a group from three of them yields exactly those three tools, each switched on, and records the other two as left out

#### Scenario: an OpenAPI URL on a private address is refused
- **GIVEN** an import URL whose host resolves to a loopback or private address
- **WHEN** it is read for import
- **THEN** the read is refused before any request is sent, and the refusal says to import the document as a file

#### Scenario: re-import applies additions and removals keeping switches
- **GIVEN** a group imported with three operations, one switched off and one with a reach override, and a document that now drops one of them and adds a new one
- **WHEN** re-import is previewed and then applied with the new operation chosen
- **THEN** the preview names one operation to add and one tool to remove and nothing changed before applying
- **AND** after applying, the dropped tool and its override are gone, the new tool is on, and the kept tools keep their switch and reach override

### Requirement: Wait for approval before a custom tool sends its secret
Binding a stored secret to a group's auth header MUST be treated as a new
destination whose target is the group's base URL and whose slot is the header
name ([credentials](../credentials/spec.md) "Hold a secret for a new
destination until a person approves it"): no call and no Test carries the
secret until a person approves it for that base URL, a call before then fails
with `SECRET_BINDING_PENDING`, and changing the base URL or the header asks
again. The group MUST report its secret as `present`, `missing` or
`pending_approval`, with the ids of the approvals it waits on.

#### Scenario: binding a stored secret to a group waits for approval
- **GIVEN** a stored secret `billing-token`
- **WHEN** a group is created with its auth header bound to `billing-token`, and an agent calls one of its tools
- **THEN** the group reports `pending_approval` naming one approval for its base URL, and the call fails with `SECRET_BINDING_PENDING` having sent nothing
- **AND** once the approval is applied the next call carries the secret

#### Scenario: moving a group's base URL asks again
- **GIVEN** a group whose secret is approved for its base URL
- **WHEN** its base URL is changed
- **THEN** the group reports `pending_approval` for the new base URL and calls carry no secret until it is approved

### Requirement: Manage custom tools on REST and the command line
Custom-tool groups MUST be managed through `/api/v1/custom-tools` — list
(failing groups first, each with its health, its secret's state, its calls and
failures in the last 24 hours and its tools), create (with tools), read,
change, delete, add / change / remove one tool, set or clear one tool's reach
override, test a draft tool once without saving it, read an OpenAPI document,
and preview and apply a re-import — and through `coffer tool` (`list`, `show`,
`add` with `--openapi` to import, `edit`, `rm`, `enable`, `disable`, `scope`,
`reimport`) and `coffer tool op` (`add`, `edit`, `rm`, `enable`, `disable`,
`scope`, `test`), with `--json` on every read. A change that waits for a secret
approval MUST report it as every other command does ([credentials](../credentials/spec.md)
"Answer a pending approval on the command line by waiting or exiting").
A group's health MUST be `off` while disabled, `failing` when its last call
in 24 hours failed, `attention` while its secret is missing or waits for
approval, `healthy` after a successful last call, and `idle` with no call in
24 hours.

#### Scenario: the command line creates a group and adds a tool
- **GIVEN** the daemon is running and a stored secret `deploy-token` whose binding is approved
- **WHEN** the user runs `coffer tool add deploy --base-url https://deploy.example/v1 --auth-header Authorization --auth-prefix "Bearer " --secret deploy-token`, then `coffer tool op add deploy rollback --method POST --path /services/{service}/rollback --arg service:string:required`
- **THEN** `coffer tool show deploy --json` lists the `rollback` tool with the changes-data flag on
- **AND** `coffer tool op test deploy rollback --arg-value service=web` prints the upstream's status line

#### Scenario: a test runs a draft tool once without saving it
- **GIVEN** a group with an approved secret
- **WHEN** a draft tool that is not saved is tested with sample arguments
- **THEN** the response's status, duration and body are returned, the group's tools are unchanged, and nothing is added to the invocation log

#### Scenario: the group list puts a failing group first
- **GIVEN** one group whose last call failed, one whose last call succeeded and one disabled
- **WHEN** the groups are listed
- **THEN** the failing group comes first with health `failing`, then the healthy one, and the disabled one last with health `off`
