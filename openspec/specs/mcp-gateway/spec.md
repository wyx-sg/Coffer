# MCP Gateway

## Purpose

The MCP gateway lets a developer register upstream MCP servers (filesystem, GitHub, Postgres, …) once in
Coffer and point every MCP client — Claude Code, Codex, any client that speaks stdio or HTTP MCP — at one
Coffer endpoint instead of editing each client's config. Coffer aggregates the upstreams' tools, resources and
prompts behind one namespaced surface, lets the user curate what that surface exposes (some tools are
dangerous, some redundant, some unwanted right now), keeps the agent able to choose well when the aggregated
catalogue grows past what a model can reason over, and records which capability was called, when, for how
long and with what outcome — never what was said. `mcp_server` was Coffer's first resource kind.

This spec owns the gateway, capability curation, the invocation record and the `coffer mcp` / shim surfaces
over them. The kind-agnostic lifecycle an `mcp_server` is managed through (immutable `uid`, rename, per-agent
reach, audit log, retention) is [resource-framework](../resource-framework/spec.md)'s, and this spec
contributes one `Kind` descriptor to it; the daemon that hosts the gateway — port, discovery file, token,
loopback posture — is [daemon](../daemon/spec.md)'s; the encrypted store behind an upstream's credential
refs, and what the user is told when its key is unavailable, are [credentials](../credentials/spec.md)'
(this spec persists refs and never holds a key).

Coffer runs as a single-user tool on the user's own machine with a small number of concurrent MCP clients
(low single digits); it is not a fleet-scale gateway. Upstreams are assumed to follow the public MCP
specification, and misbehaving ones are handled as faults. Coffer does not bundle its own snapshot of
`~/.coffer/`: the git convergence of [vault-sync](../vault-sync/spec.md) carries every system of record to a
remote the user owns, and a byte copy is `cp -r ~/.coffer/` with the daemon stopped.

## Requirements

### Requirement: Present Coffer as one MCP server
The system MUST present Coffer as a single MCP server to clients, over both an HTTP/SSE endpoint and a stdio
shim entry point.

Multiple MCP clients (for example Claude Code and Codex at the same time) MUST be able to connect
simultaneously without one disturbing the other, each getting an independent upstream subprocess set. If the
daemon crashes, running shim sessions MUST return a clean error to their MCP clients rather than hang on a
socket that will never answer. A tool call routed through Coffer SHOULD add no more than 50 ms of median
overhead compared with the same call made directly to the upstream, measured over 100 calls of a fast
in-process tool.

#### Scenario: aggregate tools across servers in one client
- **GIVEN** two MCP servers are registered and healthy,
- **WHEN** an MCP client connects through coffer's shim and lists tools,
- **THEN** every enabled tool from every registered server appears, named `<server>__<tool>`, and no two tools collide.

#### Scenario: concurrent clients
- **GIVEN** two MCP clients connect simultaneously,
- **WHEN** each lists and calls tools,
- **THEN** both succeed without interference, and each client receives a distinct upstream subprocess set (verified by counting entries in `~/.coffer/upstream-pids/`).

#### Scenario: gateway overhead stays under budget
- **GIVEN** an in-process fast tool reachable through coffer and directly,
- **WHEN** the same tool is called 100 times via coffer and 100 times directly,
- **THEN** the median per-call gateway overhead (coffer-mediated latency minus direct latency) is at most 50 ms.

### Requirement: Forward tools, resources and prompts
The system MUST forward MCP `tools`, `resources`, and `prompts` capabilities (list, call/read/get, and
list-changed notifications) between clients and upstream MCP servers.

- **Tools-only upstreams.** An upstream that implements only `tools` and replies with JSON-RPC `-32601`
  (METHOD_NOT_FOUND) for `resources/list` or `prompts/list` MUST be treated as having no resources / no
  prompts: the per-server capability view and the aggregate lists return that server's tools with an empty
  resources/prompts set (HTTP 200), not an error.
