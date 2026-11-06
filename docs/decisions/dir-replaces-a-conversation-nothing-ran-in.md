# `/dir` Replaces a Conversation Nothing Ran In

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: spec channels "Keep a chat's agent, model and directory across its conversations"

## Context

A parallel thread opens a conversation in the channel's default directory. When
the owner then sends `/dir` before the first message, Coffer opens a fresh
conversation in the new directory (a conversation's directory is fixed with its
agent session) and left the first one behind, so the Conversations list showed
two rows with the same title (2026-11-05). The owner asked whether the old
conversation could be reused.

## Options Considered

### Option A — Edit the old conversation's directory in place

- ✅ One row, nothing to delete.
- ❌ The agent provider validates the directory and model and resolves defaults
  when it creates a conversation (`init_conversation`). Writing the config
  directly skips that, so a bad directory or model would surface at the first
  turn instead of at `/dir`.

### Option B — Create the new conversation, then delete the old one when nothing ran in it (chosen)

- ✅ The new conversation passes the same validation as any other.
- ✅ Safe to delete: with no agent session id there is no turn, no agent-side
  session and nothing worth resuming; `/resume` already skips conversations
  deleted elsewhere.
- ⚠️ Two writes instead of one; if the delete fails a spare row stays, which is
  today's behaviour.

### Option C — Hide unused conversations in the list

- ✅ No deletion.
- ❌ The row still exists, search and counts disagree with the list, and every
  list filter needs the same rule.

## Decision

Option B, for `/dir` only, and only when no turn runs in the chat. `/new` keeps
the conversation it leaves: its owner typed it on purpose, and `/resume`
lists it.

## Consequences

- `open_fresh(replace_unused=True)` is used by `/dir`; the conversation port
  gained `delete_conversation`.
