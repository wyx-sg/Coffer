# Feature Specification: MCP Gateway

**Feature Branch**: `feature/mcp-gateway`
**Created**: 2026-05-20
**Status**: Accepted
**Scope note**: This spec owns the backend layer — the daemon, MCP gateway, REST API, and `coffer` CLI.
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
- new capabilities default per server policy

---

### User Story 3 — Same operations from the command line (Priority: P2)

The developer scripts setup and bulk operations from a terminal — adding servers from a dotfile, automating CI-friendly enable/disable.

**Why this priority**: Coffer's audience is developers. A full CLI is table stakes for scripted workflows and remote machines.

**Independent Test**: From a fresh install, register two servers, toggle several tools, and view audit/invocation logs entirely from the terminal — no GUI needed.

**Covering scenarios**:

- command line covers every visual operation
- command line surfaces same errors

---

### User Story 4 — Auditing & activity logs with retention controls (Priority: P3)

The developer wants to see what happened — when a server was added, when a tool was disabled, what tools were called when — without those logs growing unbounded.

**Why this priority**: Necessary for trust and debugging, but not blocking the gateway's basic operation. Retention defaults are sensible enough that most users never touch them.

**Independent Test**: Make several changes, view audit; run several tool calls, view invocations; change a retention period to a short value, wait for the next cleanup, confirm older entries are gone and newer ones remain.

**Covering scenarios**:

- audit lifecycle changes
- invocation log records calls without arguments
- configure retention per log

---

### User Story 5 — Find the right tool under aggregation overload (Priority: P2)

Once a developer has registered many upstream servers, the aggregated surface can exceed 150 tools. A coding agent's tool-selection accuracy degrades sharply past ~30–50 tools, so dumping the whole catalogue into every request both wastes context tokens and makes the agent pick wrong. The developer wants the agent to _search_ the live aggregated catalogue for the few tools that match its current intent and call them directly, instead of reasoning over the entire list.

**Why this priority**: Aggregation is only useful if the agent can still choose well at scale; this turns "I installed 30 servers" from a liability back into leverage. It builds on the core gateway (User Story 1) without changing how any upstream tool is exposed or called.

**Independent Test**: Register enough servers that the aggregated catalogue is large, then from an MCP client call `coffer__search_tools` with an intent query and a `top_k`; observe at most `top_k` ranked upstream tool schemas come back, the agent calls one of them by its `<server>__<tool>` name, and the call routes to the originating upstream as usual.

**Covering scenarios**:

- search the aggregated catalogue for matching tools

The behaviour and rationale are recorded in [ADR-018](../../docs/decisions/ADR-018-tool-retrieval-for-overload.md).

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

---

### Edge Cases

These cases are tracked by integration tests, not by the acceptance audit, except where promoted to `## Acceptance Scenarios` below (currently: tool-name collision, daemon port conflict).

- **Upstream unreachable on register**: Registration must succeed (config saved); discovery and health report the failure; the server is marked unhealthy until reachable, and there is no silent retry storm.
- **Upstream crashes mid-call**: The in-flight call returns an error; the server is marked unhealthy; a subsequent call respawns the upstream with bounded retries; the user sees the failure in the invocation log.
- **Credential missing or master key unavailable**: Registration fails with a message naming the missing credential and pointing the user at the credential setup path. No partial state is persisted. (If ciphertext exists but the master key cannot be resolved, the daemon refuses to start with `MasterKeyMissing` rather than silently lose access.)
- **Duplicate registration**: Registering a server with an existing name in the same kind is rejected with a clear error; partial-write is impossible.
- **Tool-name collision across servers**: Prevented by the `<server>__<tool>` namespace; never visible to clients.
- **Tools-only upstream**: An upstream that implements only `tools` and replies with JSON-RPC `-32601` (METHOD_NOT_FOUND) for `resources/list` or `prompts/list` is treated as having no resources / no prompts. The per-server capability view and the aggregate lists return that server's tools with an empty resources/prompts set (HTTP 200), not an error — so the management / Web-UI capability view works for tools-only servers.
- **Daemon port conflict**: The daemon's default port is taken — it picks the next free one in a small range and writes the chosen port to its discovery file; clients (shim, desktop, CLI) all read that file.
- **Daemon crash**: running shim sessions return a clean error to their MCP clients rather than hanging; a supervising surface can detect the crash and restart the daemon.
- **Concurrent clients**: Multiple MCP clients (e.g., Claude Code + Codex at the same time) connect simultaneously without one disturbing the other; each gets an independent upstream subprocess set.

