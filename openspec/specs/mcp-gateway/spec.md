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
over them. The kind-agnostic lifecycle an `mcp_server` is managed through (immutable `uid`, fixed name, per-agent
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
socket that will never answer. When the daemon restarts, a shim session MUST rebind to the new daemon and
MUST NOT run a `tools/call` twice: it resends a request after the restart only when the failure happened
before the request reached the daemon (the connection was refused or timed out), or when the method is not
`tools/call`, or when the old daemon rejected the request with 401. Any other `tools/call` failure MUST be
answered with a JSON-RPC error saying the daemon restarted mid-call and the call may or may not have run.
A tool call routed through Coffer SHOULD add no more than 50 ms of median
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

#### Scenario: a tool call is not re-run after the daemon restarts mid-call
- **GIVEN** a shim session whose daemon receives a `tools/call` and then dies before replying, and a new daemon that has come up on another port
- **WHEN** the shim's POST fails with a read error
- **THEN** the shim rebinds to the new daemon and answers that request id with a JSON-RPC error saying the call may or may not have run, without sending the call to the new daemon
- **AND** a `tools/call` whose connection was refused, a `tools/list` that failed the same way, and a request the old daemon rejected with 401 are each sent once to the new daemon and answered from it

### Requirement: Forward tools, resources and prompts
The system MUST forward MCP `tools`, `resources`, and `prompts` capabilities (list, call/read/get, and
list-changed notifications) between clients and upstream MCP servers.

- **Tools-only upstreams.** An upstream that implements only `tools` and replies with JSON-RPC `-32601`
  (METHOD_NOT_FOUND) for `resources/list` or `prompts/list` MUST be treated as having no resources / no
  prompts: the per-server capability view and the aggregate lists return that server's tools with an empty
  resources/prompts set (HTTP 200), not an error.
- **Built-in tools.** Coffer's own built-in tools under the reserved `coffer__` prefix MUST be exactly
  `coffer__search_tools` and `coffer__write`. `coffer__search_tools` MUST always be advertised in
  `tools/list`. `coffer__write` MUST be advertised only while the `knowledge` experimental feature is
  switched on ([experimental-features](../experimental-features/spec.md) "Withdraw what a switched-off feature put in front of agents"),
  and its contract is [knowledge](../knowledge/spec.md)'s. A call to any other `coffer__` name MUST be
  answered as an unknown tool.
- **Built-in tool retrieval.** `coffer__search_tools`
  ([Tool Overload](../../../docs/decisions/tool-overload-tier-the-list-search-the-rest.md)) has the contract
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
  than all of it ([Tool Overload](../../../docs/decisions/tool-overload-tier-the-list-search-the-rest.md)).
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

#### Scenario: the gateway advertises exactly two built-in tools
- **GIVEN** the `knowledge` experimental feature is switched on, and then switched off
- **WHEN** a client lists tools through coffer each time, and calls `coffer__recall` and `coffer__diagnose`
- **THEN** the `coffer__` tools listed the first time are exactly `coffer__search_tools` and `coffer__write`, and the second time exactly `coffer__search_tools`
- **AND** both calls are answered as unknown tools

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

On the command line the capabilities MUST be read with `coffer mcp cap list <server> [--type
tool|prompt|resource] [--json]` and toggled with `coffer mcp cap enable|disable <server> <ref>...`, where
each ref names its type: `tool:<name>`, `prompt:<name>` or `resource:<uri>`. A ref that names no capability
the server offers MUST be refused with nothing changed.

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
- **WHEN** the user runs `coffer mcp cap disable <server> tool:<tool> prompt:<prompt>`, then `coffer mcp cap list <server> --type tool`
- **THEN** both capabilities are disabled, and the list shows only tools, with the disabled one marked disabled
- **AND** `coffer mcp cap enable <server> tool:no-such-tool` exits non-zero and changes nothing

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
- **THEN** the new tool is enabled, its first sighting is recorded as the preference row's `first_seen_at`, and the user can disable it through the per-capability toggle ("Toggle individual capabilities").

### Requirement: Record invocations without content
The system MUST record an invocation entry for every tool call, resource read, and prompt fetch — its target,
timestamp, duration and outcome — without recording arguments or return contents. How long those entries are
kept, and the background pass that prunes them, are [resource-framework](../resource-framework/spec.md) "Prune each registered log table on its own retention period" — the retention contract
every log-writing kind inherits — not this spec's own rule. This spec contributes `mcp_invocations` to that
registry with a 30-day default. The record is read per server
(`GET /api/v1/resources/mcp_server/{uid}/invocations`, `coffer log mcp --server <server>`) or across every
server (`GET /api/v1/mcp/invocations`, `coffer log mcp` with no server), the cross-server read
including Coffer's own built-in calls (`coffer`) and deleted servers' rows (`deleted:<name>`). Both reads
page newest first by cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor"),
and both CLI forms take `--status`, `--since`, `--limit`, `--cursor` and `--json`.

#### Scenario: invocation log records calls without arguments
- **GIVEN** an MCP client has invoked tools,
- **WHEN** the user views the invocation log,
- **THEN** every call is present with timestamp, target capability, duration, and outcome, and **no call arguments or return contents are stored**.

#### Scenario: the command line reads the invocation log
- **GIVEN** a running daemon that has recorded invocations on two servers, on a Coffer built-in tool and on a deleted server
- **WHEN** the user runs `coffer log mcp --server <server>` and then `coffer log mcp --status error --json`
- **THEN** the first prints only that server's calls, newest first
- **AND** the second prints, under `invocations`, only failed calls across every server, each naming its server, including `coffer` and `deleted:<name>` rows

#### Scenario: the invocation log pages by cursor
- **GIVEN** a server with three recorded invocations
- **WHEN** its invocations are read with `limit=2` and then with the answer's `next_cursor`
- **THEN** the first page holds the two newest calls and the second the oldest, with a `null` `next_cursor`

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
  into a Coffer built-in tool call (as the `agent` argument the knowledge write tool attributes material by), it
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

### Requirement: Flag tools whose client-visible name is too long
The system MUST compute, for every discovered tool, the length of the name a client shows for
it, `mcp__coffer__<server>__<tool>`, and MUST flag each tool whose client-visible name is longer
than 64 characters, which is the limit model provider APIs place on a tool name. The flag MUST
appear on the server's Tools tab and in `coffer mcp cap list`, each carrying the length and a
note that some clients drop tool names longer than 60 characters. `coffer mcp cap list --json`
MUST carry the length on every tool row. Flagging MUST NOT disable, rename or hide the tool.

#### Scenario: a tool with an over-long client-visible name is flagged
- **GIVEN** a registered server whose upstream exposes one tool whose `mcp__coffer__<server>__<tool>` name is 70 characters long and one whose name is 40 characters long
- **WHEN** the user opens the server's Tools tab and runs `coffer mcp cap list <server> --json`
- **THEN** the long tool is flagged on both surfaces with its length and a note that some clients drop names above 60 characters, and the short one is not flagged
- **AND** both tools stay enabled and are still listed to clients under their usual names

### Requirement: Spawn a server with a secret only once its binding is approved
Before it spawns a stdio server or connects to an HTTP server with credential
refs, the gateway MUST ask the secret boundary whether each ref may go to that
server's target — the stdio command line with its working directory and
non-secret environment, or the HTTP URL — and MUST NOT start the server with
any secret a person has not approved for that target
([credentials](../credentials/spec.md) "Hold a secret for a new destination
until a person approves it"). The refused attempt surfaces as
`SECRET_BINDING_PENDING` with "waiting for approval in the Coffer app", and the
server is reachable as soon as the approval is applied, with no restart.

#### Scenario: a server whose secret is not approved is not spawned with it
- **GIVEN** a registered stdio server citing a secret that is approved for a different command line
- **WHEN** the gateway is asked to spawn it
- **THEN** nothing is spawned, the failure is `SECRET_BINDING_PENDING` naming the pending approval
- **AND** once the approval is applied the next spawn receives the secret in its environment

### Requirement: Mark a stdio server whose environment carries a secret
The resource representation of every MCP server MUST carry
`secrets_readable_by_local_processes`, true for a stdio server whose
environment carries at least one credential ref: the secret sits in the
server's initial environment, which any process of the same user can read, so
the UI labels such a server "readable by other processes on this Mac" and
nothing describes Coffer as protecting it. An HTTP server, whose headers the
gateway injects itself, and a stdio server with no secret, carry false.

#### Scenario: a stdio server with a secret is marked readable by local processes
- **GIVEN** a stdio server citing a credential ref, a stdio server citing none, and an HTTP server citing one
- **WHEN** the resources are read through the API
- **THEN** only the first carries `secrets_readable_by_local_processes: true`
