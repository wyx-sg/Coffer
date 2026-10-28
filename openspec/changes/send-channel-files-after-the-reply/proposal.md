## Why

A SeaTalk group reply with two CSV files arrived as five messages: each file,
then a text message with its caption, then the reply card. SeaTalk cannot put a
file in a card or a caption on a file, but the caption messages are Coffer's
own. Options are argued in ADR `a-reply-names-its-files-and-they-follow-it`.

## What Changes

- The reply goes out first; the agent's `MEDIA:` files are uploaded after it.
- A transport declares `media_captions` when its file message carries a
  caption (Telegram). Without it (SeaTalk), the reply ends with one
  `📎 name — caption` line per file when any file has a caption, and no text
  message follows a file.
- A file that fails to upload is said in a short follow-up line.

## Impact

- `application/channel/turn_media.py`, `turn_finish.py`;
  `domain/channel/envelopes.py`; `infrastructure/channel/seatalk.py`,
  `seatalk_media.py`, `telegram_caps.py`.
- Specs `channels` and `channels/seatalk`, edited directly (`skip_specs: true`).
- docs-site guides `channels.md`, `channels-seatalk.md` (en, zh); design canvas
  for SeaTalk channel messages.
