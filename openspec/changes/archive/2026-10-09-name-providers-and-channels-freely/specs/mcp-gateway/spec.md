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
carries no title: its fixed name and its description — a note the user keeps for themselves — are all it has,
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
- **THEN** the list shows it as `fs` with that description, and reading it back carries no `title` field

Deleting a server MUST leave no upstream process or connection for it in any session, the process-wide one
included: a spawn already under way when the delete begins, one a listing or call starts while the delete
runs, and one in a session opened during the delete are each refused or closed rather than kept, and an
evicted start is neither retried nor counted as a failure of that name. Ending a session MUST close any spawn
of that session still under way.

#### Scenario: a listing during a delete does not revive the deleted server
- **GIVEN** a stdio server `fs` with a live child in a session, and a delete whose eviction of another session's child is still under way
- **WHEN** that session, or a session opened at that moment, lists or calls `fs` before the delete removes the registration
- **THEN** that spawn is refused or its child is closed, and once the delete returns no child of `fs` is running, checked by pid

#### Scenario: ending a session closes a spawn still in flight
- **GIVEN** a session whose spawn of `fs` has started its child but has not finished starting
- **WHEN** the session ends and the spawn then finishes
- **THEN** the child is closed, the call fails as unavailable, and the ended session starts nothing more
