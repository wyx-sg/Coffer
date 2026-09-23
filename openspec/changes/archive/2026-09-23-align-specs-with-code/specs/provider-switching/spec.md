## MODIFIED Requirements

### Requirement: Keep at most one active connection per agent type
At most one connection per AGENT TYPE MAY have `is_active=true`. Activating a connection MUST clear
`is_active` on the connections holding the agents it reaches, then set the target's, via sequential
`ResourceService.update_config` calls; the single-process daemon serialises requests so switches
never interleave. Activating a connection takes its agents over from any previously active
connection, de-projecting that one from the agents the new one does not cover. Converging a vault
that holds more than one active connection for an agent type MUST project deterministically — the
first of those connections by name wins the agent type — MUST leave every `is_active` flag as it
stands, and MUST report the conflict naming both connections so the user re-activates one. No
last-write rule applies: `updated_at` is machine-local and does not travel with the document.

#### Scenario: activating a profile deactivates the previous active profile of the same wire format
- **GIVEN** connection A is active for an agent type and connection B reaches the same agent type,
- **WHEN** the user activates B,
- **THEN** B becomes active and A becomes inactive — at most one active connection per AGENT TYPE (the single-process daemon serialises the clear-then-set so switches never interleave).

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
`coffer scope set provider <name> --agents …`). `scope = []` is dormant: the connection reaches no
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
- **THEN** it projects into Claude Code's `settings.json` (the anthropic shape) with `apiKeyHelper = "coffer provider key --connection-uid <uid>"`, `GET /providers/{uid}/key` returns exactly that connection's key, and the reported agent set follows the scope.

### Requirement: Serve one model list to every surface
What a picker is OFFERED MUST be: the active reaching connection's curated `text` ids when it curates
any, in the user's order and without consulting the agent's catalogue, and otherwise the agent's own
catalogue ([agent-registry](../agent-registry/spec.md)). The catalogue describes the account the
agent logs into itself, and an active connection means the turns do not go there, so mixing the two
could only offer ids the endpoint rejects; `catalogue()` is unchanged and still reports the agent's
own models. An active connection that curates nothing changes nothing, and no active reaching
connection means the agent's own login — a provider row Coffer cannot parse degrades to that case
rather than failing the read.

That read MUST NOT touch the network: it happens on every card render and every turn, so
introspection would put a network round trip on the daemon's event loop. Levels MUST survive it — an
id the agent also reports keeps the levels the agent reported, and one the agent has never heard of
reports none, because the turn still runs through the agent's own runtime whatever endpoint it
points at. Every surface that offers a model MUST get this answer from the same place:
`GET /api/v1/agent-providers/{agent_key}/models` serves it, and a channel's `/model` card resolves it
in-process through the same function. No surface may compute its own — a web picker that
introspected the endpoint and offered the union with the agent's catalogue listed ids the endpoint
would reject and disagreed with the same user's `/model` card.

The system context Coffer adds on every turn — Claude Code's system-prompt append and Codex's
`developerInstructions` on `thread/start` and `thread/resume` — MUST state which model Coffer put the
agent on — or that Coffer set no override — and which ids are available, so the agent does not
confidently name a model it is not running on ([chat](../chat/spec.md) "Tell the agent which model it
is on").

#### Scenario: every surface offers the same models
- **GIVEN** an agent with an active connection that curates two model ids, and an agent catalogue of its own that names different ones,
- **WHEN** the model list is read for the web Chat page and for a channel's `/model` card,
- **THEN** both are exactly the connection's curated ids, in the user's order — the agent's own ids are absent, because the turns go to that endpoint,
- **AND** neither read touches the network, so an unreachable endpoint cannot silently shorten either list (see "Serve one model list to every surface").

### Requirement: Choose a model from a fixed list
Every Coffer surface that chooses a model MUST offer a fixed list with no free-text entry, always
including the current value so it stays selectable; non-chat models are never offered. A model name
and a reasoning level MUST both be passed to the agent verbatim, with no validation against a list of
Coffer's own: the CLI owns that namespace, so a renamed or added level works the day it ships, and a
level an account cannot run fails where every other unusable choice fails. A model name is still raw
passthrough everywhere the CLI accepts one.

On the built-in login the Agent page offers no model control — those slots bind a connection's
model — and shows only a line saying where the model is chosen instead (per conversation in the Chat
page's picker, or with `/model` in a channel). The reasoning effort is stored per conversation next
to the model in the provider-owned `AgentConfig` blob: `PATCH
/api/v1/chat/conversations/{id}/agent-config` takes `effort` alongside `model`, a body that mentions
one leaves the other alone, and an empty or null value clears the field so the agent runs at its own
default. Codex applies it on the turn (`turn/start {threadId, input, effort}`, omitted when unset).
Both agents get it on every surface that offers a model: the web Chat page's draft bar carries the
effort picker ([channels](../channels/spec.md) "Switch the model and reasoning effort from chat"), and a channel has `/effort`, `/model`'s sibling
([channels](../channels/spec.md) "Switch the model and reasoning effort from chat").

#### Scenario: the agent's model picker offers a fixed list without free-form entry
- **GIVEN** an agent whose model is being chosen — on its detail page or in a conversation,
- **WHEN** the model picker is opened,
- **THEN** it offers a fixed dropdown with no free-text "Custom…" entry and no text input: the agent's own catalogue (`GET /api/v1/agent-providers/{agent_key}/models`) when it is on its built-in login, and, when a connection overrides it, that connection's curated `text` ids served by the same route — never a model field stored on the connection, which carries none (TypeScript acceptance test).