## Acceptance Scenarios

Per `agents/sdd.md` and `agents/testing.md`, every scenario in this section is referenced by at least one test marked `@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="…")` (Python) or `acceptance("001-mcp-gateway", "…", …)` (TypeScript). Coverage is audited by `make verify-acceptance`.

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

### Scenario: new capabilities default per server policy

- **Given** a server is configured to auto-enable new capabilities (default) or not,
- **When** an upgrade adds a new tool to that server,
- **Then** the new tool is enabled or disabled according to that server's policy, and the event is recorded in the audit log.

### Scenario: command line covers every visual operation

- **Given** the daemon is running,
- **When** the user invokes the relevant `coffer mcp …` / `coffer resource …` / `coffer audit …` / `coffer retention …` subcommand,
- **Then** the same effect is achieved as the corresponding management operation, and machine-readable JSON output is available for scripting.

### Scenario: command line surfaces same errors

- **Given** any failure surfaced by the management API,
- **When** triggered through the command line,
- **Then** the user sees an actionable message and a non-zero exit code; `--verbose` shows a full trace.

### Scenario: audit lifecycle changes

- **Given** the user performs any add / enable / disable / update / delete on a server or capability,
- **When** they open the audit view (CLI or UI),
- **Then** they see one row per change with actor, timestamp, and a payload describing what changed.

### Scenario: invocation log records calls without arguments

- **Given** an MCP client has invoked tools,
- **When** the user views the invocation log,
- **Then** every call is present with timestamp, target capability, duration, and outcome, and **no call arguments or return contents are stored**.

### Scenario: configure retention per log

- **Given** the audit and invocation logs grow over time,
- **When** the user sets a retention period for a log (in days, or "keep forever"),
- **Then** entries older than that period are removed by the next periodic cleanup, and the change itself is audited.

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

### Scenario: store and reference a credential

- **Given** the user has not yet stored an HTTP credential,
- **When** the user issues `POST /api/v1/credentials` (or the equivalent CLI) with `ref` and the secret `value` in the request body, then registers an HTTP MCP server whose `credential_refs` cites `{ref}`,
- **Then** the credential value is written only as Fernet ciphertext in the `credentials` table (its plaintext never reaches the SQLite DB, any log, or the audit), and the server registration succeeds with the credential resolved (decrypted) at upstream-spawn time.

### Scenario: delete a credential frees the reference

- **Given** a credential `{ref}` exists and is cited by zero MCP servers,
- **When** the user issues `DELETE /api/v1/credentials/{ref}` (or the equivalent CLI),
- **Then** the ciphertext row is removed, the deletion is audited, and a later registration may reuse `{ref}` without conflict.

### Scenario: daemon status reflects ready state

- **Given** the daemon has just been started,
- **When** `GET /api/v1/daemon/status` is called,
- **Then** the response reports `status: "ready"`, a non-zero `port`, and a `started_at` timestamp — and the same values are written to `~/.coffer/daemon.json`.

### Scenario: rotating the daemon token invalidates the previous one

- **Given** the daemon has issued an auth token,
- **When** the user invokes the rotate-token operation,
- **Then** subsequent management API calls with the previous token are rejected with 401, calls with the new token succeed, and the rotation is recorded as a `token_rotated` audit entry.

### Scenario: daemon backup produces a portable SQLite copy

- **Given** the daemon has running state in `~/.coffer/coffer.db`,
- **When** the user invokes the daemon-backup operation,
- **Then** a self-consistent SQLite copy of the index is written under `~/.coffer/backups/` while the daemon keeps running, and a `backup_created` audit entry is recorded. (This copies only `coffer.db` — the rebuildable index — not the system-of-record file trees; for a complete, restorable vault snapshot use the vault backup below.)

