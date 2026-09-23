## MODIFIED Requirements

### Requirement: Choose a model from a fixed list
Every Coffer surface that chooses a model MUST offer a fixed list with no free-text entry, always
including the current value so it stays selectable; non-chat models are never offered, so an active
connection that curates models, none of them `text`, offers none. The per-conversation picker also
always carries a **Default** option that clears the conversation's model, so the agent runs its
projected default ([chat](../chat/spec.md) "Offer models from a fixed dropdown that keeps the
current value"). A model name
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
