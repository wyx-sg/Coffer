## Why

A person talking to the bot rarely says everything in one message. They forward a chat record and then add "look into this", or send a question and a correction right after it. The channel turned every inbound message into its own turn, so the agent answered the forwarded record and the follow-up separately. On SeaTalk it could also answer them in the wrong order: each websocket event was ingested in its own task, and a message that needed a download (a forwarded record with a file) reached the turn queue after the text sent behind it, so the agent answered "look into this" without having seen the record.

A direct chat is also one person's one working thread, and it should keep one context. On SeaTalk, "reply in thread" on any message in a direct chat opened a brand-new conversation, which dropped the context the person was relying on. When the person does want two tasks running side by side, there was no deliberate way to ask for it, and no way to see which parallel conversations exist.

## What Changes

- **Arrival order.** SeaTalk hands one chat's events to the channel in the order they arrived; different chats still run concurrently.
- **Coalescing.** Messages that arrive in a quick burst in one chat and thread become one turn. The channel waits a short quiet window after each message: 1.5 s after text, 5 s after a message that is rarely the whole ask (a forwarded record, or files without text). A new message in the window restarts it. Every message is still acknowledged on arrival. A command flushes what is waiting first, except `/stop`, which drops it.
- **One conversation per direct chat.** On SeaTalk, a reply-in-thread inside a direct chat belongs to the direct chat's conversation and is still answered in that thread. Only a thread opened with `/thread` is a conversation of its own.
- **`/thread [title]`** opens a parallel conversation in a direct chat. On SeaTalk the bot posts the thread's root message and replies under it start the new conversation. On Telegram the bot creates a private-chat topic. Each one is numbered per chat and carries the mark `🧵#N title`: on the root message or topic name, as the conversation's title on the web, and in `/status`.
- **`/threads`** lists the chat's parallel conversations: how many there are, and each one's mark, agent, and whether a turn is running or waiting.

## Capabilities

### New Capabilities

### Modified Capabilities
- `channels`: new requirements "Take a burst of messages as one turn" and "Open parallel conversations in a direct chat". "Answer the conversation commands from any paired chat" and "Key conversation identity by channel, chat and thread" are updated to match.
- `channels/seatalk`: new requirements "Hand a chat's events to the channel in arrival order" and "Open a parallel thread by posting its root message".
- `channels/telegram`: new requirement "Open a parallel thread as a private-chat topic".

## Impact

- Backend: `application/channel/{inbound,turn_driver,commands,card_delivery,model_switch,effort_switch,inbound_events}.py`, a new inbound burst buffer and a parallel-thread module, `domain/channel/commands.py` roster, the SeaTalk websocket ingest and adapter, the Telegram adapter, channel persistence plus one migration (two nullable columns on `channel_thread_conversations`).
- Docs: `openspec/specs/channels/data-model.md`, the channels guide and architecture pages.