### Scenario: vault backup captures db + file trees, restore round-trips them

- **Given** a populated vault under `~/.coffer/` — `coffer.db` plus the markdown file trees that are the system of record (`knowledge/`, `memory/`, `skills/`),
- **When** the user runs `coffer backup <dest>` and later `coffer restore <dest>` into a fresh vault,
- **Then** the destination holds `coffer.db` and every file tree; restoring re-places them all so a sample KB document and a sample memory fact round-trip byte-for-byte and the restored `coffer.db` is a consistent index of the restored trees.

### Scenario: backup excludes the master key by default

- **Given** the vault contains the Fernet `master.key` that decrypts the credential ciphertext in `coffer.db`,
- **When** the user runs `coffer backup <dest>` without `--include-master-key`,
- **Then** `master.key` is NOT written into the backup (so the backup is safe to copy off-machine), and the command warns that stored credentials need the key to decrypt; passing `--include-master-key` bundles the key only after printing an explicit warning.

### Scenario: gateway overhead stays under budget

- **Given** an in-process fast tool reachable through coffer and directly,
- **When** the same tool is called 100 times via coffer and 100 times directly,
- **Then** the median per-call gateway overhead (coffer-mediated latency minus direct latency) is at most 50 ms.

### Scenario: credentials never leak to logs or audit

- **Given** an MCP server registered with a credential reference,
- **When** the server is spawned, exercised, and torn down through one representative session,
- **Then** an automated scan of every database row, audit entry, invocation record, and log file under `~/.coffer/logs/` reveals zero occurrences of the credential's literal value.

### Scenario: tool-name collision across servers is prevented

- **Given** two registered MCP servers expose a tool with the same upstream name (e.g. both expose `search`),
- **When** an MCP client lists tools through coffer,
- **Then** the client sees `<server-a>__search` and `<server-b>__search` as distinct, non-colliding entries — neither upstream name is surfaced unprefixed.

### Scenario: daemon port conflict falls back to the next free port

- **Given** the default daemon port is already bound by another process,
- **When** the daemon starts,
- **Then** it picks the next free port in the supported range, writes the chosen port to `~/.coffer/daemon.json`, and every Coffer surface (shim, CLI) connects to that port without manual configuration.

### Scenario: scope an agent to a subset of servers

- **Given** two enabled MCP servers are registered and an agent is bound to a session whose MCP scope is `selected` with only the first server in its allowlist (ADR-026),
- **When** that agent lists tools through the gateway,
- **Then** only the first server's tools (plus Coffer's built-ins) appear and the second server's tools are hidden, and `coffer__search_tools` likewise ranks only in-scope tools.

### Scenario: reject an out-of-scope tool call

- **Given** an agent's MCP scope is `selected` and a server is not in its allowlist,
- **When** the agent calls that out-of-scope server's tool directly by its `<server>__<tool>` name,
- **Then** the gateway rejects the call with `MCP_SERVER_OUT_OF_SCOPE` and never forwards the request to the upstream.

### Scenario: auto-mode agent sees all enabled servers

- **Given** an agent whose MCP scope is `auto` (the default — no scope row),
- **When** the agent lists tools through the gateway,
- **Then** every enabled server's tools are exposed, exactly as before per-agent scoping existed.

### Scenario: an anonymous session is unscoped

- **Given** a gateway session with no bound agent identity (e.g. the in-process `ask` agent or a client that sent no `X-Coffer-Agent`),
- **When** that session lists tools through the gateway,
- **Then** every enabled server's tools are exposed, because scoping only applies to a known agent.

## Requirements

### Functional Requirements

**Gateway behavior**

