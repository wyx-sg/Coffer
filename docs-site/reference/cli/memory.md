---
title: coffer memory
description: "Browse and manage Coffer's memory layer"
pageClass: cli-ref
---

# coffer memory

Browse and manage Coffer's memory layer

```sh
coffer memory [OPTIONS] COMMAND [ARGS]...
```

This page matches what `coffer memory --help` prints. Add `--help` to any command below to see its options in the terminal.

## Commands

| Command | What it does |
| --- | --- |
| [`memory list`](#memory-list) | List every partition, with its note count and repository. |
| [`memory show`](#memory-show) | Show one partition, by name or uid. |
| [`memory edit`](#memory-edit) | Change a partition's title, description or settings. |
| [`memory rm`](#memory-rm) | Remove a partition. |
| [`memory sync`](#memory-sync) | Update memory: read every registered agent's native memory, then distil. |
| [`memory hook`](#memory-hook) | Answer one fire of Coffer's memory hook; reads the agent's hook JSON on stdin. |
| [`memory delivered`](#memory-delivered) | What memory delivered in the last seven days, per agent — or, for one partition, the exact session-start text each agent is given. |
| [`memory trigger`](#memory-trigger) | List, write, arm, disarm and delete memory triggers |
| [`memory trigger list`](#memory-trigger-list) | List every trigger, armed or proposed. |
| [`memory trigger add`](#memory-trigger-add) | Write a trigger; it is armed by you as it is written. |
| [`memory trigger arm`](#memory-trigger-arm) | Arm a trigger — a proposal takes effect only once a person arms it. |
| [`memory trigger disarm`](#memory-trigger-disarm) | Disarm a trigger; it stays, as a proposal. |
| [`memory trigger delete`](#memory-trigger-delete) | Delete a trigger's file. |

## memory list

List every partition, with its note count and repository.

<p class="cli-label">Synopsis</p>

```sh
coffer memory list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## memory show

Show one partition, by name or uid.

<p class="cli-label">Synopsis</p>

```sh
coffer memory show [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output for scripts |

## memory edit

Change a partition's title, description or settings.

<p class="cli-label">Synopsis</p>

```sh
coffer memory edit [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--name` <span class="cli-chip">option</span> | text |  | New name |
| `--title` <span class="cli-chip">option</span> | text |  | Display title (≤80 chars); empty clears it |
| `--description` <span class="cli-chip">option</span> | text |  |  |
| `--wait` <span class="cli-chip">option</span> | flag |  | Wait for approval in the Coffer app instead of exiting |

## memory rm

Remove a partition.

<p class="cli-label">Synopsis</p>

```sh
coffer memory rm [OPTIONS] NAME
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `NAME` <span class="cli-chip">argument</span> | text | required | Name or uid |
| `--force, --yes, -f, -y` <span class="cli-chip">option</span> | flag |  | Do not ask |

## memory sync

Update memory: read every registered agent's native memory, then distil.

Every partition left holding undistilled entries is distilled in the same call; one whose distil pass is already running is reported as skipped.

<p class="cli-label">Synopsis</p>

```sh
coffer memory sync [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  |  |

## memory hook

Answer one fire of Coffer's memory hook; reads the agent's hook JSON on stdin.

Every installed memory hook entry runs this; you rarely need to. It prints nothing, and exits 0, when the daemon is not running.

<p class="cli-label">Synopsis</p>

```sh
coffer memory hook [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--agent-uid` <span class="cli-chip">option</span> | text | required | The uid of the agent whose hook is firing |
| `--cwd` <span class="cli-chip">option</span> | text | `""` | Fallback working directory |

## memory delivered

What memory delivered in the last seven days, per agent — or, for one partition, the exact session-start text each agent is given.

<p class="cli-label">Synopsis</p>

```sh
coffer memory delivered [OPTIONS] [PARTITION]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `PARTITION` <span class="cli-chip">argument</span> | text |  | A partition: print what each agent is given at session start |
| `--agent` <span class="cli-chip">option</span> | text | `""` | Only this agent's text |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output |

## memory trigger

List, write, arm, disarm and delete memory triggers

<p class="cli-label">Synopsis</p>

```sh
coffer memory trigger [OPTIONS] COMMAND [ARGS]...
```

Subcommands: `list`, `add`, `arm`, `disarm`, `delete`.

## memory trigger list

List every trigger, armed or proposed.

<p class="cli-label">Synopsis</p>

```sh
coffer memory trigger list [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output |

## memory trigger add

Write a trigger; it is armed by you as it is written.

<p class="cli-label">Synopsis</p>

```sh
coffer memory trigger add [OPTIONS]
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `--note` <span class="cli-chip">option</span> | text | required | &lt;partition&gt;/&lt;slug&gt; of the note |
| `--kind` <span class="cli-chip">option</span> | text | `block` | block or context |
| `--command` <span class="cli-chip">option</span> | text | `""` | Regex over the executing command |
| `--unless` <span class="cli-chip">option</span> | text | `""` | Regex that keeps the trigger quiet |
| `--error` <span class="cli-chip">option</span> | text | `""` | Regex over the command's output |
| `--body` <span class="cli-chip">option</span> | text | `""` | Reason to show when the note is gone |
| `--json` <span class="cli-chip">option</span> | flag |  | JSON output |

## memory trigger arm

Arm a trigger — a proposal takes effect only once a person arms it.

<p class="cli-label">Synopsis</p>

```sh
coffer memory trigger arm [OPTIONS] TRIGGER_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `TRIGGER_ID` <span class="cli-chip">argument</span> | text | required |  |

## memory trigger disarm

Disarm a trigger; it stays, as a proposal.

<p class="cli-label">Synopsis</p>

```sh
coffer memory trigger disarm [OPTIONS] TRIGGER_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `TRIGGER_ID` <span class="cli-chip">argument</span> | text | required |  |

## memory trigger delete

Delete a trigger's file.

<p class="cli-label">Synopsis</p>

```sh
coffer memory trigger delete [OPTIONS] TRIGGER_ID
```

<p class="cli-label">Arguments and options</p>

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `TRIGGER_ID` <span class="cli-chip">argument</span> | text | required |  |
