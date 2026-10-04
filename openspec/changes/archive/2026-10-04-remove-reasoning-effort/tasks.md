## 1. Backend

- [x] 1.1 Effort is removed from the agent config, the provider's curated models, the model binding, both projections and the model catalogue; retired keys in vault files are dropped on read
- [x] 1.2 The Claude `--effort` option, the Codex `turn/start` effort and the SDK `EffortLevel` reader are removed
- [x] 1.3 Channel `/model` is one step, and the effort cards and the thread's remembered effort are removed
- [x] 1.4 Migration 0147 drops `channel_thread_conversations.preferred_effort` and the `effort` key of stored conversation configs
- [x] 1.5 REST schemas drop `effort`, `efforts`, `default_effort` and `effort_levels`; contracts regenerated

## 2. Frontend

- [x] 2.1 The Chat composer's effort picker, the Change model dialog's Effort field and the Overview Effort row are removed
- [x] 2.2 The matching i18n keys are deleted in English and Chinese

## 3. Specs and docs

- [x] 3.1 Spec deltas for agent-registry (and its claude-code and codex children), provider-switching, channels, chat, experimental-features and web-ui
- [x] 3.2 `data-model.md` for agent-registry, provider-switching, channels and chat
- [x] 3.3 `docs-site` guides, reference and architecture pages (English and Chinese)
- [x] 3.4 ADRs that described reasoning effort are rewritten in place
