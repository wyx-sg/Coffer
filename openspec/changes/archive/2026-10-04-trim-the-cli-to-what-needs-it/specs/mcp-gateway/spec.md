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
  pointing the user at the secret setup path, persisting no partial state.
- Registering a server with a name that already exists within the kind MUST be rejected with a clear error;
  a partial write is impossible.
- Registering, listing, viewing, editing, enabling, disabling, scoping and deleting a server MUST be done
  on the MCP servers page and through the resource routes; the command line carries only `coffer mcp
  test <server>`, which MUST re-query the server's capabilities and then report its health, so one
  command both refreshes what Coffer knows of the server and says whether it answers.
- `coffer mcp test` MUST exit with code 3 and name the condition on stderr when no daemon is reachable
  and one cannot be started (a missing daemon is started on demand, and only a failed or timed-out start
  exits 3). `coffer log mcp` MUST support machine-readable `--json` output.
  The same exit covers a daemon that stops answering after the command has connected to it: the lost
  connection is reported once, as a message naming the condition, never as a traceback.

#### Scenario: register a stdio MCP server
- **GIVEN** the coffer daemon is running and no MCP servers are registered,
- **WHEN** the user registers a stdio MCP server with a unique name, command, and arguments,
- **THEN** the server is persisted, its capabilities are discovered, and listing servers shows it as healthy.

#### Scenario: CLI returns non-zero exit on daemon unreachable
- **GIVEN** the daemon is not running and cannot be started (the spawn fails or the daemon does not come up within the boot timeout),
- **WHEN** `coffer mcp test <server>` is invoked,
- **THEN** the process exits with code 3 and stderr names the daemon-unreachable condition.

#### Scenario: CLI --json output is machine-readable
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
changed. The command line carries no capability commands.

#### Scenario: disable an individual capability
- **GIVEN** a registered MCP server exposes several tools,
- **WHEN** the user disables one tool,
- **THEN** subsequent tool-list requests from any client omit it, and an attempt to call it returns a tool-disabled error.

#### Scenario: disabled capability rejected through the shim
- **GIVEN** a registered MCP server with two tools, where one has been disabled via the REST API,
- **WHEN** a shim client calls `tools/list` and then `tools/call` on the disabled tool,
- **THEN** `tools/list` omits the disabled tool while listing the enabled tool, and `tools/call` returns a JSON-RPC error with code -32000 (TOOL_DISABLED) rather than a successful result.

#### Scenario: the command line toggles capabilities by typed ref
- **GIVEN** a registered MCP server exposing a tool and a prompt
- **WHEN** the tool and the prompt are each disabled through `.../capabilities/tool/disable` and `.../capabilities/prompt/disable`, then the capabilities are read
- **THEN** both capabilities are disabled, with the disabled ones marked disabled
- **AND** an enable request naming a tool the server does not offer is refused and changes nothing

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
are never quoted. The attention item's reason MUST name no command.

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

#### Scenario: coffer mcp handoff prints the server's hand-off
- **GIVEN** a server whose status read carries a `handoff`, and one whose status carries none
- **WHEN** `GET /api/v1/resources/mcp_server/{uid}/status` is read for each
- **THEN** the first carries the prompt and the Copy prompt button of the server's page offers exactly that text, and the second carries a `null` `handoff` and the page offers none

### Requirement: Flag tools whose client-visible name is too long
The system MUST compute, for every discovered tool, the length of the name a client shows for
it, `mcp__coffer__<server>__<tool>`, and MUST flag each tool whose client-visible name is longer
than 64 characters, which is the limit model provider APIs place on a tool name. The flag MUST
appear on the server's Tools tab and in the capability list
(`GET /api/v1/resources/mcp_server/{uid}/capabilities`), each carrying the length and a
note that some clients drop tool names longer than 60 characters. The capability list
MUST carry the length on every tool row. Flagging MUST NOT disable, rename or hide the tool.

#### Scenario: a tool with an over-long client-visible name is flagged
- **GIVEN** a registered server whose upstream exposes one tool whose `mcp__coffer__<server>__<tool>` name is 70 characters long and one whose name is 40 characters long
- **WHEN** the user opens the server's Tools tab and reads the capability list over REST
- **THEN** the long tool is flagged on both surfaces with its length and a note that some clients drop names above 60 characters, and the short one is not flagged
- **AND** both tools stay enabled and are still listed to clients under their usual names

### Requirement: Manage custom tools on REST and the command line
Custom-tool groups MUST be managed through `/api/v1/custom-tools` — list
(failing groups first, each with its health, its secret's state, its calls and
failures in the last 24 hours and its tools), create (with tools), read,
change, delete, add / change / remove one tool, set or clear one tool's reach
override, test a draft tool once without saving it, read an OpenAPI document,
and preview and apply a re-import — and on the Custom tools page, which calls
those routes; the command line carries no `coffer tool` command. A change that
waits for a secret approval MUST report it as a pending approval on the Secrets
page ([secret](../secret/spec.md) "Hold a secret for a new destination until a
person approves it").
A group's health MUST be `off` while disabled, `failing` when its last call
in 24 hours failed, `attention` while its secret is missing or waits for
approval, `healthy` after a successful last call, and `idle` with no call in
24 hours.

#### Scenario: the command line creates a group and adds a tool
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
