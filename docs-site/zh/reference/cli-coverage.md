---
title: CLI 覆盖表
description: 每一个网页界面和桌面应用操作、它调用的接口、对应的 coffer 命令和覆盖它的测试。
---

# CLI 覆盖表 {#cli-coverage}

人在 Coffer 页面或桌面应用里能做的每一个管理操作，都有一个调用同一接口的 `coffer` 命令，Agent 也能直接完成。本表由 CLI 的登记表生成；网页界面调用的接口没有命令时，`make lint` 会失败。

## `coffer agent` {#agent}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Agents · Connect (register) | `POST /agents` | `coffer agent add` | `test_cli_parity.py` |
| Agents · Config tab | `GET /agents/{uid}/config-files` | `coffer agent config-files` | `test_cli_parity.py` |
| Agents · Connect | `POST /agents/{uid}/coffer-connection` | `coffer agent connect` | `test_cli_parity.py` |
| Agents · the Coffer connection's state | `GET /agents/{uid}/coffer-connection` | `coffer agent connection` | `test_cli_parity.py` |
| Agents · Disconnect | `DELETE /agents/{uid}/coffer-connection` | `coffer agent disconnect` | `test_cli_parity.py` |
| Agents · Hooks tab | `GET /agents/{uid}/hooks` | `coffer agent hooks` | `test_cli_parity.py` |
| Agents · list | `GET /agents` | `coffer agent list` | `test_cli_parity.py` |
| Agents · MCP tab · Move into Coffer | `POST /agents/{uid}/mcp-entries/{entry}/adopt` | `coffer agent mcp-entry adopt` | `test_cli_parity.py` |
| Agents · MCP tab | `GET /agents/{uid}/mcp-entries` | `coffer agent mcp-entry list` | `test_cli_parity.py` |
| Agents · MCP tab · remove | `DELETE /agents/{uid}/mcp-entries/{entry}` | `coffer agent mcp-entry remove` | `test_cli_parity.py` |
| Agents · MCP tab · open an entry | `GET /agents/{uid}/mcp-entries/{entry}` | `coffer agent mcp-entry show` | `test_cli_parity.py` |
| Command line only · import several agents' entries at once | `POST /agents/mcp-import/apply` | `coffer agent mcp-import apply` | `test_cli_parity.py` |
| MCP servers · first-run · the agents' own servers | `POST /agents/mcp-import/plan` | `coffer agent mcp-import plan` | `test_cli_parity.py` |
| Agents · model picker | `GET /agent-providers/{agent_key}/models` | `coffer agent models` | `test_cli_parity.py` |
| Agents · Memory tab · files | `GET /agents/{uid}/native-memory/files` | `coffer agent native-memory files` | `test_cli_parity.py` |
| Agents · Memory tab | `GET /agents/{uid}/native-memory` | `coffer agent native-memory list` | `test_cli_parity.py` |
| Agents · Plugins tab | `GET /agents/{uid}/plugins` | `coffer agent plugin list` | `test_cli_parity.py` |
| Agents · Plugins tab · switch on or off | `PATCH /agents/{uid}/plugins/{plugin_id}` | `coffer agent plugin set` | `test_cli_parity.py` |
| Agents · Plugins tab · open | `GET /agents/{uid}/plugins/{plugin_id}` | `coffer agent plugin show` | `test_cli_parity.py` |
| Agents · Plugins tab · Uninstall | `DELETE /agents/{uid}/plugins/{plugin_id}` | `coffer agent plugin uninstall` | `test_cli_parity.py` |
| Agents · model providers per type | `GET /agent-providers` | `coffer agent providers` | `test_cli_parity.py` |
| Conversations · every agent's sessions | `GET /agent-sessions` | `coffer agent session all` | `test_cli_parity.py` |
| Agents · Sessions tab · Delete | `DELETE /agents/{uid}/sessions/{session_id}` | `coffer agent session delete` | `test_cli_parity.py` |
| Agents · Sessions tab | `GET /agents/{uid}/sessions` | `coffer agent session list` | `test_cli_parity.py` |
| Agents · Sessions tab · Rename | `PATCH /agents/{uid}/sessions/{session_id}` | `coffer agent session rename` | `test_cli_parity.py` |
| Agents · open an agent | `GET /agents/{uid}` | `coffer agent show` | `test_cli_parity.py` |
| Agents · one row per agent type | `GET /agents/types` | `coffer agent types` | `test_cli_parity.py` |
| Agents · Skills tab · Move into Coffer | `POST /agents/{uid}/unmanaged-skills/{skill}/adopt` | `coffer agent unmanaged-skill adopt` | `test_cli_parity.py` |
| Agents · Skills tab · Delete | `DELETE /agents/{uid}/unmanaged-skills/{skill}` | `coffer agent unmanaged-skill delete` | `test_cli_parity.py` |
| Agents · Skills tab · files | `GET /agents/{uid}/unmanaged-skills/{skill}/files` | `coffer agent unmanaged-skill files` | `test_cli_parity.py` |
| Agents · Skills tab · not managed | `GET /agents/{uid}/unmanaged-skills` | `coffer agent unmanaged-skill list` | `test_cli_parity.py` |
| Agents · Skills tab · open | `GET /agents/{uid}/unmanaged-skills/{skill}` | `coffer agent unmanaged-skill show` | `test_cli_parity.py` |
| Agents · edit the config dir or model | `PATCH /agents/{uid}` | `coffer agent update` | `test_cli_parity.py` |

