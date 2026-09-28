## 1. Arrival order

- [x] 1.1 SeaTalk websocket chains each event's ingest behind the previous one for the same chat key

## 2. Burst coalescing

- [x] 2.1 `application/channel/inbound_burst.py`: per `(channel, chat, thread)` buffer with 1.5 s / 5 s quiet windows, building one `QueuedInbound`
- [x] 2.2 `TurnDriver.acknowledge` at arrival (reaction, else typing); `submit` no longer acknowledges
- [x] 2.3 Commands flush the held burst first; `/stop` drops it

## 3. Parallel threads

- [x] 3.1 Migration + persistence: `parallel_ordinal`, `parallel_title` on `channel_thread_conversations`
- [x] 3.2 `conversation_thread_id` resolved at each inbound entry; conversation and session keying use it, sends use `thread_id`
- [x] 3.3 `direct_threads_are_replies` capability (SeaTalk true); adapter `open_thread` on SeaTalk and Telegram
- [x] 3.4 `/thread [title]` and `/threads` on the roster, mark `🧵#N title` on the root/topic, conversation title and `/status`

## 4. Tests and docs

- [x] 4.1 Unit + integration tests with acceptance markers for every new scenario
- [x] 4.2 `data-model.md`, channels guide, architecture page
