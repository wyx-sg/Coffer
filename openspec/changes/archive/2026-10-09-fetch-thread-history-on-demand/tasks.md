## 1. Thread reads as messages

- [x] 1.1 Add `ThreadMessage` / `ThreadRead` (`domain/channel/thread_messages.py`)
- [x] 1.2 `ContextFetchPort.fetch_thread` returns a text-only `ThreadRead`; add `fetch_message_media`
- [x] 1.3 SeaTalk: read every page text only, flag bot senders, download one message's media; Telegram: empty reads

## 2. Bounded fold with a per-conversation cursor

- [x] 2.1 `channel_thread_cursors` table, repo and migration `0153`; delete with the channel
- [x] 2.2 `predict_conversation` beside `ensure_conversation`
- [x] 2.3 `ThreadContextFolder`: seed of 20, news since the cursor, bot replies left out, older-messages note, window note on the seed
- [x] 2.4 Pending cursor written before the conversation exists, claimed in `TurnDriver.submit`
- [x] 2.5 Origin block names the channel

## 3. The read tool

- [x] 3.1 `BuiltinTool.turn_scoped` and `BuiltinToolRegistry.view(in_turn=)`; the gateway session sees its view
- [x] 3.2 `coffer__channel_read_thread` (`application/channel/thread_tool.py`), registered in `channel_wiring`
- [x] 3.3 Channel note names the tool where the transport reads threads

## 4. Tests

- [x] 4.1 Integration: seed, news only, nothing new, `/new` reseeds, cursor persisted, media of folded messages only, failed read, fresh-thread root
- [x] 4.2 Integration: tool paging, limits, unpaired chat, no-history platform, errors; turn-scoped listing over `/mcp`
- [x] 4.3 Unit and adapter tests updated for the new port; cursor repo; channel note; origin block

## 5. Spec and docs

- [x] 5.1 Spec deltas for channels, channels/seatalk, mcp-gateway; `data-model.md`
- [x] 5.2 Docs (English and Chinese): channels and SeaTalk guides, chat architecture, MCP tools reference, surfaces roster
- [x] 5.3 `make verify`, archive the change