## `coffer app` {#app}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Settings · About · check automatically | `POST /desktop/requests` | `coffer app update auto-check` | `test_approval_cli.py` |
| Settings · About · Check for updates | `POST /desktop/requests` | `coffer app update check` | `test_approval_cli.py` |
| Settings · About · Install and restart | `POST /desktop/requests` | `coffer app update install` | `test_approval_cli.py` |
| Settings · About · update status | `POST /desktop/requests` | `coffer app update status` | `test_approval_cli.py` |

## `coffer approval` {#approval}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Secrets · approvals · Approve (desktop app, after Touch ID or the login password) | `POST /desktop/requests` | `coffer approval approve` | `test_approval_cli.py` |
| Secrets · approvals · Approve (desktop app, after Touch ID or the login password) | `GET /desktop/requests/{request_id}` | `coffer approval approve` | `test_approval_cli.py` |
| Secrets · approvals · Approve (desktop app, after Touch ID or the login password) | `POST /secrets/approvals/approve` | `coffer approval approve` | `test_approval_cli.py` |
| Secrets · approvals · Approve (desktop app, after Touch ID or the login password) | `POST /secrets/approvals/{approval_id}/approve` | `coffer approval approve` | `test_approval_cli.py` |
| Secrets · approvals · Ask again | `POST /secrets/approvals/{approval_id}/ask-again` | `coffer approval ask-again` | `test_approval_cli.py` |
| Secrets · approvals · list (Secrets page, Overview) | `GET /secrets/approvals` | `coffer approval list` | `test_approval_cli.py` |
| Secrets · approvals · Reject | `POST /secrets/approvals/reject` | `coffer approval reject` | `test_approval_cli.py` |
| Secrets · approvals · Reject | `POST /secrets/approvals/{approval_id}/reject` | `coffer approval reject` | `test_approval_cli.py` |
| Secrets · approvals · open one | `GET /secrets/approvals/{approval_id}` | `coffer approval show` | `test_approval_cli.py` |

## `coffer attention` {#attention}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Overview · Ignore | `PUT /attention/ignored/{key}` | `coffer attention ignore` | `test_cli_parity.py` |
| Overview · needs you | `GET /attention` | `coffer attention list` | `test_cli_parity.py` |
| Overview · ignored · Show again | `DELETE /attention/ignored/{key}` | `coffer attention unignore` | `test_cli_parity.py` |

## `coffer channel` {#channel}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Channels · Add | `POST /resources` | `coffer channel add` | `test_cli_parity.py` |
| Channels · Add · check the credentials | `POST /channels/validate-credentials` | `coffer channel check-credentials` | `test_cli_parity.py` |
| Channels · Delete | `DELETE /resources/{uid}` | `coffer channel delete` | `test_cli_parity.py` |
| Channels · switch off | `POST /resources/{uid}/disable` | `coffer channel disable` | `test_cli_parity.py` |
| Channels · switch on | `POST /resources/{uid}/enable` | `coffer channel enable` | `test_cli_parity.py` |
| Channels · list | `GET /resources` | `coffer channel list` | `test_cli_parity.py` |
| Channels · Send a test message | `POST /channels/{uid}/notify` | `coffer channel notify` | `test_cli_parity.py` |
| Channels · People · cancel the code | `DELETE /channels/{uid}/pairing-code` | `coffer channel pairing cancel` | `test_cli_parity.py` |
| Channels · People · Add a person (pairing code) | `POST /channels/{uid}/pairing-code` | `coffer channel pairing start` | `test_cli_parity.py` |
| Channels · People · Remove | `DELETE /channels/{uid}/people/{sender_id}` | `coffer channel person remove` | `test_cli_parity.py` |
| Channels · Reach | `PUT /resources/{uid}/scope` | `coffer channel reach` | `test_cli_parity.py` |
| Channels · Restart | `POST /channels/{uid}/restart` | `coffer channel restart` | `test_cli_parity.py` |
| Channels · open a channel | `GET /resources/{uid}` | `coffer channel show` | `test_cli_parity.py` |
| Channels · a channel's state | `GET /channels/{uid}/status` | `coffer channel status` | `test_cli_parity.py` |
| Channels · edit a channel | `PATCH /resources/{uid}` | `coffer channel update` | `test_cli_parity.py` |

## `coffer cli` {#cli}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| CLIs · Add CLI | `POST /clis` | `coffer cli add` | `test_cli_parity.py` |
| CLIs · Check again | `POST /clis/{command}/check` | `coffer cli check` | `test_cli_parity.py` |
| CLIs · Check all | `POST /clis/check` | `coffer cli check-all` | `test_cli_parity.py` |
| CLIs · list | `GET /clis` | `coffer cli list` | `test_cli_list_cmd.py` |
| CLIs · Add CLI · preview | `POST /clis/preview` | `coffer cli preview` | `test_cli_parity.py` |
| CLIs · Remove | `DELETE /clis/{command}` | `coffer cli remove` | `test_cli_parity.py` |
| CLIs · open a tool | `GET /clis/{command}` | `coffer cli show` | `test_cli_parity.py` |
| CLIs · edit a tool | `PATCH /clis/{command}` | `coffer cli update` | `test_cli_parity.py` |

## `coffer conversation` {#conversation}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Conversations · Delete | `DELETE /chat/conversations/{id}` | `coffer conversation delete` | `test_cli_parity.py` |
| Conversations · Stop | `POST /chat/conversations/{id}/interrupt` | `coffer conversation interrupt` | `test_cli_parity.py` |
| Conversations · Rename | `PATCH /chat/conversations/{id}` | `coffer conversation rename` | `test_cli_parity.py` |

