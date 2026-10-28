## Why

When an idle chat rolled into a new conversation the bot first said `🆕 Started
a new conversation after 24 h idle.` The owner finds the line unnecessary: the
answer already comes from a fresh conversation and the old one stays in the list.

## What Changes

- Idle rollover (rules unchanged, see ADR
  `idle-time-rolls-over-a-direct-chat-but-never-a-thread`) no longer sends any
  line. `ensure_conversation` loses its `say` parameter and `idle_notice` is gone.
- The main spec is edited directly (`skip_specs`): the requirement and two
  scenarios say the chat is not told.

## Impact

- Code: `application/channel/conversation_ops.py`, `turn_driver.py`.
- Spec: channels "Open a new conversation after an idle period".
- Docs: guides/channels (en + zh); the ADR's consequences note.
