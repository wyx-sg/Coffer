---
title: coffer vault
description: "Hand edits the vault refused"
pageClass: cli-ref
---

# coffer vault

Hand edits the vault refused

```sh
coffer vault [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer vault --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`vault problems`](#vault-problems) | List hand edits that were refused: still on disk, not in effect until fixed. |

## vault problems

List hand edits that were refused: still on disk, not in effect until fixed.

<p class="cli-label">概要</p>

```sh
coffer vault problems [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |
