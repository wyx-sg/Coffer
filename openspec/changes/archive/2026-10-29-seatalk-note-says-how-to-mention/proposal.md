# Tell the SeaTalk agent how to @mention a person

## Why

Asking a colleague in a group thread, the agent wrote "Bowen, please share …"
without @mentioning Bowen, so Bowen got no notification. A mention tag the
agent writes already passes through the SeaTalk renderer, and a thread's lines
name each sender by email, but nothing told the agent so.

## What Changes

- SeaTalk's render notes add how to @mention a person by email.
- To keep the note under its word budget, "To send a file or image" becomes
  "To send a file".

## Impact

- `infrastructure/channel/seatalk_caps.py`, `domain/chat/channel_prompt.py`,
  their unit test, the SeaTalk guide (en, zh).
