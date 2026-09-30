## MODIFIED Requirements

### Requirement: Activate a connection into the agents its scope reaches
`POST /api/v1/providers/{uid}/activate` (and `coffer provider switch <name>`) MUST apply the
single-active rule (see "Keep at most one active connection per agent type"), then project into
every ENABLED registered agent the connection's scope reaches. The operation:

1. requires the connection to exist, else 404;
2. projects into each agent its scope reaches, and de-projects the agents the previous connection held
   and this one does not;
3. clears `is_active` on the connections that held those agents, then sets it on the target;
4. emits `provider_switched`;
5. returns `{activated, protocol, projected, skipped}`.

Projection MUST run BEFORE the activation flip, so a failed native-config write aborts the switch
with the registry unchanged. If no agent the connection reaches is registered, it MUST record the
connection active and return a non-empty `skipped` list — NOT an error.

Reach is the framework's per-agent `scope`
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)); there is no
`compatible_agents` field in the config, in `ProviderCreate` or in `ProviderPatch`. A new connection
is pre-filled from its wire through the kind's `default_scope` hook — unscoped for a credentialed
wire (including `unknown`, so an inconclusive probe hides nothing and the user decides), which reaches
every agent including one registered later, and nothing (`scope = []`) for `ollama`. Re-targeting is a scope edit (`PUT /api/v1/resources/{uid}/scope`,
`coffer provider scope <name> --agents …`). `scope = []` is dormant: the connection reaches no
agent, so no agent resolves its key. The projection writer MUST be chosen by AGENT type, not by
protocol: a connection reaching `claude_code` writes Claude's `settings.json` in the anthropic shape
and one reaching `codex` writes Codex's `config.toml`, which is how an OpenAI-compatible gateway is
routed to Claude Code. Coffer translates nothing between protocols.

#### Scenario: activate a profile whose wire matches no registered agent records active but projects nothing
- **GIVEN** no Codex agent is registered and a connection reaching only Codex exists,
- **WHEN** the user activates it,
- **THEN** its `is_active` becomes `true`, no config file is written, and the response carries `skipped: ["codex"]` (or empty `projected`).
#### Scenario: route an openai-compatible connection to Claude Code with its scope
- **GIVEN** a Claude Code agent is registered and an `openai`-wire connection is created and then scoped to `["claude_code"]`,
- **WHEN** the user activates that connection,
- **THEN** it projects into Claude Code's `settings.json` (the anthropic shape) with `apiKeyHelper = "<absolute path to the coffer CLI> proxy token --agent-uid <agent uid>"`, the model proxy routes that agent's requests to exactly that connection with that connection's key, and the reported agent set follows the scope.

### Requirement: Fail over only before the first content byte
When a request fails before the first content byte reaches the agent — a connect, TLS or DNS
error, a 5xx, 529 or 429 status, a 401 or 403, a first-byte timeout, or an error event before the
first content event (the proxy holds the response until then, bounded to 64 KiB and 5 seconds) — the proxy MUST move it to the next member of the agent's route: another enabled
connection that reaches the same agent type, speaks the same protocol and lists the requested model
among its curated models. Failover MUST never change the model, never try the same member twice for
one request, and never happen after the first content byte: an error or truncation after it goes to
the agent, whose own retry lands on a healthy member. A 429 with `retry-after` cools that member for
that long; 401 or 403 disables it until its key changes; 400, 404 and 413 are relayed and never
fail over. A local runtime connection has no fallback members. A session stays on one member until
that member fails.

#### Scenario: a failure before the first byte moves to another connection serving the model
- **GIVEN** an agent's active connection answering 503, and another connection reaching the agent that lists the requested model
- **WHEN** the agent sends a request
- **THEN** the agent receives the second connection's response and never sees the 503

#### Scenario: an error after the first content byte is passed to the agent
- **GIVEN** an active connection whose stream fails after its first content event
- **WHEN** the agent sends a streaming request
- **THEN** the agent receives the partial stream and the error, and no other connection is tried

#### Scenario: a request problem is never failed over
- **GIVEN** an active connection answering 400
- **WHEN** the agent sends a request
- **THEN** the 400 and its body reach the agent unchanged and no other connection is tried

#### Scenario: failover never changes the model
- **GIVEN** an active connection answering 529, a second connection that does not list the requested model, and a third that does
- **WHEN** the agent sends a request
- **THEN** the second connection is never tried, and the third receives the request with the model the agent asked for
