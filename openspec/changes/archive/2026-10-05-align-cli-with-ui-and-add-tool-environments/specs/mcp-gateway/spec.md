## ADDED Requirements

### Requirement: Keep a custom-tool group's environments in the group
A custom-tool group MUST keep one set of tools and one or more
**environments**, each named by the user and unique in the group, each with its
own base URL (`http` or `https`, no query or fragment), header rows (a plain
value or a stored secret behind an optional scheme, as for the group's headers
before), non-sensitive variables, an on/off switch, an optional description and
an optional timeout between 1 and 300 seconds that overrides the group's. No
environment name is reserved or special. A tool MUST NOT be copied per
environment: the tool's name, the name an agent sees (`<group>__<tool>`) and
its switch are the same in every environment. A variable is plain text used as
`{env:NAME}` in a tool's path, query, headers or body template and MUST NOT be
used in a base URL; a variable value or a plain header value that looks like a
credential MUST be refused, and a tool naming a variable that an enabled
environment of its group does not define MUST be refused when it is saved. A
group saved before environments existed MUST read as one environment named
`default` holding its base URL and header rows, with its secret bindings kept.
Environments MUST be managed through `/api/v1/custom-tools/{name}/environments`
(add, change, rename, switch on or off, delete; the last environment cannot be
deleted) and in the group's Environments section on the Custom tools page.

#### Scenario: one group serves the same tools in several environments
- **GIVEN** a group `billing` with the tool `list_invoices` and the environments `sandbox` (`https://sandbox.billing.example`) and `prod` (`https://billing.example`)
- **WHEN** an agent lists the gateway's tools
- **THEN** it is offered `billing__list_invoices` once, and no tool is named after an environment

#### Scenario: a group from before environments reads as one environment
- **GIVEN** a stored group with a top-level base URL and an `Authorization` header bound to an approved secret
- **WHEN** it is read and called
- **THEN** it lists one environment `default` with that base URL and header, and the call carries the secret with no new approval

#### Scenario: a variable is substituted per environment and refused in a base URL
- **GIVEN** environments `eu` and `us` defining the variable `region` as `eu-1` and `us-1`, and a tool `GET /v1/{env:region}/items`
- **WHEN** the tool is called once per environment
- **THEN** the requests go to `/v1/eu-1/items` on `eu`'s base URL and `/v1/us-1/items` on `us`'s
- **AND** a base URL holding `{env:region}`, and a tool naming a variable `us` lacks, are each refused when saved

#### Scenario: an environment is added, renamed, switched off and deleted
- **GIVEN** a group with the environment `default`
- **WHEN** an environment `staging` is added, renamed `uat`, switched off, and deleted, and then deleting `default` is attempted
- **THEN** each change is saved and audited, and deleting the last environment is refused with nothing changed

### Requirement: Choose a custom tool's environment on every call
Every request of a custom tool — an MCP call, a CLI test and a test on the
Custom tools page — MUST name the environment it is made in; nothing keeps a
current or default environment that one caller's choice could change for
another. The gateway MUST advertise each custom tool with the reserved argument
`coffer_environment`, an enumeration of the group's enabled environments that
is required when the group has more than one enabled environment; a group with
exactly one enabled environment uses it when the argument is absent. The
argument MUST be removed before the request is rendered, so it never reaches the
upstream path, query, headers or body, and a tool's own argument schema MUST NOT
declare it. A caller can choose only a registered, enabled environment: an
unknown name is refused with `CUSTOM_TOOL_ENVIRONMENT_UNKNOWN`, a switched-off
one with `CUSTOM_TOOL_ENVIRONMENT_DISABLED`, and a missing choice with
`CUSTOM_TOOL_ENVIRONMENT_REQUIRED`, each before any request; no argument can
change an environment's base URL, headers or credentials. Concurrent calls of
the same tool in different environments MUST each use only their own
environment's URL, headers, variables and secrets. Region, tenant or customer
ids stay ordinary arguments of the tool.

#### Scenario: concurrent calls in two environments do not mix
- **GIVEN** a group with environments `test` and `live`, each with its own base URL, variable and approved bearer secret, and a tool with a `region` argument
- **WHEN** an agent makes fifty calls of the tool at once, alternating `coffer_environment` between `test` and `live`
- **THEN** every `test` call reaches `test`'s base URL with `test`'s variable and secret and every `live` call reaches `live`'s, with no request carrying the other environment's URL, header or secret
- **AND** no upstream request carries `coffer_environment` in its path, query or body, and `region` is sent as the tool declares it

