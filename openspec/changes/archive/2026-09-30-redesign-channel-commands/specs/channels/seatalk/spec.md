## ADDED Requirements

### Requirement: Mark a main-chat mention as the group's main chat
A SeaTalk @mention sent in a group's main chat carries no thread id, and the
reply roots a new thread at the message itself. The transport MUST mark such a
message as coming from the group's main chat, so the core can treat a command
sent there as setting the group's defaults (spec channels "Set a group's
defaults from its main chat"); a mention inside a thread is not marked.

#### Scenario: a main-chat @mention is marked as group main
- **GIVEN** a SeaTalk channel receiving group @mention events
- **WHEN** one arrives with no thread id and another arrives inside a thread
- **THEN** the first is marked as the group's main chat with its own message id as
  the thread, and the second is not marked