- **FR-001**: System MUST present coffer as a single MCP server to clients, over both an HTTP/SSE endpoint and a stdio shim entry point.
- **FR-002**: System MUST forward MCP `tools`, `resources`, and `prompts` capabilities (list, call/read/get, and list-changed notifications) between clients and upstream MCP servers.
- **FR-003**: System MUST namespace every upstream capability with its server's name (`<server>__<tool>` for tools and prompts; a server-prefixed URI scheme for resources) so capabilities from different servers never collide.
- **FR-004**: System MUST route a client call on a namespaced capability to the originating upstream with the upstream's original (unprefixed) identifier.

**Resource lifecycle**

- **FR-005**: Users MUST be able to register, list, view, update, enable, disable, and delete MCP servers as resources with stable identifiers of the form `<kind>:<name>`.
- **FR-006**: System MUST validate every registration against a kind-specific schema, reject duplicates within a kind, and persist nothing on validation failure.
- **FR-007**: System MUST support both stdio and HTTP MCP transports for upstream servers.

**Capability curation**

- **FR-008**: Users MUST be able to enable or disable individual tools, resources, and prompts on a per-server basis.
- **FR-009**: System MUST preserve the user's enable/disable decisions across daemon restarts, upstream upgrades, and upstream temporary disappearances.
- **FR-010**: System MUST apply a per-server "auto-enable new capabilities" policy (default true) when a previously unseen capability is discovered.

**Per-agent scoping**

- **FR-019**: System MUST identify which agent a downstream gateway session belongs to, via an agent identity carried by the `coffer` MCP entry (an `--agent <name>` argument) and forwarded by the shim as an `X-Coffer-Agent` request header. A session presenting no identity MUST be treated as unscoped (full access), preserving backward compatibility.
- **FR-020**: System MUST support a per-agent scope mode of `auto` (the agent sees every enabled MCP server) or `selected` (the agent sees only an explicit allowlist of servers). Agents MUST default to `auto`; a newly added server MUST become visible to `auto` agents automatically but MUST NOT join any `selected` agent's allowlist.
- **FR-021**: System MUST apply each agent's effective scope — enabled servers, intersected with the allowlist when `selected` — when listing tools, resources, and prompts and when ranking `coffer__search_tools`, so that an out-of-scope server's capabilities are never surfaced to that agent.
- **FR-022**: System MUST reject a direct `tools/call`, `resources/read`, or `prompts/get` that targets an out-of-scope server — even when the capability name is supplied directly — returning an error instead of invoking the upstream.

**Credentials and safety**

- **FR-011**: System MUST store all upstream-server credentials only as Fernet ciphertext in the `credentials` table (envelope encryption), referenced from configuration by name; credential plaintext MUST never be written to the database, any log, or the audit. The Fernet master key MUST be managed solely by `infrastructure/credentials/` — a `0600` file beside the DB by default, the OS keychain opt-in. The management API MUST expose credential endpoints so a UI can manage a secret without its plaintext landing in any persisted config: write (`POST /api/v1/credentials`), delete (`DELETE /api/v1/credentials/{ref}`), an existence check (`GET /api/v1/credentials/{ref}/exists`), and an audited read (`GET /api/v1/credentials/{ref}`). The read endpoint returns the secret value and emits a `credential_read` audit event so every secret read is recorded.
- **FR-012**: System MUST bind all HTTP endpoints (management API and MCP protocol endpoint) to the loopback interface only.
- **FR-013**: System MUST require an authentication token on every management API call; the token is generated locally at daemon startup, stored with user-only file permissions, and rotatable.

**Auditing & activity logs**

- **FR-014**: System MUST record an audit entry for every lifecycle change to any resource or capability, including the actor (CLI / API / UI / system).
- **FR-015**: System MUST record an invocation entry for every tool call, resource read, and prompt fetch — without recording arguments or return contents.
- **FR-016**: System MUST provide per-table retention configuration (in days, or "keep forever") for audit and invocation logs, and a periodic background cleanup that prunes older entries.

**Surfaces**

- **FR-017**: Users MUST be able to perform every management operation through both (a) a REST API and (b) a `coffer` command-line interface, sharing the same underlying daemon and a consistent error model.

**Distribution**