## `coffer custom-tool` {#custom-tool}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Custom tools · Environments · add | `POST /custom-tools/{name}/environments` | `coffer custom-tool env add` | `test_custom_tool_cli.py` |
| Custom tools · Environments · delete | `DELETE /custom-tools/{name}/environments/{environment}` | `coffer custom-tool env delete` | `test_custom_tool_cli.py` |
| Custom tools · Environments · switch off | `PATCH /custom-tools/{name}/environments/{environment}` | `coffer custom-tool env disable` | `test_custom_tool_cli.py` |
| Custom tools · Environments · switch on | `PATCH /custom-tools/{name}/environments/{environment}` | `coffer custom-tool env enable` | `test_custom_tool_cli.py` |
| Custom tools · Environments · list | `GET /custom-tools/{name}` | `coffer custom-tool env list` | `test_custom_tool_cli.py` |
| Custom tools · Environments · set a header or bind a secret | `PATCH /custom-tools/{name}/environments/{environment}` | `coffer custom-tool env set-header` | `test_custom_tool_cli.py` |
| Custom tools · Environments · set a variable | `PATCH /custom-tools/{name}/environments/{environment}` | `coffer custom-tool env set-var` | `test_custom_tool_cli.py` |
| Custom tools · Environments · remove a header | `PATCH /custom-tools/{name}/environments/{environment}` | `coffer custom-tool env unset-header` | `test_custom_tool_cli.py` |
| Custom tools · Environments · remove a variable | `PATCH /custom-tools/{name}/environments/{environment}` | `coffer custom-tool env unset-var` | `test_custom_tool_cli.py` |
| Custom tools · Environments · edit (URL, name, timeout, description) | `PATCH /custom-tools/{name}/environments/{environment}` | `coffer custom-tool env update` | `test_custom_tool_cli.py` |
| Custom tools · add a group (by hand or from an OpenAPI document) | `POST /custom-tools` | `coffer custom-tool group create` | `test_custom_tool_cli.py` |
| Custom tools · add a group (by hand or from an OpenAPI document) | `POST /custom-tools/openapi` | `coffer custom-tool group create` | `test_custom_tool_cli.py` |
| Custom tools · delete a group | `DELETE /custom-tools/{name}` | `coffer custom-tool group delete` | `test_custom_tool_cli.py` |
| Custom tools · switch a group off | `POST /resources/{uid}/disable` | `coffer custom-tool group disable` | `test_custom_tool_cli.py` |
| Custom tools · switch a group on | `POST /resources/{uid}/enable` | `coffer custom-tool group enable` | `test_custom_tool_cli.py` |
| Custom tools · list groups | `GET /custom-tools` | `coffer custom-tool group list` | `test_custom_tool_cli.py` |
| Custom tools · set a group's reach | `PUT /resources/{uid}/scope` | `coffer custom-tool group reach` | `test_custom_tool_cli.py` |
| Custom tools · open a group | `GET /custom-tools/{name}` | `coffer custom-tool group show` | `test_custom_tool_cli.py` |
| Custom tools · edit a group | `PATCH /custom-tools/{name}` | `coffer custom-tool group update` | `test_custom_tool_cli.py` |
| Custom tools · read an OpenAPI document | `POST /custom-tools/openapi` | `coffer custom-tool import read` | `test_custom_tool_cli.py` |
| Custom tools · apply a re-import | `POST /custom-tools/{name}/reimport` | `coffer custom-tool reimport apply` | `test_custom_tool_cli.py` |
| Custom tools · preview a re-import | `POST /custom-tools/{name}/reimport/preview` | `coffer custom-tool reimport preview` | `test_custom_tool_cli.py` |
| Custom tools · add a tool | `POST /custom-tools/{name}/tools` | `coffer custom-tool tool add` | `test_custom_tool_cli.py` |
| Custom tools · delete a tool | `DELETE /custom-tools/{name}/tools/{tool}` | `coffer custom-tool tool delete` | `test_custom_tool_cli.py` |
| Custom tools · switch a tool off | `PATCH /custom-tools/{name}/tools/{tool}` | `coffer custom-tool tool disable` | `test_custom_tool_cli.py` |
| Custom tools · switch a tool on | `PATCH /custom-tools/{name}/tools/{tool}` | `coffer custom-tool tool enable` | `test_custom_tool_cli.py` |
| Custom tools · a group's Tools tab | `GET /custom-tools/{name}` | `coffer custom-tool tool list` | `test_custom_tool_cli.py` |
| Custom tools · open a tool | `GET /custom-tools/{name}` | `coffer custom-tool tool show` | `test_custom_tool_cli.py` |
| Custom tools · test a saved tool | `POST /custom-tools/{name}/tools/{tool}/preview` | `coffer custom-tool tool test` | `test_custom_tool_cli.py` |
| Custom tools · test a saved tool | `POST /custom-tools/{name}/tools/{tool}/test` | `coffer custom-tool tool test` | `test_custom_tool_cli.py` |
| Custom tools · test a tool being edited | `POST /custom-tools/{name}/preview` | `coffer custom-tool tool test-draft` | `test_custom_tool_cli.py` |
| Custom tools · test a tool being edited | `POST /custom-tools/{name}/test` | `coffer custom-tool tool test-draft` | `test_custom_tool_cli.py` |
| Custom tools · test a request before its group is saved | `POST /custom-tools/test` | `coffer custom-tool tool test-unsaved` | `test_custom_tool_cli.py` |
| Custom tools · edit a tool | `PATCH /custom-tools/{name}/tools/{tool}` | `coffer custom-tool tool update` | `test_custom_tool_cli.py` |

