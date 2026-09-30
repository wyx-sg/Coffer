---
title: coffer memory
description: "Browse and manage Coffer's memory layer"
---

# coffer memory

Part of the [CLI reference](/reference/cli), generated from the CLI's own command tree; regenerate it with `make docs-reference`, never by hand.

```sh
coffer memory [OPTIONS] COMMAND [ARGS]...
```

Browse and manage Coffer's memory layer

## memory list

```sh
coffer memory list [OPTIONS]
```

List every partition, with its note count and repository.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output for scripts |

## memory show

```sh
coffer memory show [OPTIONS] NAME
```

Show one partition, by name or uid.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--json` | option | flag |  | JSON output for scripts |

## memory edit

```sh
coffer memory edit [OPTIONS] NAME
```

Change a partition's title, description or settings.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--name` | option | text |  | New name |
| `--title` | option | text |  | Display title (≤80 chars); empty clears it |
| `--description` | option | text |  |  |
| `--wait` | option | flag |  | Wait for approval in the Coffer app instead of exiting |

## memory rm

```sh
coffer memory rm [OPTIONS] NAME
```

Remove a partition.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `NAME` | argument | text | required | Name or uid |
| `--force, --yes, -f, -y` | option | flag |  | Do not ask |

## memory sync

```sh
coffer memory sync [OPTIONS]
```

Update memory: read every registered agent's native memory, then distil.

Every partition left holding undistilled entries is distilled in the same call; one whose distil pass is already running is reported as skipped.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  |  |

## memory hook

```sh
coffer memory hook [OPTIONS]
```

Answer one fire of Coffer's memory hook; reads the agent's hook JSON on stdin.

Every installed memory hook entry runs this; you rarely need to. It prints nothing, and exits 0, when the daemon is not running.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--agent-uid` | option | text | required | The uid of the agent whose hook is firing |
| `--cwd` | option | text | `""` | Fallback working directory |

## memory delivered

```sh
coffer memory delivered [OPTIONS] [PARTITION]
```

What memory delivered in the last seven days, per agent — or, for one partition, the exact session-start text each agent is given.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `PARTITION` | argument | text |  | A partition: print what each agent is given at session start |
| `--agent` | option | text | `""` | Only this agent's text |
| `--json` | option | flag |  | JSON output |

## memory trigger

```sh
coffer memory trigger [OPTIONS] COMMAND [ARGS]...
```

List, write, arm, disarm and delete memory triggers

Subcommands: `list`, `add`, `arm`, `disarm`, `delete`.

## memory trigger list

```sh
coffer memory trigger list [OPTIONS]
```

List every trigger, armed or proposed.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--json` | option | flag |  | JSON output |

## memory trigger add

```sh
coffer memory trigger add [OPTIONS]
```

Write a trigger; it is armed by you as it is written.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `--note` | option | text | required | &lt;partition&gt;/&lt;slug&gt; of the note |
| `--kind` | option | text | `block` | block or context |
| `--command` | option | text | `""` | Regex over the executing command |
| `--unless` | option | text | `""` | Regex that keeps the trigger quiet |
| `--error` | option | text | `""` | Regex over the command's output |
| `--body` | option | text | `""` | Reason to show when the note is gone |
| `--json` | option | flag |  | JSON output |

## memory trigger arm

```sh
coffer memory trigger arm [OPTIONS] TRIGGER_ID
```

Arm a trigger — a proposal takes effect only once a person arms it.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `TRIGGER_ID` | argument | text | required |  |

## memory trigger disarm

```sh
coffer memory trigger disarm [OPTIONS] TRIGGER_ID
```

Disarm a trigger; it stays, as a proposal.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `TRIGGER_ID` | argument | text | required |  |

## memory trigger delete

```sh
coffer memory trigger delete [OPTIONS] TRIGGER_ID
```

Delete a trigger's file.

| Name | Kind | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `TRIGGER_ID` | argument | text | required |  |
