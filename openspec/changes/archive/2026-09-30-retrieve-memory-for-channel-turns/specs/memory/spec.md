## ADDED Requirements

### Requirement: Retrieve the notes a prompt names for a channel turn
A **channel-driven turn** runs no hook of Coffer's, so Coffer MUST retrieve for each of its prompts itself: the prompt MUST be ranked by the same retrieval "Retrieve the notes a prompt names" defines — the same partitions, ranker, relevance floor, top three, 1,500-byte ceiling and trivial-prompt rule — with the conversation as the session, so a note is given once per conversation. What it finds MUST be added after the user's text in the prompt the agent receives, where a `UserPromptSubmit` hook's context would land; the message stored in the conversation MUST stay the user's own text. Each delivery MUST be audited as a `prompt` fire of the answering agent (see "Audit every delivery fire"). A turn the developer drives from the web page MUST NOT be ranked here, since its agent's own hook does that; the retrieval MUST stop on the next turn after the `memory` feature is switched off, and a retrieval that fails MUST cost the turn only its notes.

#### Scenario: a channel turn's prompt brings in the notes it names
- **GIVEN** a channel-driven conversation on a registered agent in a repository whose partition holds a note about running `make verify` under Node 20, and a conversation the developer drives in the same repository
- **WHEN** each sends the prompt "why does make verify fail with undici AbortSignal under node", and the channel conversation sends it again
- **THEN** the channel turn's agent receives the prompt followed by the same text the `UserPromptSubmit` hook would add, naming the Node 20 note's file, and one `memory_delivery_fired` event names moment `prompt`, the conversation and the note
- **AND** the second channel turn is given nothing new, and the developer-driven turn's prompt reaches its agent unchanged
