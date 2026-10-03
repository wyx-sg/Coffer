## MODIFIED Requirements

### Requirement: Forward tools, resources and prompts
The system MUST forward MCP `tools`, `resources`, and `prompts` capabilities (list, call/read/get, and
list-changed notifications) between clients and upstream MCP servers.

- **Tools-only upstreams.** An upstream that implements only `tools` and replies with JSON-RPC `-32601`
  (METHOD_NOT_FOUND) for `resources/list` or `prompts/list` MUST be treated as having no resources / no
  prompts: the per-server capability view and the aggregate lists return that server's tools with an empty
  resources/prompts set (HTTP 200), not an error.
- **Built-in tools.** Coffer's own built-in tools under the reserved `coffer__` prefix MUST be exactly
  `coffer__search_tools`, which MUST always be advertised in
  `tools/list`. A call to any other `coffer__` name MUST be
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
- **WHEN** it lists tools, and calls `coffer__write`, `coffer__recall` and `coffer__diagnose`
- **THEN** the `coffer__` tools listed are exactly `coffer__search_tools`
- **AND** all three calls are answered as unknown tools

#### Scenario: a server's page reads its tiering split
- **GIVEN** a budget of three and two enabled servers whose saved tool lists hold five tools, one server's `t2` and `t3` called most, and a disabled server with tools of its own
- **WHEN** `GET /api/v1/resources/mcp_server/{uid}/tiering` is read for the server with four tools
- **THEN** it answers a catalogue of five with three listed, that server's `t2` and `t3` listed and `t1` and `t4` behind search, and a tool count of four
- **AND** nothing is spawned, and a tool the server no longer offers is not counted

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
- **THEN** it is refused as a validation error saying the name is reserved, with nothing persisted, so no upstream tool can be mistaken for a built-in or shadow `coffer__search_tools`

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
  into a Coffer built-in tool call (as an `agent` argument), it
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