- **Built-in tool retrieval.** `coffer__search_tools` MUST always be advertised in `tools/list` alongside
  Coffer's other `coffer__` built-ins
  ([Tool Retrieval](../../../docs/decisions/tool-retrieval-for-overload.md)). Its contract is
  `coffer__search_tools(query: string [required], top_k?: int = 5, max 20) -> { tools: [{ name, description,
  inputSchema, score }], total_searched: N }`. It ranks the **live** aggregated upstream catalogue against the
  query and returns the top-k **real** upstream tool schemas, which the agent then calls directly; it is a
  retrieval primitive and MUST NOT select-and-invoke on the agent's behalf. Ranking MUST be a pure,
  deterministic, local keyword ranker (BM25-lite over each tool's name + description, with name tokens
  weighted higher) — no LLM, no embeddings, no network. Results MUST be upstream-only (Coffer's own
  `coffer__` built-ins excluded); each returned `name` is the same `<server>__<tool>` identifier the agent
  would call directly, with routing unchanged; and the invocation MUST be recorded in the invocation log like
  any other gateway call.
- **Budgeted listing ("tool tiering").** `tools/list` MUST advertise a budgeted slice of the catalogue rather
  than all of it ([Budget-Driven Tool Tiering](../../../docs/decisions/budget-driven-tool-tiering.md)).
  Coffer's own `coffer__*` tools are always listed and do not consume the budget. Upstream tools are listed in
  full while they fit the budget (default 50, `COFFER_TOOL_TIERING_BUDGET`); beyond it the gateway lists the
  most-invoked ones over a trailing window (default 90 days, `COFFER_TOOL_TIERING_WINDOW_DAYS`), reserving one
  slot per server so no server becomes wholly invisible. Unlisted is **not** disabled: `tools/call` MUST gate
  on the capability preference, never on list membership, so an unlisted tool routes exactly as before, and
  `coffer__search_tools` keeps ranking the **full** catalogue. Tiering MUST fail open —
  `COFFER_TOOL_TIERING=off`, or any failure of the usage query, lists everything. The split is not reported on
  a management page.
- **`initialize` instructions.** The `initialize` response MUST carry an MCP `instructions` string stating
  what Coffer is and that `coffer__search_tools` reaches whatever tiering left unlisted. It is capped (~800
  characters) and omits the tiering sentence when nothing is actually hidden.
- **Degraded upstream discovery.** When a server misses the per-server discovery budget its tools are left
  out of that listing, but the server MUST be **named**, retried in the background, and on recovery the
  gateway MUST emit `notifications/tools/list_changed` so the client re-lists.

#### Scenario: resources forward through the gateway
- **GIVEN** an upstream server exposes resources (not only tools),
- **WHEN** a client reads a resource by its coffer URI,
- **THEN** coffer routes the read to the originating upstream with the URI rewritten back to its upstream form and returns the upstream payload unchanged.

#### Scenario: prompts forward through the gateway
- **GIVEN** an upstream server exposes prompts (not only tools),
- **WHEN** a client invokes a prompt by its `<server>__<prompt>` namespaced name,
- **THEN** coffer routes the request to the originating upstream with the original (unprefixed) prompt name and returns the upstream payload unchanged.

#### Scenario: upstream tool list changes mid-session
- **GIVEN** a client is connected and an upstream MCP server's tool list changes (upgrade, plugin reload),
- **WHEN** the upstream emits a list-changed notification,
- **THEN** coffer forwards the notification to every client whose session subscribes to that upstream so the client re-lists, and coffer's cached capabilities are refreshed on next list.

