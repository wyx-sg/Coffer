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

### Requirement: Enable newly discovered capabilities
The system MUST enable a previously unseen capability by default when it is discovered, leaving it to
"Toggle individual capabilities" to curate. There is no per-server auto-enable policy.

#### Scenario: a newly discovered capability is enabled by default
- **GIVEN** a registered server whose capabilities have already been discovered,
- **WHEN** an upgrade adds a new tool to that server,
- **THEN** the new tool is enabled, its first sighting is recorded as the preference row's `first_seen_at`, and the user can disable it through the per-capability toggle ("Toggle individual capabilities").

### Requirement: Gate server exposure by scope per session
The system MUST filter `mcp_server` exposure by its framework-level `scope`
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)) — one allow-list,
`agents`, `null` meaning unrestricted — at the gateway's per-session choke point. The value, its validation
and the routes that write it are [resource-framework](../resource-framework/spec.md) "Carry a per-agent reach on every resource"; this requirement is the enforcement.

- The session's self-reported agent identity gates `tools/list` / `resources/list` / `prompts/list` and call
  routing. A server whose scope excludes the connecting session's identity MUST be hidden from that session's
  listings and any call against it MUST be rejected with the error a disabled capability gets
  (`TOOL_DISABLED`, JSON-RPC `-32000`) and recorded as a `denied` invocation — even while it IS visible to a differently
  identified session at the same time, and while it stays registered, listed in the management surface and
  editable.
- The identity of the asking session is the only input the gate takes. Scope names agents and nothing else,
  because a server's reach is machine-local and never arrives from elsewhere
  ([vault-sync](../vault-sync/spec.md), "Keep reach machine-local") — a server that should not run here is simply
  not enabled here.
- Scope MUST NOT gate spawning: the supervisor holds no policy and has no session identity to test, so the
  decision is enforced above it. Every spawn path runs downstream of the gate (the listing fan-out spawns only
  from the already-filtered set; a call is re-checked at the invocation seam before the supervisor is asked
  for a connection), so a scoped server starts like any other enabled server but no session can start one it
  may not see.
- The management routes (including `POST /{uid}/test`) are administrative operations rather than agent
  sessions and MUST NOT be scope-gated — so the owner can always test a server no session here is allowed to
  see.

#### Scenario: an out-of-scope server is invisible to a session
- **GIVEN** an `mcp_server` resource whose `scope` names one agent only,
- **WHEN** a shim session reporting a different agent identity (or no identity at all) lists tools,
- **THEN** the server's tools are absent from that session's `tools/list`, and a call attempt against its namespaced tool name is rejected with the tool-disabled error (`TOOL_DISABLED`, JSON-RPC `-32000`) a disabled capability gets and recorded as `denied` — while a session reporting the named agent sees and may call it.

### Requirement: Re-enable a server when its preference document is deleted
The `state/mcp-preferences/<server-uid>` sync state area is this spec's, so this spec defines what deleting one of
its documents means — [vault-sync](../vault-sync/spec.md) "Let each state area define its document's deletion" requires that of every area and interprets none of them itself. A
document exists only while something on that server is disabled; deleting it therefore means "nothing is
disabled here", and Coffer MUST re-enable every capability on that server. The preference rows MUST stay —
enabled is their default, and their seen-timestamps are this machine's own record of what the server offered,
not a decision another machine took back. A rel naming a server uid this machine does not register MUST be
ignored: the deletion cannot have been about anything here. For the same reason this spec MUST NOT publish a
document for a server with nothing disabled, or a machine that re-enabled everything and a machine that never
disabled anything would add and delete the same document at each other every round.

#### Scenario: deleting a server's preference document re-enables everything on it
- **GIVEN** two registered servers that each have a disabled capability,
- **WHEN** the preference document of one of them is deleted, along with one naming a server this machine does not register,
- **THEN** every capability on that server is enabled again and its preference rows remain,
- **AND** the other server's disabled capability is untouched, the unknown rel changes nothing, and the next export publishes no document for the server with nothing disabled.
