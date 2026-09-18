# Feature Specification: MCP Gateway

**Status**: Accepted
**Scope note**: This spec owns the MCP gateway — aggregating upstream MCP servers behind one namespaced surface, curating what that surface exposes, and the `coffer mcp` / shim surfaces over it. The kind-agnostic resource lifecycle an `mcp_server` is otherwise managed through, and the audit and retention records it writes into, are spec resource-framework's; the daemon that hosts it is spec daemon's; the secrets an upstream is configured with are spec credentials'.
**Input**: User description: "Coffer's first feature — an MCP server gateway. Like mcpjungle / metamcp: one MCP client (Claude Code / Codex) connects to coffer; coffer aggregates many upstream MCP servers and re-exposes their tools, resources, and prompts as a single namespaced surface. Coffer will later manage other resource kinds (skills, memory, channels, agents) — design the first feature on top of a generic Resource framework so follow-on kinds plug in cleanly."

## User Scenarios & Testing

### User Story 1 — Aggregate multiple MCP servers in one client (Priority: P1)

A developer uses an MCP client (e.g. Claude Code or Codex) and wants to wire several MCP servers (filesystem, GitHub, Postgres, …) into it. Instead of editing each client's MCP config and re-restarting clients when the list changes, they register the upstream servers **once** in coffer and point each client at coffer's single shim. All upstream tools, resources, and prompts appear in every client, namespaced so they don't collide.

**Why this priority**: This is the core of the spec. Everything else is leverage on top. Without this, coffer is not an MCP gateway.

**Independent Test**: Install coffer (no other surface yet), register two real upstream MCP servers via the command line, configure one MCP client to use coffer's shim, restart the client, observe both servers' tools listed under `<server>__<tool>` names, call a tool, see its result.

**Covering scenarios** (full Given/When/Then under `## Acceptance Scenarios` below):

- register a stdio MCP server
- register an HTTP MCP server
- aggregate tools across servers in one client
- route a tool call to the correct upstream
- resources forward through the gateway
- prompts forward through the gateway
- upstream tool list changes mid-session

---

### User Story 2 — Curate which capabilities are exposed (Priority: P1)

The developer doesn't want every upstream tool exposed to AI. Some are dangerous (force-push, drop-table), some are redundant across two servers, some they simply don't want available right now. They need per-tool, per-resource, per-prompt on/off switches that survive daemon restarts and upstream upgrades.

**Why this priority**: Without curation, aggregation creates a worse experience than no gateway. Curation is what makes "I installed 30 servers" usable.

**Independent Test**: Register a server with multiple tools, disable one tool, restart the MCP client, observe the disabled tool is absent; re-enable it, observe it returns.

**Covering scenarios**:

- disable an individual capability
- capability preferences survive upstream changes
- a newly discovered capability is enabled by default

---

### User Story 3 — Find the right tool under aggregation overload (Priority: P2)

Once a developer has registered many upstream servers, the aggregated surface can exceed 150 tools. A coding agent's tool-selection accuracy degrades sharply past ~30–50 tools, so dumping the whole catalogue into every request both wastes context tokens and makes the agent pick wrong. The developer wants the agent to _search_ the live aggregated catalogue for the few tools that match its current intent and call them directly, instead of reasoning over the entire list.

**Why this priority**: Aggregation is only useful if the agent can still choose well at scale; this turns "I installed 30 servers" from a liability back into leverage. It builds on the core gateway (User Story 1) without changing how any upstream tool is exposed or called.

**Independent Test**: Register enough servers that the aggregated catalogue is large, then from an MCP client call `coffer__search_tools` with an intent query and a `top_k`; observe at most `top_k` ranked upstream tool schemas come back, the agent calls one of them by its `<server>__<tool>` name, and the call routes to the originating upstream as usual.

**Covering scenarios**:

- search the aggregated catalogue for matching tools

The behaviour and rationale are recorded in [Tool Retrieval](../../docs/decisions/tool-retrieval-for-overload.md).

#### `coffer__search_tools` — built-in tool-retrieval