#### Scenario: search the aggregated catalogue for matching tools
- **GIVEN** N upstream tools are aggregated and healthy through coffer,
- **WHEN** an agent calls `coffer__search_tools` with an intent query and a `top_k`,
- **THEN** it receives at most `top_k` ranked real upstream tool schemas (upstream-only, with Coffer's own `coffer__` built-ins excluded), each named `<server>__<tool>`, the response reports `total_searched`, and the gateway records the invocation.

### Requirement: Namespace every upstream capability
The system MUST namespace every upstream capability with its server's name (`<server>__<tool>` for tools and
prompts; a server-prefixed URI scheme for resources) so capabilities from different servers never collide.
A tool-name collision across servers is thereby never visible to clients.

#### Scenario: tool-name collision across servers is prevented
- **GIVEN** two registered MCP servers expose a tool with the same upstream name (e.g. both expose `search`),
- **WHEN** an MCP client lists tools through coffer,
- **THEN** the client sees `<server-a>__search` and `<server-b>__search` as distinct, non-colliding entries — neither upstream name is surfaced unprefixed.

### Requirement: Route calls to the originating upstream
The system MUST route a client call on a namespaced capability to the originating upstream with the
upstream's original (unprefixed) identifier.

If an upstream crashes mid-call, the in-flight call MUST return an error and the server MUST be marked
unhealthy; a subsequent call MUST respawn the upstream with bounded retries, and the failure MUST be visible
in the invocation log.

#### Scenario: route a tool call to the correct upstream
- **GIVEN** a client has discovered an aggregated tool list,
- **WHEN** the client calls a prefixed tool,
- **THEN** coffer forwards the call to the originating upstream with the original (unprefixed) name and returns the upstream's result unchanged.

#### Scenario: upstream crash recovery
- **GIVEN** an upstream MCP server crashes mid-session,
- **WHEN** a client calls a tool after the crash,
- **THEN** the gateway respawns the upstream and the call returns a successful result.

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
- The `coffer mcp` CLI MUST exit with code 3 and name the condition on stderr when the daemon is
  unreachable, and its `list` and `invocations` subcommands MUST support machine-readable `--json` output.

#### Scenario: register a stdio MCP server
- **GIVEN** the coffer daemon is running and no MCP servers are registered,
- **WHEN** the user registers a stdio MCP server with a unique name, command, and arguments,
- **THEN** the server is persisted, its capabilities are discovered, and listing servers shows it as healthy.

#### Scenario: CLI returns non-zero exit on daemon unreachable
- **GIVEN** the daemon is not running,
- **WHEN** `coffer mcp list` is invoked,
- **THEN** the process exits with code 3 and stderr names the daemon-unreachable condition.

#### Scenario: CLI --json output is machine-readable
- **GIVEN** any of `coffer mcp list` or `coffer mcp invocations` supports `--json`,
- **WHEN** the subcommand is invoked with `--json`,
- **THEN** stdout is a parseable JSON document with stable top-level keys (`resources` for `list`, `invocations` for `invocations`) and no human-readable framing.

### Requirement: Support stdio and HTTP upstreams
The system MUST support both stdio and HTTP MCP transports for upstream servers. An HTTP upstream MAY cite a
credential reference for its authorization header, and the credential MUST NOT leak into any log or stored
field.

#### Scenario: register an HTTP MCP server
- **GIVEN** the coffer daemon is running,
- **WHEN** the user registers an HTTP MCP server with a URL and (optionally) a credential reference for an authorization header,
- **THEN** the server is persisted and its capabilities are discovered without leaking the credential into any log or stored field.

#### Scenario: HTTP-transport MCP server round trip
- **GIVEN** an HTTP MCP server is running and registered with coffer,
- **WHEN** a shim client lists tools and calls one through coffer's aggregated endpoint,
- **THEN** both requests succeed end-to-end, returning valid MCP responses over the HTTP transport.

### Requirement: Toggle individual capabilities
Users MUST be able to enable or disable individual tools, resources, and prompts on a per-server basis.
Disabling a tool MUST make it disappear from any client's next tool-list response and MUST make any call
attempt on it fail with a tool-disabled error (JSON-RPC code -32000, TOOL_DISABLED).

