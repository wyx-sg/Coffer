## Context

`InboundProcessor.on_message` gates a message, folds in thread/quote context, and calls `TurnDriver.submit`, which queues the turn on the conversation of `(channel, chat_id, thread_id)`. Two problems sit in that path. First, it does no batching, so every message is its own turn. Second, SeaTalk's websocket ingests each event in its own task, so two messages from one chat race through their awaits (download, lookups) and can reach `submit` out of order. Telegram's poller already awaits updates one at a time.

## Decisions

### Order at the transport, coalesce in the application layer

Arrival order is only known where the frame is read, so SeaTalk serialises ingestion per chat key (`employee_code` for a DM, `group_id` for a group). It chains each event's ingest task behind the previous one for that key. Other chats keep running concurrently.

Coalescing is platform-independent, so it lives in `application/channel/inbound_burst.py`, the same way Telegram's album buffer works. The buffer is keyed by `(channel, chat_id, thread_id)` and holds each message's own text, attachments, title hint and origin. A timer is re-armed on every message. When the chat goes quiet, the buffer builds one `QueuedInbound`:
- one origin block, taken from the last message, since the reply attaches to and mentions whoever spoke last;
- the messages' texts in arrival order, separated by blank lines;
- every attachment;
- the first non-empty title hint.

The window is 1.5 s after a text message. It is 5 s after a message that is rarely the whole ask: a forwarded chat record, or attachments with no text. These are module constants, not settings: nobody should have to tune them, and a setting would be one more surface to document.

The receipt acknowledgement moves out of `submit` into `TurnDriver.acknowledge`, which runs at buffer time. It sends the 👀 reaction where the transport has reactions and a typing signal otherwise. A person should see "heard" immediately, not after the window.

Commands are never buffered. A command first flushes what its chat and thread are holding, so ordering holds. `/stop` is the exception: it drops the waiting messages, because they had not started and the person asked for stop.

Messages sent while a turn runs are coalesced the same way before they join the conversation's pending queue. Two corrections typed during a long turn therefore become one queued turn, not two.

### A conversation key apart from the reply thread

On SeaTalk, a DM reply-in-thread keeps the direct chat's conversation but is answered in that thread. That needs two thread ids:
- `thread_id` is where the reply goes;
- `conversation_thread_id` is which conversation it belongs to.

The processor resolves `conversation_thread_id` once, at each inbound entry (`on_message`, `on_callback`, `on_stop`):
- A group thread keeps its own id.
- A direct-chat thread keeps its own id when it is a parallel thread (its row carries a `parallel_ordinal`), or when the transport says a DM thread is always deliberate. Telegram is such a transport: a private-chat topic only exists if someone created it.
- Every other DM thread maps to `""`.

The capability flag is `ChannelCapabilities.direct_threads_are_replies`, true for SeaTalk.

Everything that keys a conversation or a session uses `conversation_thread_id`: the thread repository, `ensure_conversation` / `open_conversation`, and the `_session` registry. Everything that sends uses `thread_id`. The alternative was folding inside the repository, which would need a chat kind the repository does not have and a synchronous lookup for the session registry. The explicit field is more lines, but each is obvious.

### Parallel threads are rows with an ordinal

`channel_thread_conversations` gains `parallel_ordinal INTEGER NULL` and `parallel_title TEXT NULL`. A row with an ordinal is a parallel thread. The ordinal is `max + 1` over the chat's rows, so it is never reused after a conversation is replaced. No backfill is needed: existing DM thread rows have no ordinal, so they now fold into the DM conversation, which is the intended behaviour.

`/thread [title]` asks the adapter to `open_thread(chat_id, header)`, which returns the new thread id:
- SeaTalk posts the header as a new DM message, and a thread's id is its root message id.
- Telegram calls `createForumTopic` with the mark as the topic name and posts the header into it. If the bot's private-chat topics are off, it fails with a message telling the owner to turn on Threaded Mode in BotFather.

The processor then records the row, opens its conversation, and renames that conversation to the mark. The mark is `🧵#N title`, where the title defaults to `Task`. It is the one string used everywhere the thread is shown.

`/thread` is direct-chat only. In a group every thread is already its own conversation, so there `/thread` answers that.

`/threads` lists the chat's parallel threads, newest first, capped at 20. It shows the count, and for each thread its mark, its agent, and its state: running, N waiting, or idle.

## Risks

- A 1.5 s delay on every plain message. This is the price of never splitting a thought across two answers. The window only restarts on a new message, so a single message waits exactly once.
- Folding DM threads changes behaviour for existing SeaTalk DM threads: they now share the direct chat's context. This is the requested behaviour.
