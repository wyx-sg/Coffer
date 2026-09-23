## 1. Requirement text

- [x] 1.1 web-ui: `coffer audit list` in "Keep the command-line record readers"; clicked-then-settled controls in "Let the user choose when the daemon runs"
- [x] 1.2 channels: scope-bounded sticky agent in "Route the owner's messages into a turn-platform conversation" and "Answer the conversation commands from any paired chat"; list, detail page, CLI groups and ref handling in "Manage channels from the Channels page and the CLI"
- [x] 1.3 channels/seatalk: character split before rendering and byte split after it in "Render replies as SeaTalk markdown"
- [x] 1.4 chat and provider-switching: the Default option and the no-`text`-model rule in the model picker requirements
- [x] 1.5 daemon: `service status` on a host with no login service
- [x] 1.6 resource-framework: audit actor vocabulary in "Audit every lifecycle change"

## 2. Data models and contracts

- [x] 2.1 internal-engine data model: blank curation owner normalised on the curation-owner route
- [x] 2.2 resource-framework data model and contract: audit actor list
- [x] 2.3 skill-manager data model: built-in seed emits `skill_imported` / `skill_updated`; `make_agent_kind` takes `on_enabled_changed`
- [x] 2.4 agent-registry data model: `on_enabled_changed` hook wiring
- [x] 2.5 vault-sync data model: `backend/tests/contract/...` path

## 3. Tests

- [x] 3.1 `ModelPicker.test.tsx` asserts the Default option leads the list
- [x] 3.2 `test_agent_scope.py` carries the `/new starts a fresh conversation` marker for the scope-bounded case

## 4. Close

- [x] 4.1 Run `make verify`
- [x] 4.2 Archive the change (`npx openspec archive refine-spec-wording --yes`)
