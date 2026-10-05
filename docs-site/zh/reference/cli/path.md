---
title: coffer path
description: "Where Coffer keeps files you read directly."
pageClass: cli-ref
---

# coffer path

Where Coffer keeps files you read directly.

```sh
coffer path [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer path --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`path logs`](#path-logs) | The log directory and the daemon.log in it (COFFER_LOG_DIR moves both). |
| [`path skill-data`](#path-skill-data) | The directory skill scripts write logs, journals and temp files under. |

## path logs

The log directory and the daemon.log in it (COFFER_LOG_DIR moves both).

<p class="cli-label">概要</p>

```sh
coffer path logs [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON object keyed by name |

## path skill-data

The directory skill scripts write logs, journals and temp files under.

<p class="cli-label">概要</p>

```sh
coffer path skill-data [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON object keyed by name |