`coffer__search_tools` is a Coffer-built-in tool, always advertised in `tools/list` alongside Coffer's other `coffer__` built-ins. It mitigates aggregation tool-overload by ranking the **live** aggregated upstream catalogue against an intent query and returning the top-k **real** upstream tool schemas, which the agent then calls directly. It is a retrieval primitive — it returns schemas, it does **not** select-and-invoke on the agent's behalf.

Contract:

```
coffer__search_tools(query: string [required], top_k?: int = 5, max 20)
  -> { tools: [{ name, description, inputSchema, score }], total_searched: N }
```

- Ranking is a pure, deterministic, local keyword ranker (BM25-lite over each tool's name + description, with name tokens weighted higher). No LLM, no embeddings, no network.
- Results are **upstream-only**: Coffer's own `coffer__` built-in tools are excluded, since they are not the overload source.
- Each returned `name` is the same `<server>__<tool>` namespaced identifier the agent would call directly; routing is unchanged.
- The invocation is recorded in the invocation log like any other gateway call.

#### Budgeted listing ("tool tiering")

`tools/list` advertises a budgeted slice of the catalogue rather than all of it
(see [Budget-Driven Tool Tiering](../../docs/decisions/budget-driven-tool-tiering.md)).
Coffer's own `coffer__*` tools — `search_tools` among them — are always listed
and do not consume the budget. Upstream tools are listed in full while they fit
the budget (default 50, `COFFER_TOOL_TIERING_BUDGET`); beyond it the gateway
lists the most-invoked ones over a trailing window (default 90 days,
`COFFER_TOOL_TIERING_WINDOW_DAYS`), reserving one slot per server so no server
becomes wholly invisible.

Unlisted is **not** disabled: `tools/call` gates on the capability preference,
never on list membership, so an unlisted tool routes exactly as before, and
`coffer__search_tools` keeps ranking the **full** catalogue. Tiering fails open
— `COFFER_TOOL_TIERING=off`, or any failure of the usage query, lists
everything. The split is not reported on a management page: "why can't the
agent see tool X" is a question asked inside an agent session, which the
`initialize` instructions below already answer, and a UI notice restating it
was one more surface to keep true for a reader who was not the one asking.

#### `initialize` instructions

The `initialize` response carries an MCP `instructions` string stating what
Coffer is and that `coffer__search_tools` reaches whatever tiering left
unlisted. It is the only channel Coffer has into the client's system prompt, so
it is capped (~800 characters) and omits the tiering sentence when nothing is
actually hidden.

#### Degraded upstream discovery

When a server misses the per-server discovery budget its tools are left out of
that listing, but the server is **named**, retried in the background, and on
recovery the gateway emits `notifications/tools/list_changed` so the client
re-lists. Without that a client's cached `tools/list` would keep those tools
missing for the whole session, since the correcting notification could only
come from the server that never connected.

---

### User Story 4 — See what the gateway has been called (Priority: P3)

The developer wants to know which upstream capability was called, when, how
long it took and whether it worked — without the gateway keeping a copy of what
was said. That record is the gateway's own; who changed a server's
configuration, and how long either record is kept, are spec
resource-framework's.

**Why this priority**: Necessary for trust and debugging, but not blocking the
gateway's basic operation.

**Independent Test**: Call a tool several times through an MCP client, then read
the invocation log from the terminal and confirm every call is there with its
outcome and no arguments or results.

**Covering scenarios**:

- invocation log records calls without arguments

---

### Edge Cases

These cases are tracked by integration tests, not by the acceptance audit, except where promoted to `## Acceptance Scenarios` below — tool-name collision, concurrent clients and the mid-session upstream crash each have a scenario of their own down there.

- **Upstream unreachable on register**: Registration must succeed (config saved); discovery and health report the failure; the server is marked unhealthy until reachable, and there is no silent retry storm.
- **Upstream crashes mid-call**: The in-flight call returns an error; the server is marked unhealthy; a subsequent call respawns the upstream with bounded retries; the user sees the failure in the invocation log.
- **Credential missing on register**: Registration fails with a message naming the missing credential and pointing the user at the credential setup path. No partial state is persisted. What "missing" means, and what happens when ciphertext exists but its key cannot be resolved, are spec credentials'.
- **Duplicate registration**: Registering a server with an existing name in the same kind is rejected with a clear error; partial-write is impossible.
- **Tool-name collision across servers**: Prevented by the `<server>__<tool>` namespace; never visible to clients.
- **Tools-only upstream**: An upstream that implements only `tools` and replies with JSON-RPC `-32601` (METHOD_NOT_FOUND) for `resources/list` or `prompts/list` is treated as having no resources / no prompts. The per-server capability view and the aggregate lists return that server's tools with an empty resources/prompts set (HTTP 200), not an error — so the management / Web-UI capability view works for tools-only servers.
- **Daemon crash**: running shim sessions return a clean error to their MCP clients rather than hanging on a socket that will never answer.
- **Concurrent clients**: Multiple MCP clients (e.g., Claude Code + Codex at the same time) connect simultaneously without one disturbing the other; each gets an independent upstream subprocess set.

## Gateway exposure scope ([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md))

An `mcp_server` resource carries a framework-level `scope` — one allow-list of
agents, `null` meaning unrestricted (spec vault-sync, "Scope has no machine
axis, because reach does not travel"); `None` for "every agent". Its value, its
validation and the routes that write it are spec
[resource-framework](../resource-framework/spec.md) FR-004; what this spec adds
is the enforcement, at the gateway's own existing choke point — the per-session
capability listing. There is no new central gate: scope selects *who* may see a server,
never *whether* the process is allowed to start once something past that gate
asks for it.

- **Per-session identity, and nothing else.** The gateway filters a server's
  capabilities per SESSION: a server whose scope excludes the connecting
  session's identity is hidden from that session's `tools/list` /
  `resources/list` / `prompts/list`, and any call against it is rejected —
  exactly as if the server did not exist for that session — even while it IS
  visible to a differently-identified session at the same time. The identity of
  the asking session is the only input the seam takes. A server's scope is part
  of its reach, and reach is already this machine's own — it is set here and a
  converge round neither carries it away nor writes over it (spec vault-sync,
  `## What does not sync`) — so "is this server for this machine" is a question
  the gateway never has to ask: if the answer were no, the server would not be
  enabled here.
- **Shim identity handshake.** The Coffer-MCP install (spec agent-registry FR-019)
  writes `coffer-mcp-shim --agent-uid <uid>` into the agent's config, so every
  managed agent's shim reports its own agent **uid** at MCP
  handshake via `params._meta["coffer/agent-uid"]`, alongside the existing cwd
  `_meta` injection (`coffer/cwd`). The uid and not the name, because that entry
  is written once into a file Coffer does not otherwise revisit and a label goes
  stale on the first rename ([Resource Identity Is an Immutable `uid`](../../docs/decisions/resource-identity-is-an-immutable-uid.md)).
  A session's reported identity is carried
  for the life of that connection and used for every subsequent list/call.
- **Unidentified sessions.** A session with no reported identity (a
  hand-configured shim invocation, or any client that omits the `--agent-uid`
  flag) is treated as `agent=None`: it sees, and may call, only servers that
  carry no scope at all — never a scoped one, even one naming the agent that
  happens to be running unidentified. An unidentified session therefore sees
  strictly less, never more.
- **Scope is not a spawn gate.** The supervisor never consults scope: a scoped
  server is spawned like any other enabled server, and enforcement happens one
  layer above it, where the asking agent is known. That is forced, not chosen —
  the supervisor holds no policy and has no session context, so there is
  nothing down there to test scope against. A second gate would also be
  unreachable, because every spawn path runs downstream of the first: the
  listing fan-out spawns only servers from the already-filtered set, and a call
  names its server explicitly and is re-checked at the invocation seam before
  the supervisor is asked for a connection. No session can start a server it may
  not see. The management surface behaves the same way — `POST /{uid}/test`
  and the other management routes are administrative operations on a resource,
  not agent sessions, and are not scope-gated. So the owner can always run a
  server no session on this machine is allowed to see, which is how they debug
  one before widening its scope.
- **Trust boundary.** Identity is SELF-REPORTED by the shim process at
  handshake, not cryptographically verified — acceptable under the
  single-user, loopback-only posture the daemon holds (spec daemon: every
  surface binds loopback and every management call carries a local token). Any
  local process able to open the loopback MCP connection and set `_meta` could
  claim any agent uid; this is documented explicitly rather than implying a
  stronger isolation boundary than exists.

`skill` scope is enforced at its own kind's seam (spec skill-manager, delivery),
and so is every other scoped kind: `channel` and `provider` also declare
`supports_scope` and gate at their own seam. Three kinds declare no scope at all
and reject a non-null value at validation (422): `agent` — it IS the agent, so
there is nothing for a per-agent scope to narrow — and `knowledge` and `memory`,
which withdrew on 2026-09-18 ([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)
item 7).

## Acceptance Scenarios

Per `.agents/sdd.md` and `.agents/testing.md`, every scenario in this section is referenced by at least one test marked `@pytest.mark.acceptance(spec="mcp-gateway", scenario="…")` (Python) or `acceptance("mcp-gateway", "…", …)` (TypeScript). Coverage is audited by `make verify-acceptance`.

### Scenario: register a stdio MCP server

- **Given** the coffer daemon is running and no MCP servers are registered,
- **When** the user registers a stdio MCP server with a unique name, command, and arguments,
- **Then** the server is persisted, its capabilities are discovered, and listing servers shows it as healthy.

### Scenario: register an HTTP MCP server

- **Given** the coffer daemon is running,
- **When** the user registers an HTTP MCP server with a URL and (optionally) a credential reference for an authorization header,
- **Then** the server is persisted and its capabilities are discovered without leaking the credential into any log or stored field.

### Scenario: HTTP-transport MCP server round trip

- **Given** an HTTP MCP server is running and registered with coffer,
- **When** a shim client lists tools and calls one through coffer's aggregated endpoint,
- **Then** both requests succeed end-to-end, returning valid MCP responses over the HTTP transport.

### Scenario: aggregate tools across servers in one client

- **Given** two MCP servers are registered and healthy,
- **When** an MCP client connects through coffer's shim and lists tools,
- **Then** every enabled tool from every registered server appears, named `<server>__<tool>`, and no two tools collide.

### Scenario: route a tool call to the correct upstream

- **Given** a client has discovered an aggregated tool list,
- **When** the client calls a prefixed tool,
- **Then** coffer forwards the call to the originating upstream with the original (unprefixed) name and returns the upstream's result unchanged.

### Scenario: resources forward through the gateway

- **Given** an upstream server exposes resources (not only tools),
- **When** a client reads a resource by its coffer URI,
- **Then** coffer routes the read to the originating upstream with the URI rewritten back to its upstream form and returns the upstream payload unchanged.

### Scenario: prompts forward through the gateway

- **Given** an upstream server exposes prompts (not only tools),
- **When** a client invokes a prompt by its `<server>__<prompt>` namespaced name,
- **Then** coffer routes the request to the originating upstream with the original (unprefixed) prompt name and returns the upstream payload unchanged.

### Scenario: upstream tool list changes mid-session

- **Given** a client is connected and an upstream MCP server's tool list changes (upgrade, plugin reload),
- **When** the upstream emits a list-changed notification,
- **Then** coffer forwards the notification to every client whose session subscribes to that upstream so the client re-lists, and coffer's cached capabilities are refreshed on next list.

### Scenario: concurrent clients

- **Given** two MCP clients connect simultaneously,
- **When** each lists and calls tools,
- **Then** both succeed without interference, and each client receives a distinct upstream subprocess set (verified by counting entries in `~/.coffer/upstream-pids/`).

### Scenario: upstream crash recovery

- **Given** an upstream MCP server crashes mid-session,
- **When** a client calls a tool after the crash,
- **Then** the gateway respawns the upstream and the call returns a successful result.

### Scenario: disable an individual capability

- **Given** a registered MCP server exposes several tools,
- **When** the user disables one tool,
- **Then** subsequent tool-list requests from any client omit it, and an attempt to call it returns a tool-disabled error.

### Scenario: disabled capability rejected through the shim

- **Given** a registered MCP server with two tools, where one has been disabled via the REST API,
- **When** a shim client calls `tools/list` and then `tools/call` on the disabled tool,
- **Then** `tools/list` omits the disabled tool while listing the enabled tool, and `tools/call` returns a JSON-RPC error with code -32000 (TOOL_DISABLED) rather than a successful result.

### Scenario: capability preferences survive upstream changes

- **Given** the user has disabled a tool on a server,
- **When** the upstream server is upgraded so that tool's schema changes (or it briefly disappears and returns),
- **Then** the user's disabled state is preserved without manual re-configuration.

### Scenario: a newly discovered capability is enabled by default

- **Given** a registered server whose capabilities have already been discovered,
- **When** an upgrade adds a new tool to that server,
- **Then** the new tool is enabled, the event is recorded in the audit log, and the user can disable it through the per-capability toggle (FR-007).

### Scenario: invocation log records calls without arguments

- **Given** an MCP client has invoked tools,
- **When** the user views the invocation log,
- **Then** every call is present with timestamp, target capability, duration, and outcome, and **no call arguments or return contents are stored**.

### Scenario: search the aggregated catalogue for matching tools

- **Given** N upstream tools are aggregated and healthy through coffer,
- **When** an agent calls `coffer__search_tools` with an intent query and a `top_k`,
- **Then** it receives at most `top_k` ranked real upstream tool schemas (upstream-only, with Coffer's own `coffer__` built-ins excluded), each named `<server>__<tool>`, the response reports `total_searched`, and the gateway records the invocation.

### Scenario: CLI returns non-zero exit on daemon unreachable

- **Given** the daemon is not running,
- **When** `coffer mcp list` is invoked,
- **Then** the process exits with code 3 and stderr names the daemon-unreachable condition.

### Scenario: CLI --json output is machine-readable

- **Given** any of `coffer mcp list` or `coffer mcp invocations` supports `--json`,
- **When** the subcommand is invoked with `--json`,
- **Then** stdout is a parseable JSON document with stable top-level keys (`resources` for `list`, `invocations` for `invocations`) and no human-readable framing.

### Scenario: gateway overhead stays under budget

- **Given** an in-process fast tool reachable through coffer and directly,
- **When** the same tool is called 100 times via coffer and 100 times directly,
- **Then** the median per-call gateway overhead (coffer-mediated latency minus direct latency) is at most 50 ms.

### Scenario: tool-name collision across servers is prevented

- **Given** two registered MCP servers expose a tool with the same upstream name (e.g. both expose `search`),
- **When** an MCP client lists tools through coffer,
- **Then** the client sees `<server-a>__search` and `<server-b>__search` as distinct, non-colliding entries — neither upstream name is surfaced unprefixed.

### Scenario: a missing stdio launcher is named in the server status

- **Given** a stdio server (e.g. imported from another machine) whose launcher command does not resolve on this machine,
- **When** the server's status is read,
- **Then** it reports `missing <runner>` instead of a bare failing state, and the UI tells the user which command to install rather than installing it (FR-011).

### Scenario: an out-of-scope server is invisible to a session

- **Given** an `mcp_server` resource whose `scope` names one agent only,
- **When** a shim session reporting a different agent identity (or no identity at all) lists tools,
- **Then** the server's tools are absent from that session's `tools/list`, and a call attempt against its namespaced tool name is rejected exactly as if the server were never registered — while a session reporting the named agent sees and may call it.

## Requirements

### Functional Requirements

**Gateway behavior**

- **FR-001**: System MUST present coffer as a single MCP server to clients, over both an HTTP/SSE endpoint and a stdio shim entry point.
- **FR-002**: System MUST forward MCP `tools`, `resources`, and `prompts` capabilities (list, call/read/get, and list-changed notifications) between clients and upstream MCP servers.
- **FR-003**: System MUST namespace every upstream capability with its server's name (`<server>__<tool>` for tools and prompts; a server-prefixed URI scheme for resources) so capabilities from different servers never collide.
- **FR-004**: System MUST route a client call on a namespaced capability to the originating upstream with the upstream's original (unprefixed) identifier.

**Resource lifecycle**

- **FR-005**: Users MUST be able to register, list, view, update, enable, disable, rename and delete MCP servers as resources addressed by the immutable `uid` the framework mints for them ([Resource Identity Is an Immutable `uid`](../../docs/decisions/resource-identity-is-an-immutable-uid.md)); a server's `name` is a mutable label, and the per-server routes are `/api/v1/resources/mcp_server/{uid}/…`. Validating that registration against the kind's schema, rejecting a duplicate name within the kind, and persisting nothing on a validation failure are spec [resource-framework](../resource-framework/spec.md) FR-002, which every kind inherits; this requirement is what brings `mcp_server` under it, and the kind-agnostic surface those operations are served through is that spec's too.
- **FR-006**: System MUST support both stdio and HTTP MCP transports for upstream servers.

**Capability curation**

- **FR-007**: Users MUST be able to enable or disable individual tools, resources, and prompts on a per-server basis.
- **FR-008**: System MUST preserve the user's enable/disable decisions across daemon restarts, upstream upgrades, and upstream temporary disappearances.
- **FR-009**: System MUST enable a previously unseen capability by default when it is discovered, leaving it to FR-007 to curate. There is no per-server auto-enable policy: the setting existed as a config field with no UI to change it, every registered server carried the default, and a choice that is never made is not a policy.

**Invocation record**

- **FR-010**: System MUST record an invocation entry for every tool call, resource read, and prompt fetch — without recording arguments or return contents. How long those entries are kept, and the background pass that prunes them, are spec [resource-framework](../resource-framework/spec.md) FR-007 — the retention contract every log-writing kind inherits — not this spec's own rule. This spec contributes `mcp_invocations` to that registry with a 30-day default.

**Missing launcher**

- **FR-011**: A stdio server whose launcher command does not resolve on this machine (an imported server referencing e.g. `uvx` where `uv` is not installed) MUST be surfaced as such — `missing <runner>` in the server status — instead of a bare "failing" with no cause, and the UI MUST name the command to install. Coffer MUST NOT install it. Detection turns an uninformative failure into an actionable one, which is the whole of the value here; running a package manager from a long-lived daemon would widen Coffer's remit from managing configuration to installing software on the user's machine, a line the deliberately-minimal runner→formula map could not hold once pip, cargo, and go were asked for — and it only ever worked on macOS.

**Scope enforcement ([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md))**

- **FR-012**: System MUST filter `mcp_server` exposure by its framework-level `scope` — one allow-list, `agents`, `null` meaning unrestricted — at the gateway's per-session choke point: the session's self-reported agent identity gates `tools/list` / `resources/list` / `prompts/list` and call routing. A server the scope excludes is indistinguishable from a disabled capability to that session, while staying registered, listed in the management surface and editable. The identity of the asking session is the only input the gate takes; scope names agents and nothing else, because a server's reach is machine-local and never arrives from elsewhere (spec vault-sync `## What does not sync`) — a server that should not run here is simply not enabled here. Scope MUST NOT gate spawning: the supervisor holds no policy and has no session identity to test, so the decision is enforced above it. Every spawn path runs downstream of that gate (the listing fan-out spawns only from the already-filtered set; a call is re-checked at the invocation seam), so a scoped server starts like any other enabled server but no session can start one it may not see. The management routes (including `POST /{uid}/test`) are administrative operations rather than agent sessions and MUST NOT be scope-gated — so the owner can always test a server no session here is allowed to see.
- **FR-013**: System MUST accept a self-reported agent identity at MCP handshake as the agent's **uid** (`params._meta["coffer/agent-uid"]`, alongside the existing `coffer/cwd` key), written into a managed agent's shim invocation as `coffer-mcp-shim --agent-uid <uid>` by the Coffer-MCP install (spec agent-registry FR-019) — the uid rather than the name, because the entry is written once into a file Coffer does not revisit and a name goes stale on the first rename. A `_meta` carrying only the older name-based key MUST be treated as reporting no identity rather than resolved by name. A session with no reported identity MUST be treated as `agent=None`, matching only servers that carry no scope. Identity is self-reported, not cryptographically verified — a documented trust boundary, acceptable under the loopback-only, single-user posture spec daemon holds. It is reported **once, at the handshake**, and nowhere else: when the gateway threads the identity into a Coffer built-in tool call (as the `agent` argument the knowledge and memory tools authorize by), it MUST overwrite any `agent` the client put in the call's arguments with the session's, and MUST drop the argument entirely when the session reported none — so a client cannot pick a different identity per call, and no built-in tool advertises `agent` in its input schema.

**Sync state area**

- **FR-014**: The `state/mcp-preferences/<server>` sync state area is this spec's, so this spec defines what deleting one of its documents means — spec [vault-sync](../vault-sync/spec.md) FR-058 requires that of every area and interprets none of them itself. A document exists only while something on that server is disabled; deleting it therefore means "nothing is disabled here", and Coffer MUST re-enable every capability on that server. The preference rows MUST stay — enabled is their default, and their seen-timestamps are this machine's own record of what the server offered, not a decision another machine took back. A rel naming a server this machine does not register MUST be ignored: the deletion cannot have been about anything here. For the same reason this spec MUST NOT publish a document for a server with nothing disabled, or a machine that re-enabled everything and a machine that never disabled anything would add and delete the same document at each other every round.

### Key Entities

- **MCP Server** (a resource of kind `mcp_server`): Configuration for one upstream MCP server — its transport (stdio command-line or HTTP URL), credential references, and per-server timeouts.
- **Capability**: A tool, resource, or prompt exposed by an MCP server. Discovered live from the upstream; only the user's enable/disable preference and last-seen timestamp are persisted.
- **Invocation Record**: A record of a single capability call through the gateway. Includes target, timestamp, duration, and outcome — no arguments or return content.

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh source install, a user can register their first MCP server and see it usable in an MCP client within 5 minutes, without consulting documentation more than once.
- **SC-002**: With three upstream MCP servers registered, an MCP client connected through coffer's shim lists every enabled capability from every server on a single tool-list request, with zero name collisions.
- **SC-003**: A tool call routed through coffer adds no more than 50 ms of overhead compared to the same call made by the client directly to the upstream, measured over 100 calls of a fast in-process tool.
- **SC-004**: With two MCP clients (e.g., Claude Code and Codex) connected at the same time, both successfully discover and call tools without interference, for a 30-minute interactive session.
- **SC-005**: Disabling a tool causes it to disappear from any client's next tool-list response and to reject any in-flight call attempt with a tool-disabled error.
- **SC-006**: Invocation records older than their configured retention period are removed by spec resource-framework's periodic cleanup while newer entries are retained, and the cleanup does not block concurrent API calls.
- **SC-007**: Every Acceptance Scenario in this document is covered by at least one test marked with `acceptance(spec="mcp-gateway", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-008**: The full `make verify` suite (lint + unit + integration + contract + acceptance audit) passes locally and in CI; `make verify-all` (adding e2e) passes locally on macOS and in CI on Linux.

## Assumptions

- The single user runs coffer on their own machine. There is no multi-tenant or remote-access requirement.
- The MCP client (Claude Code, Codex, etc.) supports either an `stdio` MCP server configuration or an `http`/`sse` MCP server configuration; coffer ships both entry points.
- Upstream MCP servers behave according to the public MCP protocol specification. Misbehaving upstreams are handled as faults, not modelled as features.
- An upstream's secrets are resolvable when it is spawned. The encrypted store behind them, the master key that opens it, and what a user is told when that key is unavailable are spec credentials'; this spec persists refs and never holds a key.
- The daemon this gateway is served from — its port, its discovery file, its token, its loopback posture and the browser host it serves — is spec daemon's. This spec assumes a running daemon rather than specifying one.
- The kind-agnostic half of what an `mcp_server` is — the immutable-`uid` identity, the lifecycle surface (rename included), per-agent reach, the audit log and retention — is spec resource-framework's. This spec contributes one `Kind` descriptor to it and owns everything MCP-specific above it.
- Concurrent MCP client load is small (low single digits); coffer is not a fleet-scale gateway.

## Deliberately out of scope

- **Vault backup and restore.** Coffer does not bundle its own `.tar.gz` snapshot of `~/.coffer/`. The bidirectional git convergence of spec vault-sync already carries everything that is a system of record — the file trees, the resources, and the credential ciphertext — to a remote the user owns, and brings another machine's copy back. What a backup added on top of that was local-only data: the log tables (which roll off on a 30-day retention anyway) and the chat conversation rows. It also wrote its archive to the same machine by default, so it never answered the off-site question it appeared to answer. Users who want a byte-copy have `cp -r ~/.coffer/` with the daemon stopped; users who want a vault on two machines have convergence.
