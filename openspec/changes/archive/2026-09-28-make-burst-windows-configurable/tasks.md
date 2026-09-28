## 1. Settings

- [x] 1.1 `wait_after_text_seconds` / `wait_after_forward_seconds` on the channel config (0–60, defaults 1.5 / 5), carried on `ChannelBinding`
- [x] 1.2 `inbound_burst.window_for` picks the window per message from the binding
- [x] 1.3 `coffer channel register|set --wait-after-text/--wait-after-forward`
- [x] 1.4 Edit channel dialog: Message batching fields, en/zh

## 2. Tests and docs

- [x] 2.1 Config, CLI and burst tests with acceptance markers
- [x] 2.2 Channels guide, CLI reference, data model