#### Scenario: disable an individual capability
- **GIVEN** a registered MCP server exposes several tools,
- **WHEN** the user disables one tool,
- **THEN** subsequent tool-list requests from any client omit it, and an attempt to call it returns a tool-disabled error.

#### Scenario: disabled capability rejected through the shim
- **GIVEN** a registered MCP server with two tools, where one has been disabled via the REST API,
- **WHEN** a shim client calls `tools/list` and then `tools/call` on the disabled tool,
- **THEN** `tools/list` omits the disabled tool while listing the enabled tool, and `tools/call` returns a JSON-RPC error with code -32000 (TOOL_DISABLED) rather than a successful result.

### Requirement: Preserve capability decisions
The system MUST preserve the user's enable/disable decisions across daemon restarts, upstream upgrades, and
upstream temporary disappearances. A capability is discovered live from the upstream; only the user's
enable/disable preference and its last-seen timestamp are persisted.

#### Scenario: capability preferences survive upstream changes
- **GIVEN** the user has disabled a tool on a server,
- **WHEN** the upstream server is upgraded so that tool's schema changes (or it briefly disappears and returns),
- **THEN** the user's disabled state is preserved without manual re-configuration.

### Requirement: Enable newly discovered capabilities
The system MUST enable a previously unseen capability by default when it is discovered, leaving it to
"Toggle individual capabilities" to curate. There is no per-server auto-enable policy.

#### Scenario: a newly discovered capability is enabled by default
- **GIVEN** a registered server whose capabilities have already been discovered,
- **WHEN** an upgrade adds a new tool to that server,
- **THEN** the new tool is enabled, the event is recorded in the audit log, and the user can disable it through the per-capability toggle ("Toggle individual capabilities").

### Requirement: Record invocations without content
The system MUST record an invocation entry for every tool call, resource read, and prompt fetch — its target,
timestamp, duration and outcome — without recording arguments or return contents. How long those entries are
kept, and the background pass that prunes them, are [resource-framework](../resource-framework/spec.md) "Prune each registered log table on its own retention period" — the retention contract
every log-writing kind inherits — not this spec's own rule. This spec contributes `mcp_invocations` to that
registry with a 30-day default.

#### Scenario: invocation log records calls without arguments
- **GIVEN** an MCP client has invoked tools,
- **WHEN** the user views the invocation log,
- **THEN** every call is present with timestamp, target capability, duration, and outcome, and **no call arguments or return contents are stored**.

### Requirement: Name a missing stdio launcher
A stdio server whose launcher command does not resolve on this machine (an imported server referencing e.g.
`uvx` where `uv` is not installed) MUST be surfaced as such — `missing <runner>` in the server status —
instead of a bare "failing" with no cause, and the UI MUST name the command to install. Coffer MUST NOT
install it: running a package manager from a long-lived daemon would widen Coffer's remit from managing
configuration to installing software on the user's machine.

#### Scenario: a missing stdio launcher is named in the server status
- **GIVEN** a stdio server (e.g. imported from another machine) whose launcher command does not resolve on this machine,
- **WHEN** the server's status is read,
- **THEN** it reports `missing <runner>` instead of a bare failing state, and the UI tells the user which command to install rather than installing it ("Name a missing stdio launcher").

### Requirement: Gate server exposure by scope per session
The system MUST filter `mcp_server` exposure by its framework-level `scope`
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)) — one allow-list,
`agents`, `null` meaning unrestricted — at the gateway's per-session choke point. The value, its validation
and the routes that write it are [resource-framework](../resource-framework/spec.md) "Carry a per-agent reach on every resource"; this requirement is the enforcement.

- The session's self-reported agent identity gates `tools/list` / `resources/list` / `prompts/list` and call
  routing. A server whose scope excludes the connecting session's identity MUST be hidden from that session's
  listings and any call against it MUST be rejected — exactly as if the server did not exist for that
  session, indistinguishable from a disabled capability — even while it IS visible to a differently
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
- **THEN** the server's tools are absent from that session's `tools/list`, and a call attempt against its namespaced tool name is rejected exactly as if the server were never registered — while a session reporting the named agent sees and may call it.

