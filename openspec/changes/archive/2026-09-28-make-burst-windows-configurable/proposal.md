## Why

The burst windows (1.5 s after text, 5 s after a forward or files) were fixed constants. How long a pause means "I'm done" is personal: someone who types corrections in three quick lines wants a longer wait, and someone who only ever sends one message wants none.

## What Changes

- Two per-channel settings, `wait_after_text_seconds` (default 1.5) and `wait_after_forward_seconds` (default 5), each 0–60 seconds. 0 makes every message its own turn.
- Edited on the Channels page (Edit → Message batching) and with `coffer channel register|set --wait-after-text/--wait-after-forward`.

## Capabilities

### New Capabilities

### Modified Capabilities
- `channels`: "Take a burst of messages as one turn" gains the settings and two scenarios.

## Impact

- Backend: channel config, `ChannelBinding`, runtime, `inbound_burst.window_for`, CLI `channel register|set`.
- Frontend: Edit channel dialog, en/zh strings.
- Docs: channels guide, CLI reference, data model.
