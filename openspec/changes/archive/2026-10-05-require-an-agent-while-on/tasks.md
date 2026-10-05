## 1. Backend

- [x] 1.1 `validate_scope` rejects `{"agents": []}` for every kind (422 `SCOPE_INVALID`)
- [x] 1.2 Channel scope validator and `_validate_default_agent` drop the empty-list exemption; `wanted.py` loses its dormant branch and comments
- [x] 1.3 Provider: delete `starts_dormant` and `_provider_default_scope`
- [x] 1.4 Custom-tool group creation, skill adoption and MCP import refuse an empty agent list
- [x] 1.5 One-time startup step in `reach_store.py` rewrites `agents: []` records to `enabled: false, agents: null`, called from the app lifespan
- [x] 1.6 Schema docstrings + regenerated OpenAPI / TS types; backend tests updated

## 2. Web UI

- [x] 2.1 Reach panel: last ticked agent cannot be unticked (hint: turn it off); switching to Chosen agents saves nothing until one is ticked
- [x] 2.2 Draft reach pickers (add MCP, add skill, adopt, import, custom group) refuse Chosen agents with none ticked
- [x] 2.3 Bulk reach: a row left with no agent is switched off, shown so in the preview
- [x] 2.4 Delete `scope.noneSelected`, `scope.dormant`, `isDormantHere`'s empty-list case and the row labels; tests updated

## 3. Specs and docs

- [x] 3.1 Specs: resource-framework, vault-sync, skill-manager, provider-switching, channels, web-ui
- [x] 3.2 docs-site architecture + guides (en + zh), ADRs `per-agent-resource-scope`, `reach-is-machine-local-stored-by-uid-never-synced`
- [x] 3.3 UI design canvas boards that show "No agent selected"
