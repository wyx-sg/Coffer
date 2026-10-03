---
title: coffer drift
description: "See and repair drift between Coffer and the agents' own files"
pageClass: cli-ref
---

# coffer drift

See and repair drift between Coffer and the agents' own files

```sh
coffer drift [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer drift --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`drift list`](#drift-list) | List every difference a reconcile pass would find now. |
| [`drift repair`](#drift-repair) | Apply drift items now. |

## drift list

List every difference a reconcile pass would find now. Writes nothing.

<p class="cli-label">概要</p>

```sh
coffer drift list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--target` <span class="cli-chip">选项</span> | text |  | One target only |
| `--kind` <span class="cli-chip">选项</span> | text |  | Only items about this kind |
| `--uid` <span class="cli-chip">选项</span> | text |  | Only items about this resource |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |

## drift repair

Apply drift items now. Each repair is audited with you as the actor.

<p class="cli-label">概要</p>

```sh
coffer drift repair [OPTIONS] [IDS]...
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `IDS` <span class="cli-chip">参数</span> | text（可变个数） |  | Item ids from `coffer drift list` |
| `--all` <span class="cli-chip">选项</span> | 开关 |  | Every item a request would repair |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | JSON output for scripts |
