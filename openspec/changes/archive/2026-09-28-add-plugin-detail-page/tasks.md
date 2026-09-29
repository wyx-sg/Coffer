## 1. Backend

- [x] 1.1 Read a plugin package's components with descriptions (`plugin_contents.py`, `FsPluginDetailReader.read_contents`)
- [x] 1.2 `AgentPluginService.get_plugin` — listing row, marketplace source, install dir, contents; unknown id is `PluginNotFound`
- [x] 1.3 `GET /api/v1/agents/{uid}/plugins/{plugin_id}` and the contract schemas; frontend codegen
- [x] 1.4 `coffer agent plugin show <agent> <plugin_id> [--json]`

## 2. Web UI

- [x] 2.1 Remove the Plugins table's row expansion; the plugin name links to the detail page
- [x] 2.2 `AgentPluginPage` at `/agents/:uid/plugins/:pluginId` with back link, enable switch, uninstall, install dir open / reveal and contents
- [x] 2.3 Drop the i18n keys only the expansion used; add the page's en/zh strings

## 3. Tests and docs

- [x] 3.1 Unit, route, CLI and page tests with acceptance markers
- [x] 3.2 Agents guide and CLI reference
