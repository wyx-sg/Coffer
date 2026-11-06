## Why

A parallel thread opened, then `/dir` to another directory before the first
message, listed two conversations with the same title: the empty one in the
default directory and the new one (2026-11-05). The owner asked to reuse the old
conversation; it is deleted instead (ADR `dir-replaces-a-conversation-nothing-ran-in`) because the new one has to pass
the agent's own validation of its directory and model.

## What Changes

- `/dir` deletes the conversation it replaces when no turn ever ran in it and no
  turn is running in the chat. A conversation that ran stays; `/new` keeps what it
  leaves.

## Impact

- `new_conversation.open_fresh`, `ConversationPort`; channels spec "Keep a chat's
  agent, model and directory across its conversations"; channels docs.
