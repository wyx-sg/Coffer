# MCP Gateway

## Purpose

The MCP gateway lets a developer register upstream MCP servers (filesystem, GitHub, Postgres, …) once in
Coffer and point every MCP client — Claude Code, Codex, any client that speaks stdio or HTTP MCP — at one
Coffer endpoint instead of editing each client's config. Coffer aggregates the upstreams' tools, resources and
prompts behind one namespaced surface, lets the user curate what that surface exposes (some tools are
dangerous, some redundant, some unwanted right now), keeps the agent able to choose well when the aggregated
catalogue grows past what a model can reason over, and records which capability was called, when, for how
long and with what outcome — never what was said. `mcp_server` was Coffer's first resource kind.

This spec owns the gateway, capability curation, the invocation record and the `coffer mcp test` command and the shim
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
  `coffer__search_tools`, which MUST always be advertised in
  `tools/list`. A call to any other `coffer__` name MUST be
  answered as an unknown tool.
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
and the Add and Edit dialogs offer no title field.
The name MUST be at most 24 characters and MUST NOT be `coffer` (the name of Coffer's own gateway), in addition to
the existing name pattern and the ban on `__`, wherever the framework validates it — registration here and a server arriving from another machine alike.

- Registering a server whose upstream is unreachable MUST still succeed (the config is saved); discovery and
  health report the failure, the server is marked unhealthy until reachable, and there MUST be no silent
  retry storm.
- Registering a server whose secret is missing MUST fail with a message naming the missing secret and
  pointing the user at the secret setup path, persisting no partial state. A secret whose new value is
  waiting for approval is not missing: the server is registered citing it, and its value reaches the server
  only once the change is approved.
- Registering a server with a name that already exists within the kind MUST be rejected with a clear error;
  a partial write is impossible.
- Registering, listing, viewing, editing, enabling, disabling, scoping and deleting a server MUST be done
  on the MCP servers page, through the resource routes and with the `coffer mcp` commands that call
  them (`add`, `list`, `show`, `update`, `enable`, `disable`, `reach`, `delete`, `status`, `tools`,
  `tool enable|disable`, `exposure`, `calls`, `server-log`). `coffer mcp test <server>` MUST re-query
  the server's capabilities and then report its health, so one command both refreshes what Coffer
  knows of the server and says whether it answers.
- `coffer mcp test` MUST exit with code 3 and name the condition on stderr when no daemon is reachable
  and one cannot be started (a missing daemon is started on demand, and only a failed or timed-out start
  exits 3). `coffer log mcp` MUST support machine-readable `--json` output.
  The same exit covers a daemon that stops answering after the command has connected to it: the lost
  connection is reported once, as a message naming the condition, never as a traceback.

#### Scenario: register a stdio MCP server
- **GIVEN** the coffer daemon is running and no MCP servers are registered,
- **WHEN** the user registers a stdio MCP server with a unique name, command, and arguments,
- **THEN** the server is persisted, its capabilities are discovered, and listing servers shows it as healthy.

#### Scenario: coffer mcp test exits 3 when no daemon is reachable
- **GIVEN** the daemon is not running and cannot be started (the spawn fails or the daemon does not come up within the boot timeout),
- **WHEN** `coffer mcp test <server>` is invoked,
- **THEN** the process exits with code 3 and stderr names the daemon-unreachable condition.

#### Scenario: coffer log mcp --json prints a parseable document
- **GIVEN** `coffer log mcp` supports `--json`,
- **WHEN** it is invoked with `--json`,
- **THEN** stdout is a parseable JSON document with the stable top-level key `invocations` and no human-readable framing.

#### Scenario: a daemon lost mid-command exits 3
- **GIVEN** a `coffer mcp test` whose client was built against a daemon that has since stopped answering,
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
- **THEN** the command reports the server's health, and `GET /api/v1/resources/mcp_server/{uid}/capabilities` then lists the new tool
- **AND** for a server whose upstream is unreachable, the command exits non-zero and names the failure

#### Scenario: an MCP server is shown by its name
- **GIVEN** the daemon is running
- **WHEN** the user registers a server named `fs` with a stdio command and the description "Local files" through the Add dialog (`POST /api/v1/resources/mcp_server`) and then lists servers
- **THEN** the list shows it as `fs` with that description, and reading it back carries a `null` title
- **AND** a title submitted for it through the kind-agnostic update route is refused as a validation error

Deleting a server MUST leave no upstream process or connection for it in any session, the process-wide one
included: a spawn already under way when the delete begins, one a listing or call starts while the delete
runs, and one in a session opened during the delete are each refused or closed rather than kept, and an
evicted start is neither retried nor counted as a failure of that name. Ending a session MUST close any spawn
of that session still under way.

#### Scenario: a listing during a delete does not revive the deleted server
- **GIVEN** a stdio server `fs` with a live child in a session, and a delete whose eviction of another session's child is still under way
- **WHEN** that session, or a session opened at that moment, lists or calls `fs` before the delete removes the registration
- **THEN** that spawn is refused or its child is closed, and once the delete returns no child of `fs` is running, checked by pid

#### Scenario: ending a session closes a spawn still in flight
- **GIVEN** a session whose spawn of `fs` has started its child but has not finished starting
- **WHEN** the session ends and the spawn then finishes
- **THEN** the child is closed, the call fails as unavailable, and the ended session starts nothing more

### Requirement: Support stdio and HTTP upstreams
The system MUST support both stdio and HTTP MCP transports for upstream servers. An HTTP upstream MAY cite a
secret reference for its authorization header, and the secret MUST NOT leak into any log or stored
field. A secret header — on an HTTP server or a custom-tool group — MUST store only the credential
(the key a provider hands out), and its slot MAY name an auth scheme, `Bearer` or `Token`
(`auth_schemes`, keyed by header, allowed only on a header that cites a secret), which the request
puts in front of the credential: `Authorization: Bearer <key>`. A slot without a scheme MUST send the
stored value as it is. A header value that arrives as `Bearer <key>` or `Token <key>` — adopted from
an agent's own MCP entry, moved by the plaintext import, or pasted into a form — MUST be stored as
`<key>` with the scheme set on its slot.

#### Scenario: register an HTTP MCP server
- **GIVEN** the coffer daemon is running,
- **WHEN** the user registers an HTTP MCP server with a URL and (optionally) a secret reference for an authorization header,
- **THEN** the server is persisted and its capabilities are discovered without leaking the secret into any log or stored field.

#### Scenario: a secret header is sent behind its scheme
- **GIVEN** a server whose `Authorization` header cites a secret holding `<key>`, with the scheme `Bearer`, and an `X-Api-Key` header citing a secret with no scheme
- **WHEN** a request is made to it
- **THEN** it carries `Authorization: Bearer <key>` and `X-Api-Key` with the stored value unchanged
- **AND** a scheme on a header that cites no secret, or a scheme other than `Bearer` or `Token`, is refused when the config is saved

#### Scenario: an adopted Bearer header stores the key alone
- **GIVEN** an agent's own MCP entry whose `Authorization` header reads `Bearer <key>`
- **WHEN** it is adopted into Coffer with that header mapped to a secret
- **THEN** the secret holds `<key>`, the server's slot carries the scheme `Bearer`, and the value appears nowhere in the config

#### Scenario: HTTP-transport MCP server round trip
- **GIVEN** an HTTP MCP server is running and registered with coffer,
- **WHEN** a shim client lists tools and calls one through coffer's aggregated endpoint,
- **THEN** both requests succeed end-to-end, returning valid MCP responses over the HTTP transport.

### Requirement: Toggle individual capabilities
Users MUST be able to enable or disable individual tools, resources, and prompts on a per-server basis.
Disabling a tool MUST make it disappear from any client's next tool-list response and MUST make any call
attempt on it fail with a tool-disabled error (JSON-RPC code -32000, TOOL_DISABLED).

The capabilities MUST be read with `GET /api/v1/resources/mcp_server/{uid}/capabilities` and toggled with
`POST /api/v1/resources/mcp_server/{uid}/capabilities/{capability_type}/enable` or `.../disable` (the
server page's Tools tab), where `capability_type` is `tool`, `prompt` or `resource` and the body names the
capabilities by key. A key that names no capability the server offers MUST be refused with nothing
changed. `coffer mcp tool enable` and `coffer mcp tool disable` call the same routes.

#### Scenario: disable an individual capability
- **GIVEN** a registered MCP server exposes several tools,
- **WHEN** the user disables one tool,
- **THEN** subsequent tool-list requests from any client omit it, and an attempt to call it returns a tool-disabled error.

#### Scenario: disabled capability rejected through the shim
- **GIVEN** a registered MCP server with two tools, where one has been disabled via the REST API,
- **WHEN** a shim client calls `tools/list` and then `tools/call` on the disabled tool,
- **THEN** `tools/list` omits the disabled tool while listing the enabled tool, and `tools/call` returns a JSON-RPC error with code -32000 (TOOL_DISABLED) rather than a successful result.

#### Scenario: capabilities are toggled by typed ref over REST
- **GIVEN** a registered MCP server exposing a tool and a prompt
- **WHEN** the tool and the prompt are each disabled through `.../capabilities/tool/disable` and `.../capabilities/prompt/disable`, then the capabilities are read
- **THEN** both capabilities are disabled, with the disabled ones marked disabled
- **AND** an enable request naming a tool the server does not offer is refused and changes nothing

#### Scenario: switching the last disabled tool back on holds beside a pin
- **GIVEN** a server with tool `a` pinned to `listed` and tool `b` switched off
- **WHEN** `b` is switched back on, and in a second server the pin on `a` is set back to `auto` while `b` stays off
- **THEN** each change reads back after a restart — `b` enabled with `a` still pinned, and no pin left with `b` still off

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
are never quoted. The attention item's reason MUST name no command.

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

#### Scenario: a server's status carries the hand-off its page offers
- **GIVEN** a server whose status read carries a `handoff`, and one whose status carries none
- **WHEN** `GET /api/v1/resources/mcp_server/{uid}/status` is read for each
- **THEN** the first carries the prompt and the Copy prompt button of the server's page offers exactly that text, and the second carries a `null` `handoff` and the page offers none

### Requirement: Gate server exposure by scope per session
The system MUST filter `mcp_server` exposure by its framework-level `scope`
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)) — one allow-list,
`agents`, `null` meaning unrestricted, otherwise never empty — at the gateway's per-session choke point. The value, its validation
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
- The handshake happens once per session: a second `initialize` on a session that already completed one MUST
  be refused with JSON-RPC `-32600` and change nothing — not the identity, the client's capabilities or the
  cwd. A new session may report any identity, as before.
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

