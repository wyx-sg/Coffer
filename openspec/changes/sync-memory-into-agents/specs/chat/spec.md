## MODIFIED Requirements

### Requirement: Compose the agent's prompt appends in one place
The appends an agent receives on top of its own prompt MUST be composed in
**one** place, shared by every provider, in a fixed order: the note telling a
channel-driven agent it is on a chat channel — written from facts only the
channel kind holds (the platform, the chat kind, what renders there;
[channels](../channels/spec.md) "Tell a channel-driven agent it is on a chat
channel"), which it hands over as a value chat reads without importing it — then
the model note of "Tell the agent which model it is on", on every turn. Coffer
MUST put no memory into a turn, whether the turn is channel-driven or not: an
agent reaches memory only through its own native memory, which it loads itself
([memory](../memory/spec.md) "Deliver no memory into a session").

#### Scenario: a channel-driven turn carries the channel note and the model note
- **GIVEN** a conversation driven from a channel,
- **WHEN** the turn's system context is composed,
- **THEN** the channel note and the model note are appended in that order, and
  nothing from the memory layer; a conversation with no channel receives the
  model note only.
