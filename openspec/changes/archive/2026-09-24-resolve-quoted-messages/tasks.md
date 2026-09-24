## 1. Code

- [x] 1.1 `ContextFetchPort.fetch_quoted`; SeaTalk resolves it through `get_message_by_message_id`, Telegram returns empty
- [x] 1.2 SeaTalk thread read follows `next_cursor` at page size 100, capped at 20 pages, keeping pages read before a failure
- [x] 1.3 `turn_context.fold_turn_context` folds the thread, then the quote, above the message and appends their media

## 2. Tests

- [x] 2.1 History: every page read, page cap, partial failure, quote resolved, quote degrades
- [x] 2.2 Inbound: main-chat quote folded with no thread read, quote inside a thread, no fetch on a non-fetching transport

## 3. Specs and docs

- [x] 3.1 channels and channels/seatalk deltas
- [x] 3.2 ADR `seatalk-websocket-inbound` records the quote endpoint and thread paging
