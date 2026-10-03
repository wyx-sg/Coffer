---
title: coffer scan
description: "List what agents hold that Coffer does not manage: agents, skills, MCP entries."
pageClass: cli-ref
---

# coffer scan

List what agents hold that Coffer does not manage: agents, skills, MCP entries.

```sh
coffer scan [OPTIONS]
```

本页与 `coffer scan --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

With --ref, show that one row in full: an MCP entry's whole configuration (secret values withheld) or an unmanaged skill's metadata.

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--agent` <span class="cli-chip">选项</span> | text |  | Only what this agent holds |
| `--ref` <span class="cli-chip">选项</span> | text |  | Show one row in full: a type, a folder path or &lt;agent&gt;:&lt;entry&gt; |
| `--source` <span class="cli-chip">选项</span> | text |  | With --ref on an mcp row: the config-file key |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |
