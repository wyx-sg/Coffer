## 1. Binding

- [x] 1.1 `AgentConfig` carries `effort` and `tier_models` in place of `fast_model`
- [x] 1.2 Migration 0108 moves `fast_model` into the Haiku tier and strips the key
- [x] 1.3 `PATCH /agents/{uid}` and `coffer agent edit` set and clear effort and tiers

## 2. Projection

- [x] 2.1 Claude Code: top-level `model` / `effortLevel`, tier pins, `modelPicker`, local compatibility keys; delete the deprecated keys on every write
- [x] 2.2 Codex: catalogue window, auto-compact limit and effort levels; `model_reasoning_effort` only for a model with levels
- [x] 2.3 De-projection removes every key Coffer wrote and keeps what the user changed since
- [x] 2.4 Curated models record a context window and effort levels over REST

## 3. Tests and docs

- [x] 3.1 Unit, integration and migration tests
- [x] 3.2 Providers guide and CLI reference
