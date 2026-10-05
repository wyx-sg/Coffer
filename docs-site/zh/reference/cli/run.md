---
title: coffer run
description: "Run a command with secrets set only in its environment."
pageClass: cli-ref
---

# coffer run

Run a command with secrets set only in its environment.

```sh
coffer run [OPTIONS]
```

本页与 `coffer run --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

Only a secret granted to local programs in the Coffer app resolves; any other is refused and the request waits there. Each resolution is audited. Output is masked: exact secret values print as \*\*\*. Masking guards against accidents — a value landing in a transcript, a file or git — and does not hide a granted secret from an agent that runs the command.

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--secret` <span class="cli-chip">选项</span> | text（可重复） |  | NAME, ENV=NAME or ENV=coffer://secret/&lt;id&gt; of a standalone secret (repeatable) |
| `--env-file` <span class="cli-chip">选项</span> | path |  | KEY=VALUE file; coffer://secret/&lt;name&gt; values are resolved |
| `--no-masking` <span class="cli-chip">选项</span> | 开关 |  | Pass the child's output through unfiltered |
