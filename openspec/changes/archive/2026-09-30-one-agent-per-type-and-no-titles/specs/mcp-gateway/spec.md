## MODIFIED Requirements

### Requirement: Manage MCP servers as resources
Users MUST be able to register, list, view, update, enable, disable and delete MCP servers as
resources addressed by the immutable `uid` the framework mints for them
([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md));
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
and `coffer mcp add` and `coffer mcp edit` offer no `--title`.
At registration the name MUST be at most 24 characters, in addition to the existing name pattern and the ban
on `__`; a server registered earlier with a longer name MUST keep it and keep working.

- Registering a server whose upstream is unreachable MUST still succeed (the config is saved); discovery and
  health report the failure, the server is marked unhealthy until reachable, and there MUST be no silent
  retry storm.
- Registering a server whose credential is missing MUST fail with a message naming the missing credential and
  pointing the user at the credential setup path, persisting no partial state.
- Registering a server with a name that already exists within the kind MUST be rejected with a clear error;
  a partial write is impossible.
- The `coffer mcp` group MUST offer the lifecycle verbs `list`, `show`, `add`, `edit`, `rm`, `enable`,
  `disable` and `scope`, plus `test` and `cap` (see "Toggle individual capabilities"). `coffer mcp test
  <server>` MUST re-query the server's capabilities and then report its health, so one command both
  refreshes what Coffer knows of the server and says whether it answers.
- The `coffer mcp` CLI MUST exit with code 3 and name the condition on stderr when no daemon is reachable
  and one cannot be started (a missing daemon is started on demand, and only a failed or timed-out start
  exits 3), and its `list` subcommand MUST support machine-readable `--json` output.
  The same exit covers a daemon that stops answering after the command has connected to it: the lost
  connection is reported once, as a message naming the condition, never as a traceback.

#### Scenario: register a stdio MCP server
- **GIVEN** the coffer daemon is running and no MCP servers are registered,
- **WHEN** the user registers a stdio MCP server with a unique name, command, and arguments,
- **THEN** the server is persisted, its capabilities are discovered, and listing servers shows it as healthy.

#### Scenario: CLI returns non-zero exit on daemon unreachable
- **GIVEN** the daemon is not running and cannot be started (the spawn fails or the daemon does not come up within the boot timeout),
- **WHEN** `coffer mcp list` is invoked,
- **THEN** the process exits with code 3 and stderr names the daemon-unreachable condition.

#### Scenario: CLI --json output is machine-readable
- **GIVEN** `coffer mcp list` and `coffer log mcp` each support `--json`,
- **WHEN** each is invoked with `--json`,
- **THEN** stdout is a parseable JSON document with stable top-level keys (`resources` for `coffer mcp list`, `invocations` for `coffer log mcp`) and no human-readable framing.

#### Scenario: a daemon lost mid-command exits 3
- **GIVEN** a `coffer mcp list` whose client was built against a daemon that has since stopped answering,
- **WHEN** the command makes its request,
- **THEN** the process exits with code 3, and stderr names the daemon-unreachable condition exactly once and carries no traceback.

#### Scenario: a server name longer than 24 characters is refused at registration
- **GIVEN** the coffer daemon is running, and a server registered before the cap with a 30-character name
- **WHEN** the user registers a new server whose name is 25 characters long, and then one whose name is 24 characters long
- **THEN** the first is refused as a validation error naming the 24-character limit, with nothing persisted, and the second is registered
- **AND** the earlier server keeps its 30-character name, and its tools are still listed and callable

#### Scenario: test re-queries capabilities before reporting health
- **GIVEN** a registered server whose upstream has gained a tool since Coffer last discovered it
- **WHEN** the user runs `coffer mcp test <server>`
- **THEN** the command reports the server's health, and `coffer mcp cap list <server>` then lists the new tool
- **AND** for a server whose upstream is unreachable, the command exits non-zero and names the failure

#### Scenario: an MCP server is shown by its name
- **GIVEN** the daemon is running
- **WHEN** the user registers a server with `coffer mcp add fs --stdio '<command>' --description "Local files"` and then lists servers
- **THEN** the list shows it as `fs` with that description, and `coffer mcp show fs --json` carries a `null` title
- **AND** a title submitted for it through the kind-agnostic update route is refused as a validation error