#### Scenario: an environment that is not registered or is off is refused before any request
- **GIVEN** a group with an enabled environment `test`, a switched-off environment `live` and a second enabled environment `uat`
- **WHEN** a tool is called with `coffer_environment` set to `prod`, then `live`, then with no environment
- **THEN** the calls are refused with `CUSTOM_TOOL_ENVIRONMENT_UNKNOWN`, `CUSTOM_TOOL_ENVIRONMENT_DISABLED` and `CUSTOM_TOOL_ENVIRONMENT_REQUIRED`, and the upstream receives no request

#### Scenario: the advertised schema offers only enabled environments
- **GIVEN** a group with enabled environments `test` and `uat` and a switched-off `live`
- **WHEN** an agent lists the gateway's tools
- **THEN** each of the group's tools carries `coffer_environment` as a required enumeration of `test` and `uat`
- **AND** a tool whose own schema declares `coffer_environment` is refused when saved

### Requirement: Validate a custom tool's arguments before any request
A custom tool's argument schema MUST be checked as a JSON Schema when the tool is
saved — its keywords well formed, its patterns valid regular expressions, its
local `$ref`s resolvable — and a malformed schema refused with nothing saved.
Every request of a custom tool MUST validate its arguments against that schema
before anything is sent, covering at least `type` (including OpenAPI 3.0
`nullable`), `enum` and `const`, numeric bounds and `multipleOf`, string length
and `pattern`, array `items`, `prefixItems`, bounds, `uniqueItems` and
`contains`, object `properties`, `required`, `additionalProperties`,
`patternProperties`, property count and `propertyNames`, `allOf`, `anyOf`,
`oneOf`, `not`, `if`/`then`/`else`, `dependentRequired` and local `$ref`. MCP
calls, CLI tests and the page's draft and saved-tool tests MUST use the same
validator. Invalid arguments MUST be refused with `CUSTOM_TOOL_ARGUMENTS_INVALID`
(422 on REST, an in-band tool error on MCP) listing every failure with its
argument path, the keyword it broke and a message, and MUST NOT cause an
upstream request; a missing secret, a pending or refused approval, and an
unknown or switched-off environment are likewise refused before any request.

#### Scenario: invalid arguments are refused field by field with no upstream request
- **GIVEN** a tool whose schema requires `amount` as an integer between 1 and 100, `currency` in `[EUR, USD]`, `tags` as at most 3 unique strings, allows no other property, and requires exactly one of `card` or `iban`
- **WHEN** it is called through MCP, tested on the command line and tested on the page with `amount` = `0`, `currency` = `GBP`, four `tags`, an extra `note` and both `card` and `iban`
- **THEN** each answer is `CUSTOM_TOOL_ARGUMENTS_INVALID` naming `/amount` (`minimum`), `/currency` (`enum`), `/tags` (`maxItems`), `/note` (`additionalProperties`) and the `oneOf` failure
- **AND** the upstream receives no request

#### Scenario: a malformed argument schema is refused when saved
- **GIVEN** a group
- **WHEN** a tool is saved whose schema gives `minimum` as text, a `pattern` that is not a valid regular expression, or a `$ref` to a definition that does not exist
- **THEN** the save is refused as a validation error naming the schema location, and the group is unchanged

#### Scenario: a missing or unapproved secret is refused before any request
- **GIVEN** a group whose `live` environment cites a secret with no value and whose `test` environment waits for approval of its secret
- **WHEN** a tool is called in each environment
- **THEN** the `live` call answers `SECRET_MISSING` and the `test` call `SECRET_BINDING_PENDING` naming its approval and `coffer approval approve <id>`, and the upstream receives no request

### Requirement: Manage custom tools from the command line
Every custom-tool operation of the Custom tools page MUST be available as a
`coffer custom-tool` command that calls the same REST route: list, show, create,
update and delete a group; enable and disable it; set its reach; add, show,
update, enable, disable and delete a tool, including its method, path, headers,
body template, argument schema and `changes_data` (a read-only `POST` may set
`changes_data=false`); add, update, rename, enable, disable and delete an
environment and bind a secret to one of its headers; test a draft tool and a
saved tool in a chosen environment; read an OpenAPI document; and preview and
apply a re-import. A tool's definition, request template and schema MUST be
accepted from flags, a file (`--data @file`) or standard input (`--data -`).
Every command MUST offer `--json` and the exit codes of [resource-framework]
"Offer every management operation on the command line". A command whose change
leaves a secret approval pending MUST print the approval ids and the command
that approves them, and exit `9`. The commands are a client of the REST routes:
no script, local HTTP adapter, proxy or MCP wrapper takes part, and the gateway
calls the upstream API itself.

