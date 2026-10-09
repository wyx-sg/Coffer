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
  `tools/list`, plus — only for a session whose requests carry the `X-Coffer-Turn` token of a turn
  Coffer is running — the turn-scoped `coffer__ask` (see "Let an agent ask the owner a question during a Coffer turn")
  and `coffer__channel_read_thread` ([channels](../channels/spec.md) "Read a thread's earlier messages on demand").
  A call to any other `coffer__` name MUST be
  answered as an unknown tool, and so MUST a call to `coffer__channel_read_thread` outside a turn.
- **Built-in tool retrieval.** `coffer__search_tools`
  ([Tool Overload](../../../docs/decisions/tool-overload-tier-the-list-search-the-rest.md)) has the contract
  `coffer__search_tools(query: string [required], top_k?: int = 5, max 20) -> { tools: [{ name, description,
  inputSchema, score, group_description? }], total_searched: N }`. It ranks the **live** aggregated upstream catalogue against the
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
- **Output schemas.** A tool's `outputSchema`, when its upstream declares one, MUST reach the agent as
  declared, in the aggregated `tools/list` and in `coffer__search_tools` results alike; a tool that declares
  none carries no `outputSchema` key. A call result's `structuredContent` is returned as the upstream sent it.
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

#### Scenario: advertise coffer__search_tools as the one built-in tool
- **GIVEN** a client connected through coffer
- **WHEN** it lists tools, and calls `coffer__recall`, `coffer__diagnose` and the former write tool
- **THEN** the `coffer__` tools listed are exactly `coffer__search_tools`
- **AND** all three calls are answered as unknown tools

#### Scenario: a server's page reads its tiering split
- **GIVEN** a budget of three and two enabled servers whose saved tool lists hold five tools, one server's `t2` and `t3` called most, and a disabled server with tools of its own
- **WHEN** `GET /api/v1/resources/mcp_server/{uid}/tiering` is read for the server with four tools
- **THEN** it answers a catalogue of five with three listed, that server's `t2` and `t3` listed and `t1` and `t4` behind search, and a tool count of four
- **AND** nothing is spawned, and a tool the server no longer offers is not counted

#### Scenario: pass an upstream tool's output schema through
- **GIVEN** an upstream that declares an `outputSchema` on tool `typed` and none on tool `plain`
- **WHEN** the agent lists tools or searches with `coffer__search_tools`
- **THEN** `typed` carries exactly the declared `outputSchema` in both results, `plain` carries no `outputSchema` key, and a call to `typed` returns its `structuredContent` unchanged
