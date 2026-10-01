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

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--verbose, -v` | 选项 | 开关 |  | Show full tracebacks and HTTP request/response context on error. |
| `--version` | 选项 | 开关 |  | Print Coffer's version and exit. |
| `--install-completion` | 选项 | 开关 |  | Install completion for the current shell. |
| `--show-completion` | 选项 | 开关 |  | Show completion for the current shell, to copy it or customize the installation. |

## 命令组 {#command-groups}

| 命令组 | 说明 |
| --- | --- |
| [`coffer scan`](/zh/reference/cli/scan) | List what agents hold that Coffer does not manage: agents, skills, MCP entries. |
| [`coffer run`](/zh/reference/cli/run) | Run a command with secrets set only in its environment. |
| [`coffer attention`](/zh/reference/cli/attention) | What needs you now, across every kind, with the route that acts on each. |
| [`coffer migrate`](/zh/reference/cli/migrate) | Move this home out of coffer.db into the vault layout (once, daemon stopped). |
| [`coffer daemon`](/zh/reference/cli/daemon) | Daemon lifecycle |
| [`coffer open`](/zh/reference/cli/open) | Open Coffer's web UI in your browser. |
| [`coffer config`](/zh/reference/cli/config) | Read and change Coffer's settings (coffer config list shows every key) |
| [`coffer log`](/zh/reference/cli/log) | Read Coffer's records: the audit log, MCP calls and the daemon log |
| [`coffer path`](/zh/reference/cli/path) | Print where Coffer's files live (knowledge, memory, skills, agents, logs, vault) |
| [`coffer adopt`](/zh/reference/cli/adopt) | Bring one scanned item under Coffer's management |
| [`coffer discard`](/zh/reference/cli/discard) | Remove one scanned item from the agent that holds it |
| [`coffer mcp`](/zh/reference/cli/mcp) | Manage MCP servers and their capabilities |
| [`coffer tool`](/zh/reference/cli/tool) | Manage custom tools: HTTP API requests your agents call as tools |
| [`coffer secret`](/zh/reference/cli/secret) | Manage encrypted secrets. |
| [`coffer agent`](/zh/reference/cli/agent) | Manage registered AI agents |
| [`coffer channel`](/zh/reference/cli/channel) | Manage messaging channels (Telegram, SeaTalk) |
| [`coffer skill`](/zh/reference/cli/skill) | Manage skills (AgentSkills standard) |
| [`coffer cli`](/zh/reference/cli/cli) | Check the command-line tools skills and MCP servers require |
| [`coffer knowledge`](/zh/reference/cli/knowledge) | Manage Coffer's knowledge collections, the Markdown under ~/.coffer/vault/knowledge/&lt;collection&gt;/ (`coffer path knowledge` prints it). |
| [`coffer memory`](/zh/reference/cli/memory) | Browse and manage Coffer's memory layer |
| [`coffer provider`](/zh/reference/cli/provider) | Manage LLM connections and switch agents onto them |
| [`coffer proxy`](/zh/reference/cli/proxy) | Inspect the local model proxy and its per-agent tokens |
| [`coffer usage`](/zh/reference/cli/usage) | Model usage through Coffer's proxy, and subscription quota |
| [`coffer sync`](/zh/reference/cli/sync) | Keep this vault in step with a git remote you own |
| [`coffer vault`](/zh/reference/cli/vault) | The vault's history: versions, diffs, restore, and hand edits that were refused. |
| [`coffer drift`](/zh/reference/cli/drift) | See and repair drift between Coffer and the agents' own files |
