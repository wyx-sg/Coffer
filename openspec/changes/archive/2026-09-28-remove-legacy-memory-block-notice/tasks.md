## 1. Backend

- [x] 1.1 `application/agent/config_file_service.py`: delete `MEMORY_BLOCK_MARKER` and `ConfigFileContent.memory_block`
- [x] 1.2 `surfaces/http/agent_config_routes.py`: drop `memory_block` from the response model
- [x] 1.3 Tests: remove the `memory_block` assertions and the marker-detection cases, including the acceptance-marked test for the removed scenario

## 2. Frontend

- [x] 2.1 Regenerate `lib/api/generated/agent-registry.ts` from the updated contract
- [x] 2.2 `useConfigEditorState.ts`, `AgentConfigFilesEditor.tsx`, `ConfigEditorPane.tsx`: remove the flag and the notice
- [x] 2.3 i18n: remove `agents.config.memoryBlockNotice` from `en.json` and `zh.json`
- [x] 2.4 Tests: remove the notice cases from `ConfigEditorPane.test.tsx`, `AgentConfigFilesEditor.test.tsx` and `AgentConfigFilesEditor.acceptance.test.tsx`

## 3. Specs and docs

- [x] 3.1 Delta removing the requirement from `agent-registry`
- [x] 3.2 `openspec/specs/agent-registry/contracts/api.openapi.yaml` and `data-model.md`
- [x] 3.3 `docs-site/guides/agents.md`: drop the memory-block paragraph

## 4. Close

- [x] 4.1 Run `make verify`
- [x] 4.2 Archive the change in the same PR
