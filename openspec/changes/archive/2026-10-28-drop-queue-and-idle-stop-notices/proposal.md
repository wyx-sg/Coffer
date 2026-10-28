## Why

The owner finds two bot lines unnecessary: `⏳ Queued — runs when the current one
finishes.` for a message that waits behind a running turn, and `Nothing is
running.` for a `/stop` with nothing to stop. The message is received and
answered in turn; a `/stop` with nothing running has nothing to report.

## What Changes

- A message that joins the queue gets no reply of its own. The overflow notice
  for the eleventh message stays: that one is a real drop.
- `/stop` (typed or the platform's own stop, in a chat or a group's main chat)
  with no turn in flight answers nothing.
- The main spec is edited directly (`skip_specs`).

## Impact

- Code: `application/channel/turn_driver.py`, `commands.py`.
- Spec: channels. Docs: guides/channels, reference/channel-commands,
  architecture/chat (en + zh).
