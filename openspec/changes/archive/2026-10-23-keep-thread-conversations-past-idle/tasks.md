## 1. Behaviour

- [x] 1.1 `rolls_over_when_idle`: roll over only when the conversation thread id is `""`; use it in `ensure_conversation` and `predict_conversation`
- [x] 1.2 Tests: a group thread idle past the hours keeps its conversation; a thread-less group rolls over

## 2. Contract and docs

- [x] 2.1 Spec channels "Open a new conversation after an idle period" and its scenarios; data-model field note
- [x] 2.2 ADR `idle-time-rolls-over-a-direct-chat-but-never-a-thread`; trim lifetime out of `channel-conversation-identity`
- [x] 2.3 docs-site guides/channels and architecture/chat, en + zh
- [x] 2.4 Settings hint text, en + zh
