---
title: coffer scan
description: "List what agents hold that Coffer does not manage: agents, skills, MCP entries."
---

# coffer scan

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer scan [OPTIONS]
```

List what agents hold that Coffer does not manage: agents, skills, MCP entries.

With --ref, show that one row in full: an MCP entry's whole configuration (secret values withheld) or an unmanaged skill's metadata.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--agent` | 选项 | text |  | Only what this agent holds |
| `--ref` | 选项 | text |  | Show one row in full: a type, a folder path or &lt;agent&gt;:&lt;entry&gt; |
| `--source` | 选项 | text |  | With --ref on an mcp row: the config-file key |
| `--json` | 选项 | 开关 |  | JSON output for scripts |
