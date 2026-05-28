# Feature Specification: MCP Gateway

**Feature Branch**: `feature/mcp-gateway`
**Created**: 2026-05-20
**Status**: Accepted
**Scope note**: This spec owns the backend layer only — the daemon, MCP gateway, REST API, and `coffer` CLI. Every user-facing surface (web UI, Tauri desktop shell, visual language, information architecture, internationalisation) is deferred to the planned UI spec (to be drafted as `002-ui-shell` in a follow-up PR).
**Input**: User description: "Coffer's first feature — an MCP server gateway. Like mcpjungle / metamcp: one MCP client (Claude Code / Claude Desktop / Cursor) connects to coffer; coffer aggregates many upstream MCP servers and re-exposes their tools, resources, and prompts as a single namespaced surface. Coffer will later manage other resource kinds (skills, memory, channels, agents) — design the first feature on top of a generic Resource framework so follow-on kinds plug in cleanly."

## User Scenarios & Testing

### User Story 1 — Aggregate multiple MCP servers in one client (Priority: P1)

A developer uses Claude Code (or Claude Desktop, or Cursor) and wants to wire several MCP servers (filesystem, GitHub, Postgres, …) into it. Instead of editing each client's MCP config and re-restarting clients when the list changes, they register the upstream servers **once** in coffer and point each client at coffer's single shim. All upstream tools, resources, and prompts appear in every client, namespaced so they don't collide.

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

### User Story 4 — Observability with retention controls (Priority: P3)

The developer wants to see what happened — when a server was added, when a tool was disabled, what tools were called when — without those logs growing unbounded.

**Why this priority**: Necessary for trust and debugging, but not blocking the gateway's basic operation. Retention defaults are sensible enough that most users never touch them.

**Independent Test**: Make several changes, view audit; run several tool calls, view invocations; change a retention period to a short value, wait for the next cleanup, confirm older entries are gone and newer ones remain.

**Covering scenarios**:

- audit lifecycle changes
- invocation log records calls without arguments
- configure retention per log

---

### Edge Cases

These cases are tracked by integration tests, not by the acceptance audit, except where promoted to `## Acceptance Scenarios` below (currently: tool-name collision, daemon port conflict).

- **Upstream unreachable on register**: Registration must succeed (config saved); discovery and health report the failure; the server is marked unhealthy until reachable, and there is no silent retry storm.
- **Upstream crashes mid-call**: The in-flight call returns an error; the server is marked unhealthy; a subsequent call respawns the upstream with bounded retries; the user sees the failure in the invocation log.
- **Credential missing or keychain locked**: Registration fails with a message naming the missing credential and pointing the user at the credential setup path. No partial state is persisted.
- **Duplicate registration**: Registering a server with an existing name in the same kind is rejected with a clear error; partial-write is impossible.
- **Tool-name collision across servers**: Prevented by the `<server>__<tool>` namespace; never visible to clients.
- **Daemon port conflict**: The daemon's default port is taken — it picks the next free one in a small range and writes the chosen port to its discovery file; clients (shim, desktop, CLI) all read that file.
- **Daemon crash**: running shim sessions return a clean error to their MCP clients rather than hanging; a supervising surface can detect the crash and restart the daemon (desktop-app supervision is deferred to the planned UI spec — to be drafted as `002-ui-shell` in a follow-up PR).
- **Concurrent clients**: Multiple MCP clients (e.g., Claude Code + Cursor at the same time) connect simultaneously without one disturbing the other; each gets an independent upstream subprocess set.
- _(First-time install / launcher discoverability is UI-dependent and will be tracked in the planned UI spec.)_

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

### Scenario: CLI returns non-zero exit on daemon unreachable

- **Given** the daemon is not running,
- **When** `coffer mcp list` is invoked,
- **Then** the process exits with code 3 and stderr names the daemon-unreachable condition.

### Scenario: CLI --json output is machine-readable

- **Given** any of `coffer mcp list` or `coffer mcp invocations` supports `--json`,
- **When** the subcommand is invoked with `--json`,
- **Then** stdout is a parseable JSON document with stable top-level keys (`resources` for `list`, `invocations` for `invocations`) and no human-readable framing.

### Scenario: store and reference a keychain credential

- **Given** the user has not yet stored an HTTP credential,
- **When** the user issues `POST /api/v1/keychain/{ref}` (or the equivalent CLI) with a secret value, then registers an HTTP MCP server whose `credential_refs` cites `{ref}`,
- **Then** the credential value is written only to the OS keychain (never to the SQLite DB or any log), and the server registration succeeds with the credential resolved at upstream-spawn time.

### Scenario: delete a keychain credential frees the reference

- **Given** a keychain credential `{ref}` exists and is cited by zero MCP servers,
- **When** the user issues `DELETE /api/v1/keychain/{ref}` (or the equivalent CLI),
- **Then** the OS keychain entry is removed, the deletion is audited, and a later registration may reuse `{ref}` without conflict.

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
- **Then** a self-consistent SQLite copy is written under `~/.coffer/backups/` (safe to copy off-machine while the daemon keeps running) and a `backup_created` audit entry is recorded.

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

**Credentials and safety**

