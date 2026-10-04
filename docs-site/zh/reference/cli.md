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
| `--verbose, -v` <span class="cli-chip">选项</span> | 开关 |  | Show full tracebacks and HTTP request/response context on error. |
| `--version` <span class="cli-chip">选项</span> | 开关 |  | Print Coffer's version and exit. |
| `--install-completion` <span class="cli-chip">选项</span> | 开关 |  | Install completion for the current shell. |
| `--show-completion` <span class="cli-chip">选项</span> | 开关 |  | Show completion for the current shell, to copy it or customize the installation. |

## 命令组 {#command-groups}

| 命令组 | 说明 |
| --- | --- |
| [`coffer run`](/zh/reference/cli/run) | Run a command with secrets set only in its environment. |
| [`coffer daemon`](/zh/reference/cli/daemon) | Daemon lifecycle |
| [`coffer config`](/zh/reference/cli/config) | Read and change Coffer's settings (the keys read before the daemon starts) |
| [`coffer log`](/zh/reference/cli/log) | Read Coffer's records: the audit log, MCP calls and the daemon log |
| [`coffer path`](/zh/reference/cli/path) | Where Coffer's log files live |
| [`coffer mcp`](/zh/reference/cli/mcp) | Check an MCP server |
| [`coffer secret`](/zh/reference/cli/secret) | Manage encrypted secrets. |
| [`coffer vault`](/zh/reference/cli/vault) | Hand edits the vault refused |
