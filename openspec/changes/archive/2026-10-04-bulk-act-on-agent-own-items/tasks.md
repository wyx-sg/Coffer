## 1. Shared selection

- [x] 1.1 `AgentKindTab` takes `bulk`: select-all header, row checkboxes through `KindRow`'s `leading`, a selection bar in place of the search row
- [x] 1.2 `useBulkRun` runs one request per item in sequence and collects the failures; `useBulkDialog` keeps a bulk confirmation open on a partial result with Retry for the failures

## 2. Skills, MCP servers, Plugins

- [x] 2.1 Skills: Adopt with a shared reach, Delete…
- [x] 2.2 MCP servers: Adopt with default secret references (request body shared with the adopt dialog), Remove…; read-only entries are not selectable
- [x] 2.3 Plugins: Enable, Disable, Uninstall…

## 3. Specs, docs, tests

- [x] 3.1 Spec deltas for agent-registry and skill-manager
- [x] 3.2 Tests with acceptance markers for each tab, and for the shared selection
- [x] 3.3 Agents guide (en, zh)
