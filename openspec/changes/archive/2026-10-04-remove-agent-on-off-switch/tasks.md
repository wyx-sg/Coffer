## 1. Backend

- [x] 1.1 The agent kind declares `toggleable=False` and drops its `on_enabled_changed` hook
- [x] 1.2 A non-toggleable kind's resource reads enabled whatever its stored reach holds
- [x] 1.3 Every "skip a disabled agent" branch is removed from skill delivery, memory aggregation, the model catalogue, chat, provider projection and attention

## 2. Frontend

- [x] 2.1 The Off row state, Turn on / Turn off actions, Off pill and switch-off pending states are removed
- [x] 2.2 The matching i18n keys are deleted in English and Chinese; `PROVIDER_DOES_NOT_REACH_AGENT` is reworded

## 3. Specs and docs

- [x] 3.1 Spec deltas for agent-registry, skill-manager, memory, chat, provider-switching and resource-framework
- [x] 3.2 `docs-site` guides, architecture pages and reference pages (English and Chinese) say disconnect where they said turn off
- [x] 3.3 ADRs that described switching an agent off are rewritten in place