## `coffer daemon` {#daemon}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Settings · Daemon · port | `PUT /daemon/port` | `coffer daemon port set` | `test_cli_parity.py` |
| Settings · Daemon · port | `GET /daemon/port` | `coffer daemon port show` | `test_cli_parity.py` |
| Settings · Daemon · Restart daemon | `POST /daemon/restart` | `coffer daemon reload` | `test_cli_parity.py` |
| Settings · Daemon · start at login | `PUT /daemon/residency` | `coffer daemon residency set` | `test_cli_parity.py` |
| Settings · Daemon · start at login | `GET /daemon/residency` | `coffer daemon residency show` | `test_cli_parity.py` |
| Settings · Daemon · Rotate token | `POST /daemon/rotate-token` | `coffer daemon rotate-token` | `test_cli_parity.py` |
| Setup · Check again | `POST /daemon/setup/check` | `coffer daemon setup-check` | `test_cli_parity.py` |
| Settings · Daemon · status | `GET /daemon/status` | `coffer daemon status` | `test_daemon_status_cmd.py` |
| Settings · Daemon · passes in flight | `GET /upkeep/runs` | `coffer daemon status` | `test_daemon_status_cmd.py` |
| Settings · Daemon · upgrade | `GET /daemon/upgrade` | `coffer daemon upgrade` | `test_cli_parity.py` |
| Settings · Daemon · passes in flight | `GET /upkeep/runs` | `coffer daemon upkeep` | `test_cli_parity.py` |

## `coffer knowledge` {#knowledge}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Knowledge · recent changes | `GET /knowledge/changes` | `coffer knowledge changes` | `test_cli_parity.py` |
| Knowledge · collections | `GET /knowledge/collections` | `coffer knowledge collections` | `test_cli_parity.py` |
| Knowledge · New collection | `POST /knowledge/collections` | `coffer knowledge create` | `test_cli_parity.py` |
| Knowledge · Delete | `DELETE /resources/{uid}` | `coffer knowledge delete` | `test_cli_parity.py` |
| Knowledge · edit a collection's description | `PUT /knowledge/collections/{uid}/description` | `coffer knowledge describe` | `test_cli_parity.py` |
| Knowledge · list | `GET /resources` | `coffer knowledge list` | `test_cli_parity.py` |
| Knowledge · Undo a delete | `POST /knowledge/changes/{version}/restore` | `coffer knowledge restore` | `test_cli_parity.py` |
| Knowledge · open a collection | `GET /resources/{uid}` | `coffer knowledge show` | `test_cli_parity.py` |
| Knowledge · Tidy with an agent | `GET /knowledge/tidy-handoff` | `coffer knowledge tidy-handoff` | `test_cli_parity.py` |
| Knowledge · the tree | `GET /knowledge/tree` | `coffer knowledge tree` | `test_cli_parity.py` |
| Knowledge · edit a collection | `PATCH /resources/{uid}` | `coffer knowledge update` | `test_cli_parity.py` |
| Knowledge · Upload | `POST /knowledge/upload` | `coffer knowledge upload` | `test_cli_parity.py` |

## `coffer log` {#log}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Activity · Audit | `GET /audit` | `coffer log audit` | `test_log_cmd.py` |
| Activity · Daemon log | `GET /daemon/logs` | `coffer log daemon` | `test_log_cmd.py` |
| Activity · MCP calls | `GET /mcp/invocations` | `coffer log mcp` | `test_log_cmd.py` |
| MCP servers · Calls tab | `GET /resources/mcp_server/{uid}/invocations` | `coffer log mcp` | `test_log_cmd.py` |

## `coffer mcp` {#mcp}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| MCP servers · Add server | `POST /resources` | `coffer mcp add` | `test_cli_parity.py` |
| MCP servers · the built-in coffer server | `GET /mcp/builtin` | `coffer mcp builtin` | `test_cli_parity.py` |
| MCP servers · Overview · calls | `GET /resources/mcp_server/{uid}/invocations/summary` | `coffer mcp calls` | `test_cli_parity.py` |
| MCP servers · Delete | `DELETE /resources/{uid}` | `coffer mcp delete` | `test_cli_parity.py` |
| MCP servers · switch off | `POST /resources/{uid}/disable` | `coffer mcp disable` | `test_cli_parity.py` |
| MCP servers · switch on | `POST /resources/{uid}/enable` | `coffer mcp enable` | `test_cli_parity.py` |
| MCP servers · Tools tab · how a tool is exposed | `PATCH /resources/mcp_server/{uid}/tools/{tool}/exposure` | `coffer mcp exposure` | `test_cli_parity.py` |
| MCP servers · Tools tab · expose several | `PATCH /resources/mcp_server/{uid}/tools/exposure` | `coffer mcp exposure-all` | `test_cli_parity.py` |
| MCP servers · list | `GET /resources` | `coffer mcp list` | `test_cli_parity.py` |
| MCP servers · Reach | `PUT /resources/{uid}/scope` | `coffer mcp reach` | `test_cli_parity.py` |
| MCP servers · Log tab | `GET /resources/mcp_server/{uid}/log` | `coffer mcp server-log` | `test_cli_parity.py` |
| MCP servers · open a server | `GET /resources/{uid}` | `coffer mcp show` | `test_cli_parity.py` |
| MCP servers · a server's state | `GET /resources/mcp_server/{uid}/status` | `coffer mcp status` | `test_cli_parity.py` |
| MCP servers · Refresh tools | `POST /resources/mcp_server/{uid}/refresh` | `coffer mcp test` | `test_mcp_cmd.py` |
| MCP servers · Test | `POST /resources/mcp_server/{uid}/test` | `coffer mcp test` | `test_mcp_cmd.py` |
| MCP servers · Add server · Test | `POST /resources/mcp_server/test-config` | `coffer mcp test-config` | `test_cli_parity.py` |
| MCP servers · Tools tab · listed and unlisted | `GET /resources/mcp_server/{uid}/tiering` | `coffer mcp tiering` | `test_cli_parity.py` |
| MCP servers · Tools tab · switch off | `POST /resources/mcp_server/{uid}/capabilities/{capability_type}/disable` | `coffer mcp tool disable` | `test_cli_parity.py` |
| MCP servers · Tools tab · switch on | `POST /resources/mcp_server/{uid}/capabilities/{capability_type}/enable` | `coffer mcp tool enable` | `test_cli_parity.py` |
| MCP servers · Tools tab | `GET /resources/mcp_server/{uid}/capabilities` | `coffer mcp tools` | `test_cli_parity.py` |
| MCP servers · edit a server | `PATCH /resources/{uid}` | `coffer mcp update` | `test_cli_parity.py` |

