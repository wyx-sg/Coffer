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
loopback posture — is [daemon](../daemon/spec.md)'s; the encrypted store behind an upstream's secret
refs, and what the user is told when its key is unavailable, are [secret](../secret/spec.md)'
(this spec persists refs and never holds a key).

Coffer runs as a single-user tool on the user's own machine with a small number of concurrent MCP clients
(low single digits); it is not a fleet-scale gateway. Upstreams are assumed to follow the public MCP
specification, and misbehaving ones are handled as faults. Coffer does not bundle its own snapshot of
`~/.coffer/`: the git convergence of [vault-sync](../vault-sync/spec.md) carries the vault — configuration,
knowledge and secret ciphertext — to a remote the user owns (media under `content/`, the history in `runs.db`
and machine-local state do not travel), and a byte copy is `cp -r ~/.coffer/` with the daemon stopped.

While the `knowledge` feature is switched off, the built-in `coffer__write` tool is absent from the tool list (spec [experimental-features](../experimental-features/spec.md) "Close the knowledge feature's surfaces").

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
  `coffer__search_tools` and `coffer__write`. Both MUST always be advertised in
  `tools/list`; `coffer__write`'s contract is [knowledge](../knowledge/spec.md)'s. A call to any other `coffer__` name MUST be
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
  `COFFER_TOOL_TIERING=off`, or any failure of the usage query, lists everything. The split is reported per server on its page, through `GET /api/v1/resources/mcp_server/{uid}/tiering`: which of that server's tools are listed and which are reached through search, computed with the same policy over the tool lists discovery last saved for every enabled server on this machine, never by spawning one.
- **`initialize` instructions.** The `initialize` response MUST carry an MCP `instructions` string stating
  what Coffer is and that `coffer__search_tools` reaches whatever tiering left unlisted. It is capped (~800
  characters) and omits the tiering sentence when nothing is actually hidden. At `initialize` the count of
  hidden tools comes from the tool lists discovery last saved for the servers the session can see, because the
  handshake precedes the first `tools/list`; each `tools/list` then replaces that estimate with the real count.
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
- **GIVEN** a client connected through coffer
- **WHEN** it lists tools, and calls `coffer__recall` and `coffer__diagnose`
- **THEN** the `coffer__` tools listed are exactly `coffer__search_tools` and `coffer__write`
- **AND** both calls are answered as unknown tools

