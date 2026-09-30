---
title: coffer run
description: "Run a command with secrets set only in its environment."
---

# coffer run

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer run [OPTIONS]
```

Run a command with secrets set only in its environment.

Each resolution is audited. Output is masked: exact secret values print as \*\*\*. This guards against accidents — a value landing in a transcript, a file or git — and does not hide a secret from an agent that runs the command: the agent is the command's parent and can read its environment.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--secret` | 选项 | text（可重复） |  | NAME or ENV=NAME of a standalone secret (repeatable) |
| `--env-file` | 选项 | path |  | KEY=VALUE file; coffer://secret/&lt;name&gt; values are resolved |
| `--no-masking` | 选项 | 开关 |  | Pass the child's output through unfiltered |