#### Scenario: a group is configured end to end from the command line
- **GIVEN** a running daemon, a stored secret `billing-test-token` and an HTTP API answering on two base URLs
- **WHEN** an agent runs, one command at a time, `coffer custom-tool group create billing --env test=https://test.billing.example`, `coffer custom-tool env add billing live --base-url https://billing.example`, `coffer custom-tool env set-header billing test Authorization --secret billing-test-token --scheme Bearer`, `coffer custom-tool tool add billing --data @search.json` (a `POST /search` with `changes_data` false), `coffer custom-tool group reach billing --agent claude-code`, and `coffer custom-tool tool test billing search --env test --args '{"q":"x"}' --json`
- **THEN** each command exits `0` except a binding that waits for approval, which prints its approval id and `coffer approval approve <id>` and exits `9`
- **AND** the group, its two environments, the tool with `changes_data` false and the reach are what the Custom tools page shows, and the test's JSON carries the upstream's status line and the environment's actual target

#### Scenario: a change made on the page is read back by the command line
- **GIVEN** a group created with `coffer custom-tool group create`
- **WHEN** a person renames one of its environments and switches a tool off on the Custom tools page, and an agent runs `coffer custom-tool group show <group> --json`
- **THEN** the JSON carries the renamed environment and the tool switched off

#### Scenario: an OpenAPI document is imported and re-imported from the command line
- **GIVEN** an OpenAPI file with three operations
- **WHEN** an agent runs `coffer custom-tool import read --file openapi.yaml --json`, creates a group from two operations with `coffer custom-tool group create --from-openapi openapi.yaml --operation <op> --operation <op>`, and later runs `coffer custom-tool reimport preview <group> --file openapi.yaml` and `coffer custom-tool reimport apply <group> --file openapi.yaml --add <op>`
- **THEN** the read lists three draft tools, the group holds two, the preview names the one to add and changes nothing, and the apply adds it keeping every environment

## MODIFIED Requirements

### Requirement: Manage MCP servers as resources
Users MUST be able to register, list, view, update, enable, disable and delete MCP servers as
resources addressed by the immutable `uid` the framework mints for them
([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md));
the per-server routes are `/api/v1/resources/mcp_server/{uid}/…`.
Validating that registration against the kind's schema, rejecting a duplicate name within the kind, and
persisting nothing on a validation failure are [resource-framework](../resource-framework/spec.md) "Validate every registration and persist nothing on failure", which every kind inherits; this
requirement is what brings `mcp_server` under it, and the kind-agnostic surface those operations are served
through is that spec's too.