## `coffer memory` {#memory}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Memory · Delete | `DELETE /resources/{uid}` | `coffer memory delete` | `test_cli_parity.py` |
| Memory · what agents are given | `GET /memory/partitions/{uid}/delivered` | `coffer memory delivered` | `test_cli_parity.py` |
| Memory · a partition's files | `GET /memory/partitions/{uid}/files` | `coffer memory files` | `test_cli_parity.py` |
| Memory · list | `GET /resources` | `coffer memory list` | `test_cli_parity.py` |
| Memory · a partition's notes | `GET /memory/partitions/{uid}/notes` | `coffer memory notes` | `test_cli_parity.py` |
| Memory · partitions | `GET /memory/partitions` | `coffer memory partitions` | `test_cli_parity.py` |
| Memory · what Coffer reads | `GET /memory/reading` | `coffer memory reading` | `test_cli_parity.py` |
| Memory · retired notes | `GET /memory/partitions/{uid}/retired` | `coffer memory retired` | `test_cli_parity.py` |
| Memory · open a partition | `GET /resources/{uid}` | `coffer memory show` | `test_cli_parity.py` |
| Memory · Sync now | `POST /memory/sync` | `coffer memory sync` | `test_cli_parity.py` |
| Memory · Tidy with an agent | `GET /memory/tidy-handoff` | `coffer memory tidy-handoff` | `test_cli_parity.py` |
| Memory · edit a partition | `PATCH /resources/{uid}` | `coffer memory update` | `test_cli_parity.py` |

## `coffer model` {#model}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Model providers · Add · list models | `POST /models/list-models` | `coffer model list` | `test_cli_parity.py` |
| Model providers · Add · Test | `POST /models/test-connection` | `coffer model test` | `test_cli_parity.py` |

## `coffer provider` {#provider}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Model providers · Add connection | `POST /providers` | `coffer provider add` | `test_cli_parity.py` |
| Model providers · Delete | `DELETE /providers/{uid}` | `coffer provider delete` | `test_cli_parity.py` |
| Model providers · Delete… (what it affects) | `GET /providers/{uid}/delete-preview` | `coffer provider delete-preview` | `test_cli_parity.py` |
| Model providers · Add · detect a local runtime | `POST /providers/detect-local` | `coffer provider detect-local` | `test_cli_parity.py` |
| Model providers · list | `GET /providers` | `coffer provider list` | `test_cli_parity.py` |
| Settings · Usage · Refresh prices | `PUT /providers/price-list` | `coffer provider price-list refresh` | `test_cli_parity.py` |
| Settings · Usage · price list | `GET /providers/price-list` | `coffer provider price-list show` | `test_cli_parity.py` |
| Model providers · model prices | `POST /providers/{uid}/prices` | `coffer provider prices` | `test_cli_parity.py` |
| Model providers · open a connection | `GET /providers/{uid}` | `coffer provider show` | `test_cli_parity.py` |
| Agents · switch model · Switch | `POST /providers/model-switch/apply` | `coffer provider switch apply` | `test_cli_parity.py` |
| Agents · switch model · review | `POST /providers/model-switch/preview` | `coffer provider switch preview` | `test_cli_parity.py` |
| Model providers · Use for transcription | `POST /providers/{uid}/transcribe-default` | `coffer provider transcribe-default` | `test_cli_parity.py` |
| Model providers · edit a connection | `PATCH /providers/{uid}` | `coffer provider update` | `test_cli_parity.py` |

## `coffer proxy` {#proxy}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Agents · proxy key | `GET /proxy/tokens/{agent_uid}/hint` | `coffer proxy hint` | `test_cli_parity.py` |
| Agents · Rotate proxy key | `POST /proxy/tokens/{agent_uid}/rotate` | `coffer proxy rotate` | `test_cli_parity.py` |
| Model providers · local proxy | `GET /proxy/status` | `coffer proxy status` | `test_cli_parity.py` |

## `coffer resource` {#resource}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| every page · Add | `POST /resources` | `coffer resource add` | `test_cli_parity.py` |
| every page · Delete | `DELETE /resources/{uid}` | `coffer resource delete` | `test_cli_parity.py` |
| every page · switch off | `POST /resources/{uid}/disable` | `coffer resource disable` | `test_cli_parity.py` |
| every page · switch on | `POST /resources/{uid}/enable` | `coffer resource enable` | `test_cli_parity.py` |
| every page · its list | `GET /resources` | `coffer resource list` | `test_cli_parity.py` |
| every page · set Reach | `PUT /resources/{uid}/scope` | `coffer resource reach set` | `test_cli_parity.py` |
| every page · Reach | `GET /resources/{uid}/scope` | `coffer resource reach show` | `test_cli_parity.py` |
| every page · open one | `GET /resources/{uid}` | `coffer resource show` | `test_cli_parity.py` |
| every page · edit | `PATCH /resources/{uid}` | `coffer resource update` | `test_cli_parity.py` |