- **FR-011**: System MUST store all upstream-server credentials only in the operating system's keychain, referenced from configuration by name; credentials MUST never be written to the database or to any log. The management API MUST expose a keychain-write **and delete** endpoint so a UI can store or remove a secret directly in the keychain without it passing through the database.
- **FR-012**: System MUST bind all HTTP endpoints (management API and MCP protocol endpoint) to the loopback interface only.
- **FR-013**: System MUST require an authentication token on every management API call; the token is generated locally at daemon startup, stored with user-only file permissions, and rotatable.

**Observability**

- **FR-014**: System MUST record an audit entry for every lifecycle change to any resource or capability, including the actor (CLI / API / UI / system).
- **FR-015**: System MUST record an invocation entry for every tool call, resource read, and prompt fetch — without recording arguments or return contents.
- **FR-016**: System MUST provide per-table retention configuration (in days, or "keep forever") for audit and invocation logs, and a periodic background cleanup that prunes older entries.

**Surfaces**

- **FR-017**: Users MUST be able to perform every management operation through both (a) a REST API and (b) a `coffer` command-line interface, sharing the same underlying daemon and a consistent error model.

_(FR-018–FR-020 (desktop app, system tray, i18n) are deferred to the planned UI spec (to be drafted as `002-ui-shell` in a follow-up PR).)_

_(The desktop application, system tray, launch-at-login, and UI internationalisation are owned by the planned UI spec.)_

**Distribution**

- **FR-021**: The end-user install path MUST produce a working coffer daemon and shim without requiring the user to install Python or other runtimes. (Desktop-app packaging is owned by the planned UI spec — to be drafted as `002-ui-shell` in a follow-up PR.)

### Key Entities

- **Resource**: A user-managed entity inside coffer, identified by `(kind, name)`. This spec registers one kind, `mcp_server`. Each resource carries kind-specific configuration, an enabled flag, description, and timestamps. The framework is kind-agnostic so additional kinds can be added by later specs without re-modelling.
- **MCP Server** (a resource of kind `mcp_server`): Configuration for one upstream MCP server — its transport (stdio command-line or HTTP URL), credential references, and per-server policies (auto-enable, timeouts).
- **Capability**: A tool, resource, or prompt exposed by an MCP server. Discovered live from the upstream; only the user's enable/disable preference and last-seen timestamp are persisted.
- **Audit Event**: A record of a lifecycle change to any resource or capability. Includes the actor, target, event type, timestamp, and a structured payload.
- **Invocation Record**: A record of a single capability call through the gateway. Includes target, timestamp, duration, and outcome — no arguments or return content.
- **Retention Policy**: A per-log-table setting controlling how long entries are kept. Audit defaults to 365 days, invocations to 30 days; either can be set to "keep forever".

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh source install, a user can register their first MCP server and see it usable in an MCP client within 5 minutes, without consulting documentation more than once.
- **SC-002**: With three upstream MCP servers registered, an MCP client connected through coffer's shim lists every enabled capability from every server on a single tool-list request, with zero name collisions.
- **SC-003**: A tool call routed through coffer adds no more than 50 ms of overhead compared to the same call made by the client directly to the upstream, measured over 100 calls of a fast in-process tool.
- **SC-004**: With two MCP clients (e.g., Claude Code and Cursor) connected at the same time, both successfully discover and call tools without interference, for a 30-minute interactive session.
- **SC-005**: Disabling a tool causes it to disappear from any client's next tool-list response and to reject any in-flight call attempt with a tool-disabled error.
- **SC-006**: Audit and invocation logs older than their configured retention period are removed by the periodic cleanup, while newer entries are retained, and the cleanup does not block concurrent API calls.
- **SC-007**: Every Acceptance Scenario in this document is covered by at least one test marked with `acceptance(spec="001-mcp-gateway", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-008**: The full `make verify` suite (lint + unit + integration + contract + acceptance audit) passes locally and in CI; `make verify-all` (adding e2e) passes locally on macOS and in CI on Linux.
- **SC-009**: A user on a clean machine (macOS, Windows, or Linux, with no Python installation) can install coffer from a single distributable and reach the daemon "ready" state without manual setup steps beyond clicking through the installer.
- **SC-010**: No upstream-server credential value ever appears in any database table, log file, audit entry, or invocation record — verified by an automated scan of those artifacts after a representative session.

## Assumptions

- The single user runs coffer on their own machine. There is no multi-tenant or remote-access requirement.
- The MCP client (Claude Code, Claude Desktop, Cursor, etc.) supports either an `stdio` MCP server configuration or an `http`/`sse` MCP server configuration; coffer ships both entry points.
- Upstream MCP servers behave according to the public MCP protocol specification. Misbehaving upstreams are handled as faults, not modelled as features.
- The OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service / KWallet) is available and unlocked at coffer startup, or the user is shown a clear message when it isn't.
- This spec ships with one resource kind (`mcp_server`). The Resource framework is designed so additional kinds can be added by later specs without re-modelling existing data.
- Concurrent MCP client load is small (low single digits); coffer is not a fleet-scale gateway.
- macOS distribution does not include paid Apple notarization in this spec; users on macOS may need to clear quarantine on first launch.