#### Scenario: a second initialize on a session changes nothing
- **GIVEN** a server scoped to agent `A`, and a session whose handshake reported agent `B` and whose call to that server was refused
- **WHEN** the same session sends `initialize` again reporting `A`
- **THEN** that `initialize` is answered `-32600`, the next call is still refused as out of scope with no upstream request, and a new session reporting `A` may call the server

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
appear on the server's Tools tab and in the capability list
(`GET /api/v1/resources/mcp_server/{uid}/capabilities`), each carrying the length and a
note that some clients drop tool names longer than 60 characters. The capability list
MUST carry the length on every tool row. Flagging MUST NOT disable, rename or hide the tool.

#### Scenario: a tool with an over-long client-visible name is flagged
- **GIVEN** a registered server whose upstream exposes one tool whose `mcp__coffer__<server>__<tool>` name is 70 characters long and one whose name is 40 characters long
- **WHEN** the user opens the server's Tools tab and reads the capability list over REST
- **THEN** the long tool is flagged on both surfaces with its length and a note that some clients drop names above 60 characters, and the short one is not flagged
- **AND** both tools stay enabled and are still listed to clients under their usual names

### Requirement: Choose how each tool is exposed
A person MUST be able to set, per tool of a server, how it is exposed to agents: `auto` (the default) leaves the decision to the tool-listing budget, so the most-used tools stay in `tools/list` and the rest are reached through `coffer__search_tools`; `listed` pins the tool into the list; `search` leaves it to `coffer__search_tools` only. The setting is the person's, kept per (server, tool) in the server's preference document in the vault, and survives a restart and switching the tool off and on; `auto` clears it. It changes only how a tool is listed, never whether it can be called. `PATCH /api/v1/resources/mcp_server/{uid}/tools/{tool}/exposure` sets one tool and `PATCH .../tools/exposure` sets several in one call (`{tools, mode}`); an unknown tool or a set containing one is refused with 404 and nothing changes, and a mode other than the three with 422. The server's tiering read reports each tool's setting, whether it is effectively listed or behind search, and why (`pinned`, `search_only`, `within_budget`, `top_by_use`, `low_use`). Each change is audited as `tool_exposure_changed`. A custom-tool group ("Serve an HTTP API as a group of custom tools") is a server like any other here: its tools take an exposure through the same routes, kept in the group's preference document and audited the same way, and the gateway honours it in `tools/list` and `coffer__search_tools` as for any upstream tool. A group's tools are its own config, so a group's tool takes an exposure, and the tiering read reports it, before any agent has listed the group; a name that is not one of the group's tools is refused with 404.

The server page's Tools tab MUST list every tool, not only a first page: the rows render whole (past 100, the first 100 render and the rest are added 100 at a time as the end of the list scrolls into view, with no button), and its search runs over all of them, matching tool names only. Each tool row carries its exposure as a choice that reads, for example, "Auto · Listed" or "Auto · Behind search". The Resources and Prompts tabs MUST be listed in full the same way, with a search over every item's name. A custom-tool group's Tools tab carries the same exposure choice on each tool that is on (web-ui "Manage custom tool groups on their own page").

#### Scenario: a server's Tools tab lists every tool
- **GIVEN** a server with 78 tools
- **WHEN** the user opens its Tools tab
- **THEN** all 78 rows are shown, with no count line and no Show more button
- **AND** searching for one tool's name finds it among all 78

#### Scenario: a server's resources and prompts are listed in full
- **GIVEN** a server with 120 prompts
- **WHEN** the user opens its Prompts tab and scrolls to the end of the list
- **THEN** the first 100 are listed, then all 120 once the end is reached, and searching for the last one's name finds it

#### Scenario: a tool's exposure is chosen by the person
- **GIVEN** a budget of two and a server with tools `a`, `b` and `c`, where `b` is the most used
- **WHEN** the person sets `c` to `listed`
- **THEN** the tiering read reports `c` as mode `listed`, effectively listed because it is pinned, `b` as `auto` and listed, and `a` as `auto` and behind search for low use
- **AND** the Tools tab shows each tool's choice, such as "Auto · Listed" or "Auto · Behind search"