### Requirement: Take the agent identity from the handshake
The system MUST accept a self-reported agent identity at MCP handshake as the agent's **uid**
(`params._meta["coffer/agent-uid"]`, alongside the existing `coffer/cwd` key), written into a managed agent's
shim invocation as `coffer-mcp-shim --agent-uid <uid>` by the Coffer-MCP install ([agent-registry](../agent-registry/spec.md) "Install Coffer's MCP server into an agent in one action") —
the uid rather than the name, because the entry is written once into a file Coffer does not revisit and a name
goes stale on the first rename. A session's reported identity is carried for the life of that connection and
used for every subsequent list and call.

- A `_meta` carrying only the older name-based key MUST be treated as reporting no identity rather than
  resolved by name.
- A session with no reported identity (a hand-configured shim invocation, or any client that omits
  `--agent-uid`) MUST be treated as `agent=None`, matching only servers that carry no scope — never a scoped
  one, even one naming the agent that happens to be running unidentified. An unidentified session sees
  strictly less, never more.
- Identity is self-reported, not cryptographically verified — a documented trust boundary, acceptable under
  the loopback-only, single-user posture [daemon](../daemon/spec.md) holds: any local process able to open the
  loopback MCP connection and set `_meta` could claim any agent uid.
- Identity is reported **once, at the handshake**, and nowhere else: when the gateway threads the identity
  into a Coffer built-in tool call (as the `agent` argument the knowledge and memory tools authorize by), it
  MUST overwrite any `agent` the client put in the call's arguments with the session's, and MUST drop the
  argument entirely when the session reported none — so a client cannot pick a different identity per call,
  and no built-in tool advertises `agent` in its input schema.

#### Scenario: a name-only handshake is treated as unidentified
- **GIVEN** one server scoped to a single agent's uid and one unscoped server,
- **WHEN** a session's handshake `_meta` carries only the older name-based `coffer/agent` key naming that agent,
- **THEN** the session reports no identity,
- **AND** its `tools/list` shows only the unscoped server's tools.

#### Scenario: a built-in tool call carries the session's identity, not the client's
- **GIVEN** a session whose handshake reported a registered agent's uid, and a second session that reported none,
- **WHEN** each calls a Coffer built-in tool with an `agent` argument naming a different agent,
- **THEN** the identified session's call reaches the tool with its own agent in `agent`, and the unidentified session's call reaches it with no `agent` argument at all,
- **AND** no built-in tool Coffer advertises in `tools/list` declares `agent` in its input schema.

### Requirement: Re-enable a server when its preference document is deleted
The `state/mcp-preferences/<server>` sync state area is this spec's, so this spec defines what deleting one of
its documents means — [vault-sync](../vault-sync/spec.md) "Let each state area define its document's deletion" requires that of every area and interprets none of them itself. A
document exists only while something on that server is disabled; deleting it therefore means "nothing is
disabled here", and Coffer MUST re-enable every capability on that server. The preference rows MUST stay —
enabled is their default, and their seen-timestamps are this machine's own record of what the server offered,
not a decision another machine took back. A rel naming a server this machine does not register MUST be
ignored: the deletion cannot have been about anything here. For the same reason this spec MUST NOT publish a
document for a server with nothing disabled, or a machine that re-enabled everything and a machine that never
disabled anything would add and delete the same document at each other every round.

#### Scenario: deleting a server's preference document re-enables everything on it
- **GIVEN** two registered servers that each have a disabled capability,
- **WHEN** the preference document of one of them is deleted, along with one naming a server this machine does not register,
- **THEN** every capability on that server is enabled again and its preference rows remain,
- **AND** the other server's disabled capability is untouched, the unknown rel changes nothing, and the next export publishes no document for the server with nothing disabled.