## `coffer secret` {#secret}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Settings · Secrets · Back up the master key (desktop app, Touch ID) | `POST /desktop/requests` | `coffer secret backup-key` | `test_approval_cli.py` |
| Secrets · Delete | `DELETE /secrets/{ref}` | `coffer secret delete` | `test_cli_parity.py` |
| Secrets · Edit label and description | `PUT /secrets/notes` | `coffer secret describe` | `test_cli_parity.py` |
| Secrets · Not a secret | `POST /secrets/scan/ignore` | `coffer secret ignore` | `test_cli_parity.py` |
| Secrets · Move into the store | `POST /secrets/import` | `coffer secret import` | `test_cli_parity.py` |
| Settings · Security · Import a master key (desktop app, Touch ID) | `POST /desktop/requests` | `coffer secret import-key` | `test_cli_parity.py` |
| Secrets · list | `GET /secrets` | `coffer secret list` | `test_secret_cmd.py` |
| Secrets · Allow local programs (coffer run) | `POST /secrets/local-access/request` | `coffer secret local-access request` | `test_cli_parity.py` |
| Secrets · Stop allowing local programs | `POST /secrets/local-access/revoke` | `coffer secret local-access revoke` | `test_cli_parity.py` |
| Secrets · Reveal (desktop app, Touch ID) | `POST /desktop/requests` | `coffer secret reveal` | `test_approval_cli.py` |
| Secrets · Find plaintext secrets | `POST /secrets/scan` | `coffer secret scan` | `test_cli_parity.py` |
| Secrets · Add / Replace value | `POST /secrets` | `coffer secret set` | `test_secret_cmd.py` |
| Secrets · Report again | `POST /secrets/scan/unignore` | `coffer secret unignore` | `test_cli_parity.py` |

## `coffer settings` {#settings}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Settings · Secrets · approvals | `PUT /settings/secret-boundary` | `coffer settings approvals set` | `test_cli_parity.py` |
| Settings · Secrets · approvals | `GET /settings/secret-boundary` | `coffer settings approvals show` | `test_cli_parity.py` |
| Settings · Engine | `GET /internal-engine-config` | `coffer settings engine show` | `test_cli_parity.py` |
| Settings · Engine · transcription | `PUT /internal-engine-config/transcribe-model` | `coffer settings engine transcribe-model` | `test_cli_parity.py` |
| Settings · Engine · upkeep | `PUT /internal-engine-config/upkeep` | `coffer settings engine upkeep` | `test_cli_parity.py` |
| Settings · Experimental · back to default | `DELETE /daemon/features/{key}` | `coffer settings feature reset` | `test_cli_parity.py` |
| Settings · Experimental | `PUT /daemon/features/{key}` | `coffer settings feature set` | `test_cli_parity.py` |
| Settings · Experimental | `GET /daemon/features` | `coffer settings features` | `test_cli_parity.py` |
| Settings · Data · retention | `GET /retention/policies` | `coffer settings retention list` | `test_cli_parity.py` |
| Settings · Data · retention · preview | `GET /retention/policies/{table_name}/preview` | `coffer settings retention preview` | `test_cli_parity.py` |
| Settings · Data · Prune now | `POST /retention/prune` | `coffer settings retention prune` | `test_cli_parity.py` |
| Settings · Data · retention | `PATCH /retention/policies/{table_name}` | `coffer settings retention set` | `test_cli_parity.py` |
| Settings · Secrets · storage | `PUT /settings/secrets` | `coffer settings secrets set` | `test_cli_parity.py` |
| Settings · Secrets · storage | `GET /settings/secrets` | `coffer settings secrets show` | `test_cli_parity.py` |
| Settings · Data · Clear cache | `POST /storage/cache/clear` | `coffer settings storage clear-cache` | `test_cli_parity.py` |
| Settings · Data · storage | `GET /storage` | `coffer settings storage show` | `test_cli_parity.py` |

