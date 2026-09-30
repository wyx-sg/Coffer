---
title: coffer discard
description: "Remove one scanned item from the agent that holds it"
---

# coffer discard

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer discard [OPTIONS] COMMAND [ARGS]...
```

Remove one scanned item from the agent that holds it

## discard skill

```sh
coffer discard skill [OPTIONS] PATH
```

Delete an unmanaged skill folder from the agent's skill location (from disk).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PATH` | 参数 | text | 必填 | The folder path the scan printed |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## discard mcp

```sh
coffer discard mcp [OPTIONS] AGENT:ENTRY
```

Remove an MCP entry from the agent's own config file (a .bak is kept).

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `AGENT:ENTRY` | 参数 | text | 必填 | The ref the scan printed |
| `--source` | 选项 | text |  | Config-file key when the entry is in several files |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |
