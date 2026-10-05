## 1. Backend

- [x] 1.1 `FileText` in `domain/agent/config_files.py`
- [x] 1.2 `ConfigFileStore.read_preview` (1 MiB cap, binary detection) on the port and the adapter
- [x] 1.3 `AgentConfigFileService.read_preview` addressed by key and listed child
- [x] 1.4 `GET /api/v1/agents/{uid}/config-files/{key}/content`
- [x] 1.5 Route tests for the three scenarios; the auth.json scenario on the new route
- [x] 1.6 `make contracts`

## 2. Web UI

- [x] 2.1 API client and `useAgentConfigFilePreview` hook
- [x] 2.2 Preview dialog on the Config files tab, opened from a row's name
- [x] 2.3 i18n (en, zh); component and acceptance tests

## 3. Docs

- [x] 3.1 `agent-registry` Purpose and `data-model.md` constraints
- [x] 3.2 `docs-site/guides/agents.md` and its `zh/` twin