#### Scenario: a custom tool's exposure is honoured like any server's tool
- **GIVEN** a custom-tool group `billing` with the tools `list_invoices`, `get_invoice` and `void_invoice`, which no agent has listed yet
- **WHEN** the person sets `list_invoices` to `search`, and an agent lists the gateway's tools and searches for "list every invoice"
- **THEN** `billing__list_invoices` is not listed while the group's other two are, `coffer__search_tools` finds it first, and a call on it still reaches the API
- **AND** with a budget of one and `void_invoice` set to `listed`, `void_invoice` is the group's only listed tool, and the tiering read reports each tool's mode and effective state

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
An HTTP upstream's connection MUST NOT carry its secret headers to another
origin: it follows a redirect only within the endpoint's own origin
([secret](../secret/spec.md) "Send a secret only to the origin it was approved
for").

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
end. A group MUST carry one or more environments ("Keep a custom-tool group's
environments in the group"), each with a base URL (`http` or `https`) and
optional **header rows**, a per-request timeout between 1 and 300 seconds (30 by
default) and its tools. A header row is a name and a value: plain text, or a
stored secret that holds the credential alone, sent behind the row's scheme when
it has one (see "Support stdio and HTTP upstreams"), so a bearer token is stored
as `<token>` with the scheme `Bearer`. A row carries a value or a secret, never
both, and a header name appears once in an environment. Each tool MUST carry a
name unique in the group, a description, a method (GET, POST, PUT, PATCH or
DELETE), a path template relative to the base URL whose `{argument}` holes may
sit in the path or the query, optional headers, an optional JSON body template,
the JSON Schema of its arguments, an on/off switch and a changes-data flag. Like
every server, the group's name is fixed and prefixes each tool an agent sees as
`<group>__<tool>` ("Namespace every upstream capability"). A tool whose template
names an argument its schema does not declare, whose path is not a path
(`//host`, a URL with a scheme), or whose schema is not a well-formed JSON
Schema ("Validate a custom tool's arguments before any request") MUST be refused
when it is saved, with nothing persisted.

#### Scenario: a custom tool reaches the agent under its group's prefix
- **GIVEN** a group `billing` with a `list_invoices` tool, reaching every agent
- **WHEN** an agent lists the gateway's tools
- **THEN** it is offered `billing__list_invoices` with the tool's description and argument schema

#### Scenario: a group's headers are rows whose value is plain or a secret
- **GIVEN** a stored secret `billing-token`
- **WHEN** a group is created with the headers `X-Team` = `billing` and `Authorization` bound to `billing-token`, then its headers are replaced with `X-Team` = `ops`
- **THEN** the group first lists both rows, the secret one naming `billing-token` and its state and never its value, and a row giving both a value and a secret is refused
- **AND** after the replacement it lists one plain row and no secret

#### Scenario: a tool naming an undeclared argument is refused
- **GIVEN** a group `billing`
- **WHEN** a tool with path `/invoices/{id}` and an argument schema that declares no `id` is added
- **THEN** the addition is refused as a validation error naming `id`, and the group is unchanged

### Requirement: Describe a custom-tool group
A custom-tool group MUST carry an optional **description** saying what its API is
for, set when the group is created (by hand or from an OpenAPI import) and
changed later. Reading an OpenAPI document MUST return its `info.description`
(trimmed, at most 2000 characters) so the import can start the new group with
it. `coffer__search_tools` MUST score each of a group's tools against the
group's description as well as the tool's own, and return the description
beside each of the group's tools it finds as `group_description`. A tool's entry
in `tools/list` MUST keep the tool's own description, with nothing added.

#### Scenario: a group's description finds its tools in a search
- **GIVEN** a group `acme` described as weather forecasts for warehouse sites, with one tool `list_items` described only as "List items"
- **WHEN** an agent calls `coffer__search_tools` with the query "weather forecast"
- **THEN** `acme__list_items` is the first result, carrying the group's description as `group_description`
- **AND** `tools/list` still offers `acme__list_items` with the description "List items"

#### Scenario: an OpenAPI document's description is read for the new group
- **GIVEN** an OpenAPI document whose `info.description` is set, and one without it
- **WHEN** each is read for import
- **THEN** the first returns that description, trimmed, and the second returns none

### Requirement: Make a custom tool's request in the gateway
On `tools/call` for a custom tool the gateway MUST resolve the call's
environment ("Choose a custom tool's environment on every call"), validate the
arguments ("Validate a custom tool's arguments before any request"), and render
the request from the arguments and that environment — the environment's base
URL; each path hole percent-encoded so a value cannot change the path, the query
or the host; each `{env:NAME}` filled with the environment's variable; a query
pair whose hole's argument is absent dropped; the body template filled with JSON
values, or, with no template, the unused arguments sent as a JSON object for
POST, PUT and PATCH — add the environment's secret headers with each secret's
value last, send it with the environment's timeout (the group's when it sets
none) without following redirects, read at most 1 MiB of the response, and
return one text result that starts with the HTTP status line. A status of 400 or
more MUST be returned as an in-band tool error; a redirect MUST be returned, not
followed; a timeout MUST be recorded as `timeout`. The secret's value MUST NOT
appear in the result, the tool's description or schema, or any log, invocation
or audit record: an occurrence in the response is masked as `***`. Every call
MUST be recorded like any other tool call ("Record invocations without
content"), naming its environment.

#### Scenario: a custom tool call sends the rendered request with the secret
- **GIVEN** a group with base URL `https://api.example/v2`, an `Authorization` header bound to an approved secret holding `<token>` with the scheme `Bearer`, and a tool `GET /invoices/{id}?status={status}`
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
keep its switch and changes-data flag, and MUST keep every environment of the
group with its base URL, headers, secret bindings and variables unchanged. A
tool added by hand is never removed by a re-import.

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
- **GIVEN** a group imported with three operations, one of them switched off, and a document that now drops one of them and adds a new one
- **WHEN** re-import is previewed and then applied with the new operation chosen
- **THEN** the preview names one operation to add and one tool to remove and nothing changed before applying
- **AND** after applying, the dropped tool is gone, the new tool is on, and the kept tools keep their switch

#### Scenario: re-import keeps the group's environments
- **GIVEN** an imported group with environments `test` and `live`, each with its own base URL, secret header and variable
- **WHEN** it is re-imported from a document whose `servers` name another URL
- **THEN** both environments keep their base URL, headers, secret bindings and variables, and no approval is asked again

### Requirement: Wait for approval before a custom tool sends its secret
Binding a stored secret to one of an environment's headers MUST be treated as a
new destination whose target is that environment's base URL and whose slot names
the environment and the header ([secret](../secret/spec.md) "Hold a secret for
a new destination until a person approves it"): no call and no Test in that
environment carries the secret until a person approves it for that base URL, a
call before then fails with `SECRET_BINDING_PENDING` naming the approvals and
the command that approves them, and changing the environment's base URL or the
header asks again for that environment only, and so does moving the same secret
to another header ("Fix a secret's placement by its destination's definition").
Each environment is evaluated on its own: a missing secret, a pending approval or
a refusal in one environment MUST NOT stop calls in another, and only the chosen
environment's secrets are resolved for a call. A switched-off environment asks
for no approval. A group's request MUST NOT follow a redirect, and no argument
hole in a tool's path, query, headers or body MAY be filled from a stored
secret. The group MUST report each secret header's state as `present`,
`missing`, `rejected` (a person refused its binding) or `pending_approval`, per
environment and, as a whole, the worst of them in that order (`none` with no
secret header), with the ids of the approvals it waits on and of the refused
ones, and the names of the secrets concerned. A refused binding is not reported
as waiting: nothing asks the person until someone asks again.

#### Scenario: binding a stored secret to a group waits for approval
- **GIVEN** a stored secret `billing-token`
- **WHEN** a group is created with its `Authorization` header bound to `billing-token`, and an agent calls one of its tools
- **THEN** the group reports `pending_approval` naming one approval for its base URL and the secret `billing-token`, and the call fails with `SECRET_BINDING_PENDING` having sent nothing
- **AND** once the approval is applied the next call carries the secret

#### Scenario: a refused binding shows as refused, not waiting
- **GIVEN** a group whose secret binding waits for approval
- **WHEN** a person rejects the approval, and later asks again for it
- **THEN** the group reports `rejected` with the refused approval's id and the secret's name and no pending approval, and its health is `attention` for `approval_rejected`
- **AND** after asking again it reports `pending_approval` naming the new approval

#### Scenario: moving a group's base URL asks again
- **GIVEN** a group whose secret is approved for its base URL
- **WHEN** its base URL is changed
- **THEN** the group reports `pending_approval` for the new base URL and calls carry no secret until it is approved

#### Scenario: an approval in one environment does not open another
- **GIVEN** a group with environments `test` and `live`, each binding its own secret, with `test` approved and `live` pending
- **WHEN** a tool is called in `test` and in `live`, and then `test`'s base URL is changed
- **THEN** the `test` call carries its secret and the `live` call fails with `SECRET_BINDING_PENDING` naming only `live`'s approval
- **AND** after the change `test` waits for a new approval while `live`'s pending approval is unchanged

### Requirement: Manage custom tools through REST and the Custom tools page
Custom-tool groups MUST be managed through `/api/v1/custom-tools` — list
(failing groups first, each with its health, its secret's state, its calls and
failures in the last 24 hours, its environments and its tools), create (with
tools and environments), read, change, delete, add / change / remove one tool,
add / change / remove one environment, test a draft tool once without saving it,
test a saved tool, read an OpenAPI document, and preview and apply a re-import —
on the Custom tools page, which calls those routes, and with the `coffer
custom-tool` commands ("Manage custom tools from the command line"). Every test
names its environment and returns the actual target it reached (method and URL
with secret-looking query values redacted). The page MUST show each
environment's base URL, its secret state and whether it is on, and its test
panel MUST offer an environment picker. A change that waits for a secret
approval MUST report it as a pending approval on the Secrets page
([secret](../secret/spec.md) "Hold a secret for a new destination until a
person approves it"). A group's health MUST be `off` while disabled, `failing`
when its last call in 24 hours failed, `attention` while a secret of an enabled
environment is missing, waits for approval or was refused, `healthy` after a successful last
call, and `idle` with no call in 24 hours.

#### Scenario: create a custom-tool group and add a tool
- **GIVEN** the daemon is running and a stored secret `deploy-token` whose binding is approved
- **WHEN** the user creates a group `deploy` with `POST /api/v1/custom-tools` (base URL `https://deploy.example/v1`, an `Authorization` header with the scheme `Bearer` and the secret `deploy-token`), then adds a `rollback` tool with `POST /api/v1/custom-tools/deploy/tools` (method `POST`, path `/services/{service}/rollback`, a required string argument `service`)
- **THEN** reading the group lists the `rollback` tool with the changes-data flag on
- **AND** `POST /api/v1/custom-tools/deploy/test` for that tool with the argument `service=web` returns the upstream's status line

#### Scenario: a test runs a draft tool once without saving it
- **GIVEN** a group with an approved secret
- **WHEN** a draft tool that is not saved is tested with sample arguments
- **THEN** the response's status, duration and body are returned, the group's tools are unchanged, and nothing is added to the invocation log

#### Scenario: the group list puts a failing group first
- **GIVEN** one group whose last call failed, one whose last call succeeded and one disabled
- **WHEN** the groups are listed
- **THEN** the failing group comes first with health `failing`, then the healthy one, and the disabled one last with health `off`

#### Scenario: a saved tool is tested in a chosen environment and reports its target
- **GIVEN** a group with environments `test` and `live` and a saved tool `GET /status`
- **WHEN** `POST /api/v1/custom-tools/{name}/tools/status/test` is sent with `environment` = `live`
- **THEN** only `live`'s base URL receives the request, and the answer names `live` and the URL it reached

### Requirement: Hand a failing custom tool group to an agent
A group whose last call failed, and a test of a request that could not connect
or timed out (for a saved or an unsaved group), MUST carry a hand-off prompt
that hands the network problem to an agent — the group, the method and URL with
credentials and secret-looking query values redacted, the error and the machine;
no header value — and no other result does. The prompt is written by the daemon,
so a surface passes it on as served and never assembles one.

#### Scenario: a failing group carries a hand-off prompt and a healthy one does not
- **GIVEN** one group whose last call failed, one whose last call succeeded and one disabled
- **WHEN** the groups are listed
- **THEN** only the failing group carries a hand-off prompt, and it names the group
- **AND** a disabled group carries none

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
The daemon MUST describe Coffer's own `coffer` MCP server read-only, so the MCP servers page can show it beside the servers the person added: its name, its transport (Streamable HTTP), the endpoint URL agents connect to on the bound port, that it is healthy while the daemon answers, that it reaches every connected agent (with the uids of the agents connected now), its tools from the gateway's built-in tool list as agents see them (only the tools of switched-on features, each with its `coffer__` name and its input schema), and the last 24 hours of its calls in the shape a registered server's page reads. It is not a registered resource: it has no row, and nothing about it can be edited or removed.

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
A server's status read MUST also list what its command and settings need from this machine, worked out from the config alone and without starting the server: for a stdio server its **launcher** (the command's executable — `npx`, `uvx`, `docker`, `bunx`, `node`, `python` and the like) as a CLI that is `found`, with its version when it prints one, or `not_found`; and every **secret** its environment or headers cite — through a stored secret bound to the variable or header, or a `coffer://secret/<name>` written in a plain value — as `set`, `missing` on this machine, `waiting_approval`, or `refused` once a person refused its binding (a refusal is not a wait), naming the variable or header and the secret. A launcher's version is read once and kept until the daemon restarts; one that is not found is looked up again on every read. An HTTP server has no launcher, and no secret's value is read.

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
reaches the server only through its environment; a value Coffer injected into that environment is masked in
the file before it is written, whoever wrote the line (secret "Hold plaintext only in memory at the moment
of use").

#### Scenario: a server's log tells Coffer's lines from the server's
- **GIVEN** a stdio server whose log file holds a start line, a line the server printed and a launcher-not-found line, and an older rolled-aside file
- **WHEN** its log is read, and read again with a limit of two
- **THEN** the lines come newest first across both files, Coffer's marked `coffer` with their time and the server's marked `stderr`
- **AND** the limited read holds two lines and says more exist

### Requirement: Let an agent ask the owner a question during a Coffer turn
The gateway MUST offer the built-in tool `coffer__ask` to an MCP session whose
requests carry the `X-Coffer-Turn` token of a turn Coffer is running, and only to
such a session. Its input MUST take an optional markdown `context` and one to four
questions, each with a short `header`, the `question`, two to four options (a
`label` and an optional `description`) and `multi_select`. A call MUST raise the
question on that turn's conversation (spec chat "Pause a turn on a question for
the owner") and return only when every question is answered — with the chosen
labels and any free-text answer per question — or when the question is cancelled
or 24 hours pass, with a result saying no answer came. The shim MUST forward the
agent process's `COFFER_TURN_TOKEN` as `X-Coffer-Turn`, and the Codex
configuration Coffer writes for its `coffer` server MUST pass that variable
through and allow a tool call to run for 24 hours.

#### Scenario: an agent in a Coffer turn sees and calls coffer__ask
- **GIVEN** a turn Coffer runs, whose agent process has `COFFER_TURN_TOKEN` set
- **WHEN** the agent lists Coffer's tools and calls `coffer__ask` with one question and the options Yes and No
- **THEN** `coffer__ask` is in the list, and the call returns "Yes" once the owner answers Yes

#### Scenario: coffer__ask is not offered outside a Coffer turn
- **GIVEN** an agent session started in a terminal, with no turn token
- **WHEN** it lists Coffer's tools
- **THEN** `coffer__ask` is not among them, and a direct call is answered that asking works only inside a Coffer conversation

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

### Requirement: Switch off one custom tool
A custom tool that is switched off MUST be left out of `tools/list` and of
`coffer__search_tools` results, and a call on it MUST be recorded as `denied`
and answered with TOOL_DISABLED. A tool that is on reaches exactly the agents its
group reaches: a tool has no reach of its own.

#### Scenario: a switched-off custom tool is hidden and refused
- **GIVEN** a group with two tools, one switched off
- **WHEN** an agent lists the tools and then calls the switched-off one by its name
- **THEN** only the other tool is listed, and the call is refused with TOOL_DISABLED and recorded as `denied`

#### Scenario: every tool that is on follows its group's reach
- **GIVEN** a group reaching Claude Code only, with two tools that are on
- **WHEN** Claude Code and Codex each list the gateway's tools
- **THEN** Claude Code is offered both tools and Codex neither

### Requirement: Keep a custom-tool group's environments in the group
A custom-tool group MUST keep one set of tools and one or more
**environments**, each named by the user and unique in the group, each with its
own base URL (`http` or `https`, no query or fragment), header rows (a plain
value or a stored secret behind an optional scheme, as for the group's headers
before), non-sensitive variables, an on/off switch, an optional description and
an optional timeout between 1 and 300 seconds that overrides the group's. No
environment name is reserved or special. A tool MUST NOT be copied per
environment: the tool's name, the name an agent sees (`<group>__<tool>`) and
its switch are the same in every environment. A variable is plain text used as
`{env:NAME}` in a tool's path, query, headers or body template and MUST NOT be
used in a base URL; a variable value or a plain header value that looks like a
credential MUST be refused, and a tool naming a variable that an enabled
environment of its group does not define MUST be refused when it is saved. A
group saved before environments existed MUST read as one environment named
`default` holding its base URL and header rows, with its secret bindings kept.
Environments MUST be managed through `/api/v1/custom-tools/{name}/environments`
(add, change, rename, switch on or off, delete; the last environment cannot be
deleted) and in the group's Environments section on the Custom tools page. Because
names are unique regardless of case, every management route finds an environment
the same way: a change, rename or delete naming it in another case acts on that
environment (a rename that changes only its case included), and a name no
environment has is `CUSTOM_TOOL_ENVIRONMENT_NOT_FOUND` with nothing changed —
never a success that changed nothing. An environment's binding key is its first
name; a name renamed away and added again gets that name with the first free
`-<n>` suffix, shortened to stay within 40 characters, found in bounded time.

#### Scenario: one group serves the same tools in several environments
- **GIVEN** a group `billing` with the tool `list_invoices` and the environments `sandbox` (`https://sandbox.billing.example`) and `prod` (`https://billing.example`)
- **WHEN** an agent lists the gateway's tools
- **THEN** it is offered `billing__list_invoices` once, and no tool is named after an environment

#### Scenario: a group from before environments reads as one environment
- **GIVEN** a stored group with a top-level base URL and an `Authorization` header bound to an approved secret
- **WHEN** it is read and called
- **THEN** it lists one environment `default` with that base URL and header, and the call carries the secret with no new approval

#### Scenario: a variable is substituted per environment and refused in a base URL
- **GIVEN** environments `eu` and `us` defining the variable `region` as `eu-1` and `us-1`, and a tool `GET /v1/{env:region}/items`
- **WHEN** the tool is called once per environment
- **THEN** the requests go to `/v1/eu-1/items` on `eu`'s base URL and `/v1/us-1/items` on `us`'s
- **AND** a base URL holding `{env:region}`, and a tool naming a variable `us` lacks, are each refused when saved

#### Scenario: an environment is added, renamed, switched off and deleted
- **GIVEN** a group with the environment `default`
- **WHEN** an environment `staging` is added, renamed `uat`, switched off, and deleted, and then deleting `default` is attempted
- **THEN** each change is saved and audited, and deleting the last environment is refused with nothing changed

#### Scenario: an environment named in another case is changed or deleted
- **GIVEN** a group with the environments `Test` and `live`
- **WHEN** `test` is given a description, `TEST` is renamed `test`, and `TeSt` is deleted
- **THEN** each change lands on that environment and is read back, the advertised `coffer_environment` choices follow, and a name no environment has is answered 404 with nothing changed

#### Scenario: a 40-character environment name renamed and added again
- **GIVEN** an environment whose name is 40 characters long
- **WHEN** it is renamed and an environment with the original name is added, three times over
- **THEN** every add succeeds at once and every environment has its own binding key of at most 40 characters

### Requirement: Choose a custom tool's environment on every call
Every request of a custom tool — an MCP call, a CLI test and a test on the
Custom tools page — MUST name the environment it is made in; nothing keeps a
current or default environment that one caller's choice could change for
another. The gateway MUST advertise each custom tool with the reserved argument
`coffer_environment`, an enumeration of the group's enabled environments that
is required when the group has more than one enabled environment; a group with
exactly one enabled environment uses it when the argument is absent. The
argument MUST be removed before the request is rendered, so it never reaches the
upstream path, query, headers or body, and a tool's own argument schema MUST NOT
declare it. A caller can choose only a registered, enabled environment: an
unknown name is refused with `CUSTOM_TOOL_ENVIRONMENT_UNKNOWN`, a switched-off
one with `CUSTOM_TOOL_ENVIRONMENT_DISABLED`, and a missing choice with
`CUSTOM_TOOL_ENVIRONMENT_REQUIRED`, each before any request; no argument can
change an environment's base URL, headers or credentials. Concurrent calls of
the same tool in different environments MUST each use only their own
environment's URL, headers, variables and secrets. Region, tenant or customer
ids stay ordinary arguments of the tool.

#### Scenario: concurrent calls in two environments do not mix
- **GIVEN** a group with environments `test` and `live`, each with its own base URL, variable and approved bearer secret, and a tool with a `region` argument
- **WHEN** an agent makes fifty calls of the tool at once, alternating `coffer_environment` between `test` and `live`
- **THEN** every `test` call reaches `test`'s base URL with `test`'s variable and secret and every `live` call reaches `live`'s, with no request carrying the other environment's URL, header or secret
- **AND** no upstream request carries `coffer_environment` in its path, query or body, and `region` is sent as the tool declares it

#### Scenario: an environment that is not registered or is off is refused before any request
- **GIVEN** a group with an enabled environment `test`, a switched-off environment `live` and a second enabled environment `uat`
- **WHEN** a tool is called with `coffer_environment` set to `prod`, then `live`, then with no environment
- **THEN** the calls are refused with `CUSTOM_TOOL_ENVIRONMENT_UNKNOWN`, `CUSTOM_TOOL_ENVIRONMENT_DISABLED` and `CUSTOM_TOOL_ENVIRONMENT_REQUIRED`, and the upstream receives no request

#### Scenario: the advertised schema offers only enabled environments
- **GIVEN** a group with enabled environments `test` and `uat` and a switched-off `live`
- **WHEN** an agent lists the gateway's tools
- **THEN** each of the group's tools carries `coffer_environment` as a required enumeration of `test` and `uat`
- **AND** a tool whose own schema declares `coffer_environment` is refused when saved

### Requirement: Validate a custom tool's arguments before any request
A custom tool's argument schema MUST be checked as a JSON Schema when the tool is
saved — its keywords well formed, its patterns valid regular expressions, its
local `$ref`s resolvable — and a malformed schema refused with nothing saved.
Every request of a custom tool MUST validate its arguments against that schema
before anything is sent, covering at least `type` (including OpenAPI 3.0
`nullable`), `enum` and `const`, numeric bounds and `multipleOf`, string length
and `pattern`, array `items`, `prefixItems`, bounds, `uniqueItems` and
`contains`, object `properties`, `required`, `additionalProperties`,
`patternProperties`, property count and `propertyNames`, `allOf`, `anyOf`,
`oneOf`, `not`, `if`/`then`/`else`, `dependentRequired` and local `$ref`. MCP
calls, CLI tests and the page's draft and saved-tool tests MUST use the same
validator. Invalid arguments MUST be refused with `CUSTOM_TOOL_ARGUMENTS_INVALID`
(422 on REST, an in-band tool error on MCP) listing every failure with its
argument path, the keyword it broke and a message, and MUST NOT cause an
upstream request; a missing secret, a pending or refused approval, and an
unknown or switched-off environment are likewise refused before any request.

#### Scenario: invalid arguments are refused field by field with no upstream request
- **GIVEN** a tool whose schema requires `amount` as an integer between 1 and 100, `currency` in `[EUR, USD]`, `tags` as at most 3 unique strings, allows no other property, and requires exactly one of `card` or `iban`
- **WHEN** it is called through MCP, tested on the command line and tested on the page with `amount` = `0`, `currency` = `GBP`, four `tags`, an extra `note` and both `card` and `iban`
- **THEN** each answer is `CUSTOM_TOOL_ARGUMENTS_INVALID` naming `/amount` (`minimum`), `/currency` (`enum`), `/tags` (`maxItems`), `/note` (`additionalProperties`) and the `oneOf` failure
- **AND** the upstream receives no request

#### Scenario: a malformed argument schema is refused when saved
- **GIVEN** a group
- **WHEN** a tool is saved whose schema gives `minimum` as text, a `pattern` that is not a valid regular expression, or a `$ref` to a definition that does not exist
- **THEN** the save is refused as a validation error naming the schema location, and the group is unchanged

#### Scenario: a missing or unapproved secret is refused before any request
- **GIVEN** a group whose `live` environment cites a secret with no value and whose `test` environment waits for approval of its secret
- **WHEN** a tool is called in each environment
- **THEN** the `live` call answers `SECRET_MISSING` and the `test` call `SECRET_BINDING_PENDING` naming its approval and `coffer approval approve <id>`, and the upstream receives no request

### Requirement: Manage custom tools from the command line
Every custom-tool operation of the Custom tools page MUST be available as a
`coffer custom-tool` command that calls the same REST route: list, show, create,
update and delete a group; enable and disable it; set its reach; add, show,
update, enable, disable and delete a tool, including its method, path, headers,
body template, argument schema and `changes_data` (a read-only `POST` may set
`changes_data=false`); add, update, rename, enable, disable and delete an
environment and bind a secret to one of its headers; test a draft tool and a
saved tool in a chosen environment; read an OpenAPI document; and preview and
apply a re-import. A tool's definition, request template and schema MUST be
accepted from flags, a file (`--data @file`) or standard input (`--data -`).
Every command MUST offer `--json` and the exit codes of [resource-framework]
"Offer every management operation on the command line". A command whose change
leaves a secret approval pending MUST print the approval ids and the command
that approves them, and exit `9`. The commands are a client of the REST routes:
no script, local HTTP adapter, proxy or MCP wrapper takes part, and the gateway
calls the upstream API itself.

#### Scenario: a group is configured end to end from the command line
- **GIVEN** a running daemon, a stored secret `billing-test-token` and an HTTP API answering on two base URLs
- **WHEN** an agent runs, one command at a time, `coffer custom-tool group create billing --env test=https://test.billing.example`, `coffer custom-tool env add billing live --base-url https://billing.example`, `coffer custom-tool env set-header billing test Authorization --secret billing-test-token --scheme Bearer`, `coffer custom-tool tool add billing --data @search.json` (a `POST /search` with `changes_data` false), `coffer custom-tool group reach billing --agent claude-code`, and `coffer custom-tool tool test billing search --env test --args '{"q":"x"}' --json`
- **THEN** each command exits `0` except a binding that waits for approval, which prints its approval id and `coffer approval approve <id>` and exits `9`
- **AND** the group, its two environments, the tool with `changes_data` false and the reach are what the Custom tools page shows, and the test's JSON carries the upstream's status line and the environment's actual target

#### Scenario: a change made on the page is read back by the command line
- **GIVEN** a group created with `coffer custom-tool group create`
- **WHEN** a person renames one of its environments and switches a tool off on the Custom tools page, and an agent runs `coffer custom-tool group show <group> --json`
- **THEN** the JSON carries the renamed environment and the tool switched off

#### Scenario: an OpenAPI document is imported and re-imported from the command line
- **GIVEN** an OpenAPI file with three operations
- **WHEN** an agent runs `coffer custom-tool import read --file openapi.yaml --json`, creates a group from two operations with `coffer custom-tool group create --from-openapi openapi.yaml --operation <op> --operation <op>`, and later runs `coffer custom-tool reimport preview <group> --file openapi.yaml` and `coffer custom-tool reimport apply <group> --file openapi.yaml --add <op>`
- **THEN** the read lists three draft tools, the group holds two, the preview names the one to add and changes nothing, and the apply adds it keeping every environment

### Requirement: Preview a custom tool's request without sending it
The daemon MUST preview the request a custom tool would send — a saved tool with
`POST /api/v1/custom-tools/{name}/tools/{tool}/preview` and a draft with
`POST /api/v1/custom-tools/{name}/preview`, taking the same body as the matching
test — and `coffer custom-tool tool test` and `coffer custom-tool tool
test-draft` MUST offer `--dry-run`, which calls them. A preview MUST take a
test's own steps up to the request: the environment chosen by "Choose a custom
tool's environment on every call", the arguments checked by "Validate a custom
tool's arguments before any request", and the request built by the gateway's own
code ("Make a custom tool's request in the gateway"). It answers the chosen
environment, the method, the final URL, every header as it would be sent, the
rendered body, the timeout that applies and whose it is (the environment's own
or the group's), and the environment's variables. A secret header MUST carry
`***` in place of the credential (behind its scheme, `Bearer ***`), its secret's
id and name, its scheme and its state (`present`, `missing` or
`pending_approval`, read from the store's presence and the approvals, never from
the value). A preview MUST NOT read or decrypt any secret value and MUST NOT
make any HTTP request. It refuses what a call would refuse, with the same codes
and exit codes; a request that cannot be built in the chosen environment (a
`{env:NAME}` it does not define, a body template that is not JSON) is refused
with `CUSTOM_TOOL_REQUEST_INVALID` (422, exit `6`). With `--json` the command
prints the preview object as the route answers it.

#### Scenario: a dry run shows each environment's request without sending it
- **GIVEN** a group with environments `test` (the group's 30 s timeout, `region=eu-1`) and `live` (its own 7 s timeout, `region=us-1`), each with its own base URL, plain header and secret header, and a tool `POST /v1/{env:region}/search?cid={cid}` with a tool header and a body template
- **WHEN** the tool is previewed in `test` and in `live` with the same arguments
- **THEN** each answer names its environment, its own base URL with its region and the query filled, its own plain header, the tool header, the rendered body, and 30 s from the group or 7 s from the environment
- **AND** the upstream receives nothing, and no secret value is read

#### Scenario: a dry run names a secret header's secret but never its value
- **GIVEN** the same group, its secrets stored and approved
- **WHEN** the tool is previewed
- **THEN** `Authorization` reads `Bearer ***` with the secret's id, name, scheme `Bearer` and state `present`, and neither token appears anywhere in the answer

#### Scenario: a dry run refuses what a call would refuse
- **GIVEN** the same group
- **WHEN** a preview names no environment, then leaves out a required argument, then names `live` after it is switched off, then previews a draft whose path uses an `{env:NAME}` `test` does not define
- **THEN** the answers are `CUSTOM_TOOL_ENVIRONMENT_REQUIRED`, `CUSTOM_TOOL_ARGUMENTS_INVALID`, `CUSTOM_TOOL_ENVIRONMENT_DISABLED` and `CUSTOM_TOOL_REQUEST_INVALID`, each 422, and the upstream receives nothing

#### Scenario: a dry run on the command line prints the request and sends nothing
- **GIVEN** a group with environments `test` (a secret header waiting for approval) and `live`, and a saved tool `GET /status` with a plain header
- **WHEN** an agent runs `coffer custom-tool tool test <group> status --env test --dry-run --json`, the same in `live` without `--json`, the same with no `--env`, and `coffer custom-tool tool test-draft <group> --env live --dry-run` on a draft
- **THEN** the JSON names `test`, its URL and `Bearer ***` with the secret's name and `pending_approval`; the text names `live`, its URL and the plain header and says nothing was sent; the one with no environment exits `6` with `CUSTOM_TOOL_ENVIRONMENT_REQUIRED`; and the draft's URL is `live`'s
- **AND** the upstream receives nothing and no output carries the secret's value

### Requirement: Report what a custom tool's test reached
A test of a custom tool — saved, draft or of a group not saved yet — MUST
return, beside the status, URL, body and environment, the response headers that
help find the request on the API's side: `date`, `server`, `via`,
`retry-after` and the request and trace ids (`x-request-id`, `request-id`,
`x-correlation-id`, `x-trace-id`, `traceparent`, `x-b3-traceid`,
`x-amzn-requestid`, `x-amzn-trace-id`, `x-amz-request-id`, `x-amz-cf-id`,
`cf-ray`), names lower-cased, each value with the environment's secret values
masked and cut at 256 characters. Every other header — `set-cookie`,
`www-authenticate`, anything not on the list — MUST be left out. A test that got
no answer returns none. The command line prints them after the status, and the
Custom tools page shows them in the test's result. An agent's tool call is
unchanged.

#### Scenario: a test reports the request id but no cookie or credential
- **GIVEN** an environment with a secret header, and an API that answers `403` with an HTML body, `X-Request-Id`, an `X-Trace-Id` that contains the secret's value, `Set-Cookie`, `WWW-Authenticate` and an unknown header
- **WHEN** a draft tool is tested in that environment
- **THEN** the result carries `x-request-id`, `x-trace-id` with the value masked, `server` and `date`
- **AND** it carries no `set-cookie`, `www-authenticate` or unknown header, and neither the secret's value nor the cookie appears anywhere in it

### Requirement: Preview a resource or a prompt from the server page
The daemon MUST read one of a registered server's resources, and fill one of its prompts with given arguments, for the server page's row details: `POST /resources/mcp_server/{uid}/resources/read` (a `uri`) and `POST /resources/mcp_server/{uid}/prompts/get` (a `name` and its `arguments`), over the same connection the capability listings use. A text body MUST be cut at 64 KB and marked cut; a binary body MUST be described by its MIME type and size and its bytes not sent. An error the server answers with MUST come back in the body's `error`, named by its JSON-RPC code and never by the server's own text (which can echo a credential), with no contents, and MUST NOT close the connection; a server that cannot be reached is `UPSTREAM_UNAVAILABLE`. A preview is the owner looking, not an agent calling: it MUST NOT be recorded as an invocation, and it works on a row that is switched off. `coffer mcp resource read` and `coffer mcp prompt get` call the same routes.

#### Scenario: read a resource from its row
- **GIVEN** a registered server offering the text resource `file:///tmp/a.txt`
- **WHEN** its content is read through `POST /resources/mcp_server/{uid}/resources/read`
- **THEN** the answer carries the resource's text with its MIME type, not cut

#### Scenario: fill a prompt from its row
- **GIVEN** a registered server offering the prompt `summarise`
- **WHEN** it is filled through `POST /resources/mcp_server/{uid}/prompts/get` with an argument
- **THEN** the answer carries the prompt's description and its messages, each with its role

### Requirement: Answer every MCP message by the JSON-RPC rules
The `/mcp` endpoint MUST check every message before it reaches a session or an upstream, and answer by the
JSON-RPC 2.0 and MCP 2025-06-18 rules — never with an HTTP 500 or a result for a malformed message.

- **Envelope.** A body that is not JSON is HTTP 400 with JSON-RPC `-32700`. A message that is not an object,
  whose `jsonrpc` is not `"2.0"`, whose `id` is not a string or an integer, whose `method` is not a string, or
  that has neither a `method` nor a `result`/`error` is answered `-32600`; params that are not an object are
  `-32602`. The answer echoes the request's `id` only when that id is itself valid, else `null`.
- **Params.** `initialize` MUST carry `protocolVersion` (a string), `capabilities` (an object) and
  `clientInfo` with a `name` and a `version`; `tools/call` and `prompts/get` a non-empty `name` and, when
  given, object `arguments`; `resources/read` a string `uri`; a list's `cursor`, when given, is a string.
  Anything else is `-32602`.
- **Codes.** A method the gateway does not answer is `-32601`. A tool, resource or prompt that no server
  offers under that name — no `<server>__` prefix, or no such server — is `-32602`. A switched-off or
  out-of-scope capability stays `-32000` (`TOOL_DISABLED`). An upstream's own JSON-RPC error keeps its code,
  with a message of Coffer's own (an upstream's text can echo a credential), except `-32000`, which the SDK
  uses for a dropped connection; that, a timeout and anything unexpected are `-32603`.
- **Lifecycle.** Only `initialize` opens a session: any other message without `Mcp-Session-Id` is HTTP 400.
  A request on a session that has not completed `initialize` is `-32600`. The gateway speaks MCP
  `2025-06-18` and answers every `initialize` with it, whatever version was asked for. After the handshake,
  an `MCP-Protocol-Version` header naming another version is HTTP 400, on `POST` and `GET` alike; a request
  without the header is taken as the agreed version.
- **Responses and notifications.** A response the client sends (to a sampling or roots request) and every
  notification are answered with an empty 202, matched or not.

#### Scenario: a malformed message gets its JSON-RPC error
- **GIVEN** the gateway
- **WHEN** a client posts a message with no method, with `jsonrpc` `1.0`, with an array or `null` id, or an `initialize` whose params are an array or lack `protocolVersion`
- **THEN** each is answered HTTP 200 with JSON-RPC `-32600` or `-32602` carrying the request's id when it was valid and `null` otherwise, and no session is opened

#### Scenario: only initialize opens a session
- **GIVEN** a client that has not initialized
- **WHEN** it posts `tools/list` or a notification without `Mcp-Session-Id`
- **THEN** each is answered HTTP 400 and no session is opened

#### Scenario: each failure keeps its own JSON-RPC code
- **GIVEN** an initialized session and a stdio server `up`
- **WHEN** the client calls an unknown method, a tool of no server, `up`'s tool with arguments of the wrong type, and a tool switched off
- **THEN** the answers are `-32601`, `-32602`, `-32602` without the upstream's own text, and `-32000` with no upstream request

#### Scenario: an unsupported MCP-Protocol-Version header is refused
- **GIVEN** a session that agreed on `2025-06-18`
- **WHEN** it sends `ping` with that header, with none, and with `qa-invalid` or `2024-11-05`, and opens its stream with `qa-invalid`
- **THEN** the first two are answered and the others are HTTP 400

### Requirement: Cancel a request only when the client says so
A `notifications/cancelled` naming a request still being answered in the same session MUST stop it: the
upstream receives one cancellation of its own, the call is never sent again, and the cancelled request gets
no response (an empty 202 on its HTTP request). The id is looked up in the sending session only, so two
sessions using the same id never cancel each other. A cancellation for a request already answered or never
seen is accepted and changes nothing. A dropped HTTP connection is not a cancellation: the request runs to
its end and its answer is not delivered. A request id still in flight in a session MUST NOT be used again in
it; such a request is answered `-32600` and not run.

#### Scenario: a cancelled request stops upstream once and is not answered
- **GIVEN** two sessions each running a slow call of the same server under the same request id
- **WHEN** one session sends `notifications/cancelled` for that id
- **THEN** its call is answered with an empty 202 well before the slow call would end, the upstream records one start and one cancellation for it, and the other session's call completes normally

### Requirement: Relay an upstream's sampling and roots requests to the client
When an upstream asks its client for `sampling/createMessage` or `roots/list` during a request, the gateway
MUST pass the question to the downstream client of the session the upstream connection belongs to, over that
session's notification stream, and return the client's answer to the upstream. This holds for stdio
upstreams and for HTTP upstreams that keep a channel back to the client. The gateway offers each capability
to an upstream only when the session's client declared it at `initialize`; a session whose client did not is
never asked, and the upstream is told the capability is not supported.

#### Scenario: two clients each answer their own upstream's sampling and roots
- **GIVEN** a stdio server, and separately an HTTP server, whose tools ask the client to sample and to list roots, and two sessions whose clients declared both and answer differently
- **WHEN** both sessions call both tools at the same time
- **THEN** each call returns its own client's answer and each client is asked exactly once per tool

#### Scenario: a client that declared no sampling is never asked to sample
- **GIVEN** a session whose client declared neither capability
- **WHEN** it calls a tool that asks for sampling and one that asks for roots
- **THEN** both tools report that the client refused, and the client is asked nothing

### Requirement: Record invocations with redacted, bounded content
The system MUST record an invocation entry for every tool call, resource read, and prompt fetch — its target,
timestamp, duration and outcome. Each entry MUST also carry
its row `id`, and MUST name the agent whose session made the call (`agent_uid`) when that session reported one
on its handshake (see "Take the agent identity from the handshake"); a session that reported none writes
entries naming no agent, never a guessed one. A custom tool's call MUST also name the environment it was made
in (`environment`).

While call content recording is on ("Switch call content recording per machine"), the entry MUST also
carry the call's **content**: its `arguments` (a tool's or a prompt's arguments, a resource's uri), its
`result` (the coerced answer the agent received, an in-band `isError` result included), and its `error`
(the text of an exception the upstream raised or answered with, which the entry's `error_message` keeps
reducing to a Coffer-authored summary). A custom HTTP tool's call MUST also carry the `request` it sent
(method, final URL, headers and body) and the `response` it got (status, headers and body), and a Coffer
built-in tool's call carries its arguments and result like any other. A call refused before it reached an
upstream (`denied`) carries its arguments only.

Content MUST be redacted before it is written anywhere — the database, a log line, the wire — and in this
order: every value Coffer injected into that upstream for the call (a stdio or HTTP server's secret overlay,
a custom tool's resolved headers) is replaced with `••••••` wherever it appears; a header that carries
credentials (`Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key`, `X-Auth-Token`
and any header whose name holds `token`, `secret`, `key` or `auth`) and the value of any field whose name
says it holds a secret (`password`, `passwd`, `secret`, `token`, `api_key`, `apikey`, `access_key`,
`private_key`, `client_secret`, `credential`, `authorization`, `cookie`, alone or as a name's last word)
is replaced whole; then every remaining string is scanned with the bundled plaintext-secret rules
([secret](../secret/spec.md) "Detect plaintext secrets with the bundled rules") and each finding replaced.
Each part (`arguments`, `result`, `error`, `request`, `response`) is serialised as JSON and MUST be cut at
16 KB (UTF-8), keeping the start; a cut part says so (`truncated: true`) and keeps its size before the cut
(`bytes`). Content is never written to `daemon.log`, and model-provider traffic is not a call here: its
prompts and completions are never recorded.

How long entries are kept, and the background pass that prunes them, are
[resource-framework](../resource-framework/spec.md) "Prune each registered log table on its own retention period" — the retention contract
every log-writing kind inherits — not this spec's own rule. This spec contributes `mcp_invocations` to that
registry with a 30-day default. The record is read per server
(`GET /api/v1/resources/mcp_server/{uid}/invocations`, `coffer log mcp --server <server>`) or across every
server (`GET /api/v1/mcp/invocations`, `coffer log mcp` with no server), the cross-server read
including Coffer's own built-in calls (`coffer`) and the rows of servers since deleted (their uid, with no name). Both HTTP reads
can be narrowed to one agent's calls with `agent_uid`. Both reads
page newest first by cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor"),
and both CLI forms take `--status`, `--since`, `--limit`, `--cursor` and `--json`. A list carries no content;
one call is read with its content by `GET /api/v1/mcp/invocations/{id}` and `coffer log call <id>`
(404 `INVOCATION_NOT_FOUND`, exit `4`, for an id the log does not hold), whose `content` is `null` for a
call recorded while recording was off. One server's calls since a moment
(24 hours ago by default) are also read counted, for its page:
`GET /api/v1/resources/mcp_server/{uid}/invocations/summary` answers the calls, the errors (every call that
did not end `ok`) and the last call's time, per calling agent and per tool.

#### Scenario: invocation log records a call's arguments and result
- **GIVEN** content recording is on and an MCP client has called a tool with arguments `{"query": "coffer"}`
- **WHEN** the user lists the invocation log, then reads that call by its id
- **THEN** the list entry carries the timestamp, target capability, duration and outcome and no content
- **AND** the call read by id carries `arguments` `{"query": "coffer"}` and the result the client received

#### Scenario: an injected secret echoed by the upstream is masked in the record
- **GIVEN** a stdio server started with a secret injected into its environment, whose tool echoes that value in its result and in an error
- **WHEN** the tool is called twice, once succeeding and once raising, and both calls are read by id
- **THEN** the value appears in neither record, each place it stood reading `••••••`
- **AND** no file or table under `~/.coffer` holds the value

#### Scenario: secret-named fields and credential headers are masked whole
- **GIVEN** a call whose arguments hold `{"password": "hunter2-long", "max_tokens": 64, "headers": {"Authorization": "Bearer abc123def456"}}`
- **WHEN** the call is read by id
- **THEN** `password` and `Authorization` read `••••••` and `max_tokens` reads `64`

#### Scenario: a plaintext key the rules know is masked
- **GIVEN** a tool whose result holds a GitHub token in free text
- **WHEN** the call is read by id
- **THEN** the token reads `••••••` and the rest of the text is kept

#### Scenario: content past 16 KB is cut and says so
- **GIVEN** a tool whose result serialises to 40 KB
- **WHEN** the call is read by id
- **THEN** its `result` holds the first 16 KB with `truncated: true` and `bytes` of about 40 KB, and its `arguments` are whole

#### Scenario: a custom tool's call records its request and response
- **GIVEN** a custom-tool group whose `live` environment sends a secret `Authorization` header, and a tool whose API answers `200` with header `X-Sp-Error: 101` and body `{"error": "denied"}`
- **WHEN** an agent calls the tool in `live` and the call is read by id
- **THEN** `request` holds the method, the final URL, the headers with `Authorization` reading `••••••`, and the body
- **AND** `response` holds status `200`, the `X-Sp-Error` header and the body `{"error": "denied"}`

#### Scenario: a refused call records its arguments only
- **GIVEN** a tool switched off on its server
- **WHEN** an agent calls it with arguments and the call is read by id
- **THEN** the entry is `denied`, carries the arguments, and carries no result

#### Scenario: the command line reads the invocation log
- **GIVEN** a running daemon that has recorded invocations on two servers, on a Coffer built-in tool and on a deleted server
- **WHEN** the user runs `coffer log mcp --server <server>` and then `coffer log mcp --status error --json`
- **THEN** the first prints only that server's calls, newest first, each with its id
- **AND** the second prints, under `invocations`, only failed calls across every server, each naming its server, including `coffer` and the rows of a deleted server

#### Scenario: the command line reads one call with its content
- **GIVEN** a recorded call with arguments and a result, and an id the log does not hold
- **WHEN** the user runs `coffer log call <id>` for each
- **THEN** the first prints the call's metadata, then its arguments and result as indented JSON, a cut part marked as cut
- **AND** the second exits `4` saying no call has that id

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

#### Scenario: a custom tool's call names its environment in the log
- **GIVEN** a custom-tool group with the environments `test` and `live`
- **WHEN** an agent calls one of its tools in `live` and the invocation log is read
- **THEN** the entry names `live` as its environment and carries no credential

### Requirement: Switch call content recording per machine
Whether calls record their content MUST be one setting per machine, on by default, kept in
`~/.coffer/daemon-config.json` (`record_call_content`) and read with `GET /api/v1/settings/call-content`
and changed with `PUT /api/v1/settings/call-content` (`{"enabled": bool}`), and on the command line with
`coffer settings call-content show` and `coffer settings call-content set`. A change MUST take effect for
the next call in every session without a restart, MUST be audited (`call_content_recording_updated`,
naming the old and new value), and MUST NOT rewrite rows already recorded: turning recording off keeps
earlier content until retention prunes it, and turning it on records nothing for calls made while it was
off.

#### Scenario: recording is on by default and can be switched off
- **GIVEN** a fresh `~/.coffer` with no `record_call_content` setting
- **WHEN** the setting is read, an agent calls a tool, recording is switched off, and the agent calls it again
- **THEN** the setting reads on, the first call's record carries its content and the second's `content` is `null`
- **AND** the audit log holds `call_content_recording_updated` from on to off