- **FR-018**: Installing from source (`pip install ./backend`) MUST place the `coffer` CLI and the `coffer-mcp-shim` stdio entry point on the user's `PATH` as console scripts, so the daemon and shim are usable with no separate deployment step.

### Key Entities

- **Resource**: A user-managed entity inside coffer, identified by `(kind, name)`. This spec registers one kind, `mcp_server`. Each resource carries kind-specific configuration, an enabled flag, description, and timestamps. The framework is kind-agnostic so additional kinds can be added by later specs without re-modelling.
- **MCP Server** (a resource of kind `mcp_server`): Configuration for one upstream MCP server — its transport (stdio command-line or HTTP URL), credential references, and per-server policies (auto-enable, timeouts).
- **Capability**: A tool, resource, or prompt exposed by an MCP server. Discovered live from the upstream; only the user's enable/disable preference and last-seen timestamp are persisted.
- **Audit Event**: A record of a lifecycle change to any resource or capability. Includes the actor, target, event type, timestamp, and a structured payload.
- **Invocation Record**: A record of a single capability call through the gateway. Includes target, timestamp, duration, and outcome — no arguments or return content.
- **Retention Policy**: A per-log-table setting controlling how long entries are kept. Audit defaults to 365 days, invocations to 30 days; either can be set to "keep forever".
- **Agent MCP scope**: Per-agent visibility policy applied at the gateway — a `mode` (`auto` = every enabled server; `selected` = an explicit allowlist) plus the allowlist of server names used when `selected`. New agents default to `auto`; a session with no agent identity is unscoped.

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh source install, a user can register their first MCP server and see it usable in an MCP client within 5 minutes, without consulting documentation more than once.
- **SC-002**: With three upstream MCP servers registered, an MCP client connected through coffer's shim lists every enabled capability from every server on a single tool-list request, with zero name collisions.
- **SC-003**: A tool call routed through coffer adds no more than 50 ms of overhead compared to the same call made by the client directly to the upstream, measured over 100 calls of a fast in-process tool.
- **SC-004**: With two MCP clients (e.g., Claude Code and Codex) connected at the same time, both successfully discover and call tools without interference, for a 30-minute interactive session.
- **SC-005**: Disabling a tool causes it to disappear from any client's next tool-list response and to reject any in-flight call attempt with a tool-disabled error.
- **SC-006**: Audit and invocation logs older than their configured retention period are removed by the periodic cleanup, while newer entries are retained, and the cleanup does not block concurrent API calls.
- **SC-007**: Every Acceptance Scenario in this document is covered by at least one test marked with `acceptance(spec="001-mcp-gateway", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-008**: The full `make verify` suite (lint + unit + integration + contract + acceptance audit) passes locally and in CI; `make verify-all` (adding e2e) passes locally on macOS and in CI on Linux.
- **SC-009**: After installing from source (`pip install ./backend`, requiring Python 3.12+), `coffer` and `coffer-mcp-shim` are both available on the user's `PATH`, and the daemon reaches the "ready" state with no manual steps beyond `pip install`.
- **SC-010**: No upstream-server credential value ever appears in any database table, log file, audit entry, or invocation record — verified by an automated scan of those artifacts after a representative session.

## Assumptions

- The single user runs coffer on their own machine. There is no multi-tenant or remote-access requirement.
- The MCP client (Claude Code, Codex, etc.) supports either an `stdio` MCP server configuration or an `http`/`sse` MCP server configuration; coffer ships both entry points.
- Upstream MCP servers behave according to the public MCP protocol specification. Misbehaving upstreams are handled as faults, not modelled as features.
- The Fernet master key is resolvable at coffer startup (a readable `~/.coffer/master.key` by default, or an unlocked OS keychain in keychain mode), or the user is shown a clear message when it isn't (ciphertext with no resolvable key is a fatal `MasterKeyMissing` startup error).
- This spec ships with one resource kind (`mcp_server`). The Resource framework is designed so additional kinds can be added by later specs without re-modelling existing data.
- Concurrent MCP client load is small (low single digits); coffer is not a fleet-scale gateway.
