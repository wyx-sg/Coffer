## 1. Bug fixes

- [x] 1.1 Telegram reactions only from the Bot API's allowed list; completion 👌
- [x] 1.2 Tool progress keeps updating after text (test first for 1.4)
- [x] 1.3 Fence-aware chunking
- [x] 1.4 Paragraph break between text either side of a tool call
- [x] 1.5 Silent Telegram status message and continuation chunks

## 2. Status line

- [x] 2.1 `TurnStatus` + `ReplyText`; renderer split into status / surface / finish
- [x] 2.2 Header ticks on the keep-alive cadence; narration to the status line
- [x] 2.3 Transports clip the answer, never the status block
- [x] 2.4 `show_steps` setting: config, binding, CLI

## 3. Reactions

- [ ] 3.1 `ReactionSet` capability; received → working → done / failed / stopped

## 4. Completion ping

- [ ] 4.1 `notify_after_seconds` setting: config, binding, CLI, REST
- [ ] 4.2 Ping where the answer closed a persisting surface; group mention
- [ ] 4.3 Telegram name-aware mention on every group answer
- [ ] 4.4 Edit channel dialog: show steps + ping threshold, en/zh

## 5. Channel-turn instructions

- [ ] 5.1 Channel note names platform, chat kind, render facts; answer shape; `NEEDS YOU:`

## 6. Rendering

- [ ] 6.1 Telegram `## Details` collapsed
- [ ] 6.2 SeaTalk tables → bullets + CSV; long code → files
- [ ] 6.3 Continuations numbered `(2/3)`

## 7. `NEEDS YOU:` buttons

- [ ] 7.1 Question message with option buttons; owner tap enters as the owner's reply

## 8. Telegram rich draft

- [ ] 8.1 `sendRichMessageDraft` with `<tg-thinking>` in direct chats; latched fallback

## 9. SeaTalk summary card

- [ ] 9.1 Outcome card with Details / As file

## 10. Docs and archive

- [ ] 10.1 Channels guides, CLI reference, chat architecture page, data model
- [ ] 10.2 Archive the change
