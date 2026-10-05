## MODIFIED Requirements

### Requirement: Serve one model list to every surface
What a picker is OFFERED MUST be: the curated `text` ids of the connection the agent runs on when it curates
any, in the user's order and without consulting the agent's catalogue, and otherwise the agent's own
catalogue ([agent-registry](../agent-registry/spec.md)). The catalogue describes the account the
agent logs into itself, and an agent on a connection means the turns do not go there, so mixing the two
could only offer ids the endpoint rejects; `catalogue()` is unchanged and still reports the agent's
own models. A connection that curates nothing changes nothing, and an agent on no connection
means the agent's own login — a provider row Coffer cannot parse degrades to that case
rather than failing the read.

Codex's own model picker, inside Codex, is the one surface this answer does not reach when the
connection curates models but none of modality `text`: Coffer's surfaces then offer no chat model,
while the projection writes no model catalogue ("Project into Codex config without overwriting it"
writes one only for curated `text` models), so Codex keeps listing its built-in models.

That read MUST NOT touch the network: it happens on every card render and every turn, so
introspection would put a network round trip on the daemon's event loop. Every surface that offers a model MUST get this answer from the same place:
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
- **GIVEN** an agent running on a connection that curates two model ids, and an agent catalogue of its own that names different ones,
- **WHEN** the model list is read over `GET /api/v1/agent-providers/{agent_key}/models` and for a channel's `/model` card,
- **THEN** both are exactly the connection's curated ids, in the user's order — the agent's own ids are absent, because the turns go to that endpoint,
- **AND** neither read touches the network, so an unreachable endpoint cannot silently shorten either list (see "Serve one model list to every surface").

### Requirement: Choose a model from a fixed list
Every Coffer surface that chooses a model MUST offer a fixed list with no free-text entry, always
including the current value so it stays selectable; non-chat models are never offered, so a connection
an agent runs on that curates models, none of them `text`, offers none.  A model name MUST be passed to the agent verbatim, with no validation against a list of
Coffer's own (the one narrow exception is the local model proxy, which replaces a requested model its connection
does not curate with the agent's projected default — [Reach API-key and local connections through the local model proxy](#requirement-reach-api-key-and-local-connections-through-the-local-model-proxy)): the CLI owns that namespace, so a renamed or added model works the day it ships, and one an
account cannot run fails where every other unusable choice fails. A model name is still raw
passthrough everywhere the CLI accepts one. Coffer offers no reasoning-effort control on any surface: the agent runs at the effort its own configuration names.

On the built-in login the Change model dialog offers no model control — those slots bind a connection's
model — and says where the model is chosen instead (the agent's own `/model`, or `/model` in a channel); the agent's Overview › Model still shows the model its own configuration names, read-only. The model is stored per conversation in the provider-owned `AgentConfig` blob, set with `/model` in a channel; `/model default` clears it so the agent runs at its own
default.

#### Scenario: the agent's model picker offers a fixed list without free-form entry
- **GIVEN** an agent whose model is being chosen — on its detail page or on a channel's `/model` card,
- **WHEN** the model picker is opened,
- **THEN** it offers a fixed dropdown with no free-text "Custom…" entry and no text input: the agent's own catalogue (`GET /api/v1/agent-providers/{agent_key}/models`) when it is on its built-in login, and, when a connection overrides it, that connection's curated `text` ids served by the same route — never a model field stored on the connection, which carries none (TypeScript acceptance test).
