---
title: coffer memory
description: "Browse and manage Coffer's memory layer"
---

# coffer memory

属于 [CLI 参考](/zh/reference/cli)，由 CLI 自己的命令树生成；用 `make docs-reference` 重新生成，不要手工编辑。

```sh
coffer memory [OPTIONS] COMMAND [ARGS]...
```

Browse and manage Coffer's memory layer

## memory list

```sh
coffer memory list [OPTIONS]
```

List every partition, with its note count and repository.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## memory show

```sh
coffer memory show [OPTIONS] NAME
```

Show one partition, by name or uid.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--json` | 选项 | 开关 |  | JSON output for scripts |

## memory edit

```sh
coffer memory edit [OPTIONS] NAME
```

Change a partition's title, description or settings.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--name` | 选项 | text |  | New name |
| `--title` | 选项 | text |  | Display title (≤80 chars); empty clears it |
| `--description` | 选项 | text |  |  |
| `--wait` | 选项 | 开关 |  | Wait for approval in the Coffer app instead of exiting |

## memory rm

```sh
coffer memory rm [OPTIONS] NAME
```

Remove a partition.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `NAME` | 参数 | text | 必填 | Name or uid |
| `--force, --yes, -f, -y` | 选项 | 开关 |  | Do not ask |

## memory sync

```sh
coffer memory sync [OPTIONS]
```

Update memory: read every registered agent's native memory, then distil.

Every partition left holding undistilled entries is distilled in the same call; one whose distil pass is already running is reported as skipped.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  |  |

## memory hook

```sh
coffer memory hook [OPTIONS]
```

Answer one fire of Coffer's memory hook; reads the agent's hook JSON on stdin.

Every installed memory hook entry runs this; you rarely need to. It prints nothing, and exits 0, when the daemon is not running.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--agent-uid` | 选项 | text | 必填 | The uid of the agent whose hook is firing |
| `--cwd` | 选项 | text | `""` | Fallback working directory |

## memory delivered

```sh
coffer memory delivered [OPTIONS] [PARTITION]
```

What memory delivered in the last seven days, per agent — or, for one partition, the exact session-start text each agent is given.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `PARTITION` | 参数 | text |  | A partition: print what each agent is given at session start |
| `--agent` | 选项 | text | `""` | Only this agent's text |
| `--json` | 选项 | 开关 |  | JSON output |

## memory trigger

```sh
coffer memory trigger [OPTIONS] COMMAND [ARGS]...
```

List, write, arm, disarm and delete memory triggers

子命令：`list`, `add`, `arm`, `disarm`, `delete`。

## memory trigger list

```sh
coffer memory trigger list [OPTIONS]
```

List every trigger, armed or proposed.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--json` | 选项 | 开关 |  | JSON output |

## memory trigger add

```sh
coffer memory trigger add [OPTIONS]
```

Write a trigger; it is armed by you as it is written.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--note` | 选项 | text | 必填 | &lt;partition&gt;/&lt;slug&gt; of the note |
| `--kind` | 选项 | text | `block` | block or context |
| `--command` | 选项 | text | `""` | Regex over the executing command |
| `--unless` | 选项 | text | `""` | Regex that keeps the trigger quiet |
| `--error` | 选项 | text | `""` | Regex over the command's output |
| `--body` | 选项 | text | `""` | Reason to show when the note is gone |
| `--json` | 选项 | 开关 |  | JSON output |

## memory trigger arm

```sh
coffer memory trigger arm [OPTIONS] TRIGGER_ID
```

Arm a trigger — a proposal takes effect only once a person arms it.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TRIGGER_ID` | 参数 | text | 必填 |  |

## memory trigger disarm

```sh
coffer memory trigger disarm [OPTIONS] TRIGGER_ID
```

Disarm a trigger; it stays, as a proposal.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TRIGGER_ID` | 参数 | text | 必填 |  |

## memory trigger delete

```sh
coffer memory trigger delete [OPTIONS] TRIGGER_ID
```

Delete a trigger's file.

| 名称 | 类别 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `TRIGGER_ID` | 参数 | text | 必填 |  |
