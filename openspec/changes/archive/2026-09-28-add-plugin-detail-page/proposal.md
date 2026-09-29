## Why

The agent's Plugins tab expands each row inline to show a plugin's manifest detail and bundled components. The expansion crowds the table, shows names only, and leaves out what a user needs to understand a plugin: where it is installed, the subagents and hooks it adds, and what each skill or command does.

## What Changes

- The Plugins table loses its row expansion; a plugin's name opens a plugin detail page at `/agents/:uid/plugins/:pluginId`.
- The detail page shows the plugin's version, author, description, homepage, marketplace and source, its install directory with open / reveal, its enabled switch and uninstall, and the skills, commands, subagents, hook events and MCP servers it contributes, with each component's description. Its back link and a successful uninstall return to the agent's Plugins tab.
- New read-only endpoint `GET /api/v1/agents/{uid}/plugins/{plugin_id}` and matching `coffer agent plugin show <agent> <plugin_id> [--json]`.

## Capabilities

### Modified Capabilities

- `agent-registry`: adds "Read one installed plugin's detail read-only"; "Expose every agent operation through REST, CLI and the Agents page" replaces the Plugins row expansion with the plugin detail page.

## Impact

- Backend: `infrastructure/agent/plugin_contents.py` (new), `plugin_bundle.py`, `application/agent/plugin_service.py` / `plugin_views.py`, `surfaces/http/agent_workspace_routes.py`, `surfaces/cli/agent_workspace_cmd.py`.
- Contract: `openspec/specs/agent-registry/contracts/api.openapi.yaml` (`getAgentPlugin`, `PluginDetail`, `PluginComponent`).
- Frontend: `AgentPluginsTab`, new `AgentPluginPage` and its components, router, API client, hooks, en/zh strings.
- Docs: `docs-site/guides/agents.md`, CLI reference.