## `coffer skill` {#skill}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Skills · Ask an agent to fix the format | `POST /skills/conformance/handoff` | `coffer skill conformance-handoff` | `test_cli_parity.py` |
| Skills · a copy that differs · compare | `GET /skills/{uid}/copies/{agent_uid}` | `coffer skill copy compare` | `test_cli_parity.py` |
| Skills · a copy that differs · keep one | `POST /skills/{uid}/copies/{agent_uid}/resolve` | `coffer skill copy resolve` | `test_cli_parity.py` |
| Skills · Delete | `DELETE /skills/{uid}` | `coffer skill delete` | `test_cli_parity.py` |
| Skills · Delete selected | `POST /skills/bulk-delete` | `coffer skill delete-many` | `test_cli_parity.py` |
| Skills · switch off | `POST /resources/{uid}/disable` | `coffer skill disable` | `test_cli_parity.py` |
| Skills · switch on | `POST /resources/{uid}/enable` | `coffer skill enable` | `test_cli_parity.py` |
| Skills · Files tab | `GET /skills/{uid}/files` | `coffer skill files` | `test_cli_parity.py` |
| Skills · list | `GET /skills` | `coffer skill list` | `test_cli_parity.py` |
| Skills · an orphan · Adopt | `POST /skills/orphans/{name}/adopt` | `coffer skill orphan adopt` | `test_cli_parity.py` |
| Skills · an orphan's files | `GET /skills/orphans/{name}/files` | `coffer skill orphan files` | `test_cli_parity.py` |
| Skills · folders no skill owns | `GET /skills/orphans` | `coffer skill orphan list` | `test_cli_parity.py` |
| Skills · an orphan · Remove | `DELETE /skills/orphans/{name}` | `coffer skill orphan remove` | `test_cli_parity.py` |
| Skills · Reach | `PUT /resources/{uid}/scope` | `coffer skill reach` | `test_cli_parity.py` |
| Skills · Repair | `POST /skills/repair` | `coffer skill repair` | `test_cli_parity.py` |
| Skills · open a skill | `GET /skills/{uid}` | `coffer skill show` | `test_cli_parity.py` |
| Skills · Source · Change source · preview | `POST /skills/{uid}/source/change` | `coffer skill source change` | `test_cli_parity.py` |
| Skills · Source · Change source · apply | `POST /skills/{uid}/source/change/apply` | `coffer skill source change-apply` | `test_cli_parity.py` |
| Skills · Source · Check for updates | `POST /skills/{uid}/source/check` | `coffer skill source check` | `test_cli_parity.py` |
| Skills · Source · Ask an agent to merge | `POST /skills/{uid}/source/handoff` | `coffer skill source handoff` | `test_cli_parity.py` |
| Skills · Source · record the merge | `POST /skills/{uid}/source/merged` | `coffer skill source merged` | `test_cli_parity.py` |
| Skills · Import · an archive | `POST /skills/stage/archive` | `coffer skill stage-archive` | `test_cli_parity.py` |
| Skills · Import · Cancel | `DELETE /skills/stage/{staging_id}` | `coffer skill stage-cancel` | `test_cli_parity.py` |
| Skills · Import · Import | `POST /skills/stage/{staging_id}/confirm` | `coffer skill stage-confirm` | `test_cli_parity.py` |
| Skills · Import · a folder | `POST /skills/stage/folder` | `coffer skill stage-folder` | `test_cli_parity.py` |
| Skills · Import · a git repository | `POST /skills/stage/git` | `coffer skill stage-git` | `test_cli_parity.py` |
| Skills · edit a skill | `PATCH /resources/{uid}` | `coffer skill update` | `test_cli_parity.py` |
| Settings · Skills · update check | `PUT /skills/update-check` | `coffer skill update-check set` | `test_cli_parity.py` |
| Settings · Skills · update check | `GET /skills/update-check` | `coffer skill update-check show` | `test_cli_parity.py` |
| Skills · Verify | `POST /skills/verify` | `coffer skill verify` | `test_cli_parity.py` |

## `coffer sync` {#sync}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Sync · Continue | `POST /sync/continue` | `coffer sync continue` | `test_cli_parity.py` |
| Sync · a conflicting file · keep one | `POST /sync/stop/files/answer` | `coffer sync file-answer` | `test_cli_parity.py` |
| Sync · a conflicting file · discard mine | `POST /sync/stop/files/discard` | `coffer sync file-discard` | `test_cli_parity.py` |
| Sync · a conflicting file's versions | `GET /sync/stop/files/versions` | `coffer sync file-versions` | `test_cli_parity.py` |
| Sync · held · Apply | `POST /sync/hold/confirm` | `coffer sync hold-confirm` | `test_cli_parity.py` |
| Sync · a held change · diff | `GET /sync/hold/diff` | `coffer sync hold-diff` | `test_cli_parity.py` |
| Sync · held · Restore | `POST /sync/hold/restore` | `coffer sync hold-restore` | `test_cli_parity.py` |
| Sync · Join | `POST /sync/join` | `coffer sync join` | `test_cli_parity.py` |
| Sync · Join · choices | `GET /sync/join-choices` | `coffer sync join-choices` | `test_cli_parity.py` |
| Sync · Join · choose | `POST /sync/join-choices` | `coffer sync join-choose` | `test_cli_parity.py` |
| Sync · Join · discard this machine's file | `POST /sync/join-choices/discard` | `coffer sync join-discard` | `test_cli_parity.py` |
| Sync · Join · Ask an agent | `POST /sync/join-choices/handoff` | `coffer sync join-handoff` | `test_cli_parity.py` |
| Sync · Join · review | `GET /sync/join/preview` | `coffer sync join-preview` | `test_cli_parity.py` |
| Sync · Key · fingerprint | `GET /sync/key/fingerprint` | `coffer sync key fingerprint` | `test_cli_parity.py` |
| Sync · Key · import | `POST /sync/key/import` | `coffer sync key import` | `test_cli_parity.py` |
| Sync · Key · import (review) | `POST /sync/key/import/preview` | `coffer sync key import-preview` | `test_cli_parity.py` |
| Sync · Machines · rename | `PATCH /sync/machines/self` | `coffer sync machine rename` | `test_cli_parity.py` |
| Sync · Machines · Restore | `POST /sync/machines/{machine_id}/restore` | `coffer sync machine restore` | `test_cli_parity.py` |
| Sync · Machines · Retire | `DELETE /sync/machines/{machine_id}` | `coffer sync machine retire` | `test_cli_parity.py` |
| Sync · Machines | `GET /sync/machines` | `coffer sync machines` | `test_cli_parity.py` |
| Sync · waiting · diff | `GET /sync/pending/diff` | `coffer sync pending-diff` | `test_cli_parity.py` |
| Sync · a plaintext secret · where | `GET /sync/plaintext/context` | `coffer sync plaintext-context` | `test_cli_parity.py` |
| Sync · a plaintext secret · Push anyway | `POST /sync/plaintext/push-anyway` | `coffer sync push-anyway` | `test_cli_parity.py` |
| Sync · Set up · Check | `POST /sync/remote/check` | `coffer sync remote check` | `test_cli_parity.py` |
| Sync · Stop syncing | `DELETE /sync/remote` | `coffer sync remote delete` | `test_cli_parity.py` |
| Sync · Restore from the remote | `POST /sync/remote/restore` | `coffer sync remote restore` | `test_cli_parity.py` |
| Sync · Set up · remote | `PUT /sync/remote` | `coffer sync remote set` | `test_cli_parity.py` |
| Sync · a round · Roll back | `POST /sync/runs/{run_id}/rollback` | `coffer sync rollback` | `test_cli_parity.py` |
| Sync · a round · Roll back (review) | `GET /sync/runs/{run_id}/rollback-plan` | `coffer sync rollback-plan` | `test_cli_parity.py` |
| Sync · Sync now | `POST /sync/run` | `coffer sync run` | `test_cli_parity.py` |
| Sync · a round · a file's diff | `GET /sync/runs/{run_id}/diff` | `coffer sync run-diff` | `test_cli_parity.py` |
| Sync · History | `GET /sync/runs` | `coffer sync runs` | `test_cli_parity.py` |
| Sync · status | `GET /sync/status` | `coffer sync status` | `test_cli_parity.py` |
| Sync · a round that stopped | `GET /sync/stop` | `coffer sync stop` | `test_cli_parity.py` |
| Sync · Ask an agent to resolve | `POST /sync/stop/handoff` | `coffer sync stop-handoff` | `test_cli_parity.py` |
| Sync · Move the vault | `POST /sync/vault/move` | `coffer sync vault-move` | `test_cli_parity.py` |
| Sync · a round in progress | `GET /sync/status` | `coffer sync wait` | `test_cli_parity.py` |

