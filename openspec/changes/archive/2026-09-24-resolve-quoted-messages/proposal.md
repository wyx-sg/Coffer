## Why

A SeaTalk bot pulled into a group could not see the message it was asked about.
When someone quoted an earlier message and @mentioned the bot, the turn carried
only the quoted message's id. The spec said the agent would look the body up
through SeaTalk's own tools, but SeaTalk gives one message a different id per
app, so only the bot that received the event can resolve it. No tool the agent
holds can. The agent answered "I can't see the quoted message."

Threads had a similar gap. The thread endpoint pages oldest-first, and the
transport read one 50-message page, so a long thread lost the messages written
just before the @mention.

## What Changes

- channels: a quoted message is resolved by the transport and folded into the
  turn as `> sender: …` lines right above the message. The origin block still
  names the quoted id. A failed lookup leaves the turn as it was.
- channels: a thread is read in full, every page, before the turn runs.
- channels/seatalk: the quoted body comes from
  `GET /messaging/v2/get_message_by_message_id` with the bot's own token. The
  images and files it carries are downloaded like a thread message's.
- channels/seatalk: the thread endpoints are paged by `next_cursor` at the
  largest page size the API accepts (100), up to a fixed page cap.

## Capabilities

### New Capabilities

### Modified Capabilities

- `channels`: "Name a quoted message without fetching it" becomes "Ground a
  turn in the message it quotes"; "Reply in place inside threads" reads the
  whole thread.
- `channels/seatalk`: "Keep the quoted message id as a handle" becomes "Resolve
  a quoted message with the bot's own token"; adds "Read every page of a
  thread".

## Impact

`ContextFetchPort` gains `fetch_quoted`. The SeaTalk and Telegram adapters
implement it; Telegram returns nothing because its updates already carry the
quote inline. The thread and quote folding moves from `inbound.py` into
`application/channel/turn_context.py`.
