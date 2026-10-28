# Let others in a group ask the bot

## Why

The owner wants colleagues to ask the bot questions in a work group — "why
can't this user log in?" — without making them owners, because an owner drives
the agent with every permission on the owner's machine. Today a colleague either
gets "🚫 Only <bot>'s owners can use it here." or has to be paired as an owner,
which also lets them deploy, publish, change data and dispatch tasks.

## What Changes

- Owners keep full control. Someone else who @mentions the bot in a group an
  owner has already used it in is answered, read-only.
- Their turn's origin block says `asker: not an owner (read-only)`, and the
  group's channel note tells the agent to answer and run read-only checks for
  them but change nothing and start no work on their word.
- Their commands are refused in one line; their button taps stay refused.
- A per-channel switch, **Let others in the group ask** (`others_can_ask`), on
  by default, on the Settings tab under Receiving messages.
- The vault skill that guards writes gets the same rule (outside this repo).

## Impact

- Backend: channel config, binding, group gate, inbound, message origin,
  channel note.
- Web UI: one switch on the channel's Settings tab.
- Contract: `others_can_ask` in the channel settings.
- Docs (en, zh), ADR `others-in-a-group-may-ask-read-only`, Run canvas.
