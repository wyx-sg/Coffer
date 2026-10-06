---
title: coffer approval
description: "Secret approvals: list, show, approve with Touch ID, reject, ask again."
pageClass: cli-ref
---

# coffer approval

Secret approvals: list, show, approve with Touch ID, reject, ask again.

```sh
coffer approval [OPTIONS] COMMAND [ARGS]...
```

本页与 `coffer approval --help` 打印的内容一致。在下面任何命令后加 `--help`，即可在终端里查看它的选项。

## 命令 {#commands}

| 命令 | 说明 |
| --- | --- |
| [`approval list`](#approval-list) | Approvals, newest first (pending ones by default). |
| [`approval show`](#approval-show) | One approval: what it sends, to which destination and target, and its state. |
| [`approval approve`](#approval-approve) | Approve with the person's own presence check, in the desktop app. |
| [`approval reject`](#approval-reject) | Refuse approvals. |
| [`approval ask-again`](#approval-ask-again) | Ask again for a refused binding: a new request waits for a person in the desktop app. |

## approval list

Approvals, newest first (pending ones by default).

<p class="cli-label">概要</p>

```sh
coffer approval list [OPTIONS]
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--status` <span class="cli-chip">选项</span> | text | `pending` | pending, approved, rejected, superseded, or all |
| `--destination` <span class="cli-chip">选项</span> | text |  | A destination's uid |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## approval show

One approval: what it sends, to which destination and target, and its state.

<p class="cli-label">概要</p>

```sh
coffer approval show [OPTIONS] APPROVAL_ID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `APPROVAL_ID` <span class="cli-chip">参数</span> | text | 必填 |  |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## approval approve

Approve with the person's own presence check, in the desktop app.

The system prompt names each action, secret, destination and environment; the approvals are applied only after it passes, and only while each still names the target it named when asked. Exit 0 when every one is approved, 11 when the person did not confirm (cancelled, failed or timed out — they stay pending), 12 when the desktop app is not available.

<p class="cli-label">概要</p>

```sh
coffer approval approve [OPTIONS] APPROVAL_IDS...
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `APPROVAL_IDS` <span class="cli-chip">参数</span> | text（可变个数） | 必填 | The approvals to approve — exactly these |
| `--timeout` <span class="cli-chip">选项</span> | float | `120.0` | Seconds to wait for the person |
| `--no-launch` <span class="cli-chip">选项</span> | 开关 |  | Do not start the desktop app |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## approval reject

Refuse approvals. Needs no presence check: refusing only narrows.

<p class="cli-label">概要</p>

```sh
coffer approval reject [OPTIONS] APPROVAL_IDS...
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `APPROVAL_IDS` <span class="cli-chip">参数</span> | text（可变个数） | 必填 | The approvals to refuse |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |

## approval ask-again

Ask again for a refused binding: a new request waits for a person in the desktop app. Needs no presence check: asking grants nothing.

<p class="cli-label">概要</p>

```sh
coffer approval ask-again [OPTIONS] APPROVAL_ID
```

<p class="cli-label">参数与选项</p>

| 名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `APPROVAL_ID` <span class="cli-chip">参数</span> | text | 必填 | The refused approval to ask for again |
| `--json` <span class="cli-chip">选项</span> | 开关 |  | Print the daemon's answer as JSON on stdout (errors as JSON on stderr). |
