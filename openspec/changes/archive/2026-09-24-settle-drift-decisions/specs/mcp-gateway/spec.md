## MODIFIED Requirements

### Requirement: Manage MCP servers as resources
Users MUST be able to register, list, view, update, enable, disable, rename and delete MCP servers as
resources addressed by the immutable `uid` the framework mints for them
([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md));
a server's `name` is a mutable label, and the per-server routes are `/api/v1/resources/mcp_server/{uid}/…`.
Validating that registration against the kind's schema, rejecting a duplicate name within the kind, and
persisting nothing on a validation failure are [resource-framework](../resource-framework/spec.md) "Validate every registration and persist nothing on failure", which every kind inherits; this
requirement is what brings `mcp_server` under it, and the kind-agnostic surface those operations are served
through is that spec's too.

- Registering a server whose upstream is unreachable MUST still succeed (the config is saved); discovery and
  health report the failure, the server is marked unhealthy until reachable, and there MUST be no silent
  retry storm.
- Registering a server whose credential is missing MUST fail with a message naming the missing credential and
  pointing the user at the credential setup path, persisting no partial state.
- Registering a server with a name that already exists within the kind MUST be rejected with a clear error;
  a partial write is impossible.
- The `coffer mcp` CLI MUST exit with code 3 and name the condition on stderr when no daemon is reachable
  and one cannot be started (a missing daemon is started on demand, and only a failed or timed-out start
  exits 3), and its `list` and `invocations` subcommands MUST support machine-readable `--json` output.
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
- **GIVEN** any of `coffer mcp list` or `coffer mcp invocations` supports `--json`,
- **WHEN** the subcommand is invoked with `--json`,
- **THEN** stdout is a parseable JSON document with stable top-level keys (`resources` for `list`, `invocations` for `invocations`) and no human-readable framing.

#### Scenario: a daemon lost mid-command exits 3
- **GIVEN** a `coffer mcp list` whose client was built against a daemon that has since stopped answering,
- **WHEN** the command makes its request,
- **THEN** the process exits with code 3, and stderr names the daemon-unreachable condition exactly once and carries no traceback.
