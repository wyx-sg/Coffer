## MODIFIED Requirements

### Requirement: Deliver to channel turns through the system prompt
A **channel-driven turn** MUST receive the same payload through the system-prompt append the turn platform already composes ([channels](../channels/spec.md)). It MUST NOT require a hook, since Coffer owns that context itself, and the delivery MUST be audited as a `session_start` fire of the answering agent with the conversation as the session (see "Audit every delivery fire").

The agent process Coffer spawns for a channel turn still loads the agent's own settings, so an installed delivery hook fires inside it as well. Coffer MUST mark that process's environment, and in a marked process the hook MUST answer nothing, and record nothing, on `SessionStart` and `UserPromptSubmit`: those two moments belong to the turn, so the index and the prompt's notes each arrive once and are counted once. The hook's `PreToolUse` and `PostToolUse` entries MUST still answer in a marked process, because the turn delivers neither. A turn the developer drives MUST NOT be marked.

#### Scenario: a channel turn carries the index without a hook
- **GIVEN** a channel-driven conversation on a registered agent with a working directory, and no delivery hook installed anywhere
- **WHEN** a turn is taken
- **THEN** the index arrives in the **system-prompt append** the turn platform already composes, resolved once per turn from that agent's key and the conversation's own cwd
- **AND** when there is nothing to deliver the turn carries no memory header at all, rather than an empty one (see "Deliver to channel turns through the system prompt")

#### Scenario: a channel turn's own hook leaves the index and the notes to the turn
- **GIVEN** a connected agent whose delivery hook is installed and trusted, a channel-driven conversation on it, and a conversation the developer drives on the same agent
- **WHEN** the channel turn's agent process fires the hook on `SessionStart`, `UserPromptSubmit` and a `PreToolUse` that an armed trigger matches
- **THEN** the hook answers the `PreToolUse` only, and the index and the prompt's notes reach the agent once, from the turn, each audited as one fire with event `ChannelTurn` (`session_start` and `prompt`)
- **AND** the developer-driven conversation's process is not marked, and its hook answers all three

### Requirement: Retrieve the notes a prompt names for a channel turn
A **channel-driven turn** gets its prompt's notes from Coffer rather than from its hook (see "Deliver to channel turns through the system prompt"), so Coffer MUST retrieve for each of its prompts itself: the prompt MUST be ranked by the same retrieval "Retrieve the notes a prompt names" defines — the same partitions, ranker, relevance floor, top three, 1,500-byte ceiling and trivial-prompt rule — with the conversation as the session, so a note is given once per conversation. What it finds MUST be added after the user's text in the prompt the agent receives, where a `UserPromptSubmit` hook's context would land; the message stored in the conversation MUST stay the user's own text. Each delivery MUST be audited as a `prompt` fire of the answering agent (see "Audit every delivery fire"). A turn the developer drives from the web page MUST NOT be ranked here, since its agent's own hook does that, and a retrieval that fails MUST cost the turn only its notes.

#### Scenario: a channel turn's prompt brings in the notes it names
- **GIVEN** a channel-driven conversation on a registered agent in a repository whose partition holds a note about running `make verify` under Node 20, and a conversation the developer drives in the same repository
- **WHEN** each sends the prompt "why does make verify fail with undici AbortSignal under node", and the channel conversation sends it again
- **THEN** the channel turn's agent receives the prompt followed by the same text the `UserPromptSubmit` hook would add, naming the Node 20 note's file, and one `memory_delivery_fired` event names moment `prompt`, the conversation and the note
- **AND** the second channel turn is given nothing new, and the developer-driven turn's prompt reaches its agent unchanged