A server's `name` is the prefix of every capability name an agent sees, so `mcp_server` declares its name
fixed: once registered it MUST NOT change, and a changed name MUST be refused with `NAME_IMMUTABLE`
([resource-framework](../resource-framework/spec.md) "Treat a resource's name as a mutable label"). A server
carries no title: its fixed name and its description — a note the user keeps for themselves — are all it has
([resource-framework](../resource-framework/spec.md) "Carry an optional editable title on the kinds that have one"),
and the Add and Edit dialogs offer no title field.
The name MUST be at most 24 characters and MUST NOT be `coffer` (the name of Coffer's own gateway), in addition to
the existing name pattern and the ban on `__`, wherever the framework validates it — registration here and a server arriving from another machine alike.

- Registering a server whose upstream is unreachable MUST still succeed (the config is saved); discovery and
  health report the failure, the server is marked unhealthy until reachable, and there MUST be no silent
  retry storm.
- Registering a server whose secret is missing MUST fail with a message naming the missing secret and
  pointing the user at the secret setup path, persisting no partial state. A secret whose new value is
  waiting for approval is not missing: the server is registered citing it, and its value reaches the server
  only once the change is approved.
- Registering a server with a name that already exists within the kind MUST be rejected with a clear error;
  a partial write is impossible.
- Registering, listing, viewing, editing, enabling, disabling, scoping and deleting a server MUST be done
  on the MCP servers page, through the resource routes and with the `coffer mcp` commands that call
  them (`add`, `list`, `show`, `update`, `enable`, `disable`, `reach`, `delete`, `status`, `tools`,
  `tool enable|disable`, `exposure`, `calls`, `server-log`). `coffer mcp test <server>` MUST re-query
  the server's capabilities and then report its health, so one command both refreshes what Coffer
  knows of the server and says whether it answers.
- `coffer mcp test` MUST exit with code 3 and name the condition on stderr when no daemon is reachable
  and one cannot be started (a missing daemon is started on demand, and only a failed or timed-out start
  exits 3). `coffer log mcp` MUST support machine-readable `--json` output.
  The same exit covers a daemon that stops answering after the command has connected to it: the lost
  connection is reported once, as a message naming the condition, never as a traceback.

#### Scenario: register a stdio MCP server
- **GIVEN** the coffer daemon is running and no MCP servers are registered,
- **WHEN** the user registers a stdio MCP server with a unique name, command, and arguments,
- **THEN** the server is persisted, its capabilities are discovered, and listing servers shows it as healthy.

#### Scenario: coffer mcp test exits 3 when no daemon is reachable
- **GIVEN** the daemon is not running and cannot be started (the spawn fails or the daemon does not come up within the boot timeout),
- **WHEN** `coffer mcp test <server>` is invoked,
- **THEN** the process exits with code 3 and stderr names the daemon-unreachable condition.

#### Scenario: coffer log mcp --json prints a parseable document
- **GIVEN** `coffer log mcp` supports `--json`,
- **WHEN** it is invoked with `--json`,
- **THEN** stdout is a parseable JSON document with the stable top-level key `invocations` and no human-readable framing.

#### Scenario: a daemon lost mid-command exits 3
- **GIVEN** a `coffer mcp test` whose client was built against a daemon that has since stopped answering,
- **WHEN** the command makes its request,
- **THEN** the process exits with code 3, and stderr names the daemon-unreachable condition exactly once and carries no traceback.

#### Scenario: a server name longer than 24 characters is refused at registration
- **GIVEN** the coffer daemon is running
- **WHEN** the user registers a new server whose name is 25 characters long, and then one whose name is 24 characters long
- **THEN** the first is refused as a validation error naming the 24-character limit, with nothing persisted, and the second is registered

#### Scenario: a server cannot take the name of Coffer's own gateway
- **GIVEN** the coffer daemon is running
- **WHEN** the user registers a server named `coffer`
- **THEN** it is refused as a validation error saying the name is reserved, with nothing persisted, so no upstream tool can be mistaken for a built-in or shadow `coffer__search_tools`

#### Scenario: test re-queries capabilities before reporting health
- **GIVEN** a registered server whose upstream has gained a tool since Coffer last discovered it
- **WHEN** the user runs `coffer mcp test <server>`
- **THEN** the command reports the server's health, and `GET /api/v1/resources/mcp_server/{uid}/capabilities` then lists the new tool
- **AND** for a server whose upstream is unreachable, the command exits non-zero and names the failure

#### Scenario: an MCP server is shown by its name
- **GIVEN** the daemon is running
- **WHEN** the user registers a server named `fs` with a stdio command and the description "Local files" through the Add dialog (`POST /api/v1/resources/mcp_server`) and then lists servers
- **THEN** the list shows it as `fs` with that description, and reading it back carries a `null` title
- **AND** a title submitted for it through the kind-agnostic update route is refused as a validation error

### Requirement: Toggle individual capabilities
Users MUST be able to enable or disable individual tools, resources, and prompts on a per-server basis.
Disabling a tool MUST make it disappear from any client's next tool-list response and MUST make any call
attempt on it fail with a tool-disabled error (JSON-RPC code -32000, TOOL_DISABLED).

The capabilities MUST be read with `GET /api/v1/resources/mcp_server/{uid}/capabilities` and toggled with
`POST /api/v1/resources/mcp_server/{uid}/capabilities/{capability_type}/enable` or `.../disable` (the
server page's Tools tab), where `capability_type` is `tool`, `prompt` or `resource` and the body names the
capabilities by key. A key that names no capability the server offers MUST be refused with nothing
changed. `coffer mcp tool enable` and `coffer mcp tool disable` call the same routes.

#### Scenario: disable an individual capability
- **GIVEN** a registered MCP server exposes several tools,
- **WHEN** the user disables one tool,
- **THEN** subsequent tool-list requests from any client omit it, and an attempt to call it returns a tool-disabled error.

#### Scenario: disabled capability rejected through the shim
- **GIVEN** a registered MCP server with two tools, where one has been disabled via the REST API,
- **WHEN** a shim client calls `tools/list` and then `tools/call` on the disabled tool,
- **THEN** `tools/list` omits the disabled tool while listing the enabled tool, and `tools/call` returns a JSON-RPC error with code -32000 (TOOL_DISABLED) rather than a successful result.

#### Scenario: capabilities are toggled by typed ref over REST
- **GIVEN** a registered MCP server exposing a tool and a prompt
- **WHEN** the tool and the prompt are each disabled through `.../capabilities/tool/disable` and `.../capabilities/prompt/disable`, then the capabilities are read
- **THEN** both capabilities are disabled, with the disabled ones marked disabled
- **AND** an enable request naming a tool the server does not offer is refused and changes nothing

### Requirement: Record invocations without content
The system MUST record an invocation entry for every tool call, resource read, and prompt fetch — its target,
timestamp, duration and outcome — without recording arguments or return contents. Each entry MUST also carry
its row `id`, and MUST name the agent whose session made the call (`agent_uid`) when that session reported one
on its handshake (see "Take the agent identity from the handshake"); a session that reported none writes
entries naming no agent, never a guessed one. A custom tool's call MUST also name the environment it was made
in (`environment`), and no entry carries a header, a variable or a credential. How long those entries are
kept, and the background pass that prunes them, are [resource-framework](../resource-framework/spec.md) "Prune each registered log table on its own retention period" — the retention contract
every log-writing kind inherits — not this spec's own rule. This spec contributes `mcp_invocations` to that
registry with a 30-day default. The record is read per server
(`GET /api/v1/resources/mcp_server/{uid}/invocations`, `coffer log mcp --server <server>`) or across every
server (`GET /api/v1/mcp/invocations`, `coffer log mcp` with no server), the cross-server read
including Coffer's own built-in calls (`coffer`) and the rows of servers since deleted (their uid, with no name). Both HTTP reads
can be narrowed to one agent's calls with `agent_uid`. Both reads
page newest first by cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor"),
and both CLI forms take `--status`, `--since`, `--limit`, `--cursor` and `--json`. One server's calls since a moment
(24 hours ago by default) are also read counted, for its page:
`GET /api/v1/resources/mcp_server/{uid}/invocations/summary` answers the calls, the errors (every call that
did not end `ok`) and the last call's time, per calling agent and per tool.

#### Scenario: invocation log records calls without arguments
- **GIVEN** an MCP client has invoked tools,
- **WHEN** the user views the invocation log,
- **THEN** every call is present with timestamp, target capability, duration, and outcome, and **no call arguments or return contents are stored**.

#### Scenario: the command line reads the invocation log
- **GIVEN** a running daemon that has recorded invocations on two servers, on a Coffer built-in tool and on a deleted server
- **WHEN** the user runs `coffer log mcp --server <server>` and then `coffer log mcp --status error --json`
- **THEN** the first prints only that server's calls, newest first
- **AND** the second prints, under `invocations`, only failed calls across every server, each naming its server, including `coffer` and the rows of a deleted server

#### Scenario: the invocation log pages by cursor
- **GIVEN** a server with three recorded invocations
- **WHEN** its invocations are read with `limit=2` and then with the answer's `next_cursor`
- **THEN** the first page holds the two newest calls and the second the oldest, with a `null` `next_cursor`

#### Scenario: a server's page reads its calls counted
- **GIVEN** a server with four calls in the last day — two by one agent, one of them failed, one by another agent and one by a session that reported none — and one older call
- **WHEN** `GET /api/v1/resources/mcp_server/{uid}/invocations/summary` is read
- **THEN** it answers four calls and one error, per agent 2/1, 1/0 and 1/0 for the session that reported none, and per tool the calls and errors of each tool
- **AND** the older call and another server's calls are not counted

#### Scenario: the invocation log names the calling agent
- **GIVEN** an agent's session connected through its shim made a call, and a session that reported no agent made another
- **WHEN** the invocation log is read, and read again with `agent_uid` set to that agent's uid
- **THEN** the first call's entry names that agent's uid and the second's names none
- **AND** the filtered read holds only the first call

#### Scenario: a custom tool's call names its environment in the log
- **GIVEN** a custom-tool group with the environments `test` and `live`
- **WHEN** an agent calls one of its tools in `live` and the invocation log is read
- **THEN** the entry names `live` as its environment and carries no header or credential

### Requirement: Serve an HTTP API as a group of custom tools
The gateway MUST support a third upstream transport, `http_api`, whose server
is a **custom-tool group**: an `mcp_server` whose tools are HTTP requests the
gateway makes itself, with no process to run and no MCP server at the other
end. A group MUST carry one or more environments ("Keep a custom-tool group's
environments in the group"), each with a base URL (`http` or `https`) and
optional **header rows**, a per-request timeout between 1 and 300 seconds (30 by
default) and its tools. A header row is a name and a value: plain text, or a
stored secret that holds the credential alone, sent behind the row's scheme when
it has one (see "Support stdio and HTTP upstreams"), so a bearer token is stored
as `<token>` with the scheme `Bearer`. A row carries a value or a secret, never
both, and a header name appears once in an environment. Each tool MUST carry a
name unique in the group, a description, a method (GET, POST, PUT, PATCH or
DELETE), a path template relative to the base URL whose `{argument}` holes may
sit in the path or the query, optional headers, an optional JSON body template,
the JSON Schema of its arguments, an on/off switch and a changes-data flag. Like
every server, the group's name is fixed and prefixes each tool an agent sees as
`<group>__<tool>` ("Namespace every upstream capability"). A tool whose template
names an argument its schema does not declare, whose path is not a path
(`//host`, a URL with a scheme), or whose schema is not a well-formed JSON
Schema ("Validate a custom tool's arguments before any request") MUST be refused
when it is saved, with nothing persisted.

#### Scenario: a custom tool reaches the agent under its group's prefix
- **GIVEN** a group `billing` with a `list_invoices` tool, reaching every agent
- **WHEN** an agent lists the gateway's tools
- **THEN** it is offered `billing__list_invoices` with the tool's description and argument schema

#### Scenario: a group's headers are rows whose value is plain or a secret
- **GIVEN** a stored secret `billing-token`
- **WHEN** a group is created with the headers `X-Team` = `billing` and `Authorization` bound to `billing-token`, then its headers are replaced with `X-Team` = `ops`
- **THEN** the group first lists both rows, the secret one naming `billing-token` and its state and never its value, and a row giving both a value and a secret is refused
- **AND** after the replacement it lists one plain row and no secret

#### Scenario: a tool naming an undeclared argument is refused
- **GIVEN** a group `billing`
- **WHEN** a tool with path `/invoices/{id}` and an argument schema that declares no `id` is added
- **THEN** the addition is refused as a validation error naming `id`, and the group is unchanged

### Requirement: Make a custom tool's request in the gateway
On `tools/call` for a custom tool the gateway MUST resolve the call's
environment ("Choose a custom tool's environment on every call"), validate the
arguments ("Validate a custom tool's arguments before any request"), and render
the request from the arguments and that environment — the environment's base
URL; each path hole percent-encoded so a value cannot change the path, the query
or the host; each `{env:NAME}` filled with the environment's variable; a query
pair whose hole's argument is absent dropped; the body template filled with JSON
values, or, with no template, the unused arguments sent as a JSON object for
POST, PUT and PATCH — add the environment's secret headers with each secret's
value last, send it with the environment's timeout (the group's when it sets
none) without following redirects, read at most 1 MiB of the response, and
return one text result that starts with the HTTP status line. A status of 400 or
more MUST be returned as an in-band tool error; a redirect MUST be returned, not
followed; a timeout MUST be recorded as `timeout`. The secret's value MUST NOT
appear in the result, the tool's description or schema, or any log, invocation
or audit record: an occurrence in the response is masked as `***`. Every call
MUST be recorded like any other tool call ("Record invocations without
content"), naming its environment.

#### Scenario: a custom tool call sends the rendered request with the secret
- **GIVEN** a group with base URL `https://api.example/v2`, an `Authorization` header bound to an approved secret holding `<token>` with the scheme `Bearer`, and a tool `GET /invoices/{id}?status={status}`
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

### Requirement: Wait for approval before a custom tool sends its secret
Binding a stored secret to one of an environment's headers MUST be treated as a
new destination whose target is that environment's base URL and whose slot names
the environment and the header ([secret](../secret/spec.md) "Hold a secret for
a new destination until a person approves it"): no call and no Test in that
environment carries the secret until a person approves it for that base URL, a
call before then fails with `SECRET_BINDING_PENDING` naming the approvals and
the command that approves them, and changing the environment's base URL or the
header asks again for that environment only, and so does moving the same secret
to another header ("Fix a secret's placement by its destination's definition").
Each environment is evaluated on its own: a missing secret, a pending approval or
a refusal in one environment MUST NOT stop calls in another, and only the chosen
environment's secrets are resolved for a call. A switched-off environment asks
for no approval. A group's request MUST NOT follow a redirect, and no argument
hole in a tool's path, query, headers or body MAY be filled from a stored
secret. The group MUST report each secret header's state as `present`,
`missing` or `pending_approval`, per environment and, as a whole, the worst of
them (`none` with no secret header), with the ids of the approvals it waits on
and the names of the secrets concerned.

#### Scenario: binding a stored secret to a group waits for approval
- **GIVEN** a stored secret `billing-token`
- **WHEN** a group is created with its `Authorization` header bound to `billing-token`, and an agent calls one of its tools
- **THEN** the group reports `pending_approval` naming one approval for its base URL and the secret `billing-token`, and the call fails with `SECRET_BINDING_PENDING` having sent nothing
- **AND** once the approval is applied the next call carries the secret

#### Scenario: moving a group's base URL asks again
- **GIVEN** a group whose secret is approved for its base URL
- **WHEN** its base URL is changed
- **THEN** the group reports `pending_approval` for the new base URL and calls carry no secret until it is approved

#### Scenario: an approval in one environment does not open another
- **GIVEN** a group with environments `test` and `live`, each binding its own secret, with `test` approved and `live` pending
- **WHEN** a tool is called in `test` and in `live`, and then `test`'s base URL is changed
- **THEN** the `test` call carries its secret and the `live` call fails with `SECRET_BINDING_PENDING` naming only `live`'s approval
- **AND** after the change `test` waits for a new approval while `live`'s pending approval is unchanged

### Requirement: Manage custom tools through REST and the Custom tools page
Custom-tool groups MUST be managed through `/api/v1/custom-tools` — list
(failing groups first, each with its health, its secret's state, its calls and
failures in the last 24 hours, its environments and its tools), create (with
tools and environments), read, change, delete, add / change / remove one tool,
add / change / remove one environment, test a draft tool once without saving it,
test a saved tool, read an OpenAPI document, and preview and apply a re-import —
on the Custom tools page, which calls those routes, and with the `coffer
custom-tool` commands ("Manage custom tools from the command line"). Every test
names its environment and returns the actual target it reached (method and URL
with secret-looking query values redacted). The page MUST show each
environment's base URL, its secret state and whether it is on, and its test
panel MUST offer an environment picker. A change that waits for a secret
approval MUST report it as a pending approval on the Secrets page
([secret](../secret/spec.md) "Hold a secret for a new destination until a
person approves it"). A group's health MUST be `off` while disabled, `failing`
when its last call in 24 hours failed, `attention` while a secret of an enabled
environment is missing or waits for approval, `healthy` after a successful last
call, and `idle` with no call in 24 hours.

#### Scenario: create a custom-tool group and add a tool
- **GIVEN** the daemon is running and a stored secret `deploy-token` whose binding is approved
- **WHEN** the user creates a group `deploy` with `POST /api/v1/custom-tools` (base URL `https://deploy.example/v1`, an `Authorization` header with the scheme `Bearer` and the secret `deploy-token`), then adds a `rollback` tool with `POST /api/v1/custom-tools/deploy/tools` (method `POST`, path `/services/{service}/rollback`, a required string argument `service`)
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

#### Scenario: a saved tool is tested in a chosen environment and reports its target
- **GIVEN** a group with environments `test` and `live` and a saved tool `GET /status`
- **WHEN** `POST /api/v1/custom-tools/{name}/tools/status/test` is sent with `environment` = `live`
- **THEN** only `live`'s base URL receives the request, and the answer names `live` and the URL it reached

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
keep its switch and changes-data flag, and MUST keep every environment of the
group with its base URL, headers, secret bindings and variables unchanged. A
tool added by hand is never removed by a re-import.

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

#### Scenario: re-import keeps the group's environments
- **GIVEN** an imported group with environments `test` and `live`, each with its own base URL, secret header and variable
- **WHEN** it is re-imported from a document whose `servers` name another URL
- **THEN** both environments keep their base URL, headers, secret bindings and variables, and no approval is asked again
