---
title: coffer adopt
description: "Bring one scanned item under Coffer's management"
---

# coffer adopt

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer adopt [OPTIONS] COMMAND [ARGS]...
```

Bring one scanned item under Coffer's management

## adopt skill

```sh
coffer adopt skill [OPTIONS] PATH
```

Move an unmanaged skill folder into Coffer's master store and link it back.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | The folder path the scan printed |

## adopt mcp

```sh
coffer adopt mcp [OPTIONS] AGENT:ENTRY
```

Register an agent's direct MCP entry as a Coffer MCP server and remove it from the agent.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `AGENT:ENTRY` | 参数 | text | 必填 | The ref the scan printed |
| `--name` | 选项 | text |  | Register the server under this name |
| `--source` | 选项 | text |  | Config-file key when the entry is in several files |
| `--secret` | 选项 | text（可重复） |  | KEY=SECRET_REF for a secret-like env/header key (repeatable) |
