---
title: CLI 参考
description: 每一个 coffer 命令、参数和选项，由 CLI 自身生成。
---

# CLI 参考 {#cli-reference}

本页列出每个 `coffer` 命令都接受的选项，以及每个顶层命令组。每个命令组有自己的页面，
列出组内的每个命令、参数和选项。这些页面由 CLI 自己的命令树生成，所以和 `main` 上的
版本执行 `coffer <command> --help` 打印的内容一致。命令说明直接取自 CLI，因此保持英文。

::: info 生成的页面
不要手工编辑这些页面。用 `make docs-reference` 重新生成（它会运行
`docs-site/scripts/gen_cli_reference.py`）；页面和 CLI 不一致时 `make lint` 会失败。
:::

大多数命令通过管理 API 与本机的守护进程通信，守护进程没在运行时会先把它启动。所有命令
共用的退出码见[错误码](/zh/reference/error-codes#cli-exit-codes)。

## 全局选项 {#global-options}

```sh
coffer [OPTIONS] COMMAND [ARGS]...
```

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--verbose, -v` <span class="cli-chip">选项</span> | 开关 |  | On an error, also show the request behind it (method, path, status) and, for an unexpected one, the traceback. |
| `--version` <span class="cli-chip">选项</span> | 开关 |  | Print Coffer's version and exit. |
| `--install-completion` <span class="cli-chip">选项</span> | 开关 |  | Install completion for the current shell. |
| `--show-completion` <span class="cli-chip">选项</span> | 开关 |  | Show completion for the current shell, to copy it or customize the installation. |

## 命令组 {#command-groups}

| 命令组 | 说明 |
| --- | --- |
| [`coffer run`](/zh/reference/cli/run) | Run a command with secrets set only in its environment. |
| [`coffer update`](/zh/reference/cli/update) | Upgrade Coffer to the newest release and restart the daemon on it. |
| [`coffer uninstall`](/zh/reference/cli/uninstall) | Remove Coffer from this Mac: disconnect the agents, remove the skill links, start at login, the binaries and the installer's PATH lines, then stop the daemon. |
| [`coffer daemon`](/zh/reference/cli/daemon) | The Coffer daemon: start, stop, status, and its settings. |
| [`coffer config`](/zh/reference/cli/config) | Daemon settings read before it binds (work while it is down). |
| [`coffer log`](/zh/reference/cli/log) | Read Coffer's audit, MCP and daemon logs. |
| [`coffer path`](/zh/reference/cli/path) | Where Coffer keeps files you read directly. |
| [`coffer mcp`](/zh/reference/cli/mcp) | MCP servers: register, change, test, their tools and logs. |
| [`coffer secret`](/zh/reference/cli/secret) | Secrets: list, store, delete, reveal in the app, import, approvals. |
| [`coffer cli`](/zh/reference/cli/cli) | Command-line tools Coffer manages for skills. |
| [`coffer memory`](/zh/reference/cli/memory) | Memory partitions (notes are plain files you edit directly). |
| [`coffer proxy`](/zh/reference/cli/proxy) | The local model proxy. |
| [`coffer vault`](/zh/reference/cli/vault) | The vault's history and the hand edits it refused. |
| [`coffer custom-tool`](/zh/reference/cli/custom-tool) | Custom tools: groups of HTTP API requests served as MCP tools. |
| [`coffer approval`](/zh/reference/cli/approval) | Secret approvals: list, show, approve with Touch ID, reject, ask again. |
| [`coffer app`](/zh/reference/cli/app) | The Coffer desktop app. |
| [`coffer resource`](/zh/reference/cli/resource) | Any resource by uid: show, rename, switch on or off, reach, delete. |
| [`coffer channel`](/zh/reference/cli/channel) | Messaging channels: status, pairing, people, notify, restart. |
| [`coffer knowledge`](/zh/reference/cli/knowledge) | Knowledge collections (documents are plain files you edit directly). |
| [`coffer skill`](/zh/reference/cli/skill) | Skills: import, update, delivery to agents, sources. |
| [`coffer agent`](/zh/reference/cli/agent) | Manage coding agents: add, connect, their MCP entries, plugins and sessions. |
| [`coffer provider`](/zh/reference/cli/provider) | Model providers: connections, prices, switching agents' models. |
| [`coffer model`](/zh/reference/cli/model) | Ask a model endpoint which models it serves, or test it. |
| [`coffer conversation`](/zh/reference/cli/conversation) | Conversations: rename, stop a turn, delete (list: agent session all). |
| [`coffer settings`](/zh/reference/cli/settings) | Settings: approvals, secret storage, features, data, upkeep. |
| [`coffer attention`](/zh/reference/cli/attention) | What needs you (the Overview list): list, ignore, un-ignore. |
| [`coffer usage`](/zh/reference/cli/usage) | Model usage and cost. |
| [`coffer sync`](/zh/reference/cli/sync) | Vault sync: remote, rounds, machines, conflicts. |
