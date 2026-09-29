## Why

Native memory projection into `CLAUDE.md` / `AGENTS.md` was retired long ago, yet the config-files editor still scans every instructions file for the old `<!-- coffer:memory` marker and shows a notice calling the block a leftover that is safe to delete. The notice keeps a retired mechanism alive in the wire contract and the UI for a block users have long since removed or never had.

## What Changes

- The config-file read no longer reports `memory_block`; `ConfigFileContent` loses the field in the service, the REST response and the contract.
- The Config files editor no longer shows the legacy memory-block notice.
- The requirement "Annotate a leftover memory-projection block as safe to delete" is removed from `agent-registry`.

## Capabilities

### New Capabilities

### Modified Capabilities
- `agent-registry`: removes "Annotate a leftover memory-projection block as safe to delete".

## Impact

- `backend/coffer/application/agent/config_file_service.py`, `backend/coffer/surfaces/http/agent_config_routes.py`.
- `openspec/specs/agent-registry/contracts/api.openapi.yaml` and `data-model.md`; `frontend/src/lib/api/generated/agent-registry.ts` regenerated.
- `frontend/src/lib/hooks/useConfigEditorState.ts`, `frontend/src/components/agents/AgentConfigFilesEditor.tsx`, `ConfigEditorPane.tsx`; the `agents.config.memoryBlockNotice` i18n string.
- Docs: `docs-site/guides/agents.md`.
