## MODIFIED Requirements

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
including Coffer's own built-in calls (`coffer`) and deleted servers' rows (`deleted:<name>`). Both HTTP reads
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
- **AND** the second prints, under `invocations`, only failed calls across every server, each naming its server, including `coffer` and `deleted:<name>` rows

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
  `COFFER_TOOL_TIERING=off`, or any failure of the usage query, lists everything. The split is reported per server on its page, through `GET /api/v1/resources/mcp_server/{uid}/tiering`: which of that server's tools are listed and which are reached through search, computed with the same policy over the tool lists discovery last saved for every enabled server on this machine, never by spawning one.
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

#### Scenario: a server's page reads its tiering split
- **GIVEN** a budget of three and two enabled servers whose saved tool lists hold five tools, one server's `t2` and `t3` called most, and a disabled server with tools of its own
- **WHEN** `GET /api/v1/resources/mcp_server/{uid}/tiering` is read for the server with four tools
- **THEN** it answers a catalogue of five with three listed, that server's `t2` and `t3` listed and `t1` and `t4` behind search, and a tool count of four
- **AND** nothing is spawned, and a tool the server no longer offers is not counted

## ADDED Requirements

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