## `coffer usage` {#usage}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| Usage | `GET /usage/summary` | `coffer usage summary` | `test_cli_parity.py` |

## `coffer vault` {#vault}

| 界面操作 | 接口 | 命令 | 验收 |
| --- | --- | --- | --- |
| History tab · a version's changes | `GET /vault/diff` | `coffer vault diff` | `test_cli_parity.py` |
| Knowledge, Skills · History tab | `GET /vault/history` | `coffer vault history` | `test_cli_parity.py` |
| no page: hand edits the vault refused | `GET /vault/problems` | `coffer vault problems` | `test_vault_cmd.py` |
| History tab · Restore this version | `POST /vault/restore` | `coffer vault restore` | `test_cli_parity.py` |

## 没有命令的操作 {#without-a-command}

普通文件用你自己的工具读写；少数操作只在窗口前有意义。

| 接口 | 原因 |
| --- | --- |
| `GET /agents/{uid}/config-files/{key}/content` | 普通文件: an agent's config file is its own plain file |
| `GET /agents/{uid}/native-memory/files/content` | 普通文件: an agent's native memory is its own plain file |
| `GET /agents/{uid}/unmanaged-skills/{skill}/files/content` | 普通文件: a skill's files are plain files |
| `GET /channels/{uid}/people/{sender_id}/avatar` | 窗口操作: a paired person's picture in the owner list |
| `GET /fs/browse` | 窗口操作: the folder picker's own listing |
| `GET /fs/editors` | 窗口操作: which editors the Open in… menu offers |
| `POST /fs/open` | 窗口操作: opens a file in the person's editor |
| `POST /fs/pick-folder` | 窗口操作: a native folder picker for the person |
| `POST /fs/reveal` | 窗口操作: reveals a file in Finder |
| `POST /fs/terminal` | 窗口操作: opens a terminal window for the person |
| `GET /fs/terminals` | 窗口操作: which terminals the Open in… menu offers |
| `DELETE /knowledge/file` | 普通文件: a knowledge document is a plain file |
| `GET /knowledge/file` | 普通文件: a knowledge document is a plain file |
| `DELETE /memory/partitions/{uid}/notes/{slug}` | 普通文件: a memory note is a plain Markdown file |
| `GET /memory/partitions/{uid}/notes/{slug}` | 普通文件: a memory note is a plain Markdown file |
| `GET /skills/orphans/{name}/files/content` | 普通文件: a skill's files are plain files |
| `GET /skills/{uid}/files/content` | 普通文件: a skill's files are plain files |
| `POST /sync/join-choices/editor` | 窗口操作: opens a conflicting file in the editor |
| `POST /sync/stop/files/editor` | 窗口操作: opens a conflicting file in the editor |

## 桌面应用 {#desktop-app}

| 桌面命令 | 命令 |
| --- | --- |
| `approve_pending` | `coffer approval approve` |
| `approve_pending_batch` | `coffer approval approve` |
| `check_for_updates` | `coffer app update check` |
| `daemon_version_matches` | 页面内部: the page's handshake with the shell |
| `export_master_key_backup` | `coffer secret backup-key` |
| `get_daemon_info` | 页面内部: the page's handshake with the shell |
| `import_master_key` | `coffer secret import-key` |
| `install_update` | `coffer app update install` |
| `restart_daemon` | `coffer daemon restart` |
| `reveal_secret` | `coffer secret reveal` |
| `set_attention_count` | 页面内部: the menu bar's count, set by the page |
| `set_ui_language` | 窗口操作: the window's interface language |
| `set_update_auto_check` | `coffer app update auto-check` |
| `show_daemon_log` | `coffer log daemon` |
| `update_status` | `coffer app update status` |