#### Scenario: a server's page reads its tiering split
- **GIVEN** a budget of three and two enabled servers whose saved tool lists hold five tools, one server's `t2` and `t3` called most, and a disabled server with tools of its own
- **WHEN** `GET /api/v1/resources/mcp_server/{uid}/tiering` is read for the server with four tools
- **THEN** it answers a catalogue of five with three listed, that server's `t2` and `t3` listed and `t1` and `t4` behind search, and a tool count of four
- **AND** nothing is spawned, and a tool the server no longer offers is not counted

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
and `coffer mcp add` and `coffer mcp edit` offer no `--title`.
The name MUST be at most 24 characters and MUST NOT be `coffer` (the name of Coffer's own gateway), in addition to
the existing name pattern and the ban on `__`, wherever the framework validates it — registration here and a server arriving from another machine alike.

- Registering a server whose upstream is unreachable MUST still succeed (the config is saved); discovery and
  health report the failure, the server is marked unhealthy until reachable, and there MUST be no silent
  retry storm.
- Registering a server whose secret is missing MUST fail with a message naming the missing secret and
  pointing the user at the secret setup path, persisting no partial state.
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
- **GIVEN** the coffer daemon is running
- **WHEN** the user registers a new server whose name is 25 characters long, and then one whose name is 24 characters long
- **THEN** the first is refused as a validation error naming the 24-character limit, with nothing persisted, and the second is registered

#### Scenario: a server cannot take the name of Coffer's own gateway
- **GIVEN** the coffer daemon is running
- **WHEN** the user registers a server named `coffer`
- **THEN** it is refused as a validation error saying the name is reserved, with nothing persisted, so no upstream tool can be mistaken for a built-in or shadow `coffer__write` or `coffer__search_tools`

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
secret reference for its authorization header, and the secret MUST NOT leak into any log or stored
field.

#### Scenario: register an HTTP MCP server
- **GIVEN** the coffer daemon is running,
- **WHEN** the user registers an HTTP MCP server with a URL and (optionally) a secret reference for an authorization header,
- **THEN** the server is persisted and its capabilities are discovered without leaking the secret into any log or stored field.

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
decisions and when each capability was seen are persisted. A capability switched off is listed in its
server's preference document in the vault, `state/mcp-preferences/<server name>.json`, which carries the
server's uid; when this machine first and last saw each capability is a derived record of this machine's,
in `~/.coffer/derived/derived.db`, because it is a fact about what this machine's upstream offered.

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
- **THEN** the new tool is enabled, its first sighting on this machine is recorded as its `first_seen_at`, and the user can disable it through the per-capability toggle ("Toggle individual capabilities").

### Requirement: Record invocations without content
The system MUST record an invocation entry for every tool call, resource read, and prompt fetch — its target,
timestamp, duration and outcome — without recording arguments or return contents. Each entry MUST also carry
its row `id`, and MUST name the agent whose session made the call (`agent_uid`) when that session reported one
on its handshake (see "Take the agent identity from the handshake"); a session that reported none writes
entries naming no agent, never a guessed one. How long those entries are
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
are never quoted. The attention item's reason MUST name no command. `coffer mcp handoff <name>` MUST print the
status read's prompt as served.

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
- **WHEN** `coffer mcp handoff <name>` is run for each
- **THEN** the first prints the prompt exactly as the route serves it, and the second says there is nothing to hand off and exits 5

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

- A session id the daemon does not know — its idle session was dropped, or the daemon restarted — MUST be
  answered `404` for every method but `initialize` (and for a notification stream), never silently rebuilt as
  a session that lost the handshake's identity and scope; the shim MUST then replay its cached `initialize` and
  resend the call. A session id that starts with `__` MUST NOT be taken as a client's session id. An open
  notification stream MUST keep its session from being reaped as idle.
- A `_meta` carrying only a name-based `coffer/agent` key MUST be treated as reporting no identity rather than
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

#### Scenario: a dropped session is answered 404 and the client handshakes again
- **GIVEN** a session whose handshake reported an agent's uid and that the idle reaper has since dropped,
- **WHEN** the client sends `tools/list` on its old session id,
- **THEN** the answer is `404` and no session is created; an `initialize` carrying the identity then opens a new one, and the shim does both and resends the call

#### Scenario: a name-only handshake is treated as unidentified
- **GIVEN** one server scoped to a single agent's uid and one unscoped server,
- **WHEN** a session's handshake `_meta` carries only a `coffer/agent` key naming that agent, and no `coffer/agent-uid`,
- **THEN** the session reports no identity,
- **AND** its `tools/list` shows only the unscoped server's tools.

#### Scenario: a built-in tool call carries the session's identity, not the client's
- **GIVEN** a session whose handshake reported a registered agent's uid, and a second session that reported none,
- **WHEN** each calls a Coffer built-in tool with an `agent` argument naming a different agent,
- **THEN** the identified session's call reaches the tool with its own agent in `agent`, and the unidentified session's call reaches it with no `agent` argument at all,
- **AND** no built-in tool Coffer advertises in `tools/list` declares `agent` in its input schema.

### Requirement: Re-enable a server when its preference document is deleted
A server's preference document, `state/mcp-preferences/<server name>.json` in the vault, is this spec's, so
this spec defines what deleting it means ([vault-sync](../vault-sync/spec.md) "Converge shared state areas").
The document carries the server's uid and exists only while something on that server is disabled; deleting
it — by hand, or by a sync round that brings another machine's re-enabling — therefore means "nothing is
disabled here", and Coffer MUST re-enable every capability on that server. When each capability was seen
MUST stay: it is this machine's own derived record of what the server offered, not a decision another machine
took back. For the same reason this spec MUST NOT write a document for a server with nothing disabled, or a machine that re-enabled everything and a machine that never
disabled anything would add and delete the same document at each other every round.

#### Scenario: deleting a server's preference document re-enables everything on it
- **GIVEN** two registered servers that each have a disabled capability,
- **WHEN** the preference document of one of them is deleted by a sync commit,
- **THEN** every capability on that server is enabled again, and each is still listed with when it was seen,
- **AND** the other server's disabled capability is untouched, and no preference document is written back for the server with nothing disabled.

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
Before it spawns a stdio server or connects to an HTTP server with secret
refs, the gateway MUST ask the secret boundary whether each ref may go to that
server's target — the stdio command line with its working directory and
non-secret environment, or the HTTP URL — and MUST NOT start the server with
any secret a person has not approved for that target
([secret](../secret/spec.md) "Hold a secret for a new destination
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
environment carries at least one secret ref: the secret sits in the
server's initial environment, which any process of the same user can read, so
the UI labels such a server "readable by other processes on this Mac" and
nothing describes Coffer as protecting it. An HTTP server, whose headers the
gateway injects itself, and a stdio server with no secret, carry false.

#### Scenario: a stdio server with a secret is marked readable by local processes
- **GIVEN** a stdio server citing a secret ref, a stdio server citing none, and an HTTP server citing one
- **WHEN** the resources are read through the API
- **THEN** only the first carries `secrets_readable_by_local_processes: true`

### Requirement: Serve an HTTP API as a group of custom tools
The gateway MUST support a third upstream transport, `http_api`, whose server
is a **custom-tool group**: an `mcp_server` whose tools are HTTP requests the
gateway makes itself, with no process to run and no MCP server at the other
end. A group MUST carry a base URL (`http` or `https`), optional **header
rows**, a per-request timeout between 1 and 300 seconds (30 by default) and its
tools. A header row is a name and a value: plain text, or a stored secret that
holds the WHOLE header value — nothing is put around it, so a bearer token is
stored as `Bearer <token>`. A row carries a value or a secret, never both, and a
header name appears once. Each tool MUST carry a name unique in
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

#### Scenario: a group's headers are rows whose value is plain or a whole secret
- **GIVEN** a stored secret `billing-token`
- **WHEN** a group is created with the headers `X-Team` = `billing` and `Authorization` bound to `billing-token`, then its headers are replaced with `X-Team` = `ops`
- **THEN** the group first lists both rows, the secret one naming `billing-token` and its state and never its value, and a row giving both a value and a secret is refused
- **AND** after the replacement it lists one plain row and no secret

#### Scenario: a tool naming an undeclared argument is refused
- **GIVEN** a group `billing`
- **WHEN** a tool with path `/invoices/{id}` and an argument schema that declares no `id` is added
- **THEN** the addition is refused as a validation error naming `id`, and the group is unchanged

### Requirement: Make a custom tool's request in the gateway
On `tools/call` for a custom tool the gateway MUST render the request from the
arguments — each path hole percent-encoded so a value cannot change the path,
the query or the host; a query pair whose hole's argument is absent dropped;
the body template filled with JSON values, or, with no template, the unused
arguments sent as a JSON object for POST, PUT and PATCH — add the group's
secret headers with each secret's value last, send it with the group's timeout without
following redirects, read at most 1 MiB of the response, and return one text
result that starts with the HTTP status line. A status of 400 or more MUST be
returned as an in-band tool error; a redirect MUST be returned, not followed;
a timeout MUST be recorded as `timeout`. The secret's value MUST NOT appear in
the result, the tool's description or schema, or any log, invocation or audit
record: an occurrence in the response is masked as `***`. Every call MUST be
recorded like any other tool call ("Record invocations without content").

#### Scenario: a custom tool call sends the rendered request with the secret
- **GIVEN** a group with base URL `https://api.example/v2`, an `Authorization` header bound to an approved secret holding `Bearer <token>`, and a tool `GET /invoices/{id}?status={status}`
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
and answered with TOOL_DISABLED. A reach override is either a list of agent uids that
narrows the group's reach for that one tool, or `all` — every agent the group
reaches, agents added later included — and no override at all follows the
group; an agent the group does not reach is not reached by any of its tools. Like every reach, an override is kept on
this machine only, in `~/.coffer/local/tool-reach.json`, and never travels with sync. Removing a tool or its group
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

#### Scenario: a tool's own reach can be every agent, apart from the group's
- **GIVEN** a group reaching Claude Code and a tool with no override
- **WHEN** the tool's reach is set to every agent, then to Claude Code only, then cleared
- **THEN** the tool reads `all`, then `chosen` with Claude Code, then follows the group
- **AND** `all` is stored as `all`, not as a list of today's agents

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
keep its switch, changes-data flag and reach override. A tool added by hand is
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
- **GIVEN** a group imported with three operations, one switched off and one with a reach override, and a document that now drops one of them and adds a new one
- **WHEN** re-import is previewed and then applied with the new operation chosen
- **THEN** the preview names one operation to add and one tool to remove and nothing changed before applying
- **AND** after applying, the dropped tool and its override are gone, the new tool is on, and the kept tools keep their switch and reach override

### Requirement: Wait for approval before a custom tool sends its secret
Binding a stored secret to one of a group's headers MUST be treated as a new
destination whose target is the group's base URL and whose slot is the header
name ([secret](../secret/spec.md) "Hold a secret for a new
destination until a person approves it"): no call and no Test carries the
secret until a person approves it for that base URL, a call before then fails
with `SECRET_BINDING_PENDING`, and changing the base URL or the header asks
again. The group MUST report each secret header's state as `present`, `missing`
or `pending_approval` and, as a whole, the worst of them (`none` with no secret
header), with the ids of the approvals it waits on and the names of the secrets
concerned.

#### Scenario: binding a stored secret to a group waits for approval
- **GIVEN** a stored secret `billing-token`
- **WHEN** a group is created with its `Authorization` header bound to `billing-token`, and an agent calls one of its tools
- **THEN** the group reports `pending_approval` naming one approval for its base URL and the secret `billing-token`, and the call fails with `SECRET_BINDING_PENDING` having sent nothing
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
approval MUST report it as every other command does ([secret](../secret/spec.md)
"Answer a pending approval on the command line by waiting or exiting").
A group's health MUST be `off` while disabled, `failing` when its last call
in 24 hours failed, `attention` while its secret is missing or waits for
approval, `healthy` after a successful last call, and `idle` with no call in
24 hours.
A failing group, and a test of a request that could not connect or timed out
(for a saved or an unsaved group), MUST carry a hand-off prompt that hands the
network problem to an agent — the group, the method and URL with credentials
and secret-looking query values redacted, the error and the machine; no header
value — and no other result does.

#### Scenario: the command line creates a group and adds a tool
- **GIVEN** the daemon is running and a stored secret `deploy-token` whose binding is approved
- **WHEN** the user runs `coffer tool add deploy --base-url https://deploy.example/v1 --secret-header Authorization=deploy-token`, then `coffer tool op add deploy rollback --method POST --path /services/{service}/rollback --arg service:string:required`
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
- **AND** only the failing group carries a hand-off prompt naming the group

### Requirement: Test an unsaved server config before adding it
The daemon MUST test an MCP server config that is not registered, so the Add dialog can show what a server offers before Add server: a stdio server is started for the length of the test and an HTTP one is connected to, MCP `initialize` and `tools/list` run (and the resource and prompt counts are read when the server declares them), the newest stderr lines are kept, and everything is then discarded. The test MUST persist nothing — no resource, no health record, no invocation record, no audit event. A URL typed into the form MUST pass the SSRF guard before any request, and a redirect MUST NOT lead the test to another origin. A config citing a stored secret MUST NOT be started, because a stored secret is released only to a registered destination whose binding a person approved; values typed into the form's secret rows apply to this test only and MUST NOT be stored, logged, audited or echoed — every typed secret value is redacted from the stderr tail and the error message. The whole test MUST end within a hard time limit (30 seconds, the config's own timeouts capped by it), and a stdio server's whole process group MUST be stopped when the test ends, whether it passed, failed, ran out of time or its caller went away. A failed test names its cause with a stable code: `url_refused`, `spawn_failed`, `exited` (with the exit code), `timeout`, `initialize_failed`, `connect_failed`, `auth_rejected` (an HTTP server answered 401 or 403) or `stored_secret_not_released`. A failure that depends on this machine — `spawn_failed`, `exited`, `timeout` or `connect_failed` — MUST also carry a hand-off prompt (the missing launcher to install, else the cause to find) built from the config's names with no secret value; `url_refused`, `auth_rejected`, `stored_secret_not_released` and `initialize_failed` carry none.

#### Scenario: a stdio config is tested without saving anything
- **GIVEN** the daemon is running and no MCP server is registered
- **WHEN** the Add dialog tests a stdio config whose server offers two tools, one resource and one prompt
- **THEN** the result is a pass naming both tools with a count of one resource and one prompt
- **AND** no resource, health record, invocation record or audit event exists afterwards

#### Scenario: a typed private URL is refused before any request
- **GIVEN** the daemon is running
- **WHEN** the Add dialog tests an HTTP config whose URL names a loopback address
- **THEN** the result is a failure with code `url_refused` saying that a server there is tested once it is added, and no request was made to that address

#### Scenario: a config citing a stored secret is not started
- **GIVEN** the daemon is running
- **WHEN** the Add dialog tests a stdio config whose environment cites a stored secret
- **THEN** the result is a failure with code `stored_secret_not_released` naming the key, and no process was started

#### Scenario: a failed test shows the exit code and the redacted stderr tail
- **GIVEN** a stdio config whose command prints the secret typed into the form on stderr and exits with status 3
- **WHEN** the Add dialog tests it with that secret typed in
- **THEN** the result is a failure with code `exited` and exit code 3, and its stderr tail shows the line with the secret redacted

#### Scenario: a failed unsaved test that depends on this machine carries a hand-off
- **GIVEN** a stdio config whose command is not found, or whose process exits, and whose environment holds a plain value
- **WHEN** the Add dialog tests it
- **THEN** the result carries a hand-off prompt naming the command, the error and the variable's name, and no secret or plain value
- **AND** a failure the person must fix themselves, such as a cited stored secret, carries no hand-off

#### Scenario: a test past its time limit stops the server's whole process group
- **GIVEN** a stdio server that forks a child and never completes `initialize`
- **WHEN** the test runs past its time limit
- **THEN** the result is a failure with code `timeout`, and neither the server nor the child it forked is still running

### Requirement: Report what a test of a registered server found
A test of a registered MCP server MUST report what the unsaved-config test reports — the tools found with their count, the resource and prompt counts, the redacted stderr tail, the failure code and the exit code — run by the same probe, with the server's stored secrets released per its approved binding and its whole process group stopped when the test ends. It MUST still record the outcome as the server's health.

#### Scenario: a registered server's test lists its tools and records its health
- **GIVEN** a registered stdio server offering two tools
- **WHEN** the user tests it
- **THEN** the result is a pass naming both tools, and the server's status reads healthy

### Requirement: Describe the built-in coffer server
The daemon MUST describe Coffer's own `coffer` MCP server read-only, so the MCP servers page can show it beside the servers the person added: its name, its transport (Streamable HTTP), the endpoint URL agents connect to on the bound port, that it is healthy while the daemon answers, that it reaches every connected agent (with the uids of the agents connected now), its tools from the gateway's built-in tool list as agents see them (only the tools of switched-on features, each with its `coffer__` name), and the last 24 hours of its calls in the shape a registered server's page reads. It is not a registered resource: it has no row, and nothing about it can be edited or removed.

#### Scenario: the built-in coffer server is described read-only
- **GIVEN** the daemon is running with one agent connected and a built-in tool called once
- **WHEN** the MCP servers page reads the built-in server
- **THEN** it is named `coffer` with the endpoint `http://127.0.0.1:<port>/mcp`, reaches that agent, lists `search_tools` as `coffer__search_tools`, and counts the one call
- **AND** no `mcp_server` resource named `coffer` exists

### Requirement: Read a server's capability list from its saved switches
The capability list of one MCP server MUST also be readable from its saved switches alone, without reaching the server, so the page of a server that is failing, off or missing its launcher or secret shows its tools at once instead of waiting out the discovery timeout. That read MUST say it came from the saved switches (`from_cache`), and a server that never listed anything MUST read as empty lists rather than an error.

#### Scenario: the saved-switches read answers without reaching the server
- **GIVEN** a registered MCP server whose tools were listed once, and a discovery that would fail if asked
- **WHEN** the page reads its capability list from the saved switches
- **THEN** the answer lists those tools from the saved switches without asking the server, and a server never listed reads as empty lists

### Requirement: Test a custom tool request before its group is saved
The daemon MUST run a request of a custom-tool group that is not saved yet — its base URL, headers and timeout given inline with the draft tool and sample arguments — once, and return what came back in the same shape as a saved group's test, saving nothing and logging no invocation. No stored secret is sent: an unsaved group has no approved binding, so the request goes without its secret headers. Its base URL was typed into a form, so it MUST pass the SSRF guard before anything is sent (Principles → Network defaults); a refused address is reported as not tested. Every test result — saved group or not — MUST say how a request failed when no answer came back: the request could not be built, it timed out, it could not connect, or its address was refused.

#### Scenario: a request of an unsaved group is tested without its secret
- **GIVEN** no group exists and an HTTP API answering on a public address
- **WHEN** a draft request with a base URL, a header and sample arguments is tested
- **THEN** the API receives the request with that header and no secret header, the answer's status and body come back, and still no group exists

#### Scenario: an unsaved group on a private address is not tested
- **GIVEN** a draft request whose base URL resolves to a loopback address
- **WHEN** it is tested before the group is saved
- **THEN** nothing is sent and the result says the address was refused

#### Scenario: a failed test says how it failed
- **GIVEN** a draft request whose base URL has nothing listening, and one whose path names an argument it does not declare
- **WHEN** each is tested
- **THEN** the first reports it could not connect and the second that the request could not be built, while a request the API answers reports no failure
- **AND** only the one that could not connect carries a hand-off prompt

### Requirement: List what a re-import changes in the tools it keeps
A re-import's preview MUST name, besides the operations it would add and the tools it would remove, every kept tool whose operation the spec now describes differently — an argument it now requires, or a changed method, path or body template — with the operation's text as last imported and as it now reads (the old text is absent for a tool imported before Coffer kept it), and an OpenAPI reading MUST carry each operation's first tag, so the import form can group operations by it.

#### Scenario: a re-import preview names the tools the spec changed
- **GIVEN** a group imported from a spec whose `POST /invoices` took no arguments
- **WHEN** the spec now requires a `currency` query argument there and the group is previewed for re-import
- **THEN** the preview names `create_invoice` as changed with the new required argument `currency`, and the group's tools are unchanged

#### Scenario: a re-import preview shows an operation's old and new text
- **GIVEN** a group imported from a multi-line spec, and a spec whose `POST /invoices` request body now requires `currency`
- **WHEN** the group is previewed for re-import
- **THEN** the changed tool carries its operation key, the operation's old text, its new text and the new text's first and last line

### Requirement: Hand a failing MCP server's diagnosis to an agent
Finding why a server will not start or answer depends on the machine, so a failing server MUST offer its
diagnosis as a hand-off prompt for the person's agent (Principle IV, AI-Native). The status read of a
server that reads `failing` (and is not missing its launcher or a secret), a failed test of a registered
server whose launcher resolves, and the `mcp_failing` attention item MUST carry `handoff`: one prompt naming
the server, its transport and a config summary — the command line and working directory, or the URL — with
the NAMES of its environment variables, headers and stored secrets and never their values, a URL's
`user:pass@` and secret-named query values and any secret-looking argument reading `<secret>`; the error of
the test or of the last failed call; at most the newest 20 lines the server printed on stderr (the test's
own capture, else the server's log file, whose path it names), each passed through the same secret scrub;
and this machine. Its steps MUST ask to find the cause (a missing environment variable, a wrong path, a
package that won't start) and propose the fix before changing anything, MUST forbid reading or changing the
secrets Coffer stores, and MUST name `coffer mcp test <name>` to verify. A resolved secret is never read for
it. A test that failed because a stored secret was not released carries no `handoff`: that fix is the
person's own. `coffer mcp test <name> --prompt` MUST print a failed test's prompt as served.

#### Scenario: the diagnosis prompt never carries a secret value
- **GIVEN** a failing stdio server whose arguments hold a token, whose environment sets a value, whose stored secret is cited by a key, and whose stderr printed a bearer token
- **WHEN** its diagnosis prompt is built
- **THEN** it names the environment variable and the secret's key, quotes the command line and the stderr lines with every one of those values replaced by `<secret>`
- **AND** none of the values appears anywhere in the prompt

#### Scenario: a failed test hands over its error and its stderr
- **GIVEN** a registered stdio server whose launcher resolves but whose test fails with an error after printing 25 stderr lines
- **WHEN** it is tested
- **THEN** the result carries a `handoff` naming the server, its transport, the error and the newest 20 stderr lines, and naming `coffer mcp test <name>`

#### Scenario: a failing server's status and attention item carry the diagnosis
- **GIVEN** an enabled server whose last test failed
- **WHEN** its status and the attention list are read
- **THEN** the status's `handoff` and the `mcp_failing` item's `handoff` both ask to find the cause without changing stored secrets, and the item's reason names no command

#### Scenario: coffer mcp test prints the diagnosis with --prompt
- **GIVEN** a server whose test fails with a `handoff`
- **WHEN** `coffer mcp test <name>` is run, and run again with `--prompt`
- **THEN** both exit 7; the first points at `--prompt`, and the second prints the prompt exactly as the route serves it

### Requirement: Explain a server's state on its page
A server's status read (`GET /api/v1/resources/mcp_server/{uid}/status`) MUST say, beside the state word,
what the page needs to explain it, from persisted state only and without spawning the server: the last
transport failure (its message and time) and since when the server has been failing — the newest run of
calls that failed to reach it, where a `denied` call is skipped and a call the upstream answered, or one
that succeeded, ends the run — or, with no such calls, the time of the failing test; the time and target
of the last successful call; when the health record was last written; and the first secret the server's
transport cites that has no value on this machine, by the environment or header key that cites it and by
the secret's own reference (a vault restored on a new machine carries references, not values). A secret's
value is never read for this; a server that cites none never asks the secret store.

#### Scenario: a failing server says its last error and since when
- **GIVEN** a server whose last calls are a success, a transport error, a denied call and a timeout, newest last
- **WHEN** its status is read
- **THEN** it reads failing with the timeout as the last error, failing since the transport error, and the earlier success as the last successful call with its tool

#### Scenario: a secret missing on this machine is named
- **GIVEN** an HTTP server whose `Authorization` header cites a secret with no value in this machine's store
- **WHEN** its status is read
- **THEN** it names `Authorization` as the key and the secret's reference, and once the value is stored it names none

### Requirement: Show what an MCP server requires
A server's status read MUST also list what its command and settings need from this machine, worked out from the config alone and without starting the server: for a stdio server its **launcher** (the command's executable — `npx`, `uvx`, `docker`, `bunx`, `node`, `python` and the like) as a CLI that is `found`, with its version when it prints one, or `not_found`; and every **secret** its environment or headers cite — through a stored secret bound to the variable or header, or a `coffer://secret/<name>` written in a plain value — as `set`, `missing` on this machine or `waiting_approval`, naming the variable or header and the secret. A launcher's version is read once and kept until the daemon restarts; one that is not found is looked up again on every read. An HTTP server has no launcher, and no secret's value is read.

#### Scenario: a server's page lists what it requires
- **GIVEN** a stdio server started with `npx` whose environment binds one stored secret that is set, one that is missing, and one that waits for approval
- **WHEN** its status is read
- **THEN** it lists the `npx` launcher as found with its version, then each secret as `set`, `missing` and `waiting_approval` by its variable name
- **AND** a launcher that is not on this machine reads `not_found`, and an HTTP server lists its header secrets and no launcher

### Requirement: Record why a registered server's test failed
A test of a registered server that fails MUST store, with the failing health record, why it failed as one
of four reasons: `auth_rejected` (an HTTP server answered 401 or 403, so its key is refused),
`unreachable` (the connection was refused or timed out), `command_not_found` (a stdio launcher or working
directory does not exist) or `other`. A passing test MUST store none. The status read MUST carry the
stored reason as `failure_reason` while the server reads `failing`.

#### Scenario: a rejected key is recorded as auth_rejected
- **GIVEN** a registered HTTP server whose upstream answers 401
- **WHEN** it is tested and its status is read
- **THEN** the test's error code is `auth_rejected`, and the status reads failing with `failure_reason` `auth_rejected`

#### Scenario: a failed test's error code maps to a reason
- **GIVEN** the error codes a test can fail with
- **WHEN** each is classified
- **THEN** `auth_rejected` stays `auth_rejected`, `connect_failed` and `timeout` read `unreachable`, `spawn_failed` reads `command_not_found`, and every other code reads `other`

### Requirement: Notice a rejected key from real calls
When a call an agent makes through the gateway is rejected by the upstream HTTP server's authentication
(the endpoint answers 401 or 403 at the transport, whether while the connection is opened or on the
request itself), the gateway MUST record the server as `failing` with reason `auth_rejected`, so the
Overview shows the key-rejected item without anyone pressing Test, and MUST announce the change to the
attention list. A later call that the upstream answers MUST record the server `healthy` again when the
stored state was `auth_rejected`; a call to a server with no such record MUST NOT write health. A tool
result carrying `isError` is a tool-level error over a healthy connection: it MUST NOT mark a server
failing, and it counts as an answered call. Other runtime failures (unreachable, a missing launcher) MUST
NOT be recorded by the gateway; they stay as the last test left them.

#### Scenario: a rejected key from a real call reaches the Overview
- **GIVEN** a registered HTTP server whose upstream answers 401 to a tool call
- **WHEN** an agent calls one of its tools through the gateway
- **THEN** the server's health reads failing with `failure_reason` `auth_rejected`, and the attention list carries `mcp_key_rejected` for it

#### Scenario: an answered call clears a recorded rejection
- **GIVEN** a server recorded as failing with `auth_rejected`
- **WHEN** a later forwarded call is answered by the upstream
- **THEN** the server's health reads healthy

#### Scenario: a tool error result does not mark a server failing
- **GIVEN** a healthy server whose tool returns a result with `isError`
- **WHEN** an agent calls it
- **THEN** no health is written and the server is not recorded as failing

#### Scenario: answered calls to a healthy server write nothing
- **GIVEN** a server with no recorded rejection
- **WHEN** forwarded calls to it are answered
- **THEN** its health is read at most once and never written

### Requirement: Read a server's own log from its page
The daemon MUST serve the newest lines of a stdio server's own log file — what it printed on stderr and the
lines Coffer writes there when it starts the server, when a start fails (a launcher not found on `PATH`,
a start that timed out) and when it stops it — through `GET /api/v1/resources/mcp_server/{uid}/log`,
newest first, each line saying whether Coffer or the server wrote it and, for Coffer's lines, when. Only
the tail is read, from the current file and then the one rolled aside. A server Coffer does not start
(Streamable HTTP) has no log and answers none. Coffer's lines name the command and never a secret, which
reaches the server only through its environment.

#### Scenario: a server's log tells Coffer's lines from the server's
- **GIVEN** a stdio server whose log file holds a start line, a line the server printed and a launcher-not-found line, and an older rolled-aside file
- **WHEN** its log is read, and read again with a limit of two
- **THEN** the lines come newest first across both files, Coffer's marked `coffer` with their time and the server's marked `stderr`
- **AND** the limited read holds two lines and says more exist

### Requirement: Hand a failing MCP call's diagnosis to an agent
A call whose server never answered — it failed without the upstream returning a
result or a JSON-RPC error, or it timed out — MUST carry `handoff` on its
invocation record: one prompt naming the server, the tool, the error (passed
through the same secret scrub as a server's diagnosis), how many calls to that
server failed in the last 24 hours, the session and the call's id, and this
machine. Its steps MUST ask to find the cause and propose the fix before changing
anything, MUST forbid reading or changing the secrets Coffer stores, and MUST name
`coffer mcp test <name>`. It MUST NOT contain the call's arguments or result,
which Coffer never stores. A call that succeeded, a denied call and a call the
upstream answered with its own error carry no `handoff`.

#### Scenario: an unanswered call carries a hand-off without arguments
- **GIVEN** an errored call, a timed-out call, a successful call, a denied call and a call the upstream answered with an error result
- **WHEN** the invocations are read
- **THEN** the errored and timed-out calls carry a prompt naming the server, tool, error, session, call id and the count of the server's failures in the last 24 hours
- **AND** the other three carry none

### Requirement: Read every failed call at once
`GET /api/v1/mcp/invocations` MUST accept `status=failed` besides the four
outcomes, selecting every call that is not `ok` — an error, a timeout or a
denial — for the page and for its count.

#### Scenario: status failed is every outcome but ok
- **GIVEN** an ok, an errored, a timed-out and a denied call
- **WHEN** the invocations are read with `status=failed`
- **THEN** the errored, timed-out and denied calls are listed, and the total is three
