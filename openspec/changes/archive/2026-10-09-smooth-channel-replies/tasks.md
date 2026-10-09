## 1. Reply text

- [x] 1.1 `ReplyText.answer()` returns the text after the last tool call, falling back to the last non-empty segment; the renderer delivers it
- [x] 1.2 Unit and integration tests for both cases; update the segment test

## 2. SeaTalk shows only typing

- [x] 2.1 SeaTalk declares no live surface and `open_live_text` returns `None`
- [x] 2.2 Delete `seatalk_live.py`, `seatalk_stream_text.py`, the interim-snapshot helpers in `render.py`, `MIN_UPDATE_INTERVAL` / `COFFER_SEATALK_STREAM_INTERVAL`
- [x] 2.3 Remove `live_text_persists`, `streams_in_groups`, the turn-start acknowledgement and per-snapshot mention from the core
- [x] 2.4 Do not record a SeaTalk direct-chat text reply for `/del`
- [x] 2.5 Tests: the real adapter types and sends one answer message; no stream request; numbered long reply

## 3. Remove the long-turn ping

- [x] 3.1 Remove `notify_after_seconds` from config (dropped on read), binding, driver and renderer; remove the question ping
- [x] 3.2 Regenerate the REST contract and frontend types (`make contracts`)
- [x] 3.3 Remove the Channels settings field, its strings, parsing and tests; update the e2e settings flow
- [x] 3.4 Offer the step-lines switch only for a channel type with a live status line

## 4. Remove the details card

- [x] 4.1 Delete `details_card.py`, its callback routes and the card path in `turn_finish.py`
- [x] 4.2 Tell the agent about `## Details` only where the transport collapses it (`ChannelNote.collapses_details`), and that only the text after its last tool call is sent

## 5. Docs and specs

- [x] 5.1 Spec deltas for channels, channels/seatalk, channels/telegram; data-model.md
- [x] 5.2 SeaTalk and channels guides, chat architecture page, configuration reference (English and Chinese); the live-surface ADR
- [x] 5.3 `make verify`; archive the change
