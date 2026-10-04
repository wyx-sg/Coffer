## MODIFIED Requirements

### Requirement: Compose the agent's prompt appends in one place
The appends an agent receives on top of its own prompt MUST be composed in
**one** place, shared by every provider, in a fixed order: the note telling a
channel-driven agent it is on a chat channel — written from facts only the
channel kind holds (the platform, the chat kind, what renders there;
[channels](../channels/spec.md) "Tell a channel-driven agent it is on a chat
channel"), which it hands over as a value chat reads without importing it; then, for a channel-driven turn
only, the memory digest, whose content is memory's own ([memory](../memory/spec.md) "Deliver to channel turns through the system prompt") and
whose injection point is this one; then the model note of "Tell the agent which
model it is on", on every turn. Composing it here is what lets memory reach an
agent with no session-start hook and no install — Coffer owns this turn's
context itself. An agent the developer drives themselves receives memory
through its own hook instead, never both.

#### Scenario: a channel-driven turn carries the memory digest
- **GIVEN** a conversation driven from a channel and a memory digest to deliver,
- **WHEN** the turn's system context is composed,
- **THEN** the channel note, the memory digest and the model note are appended in
  that order; a conversation with no channel receives the model note only.
