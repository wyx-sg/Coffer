## Why

Coming back to a SeaTalk group thread a day later answered `🆕 Started a new
conversation after 24 h idle.` and dropped the agent's working state, although
the owner had returned to that thread precisely to carry on. A thread is
already the boundary between tasks, and `/resume` is not available in a group,
so the old conversation could not be brought back from the chat. The options
are argued in ADR `idle-time-rolls-over-a-direct-chat-but-never-a-thread`.

## What Changes

- **Idle rollover applies only to a key without a thread**: a direct chat (its
  casual replies-in-thread included) and a group whose main chat is one
  conversation. Group threads, forum topics, parallel threads and Telegram
  private-chat topics keep their conversation however long they sit idle;
  `/new` there starts over, and parallel threads still close after 24 idle hours.
- The setting keeps its name, range and default; its hint on the Settings tab
  says it is about direct chats.
- The main spec is edited directly (`skip_specs`): the scenario "the idle period
  applies to each group thread's conversation" is replaced by "a group thread
  idle past the configured hours keeps its conversation" and "a group that is
  one conversation rolls over like a direct chat".

## Impact

- Code: `application/channel/conversation_ops.py` (`rolls_over_when_idle`, used
  by `ensure_conversation` and `predict_conversation`).
- Spec: channels "Open a new conversation after an idle period"; data model
  field note.
- Docs: guides/channels, architecture/chat (en + zh); ADRs
  `idle-time-rolls-over-a-direct-chat-but-never-a-thread` (new) and
  `channel-conversation-identity`.
- UI: the idle field's hint text (en + zh).
